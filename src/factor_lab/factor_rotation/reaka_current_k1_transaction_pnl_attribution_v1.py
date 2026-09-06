# pyright: reportAny=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false, reportGeneralTypeIssues=false
# pyright: reportAttributeAccessIssue=false, reportIndexIssue=false
# pyright: reportArgumentType=false, reportReturnType=false
# pyright: reportCallIssue=false, reportOperatorIssue=false
"""Per-stock, per-trade realised P&L attribution for current REAKA K1."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Final, cast

import numpy as np
import pandas as pd

from factor_lab.factor_rotation.reaka_current_k1_factor_attribution_v1 import (
    INPUT_ROOT,
    POLICY_ID,
    STORE_ROOT,
    SegmentFit,
    _exposure_index,
    _fit_for_prices,
    factor_input_inventory,
    file_digest,
    write_csv,
    write_json,
)
from factor_lab.factor_rotation.reaka_current_k1_factor_attribution_v2 import (
    run_corrected_account_path,
)
from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    CLOCK_SUFFIX,
    IntradayK1InputStore,
    read_json,
)
from factor_lab.factor_rotation.reaka_intraday_portfolio_mapping_v1 import (
    SLIPPAGE_MULTIPLIERS,
    AccountPath,
    buy_cost_bps,
    prepare_account_inputs,
    sell_cost_bps,
)
from factor_lab.governance.canonicalization import canonical_digest

ROOT: Final = Path(__file__).resolve().parents[3]
CONTRACT_PATH: Final = ROOT / "docs/ops/reaka_current_k1_2019_2020_transaction_pnl_attribution@1.1.json"
SCHEMA_ID: Final = "factorlab.reaka_current_K1_trade_attribution@1.0"
YEARS: Final = (2019, 2020)
CLOCKS: Final = ("14:30", "14:45")
TOP_LEVEL_GROUPS: Final = ("index", "size", "industry", "other")
SCIENTIFIC_FILES: Final = (
    "factor_input_inventory.json",
    "factor_return_ledger.csv",
    "stock_trade_segment_attribution.csv",
    "trade_episode_attribution.csv",
    "annual_contribution.csv",
    "result.json",
)


def _load_contract() -> dict[str, object]:
    payload = read_json(CONTRACT_PATH)
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    if stored != canonical_digest(body) or payload.get("formal_execution_allowed") is not True:
        raise ValueError("current_K1_trade_attribution_contract_invalid")
    return payload


def build_episode_lookup(
    daily_dates: pd.DatetimeIndex,
    holdings: pd.DataFrame,
) -> tuple[dict[tuple[pd.Timestamp, str], str], dict[str, dict[str, object]]]:
    """Assign one deterministic id to each contiguous non-zero holding run."""

    date_position = {pd.Timestamp(day): position for position, day in enumerate(daily_dates)}
    lookup: dict[tuple[pd.Timestamp, str], str] = {}
    metadata: dict[str, dict[str, object]] = {}
    local = holdings.copy()
    local["date"] = pd.to_datetime(local["date"])
    for symbol, frame in local.groupby("symbol", sort=True):
        ordered = frame.sort_values("date", kind="mergesort")
        prior_position = -2
        ordinal = 0
        episode_id = ""
        for row in ordered.itertuples(index=False):
            day = pd.Timestamp(row.date)
            position = date_position[day]
            if position != prior_position + 1:
                ordinal += 1
                episode_id = f"{symbol}:{day.strftime('%Y%m%d')}:{ordinal:03d}"
                metadata[episode_id] = {
                    "symbol": str(symbol),
                    "episode_start_date": day,
                    "episode_last_holding_date": day,
                }
            else:
                metadata[episode_id]["episode_last_holding_date"] = day
            lookup[(day, str(symbol))] = episode_id
            prior_position = position
    return lookup, metadata


def stock_factor_piece(
    *,
    symbol: str,
    actual_stock_return: float,
    account_start_weight: float,
    fit: SegmentFit,
    store: IntradayK1InputStore,
    exposure_index: int,
    symbol_positions: Mapping[str, int],
) -> dict[str, float]:
    """Decompose one stock return and its account-weighted contribution."""

    position = symbol_positions.get(symbol)
    stock_index = 0.0
    stock_size = 0.0
    stock_industry = 0.0
    if position is not None and bool(np.asarray(store.exposure_available[exposure_index, position], dtype=bool).any()):
        exposure = np.asarray(store.stock_factor_exposures[exposure_index, position], dtype=np.float64)
        fitted = exposure * fit.coefficient
        stock_index = float(fitted[0])
        stock_size = float(fitted[1])
        stock_industry = float(fitted[2:].sum())
    stock_other = float(actual_stock_return - stock_index - stock_size - stock_industry)
    return {
        "stock_index_return": stock_index,
        "stock_size_return": stock_size,
        "stock_industry_return": stock_industry,
        "stock_other_return": stock_other,
        "index_account_contribution": account_start_weight * stock_index,
        "size_account_contribution": account_start_weight * stock_size,
        "industry_account_contribution": account_start_weight * stock_industry,
        "other_gross_account_contribution": account_start_weight * stock_other,
    }


def _market_year(clock: str, tree: str, year: int) -> pd.DataFrame:
    suffix = CLOCK_SUFFIX[clock]
    path = INPUT_ROOT / tree / f"daily_market_panel_{suffix}.parquet"
    frame = pd.read_parquet(
        path,
        columns=[
            "date",
            "symbol",
            "previous_tradable_close",
            "hfq_price_multiplier",
            "accounting_execution_price",
            "accounting_close_price",
        ],
        filters=[
            ("date", ">=", pd.Timestamp(f"{year}-01-01")),
            ("date", "<=", pd.Timestamp(f"{year}-12-31")),
        ],
    )
    frame["date"] = pd.to_datetime(frame["date"])
    frame["accounting_previous_close"] = pd.to_numeric(
        frame["previous_tradable_close"], errors="coerce"
    ).to_numpy(np.float64) * pd.to_numeric(frame["hfq_price_multiplier"], errors="coerce").to_numpy(np.float64)
    return frame.sort_values(["date", "symbol"], kind="mergesort", ignore_index=True)


def _factor_ledger_rows(
    *,
    day: pd.Timestamp,
    clock: str,
    segment: str,
    exposure_index: int,
    fit: SegmentFit,
    store: IntradayK1InputStore,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for position, factor_id in enumerate(store.factor_ids):
        group = "index" if position == 0 else "size" if position == 1 else "industry"
        rows.append(
            {
                "date": day.strftime("%Y-%m-%d"),
                "decision_clock": clock,
                "segment": segment,
                "exposure_decision_position": exposure_index,
                "factor_id": factor_id,
                "factor_group": group,
                "realized_factor_return": float(fit.coefficient[position]),
                "cross_section_observation_count": fit.observation_count,
                "cross_section_design_rank": fit.rank,
                "cross_section_condition_number": fit.condition_number,
            }
        )
    return rows


def _episode_for_leg(
    *,
    direction: str,
    day: pd.Timestamp,
    previous_day: pd.Timestamp,
    symbol: str,
    lookup: Mapping[tuple[pd.Timestamp, str], str],
) -> str:
    key = (day, symbol) if direction == "buy" else (previous_day, symbol)
    episode = lookup.get(key)
    if episode is None:
        raise ValueError(f"current_K1_trade_episode_missing:{direction}:{day.date()}:{symbol}")
    return episode


def build_trade_attribution(
    *,
    year: int,
    clock: str,
    slip: float,
    path: AccountPath,
    store: IntradayK1InputStore,
    market: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Build factor, stock-segment, episode, and annual ledgers."""

    daily_all = path.daily.sort_values("date", kind="mergesort", ignore_index=True)
    daily_all["date"] = pd.to_datetime(daily_all["date"])
    holdings = path.holdings.copy()
    holdings["date"] = pd.to_datetime(holdings["date"])
    trades = path.trades.copy()
    if not trades.empty:
        trades["date"] = pd.to_datetime(trades["date"])
    daily = daily_all.loc[daily_all["date"].dt.year.eq(year)]
    holding_groups = {
        pd.Timestamp(day): frame.set_index("symbol") for day, frame in holdings.groupby("date", sort=True)
    }
    trade_groups = {pd.Timestamp(day): frame for day, frame in trades.groupby("date", sort=True)}
    market_groups = {pd.Timestamp(day): frame.set_index("symbol") for day, frame in market.groupby("date", sort=True)}
    episode_lookup, episode_metadata = build_episode_lookup(pd.DatetimeIndex(daily_all["date"]), holdings)
    symbol_positions = {str(symbol): position for position, symbol in enumerate(store.symbols.astype(str))}
    piece_rows: list[dict[str, object]] = []
    factor_rows: list[dict[str, object]] = []
    maximum_daily_identity_error = 0.0
    maximum_leg_cost_error = 0.0
    for daily_row in daily.itertuples(index=False):
        day = pd.Timestamp(daily_row.date)
        day_position = int(daily_all.index[daily_all["date"].eq(day)][0])
        if day_position == 0:
            raise ValueError("current_K1_trade_attribution_prior_day_missing")
        previous_day = pd.Timestamp(daily_all.iloc[day_position - 1]["date"])
        previous = holding_groups.get(previous_day, pd.DataFrame()).copy()
        current = holding_groups.get(day, pd.DataFrame()).copy()
        previous_nav = float(daily_all.iloc[day_position - 1]["nav"])
        day_market = market_groups[day]
        is_rebalance = bool(daily_row.is_rebalance)
        pre_index = _exposure_index(store, day, before_current=is_rebalance)
        post_index = _exposure_index(store, day, before_current=False)
        full_fit = _fit_for_prices(
            day_market.reset_index(),
            start_column="accounting_previous_close",
            end_column="accounting_close_price",
            store=store,
            exposure_index=pre_index,
        )
        factor_rows.extend(
            _factor_ledger_rows(
                day=day,
                clock=clock,
                segment="previous_close_to_close",
                exposure_index=pre_index,
                fit=full_fit,
                store=store,
            )
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
            factor_rows.extend(
                _factor_ledger_rows(
                    day=day,
                    clock=clock,
                    segment="previous_close_to_execution",
                    exposure_index=pre_index,
                    fit=pre_fit,
                    store=store,
                )
            )
            factor_rows.extend(
                _factor_ledger_rows(
                    day=day,
                    clock=clock,
                    segment="execution_to_close",
                    exposure_index=post_index,
                    fit=post_fit,
                    store=store,
                )
            )
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

        def append_piece(
            *,
            symbol: str,
            quantity: float,
            start_price: float,
            end_price: float,
            fit: SegmentFit,
            exposure_index: int,
            segment: str,
            episode_id: str,
            attribution_day: pd.Timestamp,
            nav_value: float,
        ) -> None:
            if quantity <= 0.0 or not (
                math.isfinite(start_price)
                and math.isfinite(end_price)
                and start_price > 0.0
                and end_price > 0.0
            ):
                return
            actual = end_price / start_price - 1.0
            start_weight = quantity * start_price / nav_value
            components = stock_factor_piece(
                symbol=symbol,
                actual_stock_return=actual,
                account_start_weight=start_weight,
                fit=fit,
                store=store,
                exposure_index=exposure_index,
                symbol_positions=symbol_positions,
            )
            piece_rows.append(
                {
                    "year": year,
                    "date": attribution_day.strftime("%Y-%m-%d"),
                    "decision_clock": clock,
                    "slippage_multiplier": slip,
                    "symbol": symbol,
                    "trade_episode_id": episode_id,
                    "segment": segment,
                    "execution_direction": "",
                    "execution_leg_weight": 0.0,
                    "shares": quantity,
                    "start_price": start_price,
                    "end_price": end_price,
                    "account_start_weight": start_weight,
                    "actual_stock_return": actual,
                    **components,
                    "transaction_cost_account_contribution": 0.0,
                }
            )

        for symbol in sorted(set(q0) | set(q1)):
            start_price = p0.get(symbol, float("nan"))
            close_price = p1.get(symbol, float("nan"))
            prior_episode = episode_lookup.get((previous_day, symbol))
            current_episode = episode_lookup.get((day, symbol))
            if symbol in reallocated:
                execution_price = (
                    float(day_market.loc[symbol, "accounting_execution_price"])
                    if symbol in day_market.index and pd.notna(day_market.loc[symbol, "accounting_execution_price"])
                    else start_price
                )
                if q0.get(symbol, 0.0) > 0.0 and prior_episode is not None:
                    append_piece(
                        symbol=symbol,
                        quantity=q0[symbol],
                        start_price=start_price,
                        end_price=execution_price,
                        fit=pre_fit,
                        exposure_index=pre_index,
                        segment="previous_close_to_execution",
                        episode_id=prior_episode,
                        attribution_day=day,
                        nav_value=previous_nav,
                    )
                if q1.get(symbol, 0.0) > 0.0 and current_episode is not None:
                    append_piece(
                        symbol=symbol,
                        quantity=q1[symbol],
                        start_price=execution_price,
                        end_price=close_price,
                        fit=post_fit,
                        exposure_index=post_index,
                        segment="execution_to_close",
                        episode_id=current_episode,
                        attribution_day=day,
                        nav_value=previous_nav,
                    )
            elif q0.get(symbol, 0.0) > 0.0 and prior_episode is not None:
                append_piece(
                    symbol=symbol,
                    quantity=q0[symbol],
                    start_price=start_price,
                    end_price=close_price,
                    fit=full_fit,
                    exposure_index=pre_index,
                    segment="previous_close_to_close",
                    episode_id=prior_episode,
                    attribution_day=day,
                    nav_value=previous_nav,
                )
        if not day_trades.empty:
            unique_total = np.unique(day_trades["daily_total_cost"].to_numpy(np.float64))
            if len(unique_total) != 1:
                raise ValueError("current_K1_trade_attribution_daily_cost_not_unique")
            allocated_cost = 0.0
            for leg in day_trades.itertuples(index=False):
                direction = str(leg.direction)
                rate = buy_cost_bps(slip) if direction == "buy" else sell_cost_bps(slip)
                leg_cost = float(leg.execution_nav) * float(leg.weight) * rate / 10_000.0
                allocated_cost += leg_cost
                episode_id = _episode_for_leg(
                    direction=direction,
                    day=day,
                    previous_day=previous_day,
                    symbol=str(leg.symbol),
                    lookup=episode_lookup,
                )
                piece_rows.append(
                    {
                        "year": year,
                        "date": day.strftime("%Y-%m-%d"),
                        "decision_clock": clock,
                        "slippage_multiplier": slip,
                        "symbol": str(leg.symbol),
                        "trade_episode_id": episode_id,
                        "segment": "transaction_cost",
                        "execution_direction": direction,
                        "execution_leg_weight": float(leg.weight),
                        "shares": 0.0,
                        "start_price": 0.0,
                        "end_price": 0.0,
                        "account_start_weight": 0.0,
                        "actual_stock_return": 0.0,
                        "stock_index_return": 0.0,
                        "stock_size_return": 0.0,
                        "stock_industry_return": 0.0,
                        "stock_other_return": 0.0,
                        "index_account_contribution": 0.0,
                        "size_account_contribution": 0.0,
                        "industry_account_contribution": 0.0,
                        "other_gross_account_contribution": 0.0,
                        "transaction_cost_account_contribution": -leg_cost / previous_nav,
                    }
                )
            cost_error = abs(allocated_cost - float(unique_total[0])) / previous_nav
            maximum_leg_cost_error = max(maximum_leg_cost_error, cost_error)
            if cost_error > 1.0e-12:
                raise RuntimeError(f"current_K1_trade_leg_cost_allocation_failed:{day.date()}:{cost_error}")
        local_indices = [position for position, row in enumerate(piece_rows) if row["date"] == day.strftime("%Y-%m-%d")]
        daily_simple = 0.0
        for position in local_indices:
            row = piece_rows[position]
            other_net = float(row["other_gross_account_contribution"]) + float(
                row["transaction_cost_account_contribution"]
            )
            total = (
                float(row["index_account_contribution"])
                + float(row["size_account_contribution"])
                + float(row["industry_account_contribution"])
                + other_net
            )
            row["other_net_account_contribution"] = other_net
            row["total_net_account_contribution"] = total
            daily_simple += total
        daily_return = float(daily_row.daily_return)
        identity_error = abs(daily_simple - daily_return)
        maximum_daily_identity_error = max(maximum_daily_identity_error, identity_error)
        if identity_error > 1.0e-10:
            raise RuntimeError(f"current_K1_trade_daily_identity_failed:{day.date()}:{identity_error}")
        scale = math.log1p(daily_return) / daily_return if abs(daily_return) > 1.0e-15 else 1.0
        for position in local_indices:
            row = piece_rows[position]
            row["account_daily_return"] = daily_return
            for group in TOP_LEVEL_GROUPS:
                source = "other_net_account_contribution" if group == "other" else f"{group}_account_contribution"
                row[f"linked_log_{group}_contribution"] = float(row[source]) * scale
            row["linked_log_total_contribution"] = float(row["total_net_account_contribution"]) * scale
    pieces = pd.DataFrame(piece_rows).sort_values(
        ["date", "symbol", "trade_episode_id", "segment", "execution_direction"],
        kind="mergesort",
        ignore_index=True,
    )
    factors = pd.DataFrame(factor_rows).drop_duplicates(
        ["date", "decision_clock", "segment", "factor_id"], keep="first"
    ).sort_values(["date", "segment", "factor_id"], kind="mergesort", ignore_index=True)
    episode_rows: list[dict[str, object]] = []
    year_last_day = pd.Timestamp(daily["date"].max())
    last_holdings = set(holding_groups.get(year_last_day, pd.DataFrame()).index.astype(str))
    for episode_id, local in pieces.groupby("trade_episode_id", sort=True):
        meta = episode_metadata[str(episode_id)]
        symbol = str(meta["symbol"])
        linked = {group: float(local[f"linked_log_{group}_contribution"].sum()) for group in TOP_LEVEL_GROUPS}
        total = float(sum(linked.values()))
        episode_rows.append(
            {
                "year": year,
                "decision_clock": clock,
                "slippage_multiplier": slip,
                "trade_episode_id": str(episode_id),
                "symbol": symbol,
                "episode_start_date": pd.Timestamp(meta["episode_start_date"]).strftime("%Y-%m-%d"),
                "episode_last_holding_date": pd.Timestamp(meta["episode_last_holding_date"]).strftime("%Y-%m-%d"),
                "first_attribution_date": str(local["date"].min()),
                "last_attribution_date": str(local["date"].max()),
                "open_at_year_end": symbol in last_holdings and str(local["date"].max()) == year_last_day.strftime("%Y-%m-%d"),
                "position_segment_count": int(local["segment"].ne("transaction_cost").sum()),
                "execution_leg_count": int(local["segment"].eq("transaction_cost").sum()),
                "linked_log_index_contribution": linked["index"],
                "linked_log_size_contribution": linked["size"],
                "linked_log_industry_contribution": linked["industry"],
                "linked_log_other_contribution": linked["other"],
                "linked_log_total_contribution": total,
                "transaction_cost_account_contribution": float(local["transaction_cost_account_contribution"].sum()),
            }
        )
    episodes = pd.DataFrame(episode_rows).sort_values(
        ["trade_episode_id"], kind="mergesort", ignore_index=True
    )
    group_values = {
        group: float(pieces[f"linked_log_{group}_contribution"].sum()) for group in TOP_LEVEL_GROUPS
    }
    net = float(sum(group_values.values()))
    absolute_total = max(float(sum(abs(value) for value in group_values.values())), 1.0e-15)
    annual_rows = [
        {
            "year": year,
            "decision_clock": clock,
            "slippage_multiplier": slip,
            "group": group,
            "linked_log_contribution": value,
            "signed_contribution_rate": value / net if abs(net) > 1.0e-15 else np.nan,
            "absolute_contribution_share": abs(value) / absolute_total,
            "annual_net_log_return": net,
        }
        for group, value in group_values.items()
    ]
    annual = pd.DataFrame(annual_rows)
    diagnostics = {
        "daily_count": int(len(daily)),
        "stock_trade_segment_row_count": int(len(pieces)),
        "trade_episode_count": int(len(episodes)),
        "execution_leg_count": int(pieces["segment"].eq("transaction_cost").sum()),
        "maximum_daily_account_identity_error": maximum_daily_identity_error,
        "maximum_execution_leg_cost_allocation_error": maximum_leg_cost_error,
        "annual_net_log_return": net,
        "annual_episode_sum_error": abs(float(episodes["linked_log_total_contribution"].sum()) - net),
        "annual_contribution_rate_sum_error": abs(float(annual["signed_contribution_rate"].sum()) - 1.0),
        "post_2020_rows_read": 0,
    }
    return factors, pieces, episodes, annual, diagnostics


def execute_trade_attribution_year(
    *,
    tree: str,
    year: int,
    output_root: Path,
) -> dict[str, object]:
    if tree not in {"formal", "isolated"} or year not in YEARS:
        raise ValueError("current_K1_trade_attribution_scope_invalid")
    contract = _load_contract()
    output_root.mkdir(parents=True, exist_ok=False)
    factor_parts: list[pd.DataFrame] = []
    piece_parts: list[pd.DataFrame] = []
    episode_parts: list[pd.DataFrame] = []
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
            raise ValueError("current_K1_trade_attribution_inventory_mismatch")
        score_path = INPUT_ROOT / tree / f"bounded_score_panel_{suffix}.parquet"
        market_path = INPUT_ROOT / tree / f"daily_market_panel_{suffix}.parquet"
        scores = pd.read_parquet(score_path)
        scores["decision_date"] = pd.to_datetime(scores["decision_date"])
        scores = scores.loc[scores["decision_date"].dt.year.le(year)]
        market_all = pd.read_parquet(market_path)
        market_all["date"] = pd.to_datetime(market_all["date"])
        market_all = market_all.loc[market_all["date"].dt.year.le(year)]
        prepared = prepare_account_inputs(scores=scores, market=market_all, clock=clock, end_year=year)
        market_year = _market_year(clock, tree, year)
        reference_factor_digest = ""
        for slip in SLIPPAGE_MULTIPLIERS:
            account = run_corrected_account_path(prepared=prepared, slippage_multiplier=slip)
            factors, pieces, episodes, annual, local_diagnostics = build_trade_attribution(
                year=year,
                clock=clock,
                slip=slip,
                path=account,
                store=store,
                market=market_year,
            )
            encoded = factors.to_csv(index=False, lineterminator="\n", float_format="%.17g").encode()
            factor_digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
            if not reference_factor_digest:
                reference_factor_digest = factor_digest
                factor_parts.append(factors)
            elif factor_digest != reference_factor_digest:
                raise RuntimeError("current_K1_trade_factor_ledger_changed_by_slippage")
            piece_parts.append(pieces)
            episode_parts.append(episodes)
            annual_parts.append(annual)
            diagnostics[f"{suffix}_slip_{slip:g}"] = local_diagnostics
        for path in (store_path / "manifest.json", score_path, market_path):
            input_digests[str(path.relative_to(ROOT))] = file_digest(path)
    if inventory_payload is None:
        raise RuntimeError("current_K1_trade_attribution_inventory_missing")
    factors = pd.concat(factor_parts, ignore_index=True).sort_values(
        ["date", "decision_clock", "segment", "factor_id"], kind="mergesort", ignore_index=True
    )
    pieces = pd.concat(piece_parts, ignore_index=True).sort_values(
        ["year", "decision_clock", "slippage_multiplier", "date", "symbol", "segment"],
        kind="mergesort",
        ignore_index=True,
    )
    episodes = pd.concat(episode_parts, ignore_index=True).sort_values(
        ["year", "decision_clock", "slippage_multiplier", "trade_episode_id"],
        kind="mergesort",
        ignore_index=True,
    )
    annual = pd.concat(annual_parts, ignore_index=True).sort_values(
        ["year", "decision_clock", "slippage_multiplier", "group"], kind="mergesort", ignore_index=True
    )
    write_json(output_root / "factor_input_inventory.json", inventory_payload)
    write_csv(output_root / "factor_return_ledger.csv", factors)
    write_csv(output_root / "stock_trade_segment_attribution.csv", pieces)
    write_csv(output_root / "trade_episode_attribution.csv", episodes)
    write_csv(output_root / "annual_contribution.csv", annual)
    result = write_json(
        output_root / "result.json",
        {
            "schema_id": SCHEMA_ID,
            "status": "completed_per_stock_per_trade_realized_return_attribution",
            "year": year,
            "candidate_identity": "d8-h8-K1-r0_fit_prefix_successor_incumbent",
            "account_policy": POLICY_ID,
            "top_level_groups": list(TOP_LEVEL_GROUPS),
            "other_subcomponents": ["stock_specific_residual", "transaction_cost"],
            "trade_definition": "one_contiguous_nonzero_holding_episode_with_all_execution_legs",
            "index_identity": "orthogonal_market_cloudridge_v1",
            "factor_input_inventory_digest": inventory_payload["canonical_digest"],
            "diagnostics": diagnostics,
            "score_or_selection_attribution_run": False,
            "model_or_checkpoint_changed": False,
            "2019_2020_enter_model_training": False,
            "post_2020_rows_read": 0,
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    scientific = {name: file_digest(output_root / name) for name in SCIENTIFIC_FILES}
    return write_json(
        output_root / "execution_receipt.json",
        {
            "schema_id": "factorlab.reaka_current_K1_trade_attribution_execution@1.0",
            "status": "completed",
            "tree": tree,
            "year": year,
            "backend": "cpu_exact_sequential_account_and_small_14D_OLS",
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
    "SCIENTIFIC_FILES",
    "TOP_LEVEL_GROUPS",
    "build_episode_lookup",
    "build_trade_attribution",
    "execute_trade_attribution_year",
    "stock_factor_piece",
]
