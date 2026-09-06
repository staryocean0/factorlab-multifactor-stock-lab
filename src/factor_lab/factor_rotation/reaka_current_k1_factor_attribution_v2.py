# pyright: reportAny=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false, reportGeneralTypeIssues=false
# pyright: reportAttributeAccessIssue=false, reportIndexIssue=false
# pyright: reportArgumentType=false, reportReturnType=false
# pyright: reportCallIssue=false, reportOperatorIssue=false
"""Conservation-corrected current K1 2019/2020 factor attribution."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, cast

import numpy as np
import pandas as pd
import torch

from factor_lab.factor_rotation.reaka_current_k1_factor_attribution_v1 import (
    CHECKPOINT_ROOT,
    CLOCKS,
    GROUPS,
    INPUT_ROOT,
    NORMALIZER_ROOT,
    POLICY_ID,
    RETURN_GROUPS,
    SCIENTIFIC_FILES,
    STORE_ROOT,
    _exposure_index,
    _fit_for_prices,
    _piece_contribution,
    factor_input_inventory,
    file_digest,
    linked_log_contributions,
    score_group_influence,
    write_csv,
    write_json,
)
from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    CLOCK_SUFFIX,
    IntradayK1InputStore,
    read_json,
)
from factor_lab.factor_rotation.reaka_intraday_portfolio_mapping_v1 import (
    INITIAL_NAV,
    SLIPPAGE_MULTIPLIERS,
    AccountPath,
    PreparedAccountInputs,
    apply_non_rebalance_day,
    apply_rebalance_day,
    build_execution_target,
    current_weights_from_book,
    policy_by_id,
    prepare_account_inputs,
)
from factor_lab.governance.canonicalization import canonical_digest

ROOT: Final = Path(__file__).resolve().parents[3]
CONTRACT_PATH: Final = ROOT / "docs/ops/reaka_current_k1_2019_2020_factor_attribution@2.0.json"
SCHEMA_ID: Final = "factorlab.reaka_current_K1_factor_attribution@2.0"
YEARS: Final = (2019, 2020)


def apply_rebalance_day_conserving_forced_value(
    *,
    previous_shares: Mapping[str, float],
    previous_cash: float,
    execution_prices: Mapping[str, float],
    close_prices: Mapping[str, float],
    target_weights: Mapping[str, float],
    forced_symbols: Sequence[str],
    blocked_buy_symbols: Sequence[str],
    previous_mark_prices: Mapping[str, float],
    slippage_multiplier: float,
) -> dict[str, object]:
    """Value an untradable forced holding before allocating free targets."""

    allocation_prices = dict(execution_prices)
    for symbol in forced_symbols:
        if symbol in allocation_prices:
            continue
        mark = previous_mark_prices.get(symbol)
        if mark is None or not math.isfinite(float(mark)) or float(mark) <= 0.0:
            raise ValueError(f"current_K1_forced_holding_mark_missing:{symbol}")
        allocation_prices[symbol] = float(mark)
    result = apply_rebalance_day(
        previous_shares=previous_shares,
        previous_cash=previous_cash,
        open_prices=allocation_prices,
        close_prices=close_prices,
        target_weights=target_weights,
        forced_symbols=forced_symbols,
        blocked_buy_symbols=blocked_buy_symbols,
        previous_mark_prices=previous_mark_prices,
        slippage_multiplier=slippage_multiplier,
    )
    overnight = float(result["overnight_nav"])
    after_cost = float(result["nav_after_cost"])
    cost = float(result["cost"])
    if abs(overnight - cost - after_cost) > max(1.0, overnight) * 1.0e-12:
        raise RuntimeError("current_K1_conserving_rebalance_nav_after_cost_failed")
    return result


def run_corrected_account_path(
    *,
    prepared: PreparedAccountInputs,
    slippage_multiplier: float,
) -> AccountPath:
    policy = policy_by_id(POLICY_ID)
    shares: dict[str, float] = {}
    cash = float(INITIAL_NAV)
    nav = float(INITIAL_NAV)
    previous_marks: dict[str, float] = {}
    last_size_labels: dict[str, str] = {}
    daily_rows: list[dict[str, object]] = []
    holding_rows: list[dict[str, object]] = []
    trade_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    for day in sorted(prepared.market_days):
        market_day = prepared.market_days[day]
        last_size_labels.update(market_day.current_size_labels)
        previous_nav = nav
        if day in prepared.decision_groups:
            ranked = prepared.decision_groups[day]
            execution_prices = market_day.execution_prices
            mark_execution = {
                symbol: execution_prices.get(symbol, previous_marks.get(symbol, float("nan")))
                for symbol in shares
            }
            current_weights, execution_nav = current_weights_from_book(
                shares=shares,
                prices=mark_execution,
                cash=cash,
            )
            target, forced, blocked_buy, events = build_execution_target(
                ranked,
                policy=policy,
                previous_shares=shares,
                current_weights=current_weights,
                tradability=market_day.tradability,
                size_labels=last_size_labels,
            )
            result = apply_rebalance_day_conserving_forced_value(
                previous_shares=shares,
                previous_cash=cash,
                execution_prices=execution_prices,
                close_prices=market_day.close_prices,
                target_weights=target,
                forced_symbols=forced,
                blocked_buy_symbols=blocked_buy,
                previous_mark_prices=previous_marks,
                slippage_multiplier=slippage_multiplier,
            )
            shares = cast(dict[str, float], result["shares"])
            cash = float(result["cash"])
            nav = float(result["close_nav"])
            for event in events:
                event_rows.append({"date": day, **event})
            for direction, legs in (
                ("buy", cast(Mapping[str, float], result["buy_legs"])),
                ("sell", cast(Mapping[str, float], result["sell_legs"])),
            ):
                for symbol, weight in sorted(legs.items()):
                    trade_rows.append(
                        {
                            "date": day,
                            "symbol": symbol,
                            "direction": direction,
                            "weight": float(weight),
                            "daily_total_cost": float(result["cost"]),
                            "execution_nav": float(execution_nav),
                        }
                    )
        else:
            nav = apply_non_rebalance_day(
                shares=shares,
                cash=cash,
                close_prices=market_day.close_prices,
                previous_mark_prices=previous_marks,
            )
        daily_return = nav / previous_nav - 1.0 if previous_nav > 0.0 else 0.0
        daily_rows.append(
            {
                "date": day,
                "nav": nav,
                "daily_return": daily_return,
                "cash": cash,
                "cash_weight": cash / nav if nav > 0.0 else 0.0,
                "holding_count": len(shares),
                "is_rebalance": day in prepared.decision_groups,
            }
        )
        for symbol, quantity in sorted(shares.items()):
            mark = market_day.close_prices.get(symbol, previous_marks.get(symbol))
            if mark is None:
                raise ValueError(f"current_K1_corrected_holding_mark_missing:{day.date()}:{symbol}")
            holding_rows.append(
                {
                    "date": day,
                    "symbol": symbol,
                    "shares": float(quantity),
                    "mark_price": float(mark),
                    "market_value": float(quantity) * float(mark),
                }
            )
        previous_marks.update(market_day.close_prices)
    daily = pd.DataFrame(daily_rows)
    returns = daily["daily_return"].to_numpy(np.float64)
    wealth = np.cumprod(1.0 + returns)
    running = np.maximum.accumulate(wealth)
    volatility = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    metrics = {
        "total_return": float(wealth[-1] - 1.0),
        "annualized_return": float(wealth[-1] ** (252.0 / len(returns)) - 1.0),
        "sharpe": float(returns.mean() / volatility * math.sqrt(252.0)) if volatility > 0.0 else 0.0,
        "maximum_drawdown": float((wealth / running - 1.0).min()),
        "net_log_return": float(np.log1p(returns).sum()),
    }
    return AccountPath(
        daily=daily,
        holdings=pd.DataFrame(holding_rows),
        trades=pd.DataFrame(trade_rows),
        events=pd.DataFrame(event_rows),
        metrics=metrics,
    )


def attribute_corrected_account(
    *,
    year: int,
    clock: str,
    slip: float,
    path: AccountPath,
    store: IntradayK1InputStore,
    market: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    daily_all = path.daily.sort_values("date", kind="mergesort", ignore_index=True)
    holdings_all = path.holdings.copy()
    holdings_all["date"] = pd.to_datetime(holdings_all["date"])
    trades_all = path.trades.copy()
    if not trades_all.empty:
        trades_all["date"] = pd.to_datetime(trades_all["date"])
    daily = daily_all.loc[pd.to_datetime(daily_all["date"]).dt.year.eq(year)].copy()
    holding_groups = {
        pd.Timestamp(day): frame.set_index("symbol")
        for day, frame in holdings_all.groupby("date", sort=True)
    }
    trade_groups = {
        pd.Timestamp(day): frame for day, frame in trades_all.groupby("date", sort=True)
    }
    market_groups = {
        pd.Timestamp(day): frame.set_index("symbol") for day, frame in market.groupby("date", sort=True)
    }
    symbol_positions = {str(symbol): position for position, symbol in enumerate(store.symbols.astype(str))}
    rows: list[dict[str, object]] = []
    max_book_error = 0.0
    max_condition = 0.0
    min_rank = 14
    for row in daily.itertuples(index=False):
        day = pd.Timestamp(row.date)
        day_position = int(daily_all.index[daily_all["date"].eq(day)][0])
        if day_position == 0:
            raise ValueError("current_K1_corrected_account_missing_prior_day")
        previous_day = pd.Timestamp(daily_all.iloc[day_position - 1]["date"])
        previous = holding_groups.get(previous_day, pd.DataFrame()).copy()
        current = holding_groups.get(day, pd.DataFrame()).copy()
        previous_nav = float(daily_all.iloc[day_position - 1]["nav"])
        day_market = market_groups[day]
        is_rebalance = bool(row.is_rebalance)
        pre_index = _exposure_index(store, day, before_current=is_rebalance)
        post_index = _exposure_index(store, day, before_current=False)
        full_fit = _fit_for_prices(
            day_market.reset_index(),
            start_column="accounting_previous_close",
            end_column="accounting_close_price",
            store=store,
            exposure_index=pre_index,
        )
        pre_fit = full_fit
        post_fit = full_fit
        if is_rebalance:
            pre_fit = _fit_for_prices(
                day_market.reset_index(),
                start_column="accounting_previous_close",
                end_column="accounting_execution_price",
                store=store,
                exposure_index=pre_index,
            )
            post_fit = _fit_for_prices(
                day_market.reset_index(),
                start_column="accounting_execution_price",
                end_column="accounting_close_price",
                store=store,
                exposure_index=post_index,
            )
        for fit in (full_fit, pre_fit, post_fit):
            max_condition = max(max_condition, fit.condition_number)
            min_rank = min(min_rank, fit.rank)
        q0 = {str(symbol): float(value) for symbol, value in previous.get("shares", pd.Series(dtype=float)).items()}
        p0 = {str(symbol): float(value) for symbol, value in previous.get("mark_price", pd.Series(dtype=float)).items()}
        q1 = {str(symbol): float(value) for symbol, value in current.get("shares", pd.Series(dtype=float)).items()}
        p1 = {str(symbol): float(value) for symbol, value in current.get("mark_price", pd.Series(dtype=float)).items()}
        day_trades = trade_groups.get(day, pd.DataFrame())
        recorded_trades = set(day_trades.get("symbol", pd.Series(dtype=str)).astype(str))
        reallocated = recorded_trades | {
            symbol
            for symbol in set(q0) | set(q1)
            if not np.isclose(q0.get(symbol, 0.0), q1.get(symbol, 0.0), rtol=1.0e-12, atol=1.0e-8)
        }
        simple = {group: 0.0 for group in RETURN_GROUPS}

        def add_piece(
            symbol: str,
            quantity: float,
            start_price: float,
            end_price: float,
            fit: object,
            exposure_index: int,
            nav_value: float,
            accumulator: dict[str, float],
        ) -> None:
            if quantity == 0.0 or not (math.isfinite(start_price) and math.isfinite(end_price) and start_price > 0.0):
                return
            start_value = quantity * start_price / nav_value
            contribution = _piece_contribution(
                symbol=symbol,
                start_value=start_value,
                actual_return=end_price / start_price - 1.0,
                fit=fit,
                store=store,
                exposure_index=exposure_index,
                symbol_positions=symbol_positions,
            )
            for group, value in contribution.items():
                accumulator[group] += value

        for symbol in sorted(set(q0) | set(q1)):
            start_price = p0.get(symbol, float("nan"))
            close_price = p1.get(symbol, float("nan"))
            if symbol in reallocated:
                execution_price = (
                    float(day_market.loc[symbol, "accounting_execution_price"])
                    if symbol in day_market.index and pd.notna(day_market.loc[symbol, "accounting_execution_price"])
                    else start_price
                )
                add_piece(
                    symbol,
                    q0.get(symbol, 0.0),
                    start_price,
                    execution_price,
                    pre_fit,
                    pre_index,
                    previous_nav,
                    simple,
                )
                add_piece(
                    symbol,
                    q1.get(symbol, 0.0),
                    execution_price,
                    close_price,
                    post_fit,
                    post_index,
                    previous_nav,
                    simple,
                )
            else:
                add_piece(
                    symbol,
                    q0.get(symbol, 0.0),
                    start_price,
                    close_price,
                    full_fit,
                    pre_index,
                    previous_nav,
                    simple,
                )
        cost = 0.0
        if not day_trades.empty:
            values = np.unique(day_trades["daily_total_cost"].to_numpy(np.float64))
            if len(values) != 1:
                raise ValueError("current_K1_corrected_daily_cost_not_unique")
            cost = float(values[0]) / previous_nav
        simple["transaction_cost"] = -cost
        daily_return = float(row.daily_return)
        book_error = float(sum(simple.values()) - daily_return)
        max_book_error = max(max_book_error, abs(book_error))
        if abs(book_error) > 1.0e-10:
            raise RuntimeError(f"current_K1_corrected_book_identity_failed:{day.date()}:{book_error}")
        linked = linked_log_contributions(simple, daily_return)
        for group in RETURN_GROUPS:
            rows.append(
                {
                    "year": year,
                    "date": day.strftime("%Y-%m-%d"),
                    "decision_clock": clock,
                    "slippage_multiplier": slip,
                    "group": group,
                    "simple_contribution": simple[group],
                    "linked_log_contribution": linked[group],
                    "daily_return": daily_return,
                    "is_rebalance": is_rebalance,
                }
            )
    detail = pd.DataFrame(rows).sort_values(
        ["date", "decision_clock", "slippage_multiplier", "group"],
        kind="mergesort",
        ignore_index=True,
    )
    summary = (
        detail.groupby(["year", "decision_clock", "slippage_multiplier", "group"], sort=True)
        .agg(
            simple_contribution_sum=("simple_contribution", "sum"),
            linked_log_contribution=("linked_log_contribution", "sum"),
        )
        .reset_index()
    )
    year_returns = daily["daily_return"].to_numpy(np.float64)
    diagnostics = {
        "daily_count": int(len(daily)),
        "maximum_book_identity_error_before_any_residual_adjustment": max_book_error,
        "maximum_cross_section_condition_number": max_condition,
        "minimum_cross_section_design_rank": min_rank,
        "net_log_return_recomputed": float(np.log1p(year_returns).sum()),
        "net_log_contribution_sum": float(summary["linked_log_contribution"].sum()),
        "forced_carry_accounting": "valued_before_free_target_allocation",
    }
    return detail, summary, diagnostics


def _market_year(clock: str, tree: str, year: int) -> pd.DataFrame:
    suffix = CLOCK_SUFFIX[clock]
    path = INPUT_ROOT / tree / f"daily_market_panel_{suffix}.parquet"
    start = pd.Timestamp(f"{year}-01-01")
    end = pd.Timestamp(f"{year}-12-31")
    columns = [
        "date",
        "symbol",
        "previous_tradable_close",
        "hfq_price_multiplier",
        "accounting_execution_price",
        "accounting_close_price",
    ]
    frame = pd.read_parquet(path, columns=columns, filters=[("date", ">=", start), ("date", "<=", end)])
    frame["date"] = pd.to_datetime(frame["date"])
    frame["accounting_previous_close"] = pd.to_numeric(
        frame["previous_tradable_close"], errors="coerce"
    ).to_numpy(np.float64) * pd.to_numeric(frame["hfq_price_multiplier"], errors="coerce").to_numpy(np.float64)
    return frame.sort_values(["date", "symbol"], kind="mergesort", ignore_index=True)


def _load_contract() -> dict[str, object]:
    payload = read_json(CONTRACT_PATH)
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    if stored != canonical_digest(body) or payload.get("formal_execution_allowed") is not True:
        raise ValueError("current_K1_factor_attribution_v2_contract_invalid")
    return payload


def execute_year_v2(
    *,
    tree: str,
    year: int,
    output_root: Path,
) -> dict[str, object]:
    if tree not in {"formal", "isolated"} or year not in YEARS:
        raise ValueError("current_K1_factor_attribution_v2_scope_invalid")
    contract = _load_contract()
    output_root.mkdir(parents=True, exist_ok=False)
    score_parts: list[pd.DataFrame] = []
    daily_parts: list[pd.DataFrame] = []
    annual_parts: list[pd.DataFrame] = []
    diagnostics: dict[str, object] = {}
    inventory_payload: dict[str, object] | None = None
    input_digests: dict[str, str] = {}
    for clock in CLOCKS:
        suffix = CLOCK_SUFFIX[clock]
        store_path = STORE_ROOT / tree / suffix
        store = IntradayK1InputStore.load(store_path)
        inventory = factor_input_inventory(store.factor_ids)
        if inventory_payload is None:
            inventory_payload = inventory
        elif inventory_payload["canonical_digest"] != inventory["canonical_digest"]:
            raise ValueError("current_K1_factor_attribution_v2_inventory_mismatch")
        normalizer_path = NORMALIZER_ROOT / suffix / "normalizer.json"
        normalizer = read_json(normalizer_path)
        score_path = INPUT_ROOT / tree / f"bounded_score_panel_{suffix}.parquet"
        score_panel_year = pd.read_parquet(
            score_path,
            filters=[
                ("decision_date", ">=", pd.Timestamp(f"{year}-01-01")),
                ("decision_date", "<=", pd.Timestamp(f"{year}-12-31")),
            ],
        )
        influence, score_diagnostics = score_group_influence(
            store=store,
            normalizer=normalizer,
            checkpoint_root=CHECKPOINT_ROOT / tree / suffix / "checkpoints",
            year=year,
            device=torch.device("cpu"),
            score_panel=score_panel_year,
        )
        influence["decision_clock"] = clock
        score_parts.append(influence)
        score_all = pd.read_parquet(score_path)
        score_all["decision_date"] = pd.to_datetime(score_all["decision_date"])
        score_all = score_all.loc[score_all["decision_date"].dt.year.le(year)]
        market_path = INPUT_ROOT / tree / f"daily_market_panel_{suffix}.parquet"
        market_all = pd.read_parquet(market_path)
        market_all["date"] = pd.to_datetime(market_all["date"])
        market_all = market_all.loc[market_all["date"].dt.year.le(year)]
        prepared = prepare_account_inputs(
            scores=score_all,
            market=market_all,
            clock=clock,
            end_year=year,
        )
        market_year = _market_year(clock, tree, year)
        for slip in SLIPPAGE_MULTIPLIERS:
            account = run_corrected_account_path(prepared=prepared, slippage_multiplier=slip)
            detail, annual, account_diagnostics = attribute_corrected_account(
                year=year,
                clock=clock,
                slip=slip,
                path=account,
                store=store,
                market=market_year,
            )
            daily_parts.append(detail)
            annual_parts.append(annual)
            diagnostics[f"{suffix}_slip_{slip:g}"] = {
                **account_diagnostics,
                "corrected_full_prefix_account_metrics": account.metrics,
            }
        diagnostics[f"{suffix}_score"] = score_diagnostics
        for path in (store_path / "manifest.json", normalizer_path, score_path, market_path):
            input_digests[str(path.relative_to(ROOT))] = file_digest(path)
        for seed in (11, 29, 47):
            path = CHECKPOINT_ROOT / tree / suffix / "checkpoints" / f"seed_{seed}" / "manifest.json"
            input_digests[str(path.relative_to(ROOT))] = file_digest(path)
    if inventory_payload is None:
        raise RuntimeError("current_K1_factor_attribution_v2_inventory_missing")
    score = pd.concat(score_parts, ignore_index=True).sort_values(
        ["year", "decision_clock", "group"], kind="mergesort", ignore_index=True
    )
    daily = pd.concat(daily_parts, ignore_index=True).sort_values(
        ["date", "decision_clock", "slippage_multiplier", "group"], kind="mergesort", ignore_index=True
    )
    annual = pd.concat(annual_parts, ignore_index=True).sort_values(
        ["year", "decision_clock", "slippage_multiplier", "group"], kind="mergesort", ignore_index=True
    )
    write_json(output_root / "factor_input_inventory.json", inventory_payload)
    write_csv(output_root / "score_group_influence.csv", score)
    write_csv(output_root / "daily_return_attribution.csv", daily)
    write_csv(output_root / "annual_attribution.csv", annual)
    result = write_json(
        output_root / "result.json",
        {
            "schema_id": SCHEMA_ID,
            "status": "completed_conservation_corrected_detailed_validation_attribution",
            "year": year,
            "candidate_identity": "d8-h8-K1-r0_fit_prefix_successor_incumbent",
            "account_policy": POLICY_ID,
            "return_groups": list(RETURN_GROUPS),
            "score_groups": list(GROUPS),
            "factor_input_inventory_digest": inventory_payload["canonical_digest"],
            "diagnostics": diagnostics,
            "old_P7_account_results_valid": False,
            "old_2021_2026_aggregate_blackbox_result_valid": False,
            "post_2020_rows_read": 0,
            "model_or_checkpoint_changed": False,
            "result_used_for_training": False,
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    scientific = {name: file_digest(output_root / name) for name in SCIENTIFIC_FILES}
    return write_json(
        output_root / "execution_receipt.json",
        {
            "schema_id": "factorlab.reaka_current_K1_factor_attribution_execution@2.0",
            "status": "completed",
            "tree": tree,
            "year": year,
            "backend": "cpu_exact",
            "contract_digest": contract["canonical_digest"],
            "result_digest": result["canonical_digest"],
            "scientific_file_digests": scientific,
            "input_digests": dict(sorted(input_digests.items())),
            "source_digests": cast(Mapping[str, object], contract["source_closure"]),
            "post_2020_rows_read": 0,
            "training_run": False,
            "production_authority": False,
        },
    )


__all__ = [
    "apply_rebalance_day_conserving_forced_value",
    "attribute_corrected_account",
    "execute_year_v2",
    "run_corrected_account_path",
]
