# pyright: reportAny=false
# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportOperatorIssue=false
# pyright: reportReturnType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Current REAKA K1 account snapshot and the two project-level ledgers."""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import numpy as np
import pandas as pd
import torch
from numpy.typing import NDArray

from factor_lab.factor_rotation import reaka_current_generation_aggregate_blackbox_gpu_v2 as gpu
from factor_lab.factor_rotation import reaka_current_generation_aggregate_blackbox_v1 as base
from factor_lab.factor_rotation import reaka_current_k1_post2020_annual_four_group_blackbox_v1 as post
from factor_lab.factor_rotation.reaka_current_k1_factor_attribution_v1 import (
    INPUT_ROOT,
    POLICY_ID,
    SegmentFit,
    _exposure_index,
    file_digest,
    fit_factor_segment,
    write_csv,
    write_json,
)
from factor_lab.factor_rotation.reaka_current_k1_factor_attribution_v2 import (
    apply_rebalance_day_conserving_forced_value,
    run_corrected_account_path,
)
from factor_lab.factor_rotation.reaka_current_k1_transaction_pnl_attribution_v1 import (
    build_episode_lookup,
    stock_factor_piece,
)
from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    CLOCK_SUFFIX,
    IntradayK1InputStore,
    read_json,
)
from factor_lab.factor_rotation.reaka_intraday_portfolio_mapping_v1 import (
    COMMON_ROOT_POLICY_ID,
    INITIAL_NAV,
    AccountPath,
    account_metrics,
    apply_non_rebalance_day,
    build_execution_target,
    buy_cost_bps,
    current_weights_from_book,
    policy_by_id,
    prepare_account_inputs,
    rank_portfolio_table,
    sell_cost_bps,
)
from factor_lab.governance.canonicalization import canonical_digest
from factor_lab.portfolio.account_research_bundle import (
    AccountSnapshotIdentity,
    materialize_account_snapshot,
    validate_factor_return_surface,
    validate_realized_pnl_ledger,
    validate_selection_opportunity_ledger,
)

ROOT: Final = Path(__file__).resolve().parents[3]
CONTRACT_PATH: Final = ROOT / "docs/ops/reaka_current_k1_account_ledgers@1.5.json"
CACHE_ROOT: Final = ROOT / "output/factor-rotation/reaka_current_generation_blackbox_gpu_cache_v2_2007_2026"
HISTORICAL_SCORE_ROOT: Final = ROOT / "output/factor-rotation/reaka_intraday_portfolio_mapping_inputs_v2_2011_2020"
HISTORICAL_ANNUAL_ROOT: Final = (
    ROOT / "output/factor-rotation/reaka_current_k1_2011_2020_annual_four_group_attribution_v1_2"
)
POST2020_ANNUAL_ROOT: Final = (
    ROOT / "output/factor-rotation/reaka_current_k1_2021_2026_annual_four_group_blackbox_v1"
)
MODEL_IDENTITY: Final = "d8-h8-K1-r0_fit_prefix_successor_incumbent"
STRATEGY_ID: Final = "REAKA_D5_H20_R5_CURRENT_GENERATION_V1"
CLOCKS: Final = ("14:30", "14:45")
PRIMARY_SLIPPAGE: Final = 1.0
HORIZON_DAYS: Final = 20
TOP_N: Final = 30
COMPONENTS: Final = ("index", "size", "industry", "other")
SOURCE_FILES: Final[tuple[str, ...]] = (
    "docs/ops/reaka_current_k1_account_ledgers@1.0.json",
    "docs/ops/reaka_current_k1_account_ledgers@1.1.json",
    "docs/ops/reaka_current_k1_account_ledgers@1.2.json",
    "docs/ops/reaka_current_k1_account_ledgers@1.3.json",
    "docs/ops/reaka_current_k1_account_ledgers@1.4.json",
    "docs/ops/evidence/reaka_current_k1_account_ledgers_v1_20260902/pre_result_trade_cost_allocation_incident.json",
    "docs/ops/evidence/reaka_current_k1_account_ledgers_v1_20260902/pre_result_v1_1_source_closure_incident.json",
    "docs/ops/evidence/reaka_current_k1_account_ledgers_v1_20260902/pre_result_v1_2_trade_leg_identity_incident.json",
    "docs/ops/evidence/reaka_current_k1_account_ledgers_v1_20260902/pre_acceptance_v1_3_pnl_segmentation_incident.json",
    "docs/ops/evidence/reaka_current_k1_account_ledgers_v1_20260902/pre_acceptance_v1_4_packaging_incident.json",
    "docs/ops/post_training_account_audit@1.1.json",
    "docs/ops/reaka_current_k1_account_ledgers_whitepaper.md",
    "docs/user/reaka_current_k1_account_ledgers_workflow.md",
    "src/factor_lab/portfolio/account_research_bundle.py",
    "src/factor_lab/factor_rotation/reaka_current_k1_account_ledgers_v1.py",
    "src/factor_lab/factor_rotation/reaka_current_k1_factor_attribution_v1.py",
    "src/factor_lab/factor_rotation/reaka_current_k1_factor_attribution_v2.py",
    "src/factor_lab/factor_rotation/reaka_current_k1_transaction_pnl_attribution_v1.py",
    "src/factor_lab/factor_rotation/reaka_current_k1_post2020_annual_four_group_blackbox_v1.py",
    "src/factor_lab/factor_rotation/reaka_current_generation_aggregate_blackbox_gpu_v2.py",
    "src/factor_lab/factor_rotation/reaka_current_generation_aggregate_blackbox_v1.py",
    "scripts/factor_rotation/run_reaka_current_k1_account_ledgers_v1.py",
    "scripts/factor_rotation/finalize_reaka_current_k1_account_ledgers_v1.py",
    "scripts/factor_rotation/validate_reaka_current_k1_account_ledgers_v1.py",
    "tests/unit/test_reaka_current_k1_account_ledgers_v1.py",
)


@dataclass(frozen=True, slots=True)
class PriceSurface:
    dates: pd.DatetimeIndex
    previous_close: NDArray[np.float64]
    execution: NDArray[np.float64]
    close: NDArray[np.float64]
    buy_ok: NDArray[np.bool_]

    def row(self, day: pd.Timestamp) -> int:
        position = int(self.dates.searchsorted(day))
        if position >= len(self.dates) or self.dates[position] != day:
            raise ValueError(f"current_K1_ledger_price_day_missing:{day.date()}")
        return position


@dataclass(frozen=True, slots=True)
class FitJob:
    date: pd.Timestamp
    variant_id: str
    segment_id: str
    segment_kind: str
    segment_start_time: pd.Timestamp
    segment_end_time: pd.Timestamp
    exposure_available_at: pd.Timestamp
    exposure_index: int
    returns: NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class FitBatchResult:
    surface: pd.DataFrame
    fits: dict[str, SegmentFit]
    diagnostics: dict[str, object]


def source_closure() -> dict[str, str]:
    return {relative: file_digest(ROOT / relative) for relative in SOURCE_FILES}


def _load_contract() -> dict[str, object]:
    payload = read_json(CONTRACT_PATH)
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    if stored != canonical_digest(body):
        raise ValueError("current_K1_account_ledgers_contract_digest_invalid")
    if payload.get("formal_execution_allowed") is not True:
        raise ValueError("current_K1_account_ledgers_execution_not_open")
    if payload.get("source_closure") != source_closure():
        raise ValueError("current_K1_account_ledgers_source_closure_drift")
    return payload


def _load_historical_scores(tree: str, clock: str) -> pd.DataFrame:
    suffix = CLOCK_SUFFIX[clock]
    path = HISTORICAL_SCORE_ROOT / tree / f"bounded_score_panel_{suffix}.parquet"
    frame = pd.read_parquet(path)
    frame["decision_date"] = pd.to_datetime(frame["decision_date"], errors="raise").dt.normalize()
    frame["symbol"] = frame["symbol"].astype(str).str.zfill(6)
    frame["decision_clock"] = clock
    return frame.sort_values(["decision_date", "symbol"], kind="mergesort", ignore_index=True)


def _load_historical_market(tree: str, clock: str) -> pd.DataFrame:
    suffix = CLOCK_SUFFIX[clock]
    path = INPUT_ROOT / tree / f"daily_market_panel_{suffix}.parquet"
    frame = pd.read_parquet(path)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    frame["symbol"] = frame["symbol"].astype(str).str.zfill(6)
    frame["accounting_previous_close"] = (
        pd.to_numeric(frame["previous_tradable_close"], errors="coerce").to_numpy(np.float64)
        * pd.to_numeric(frame["hfq_price_multiplier"], errors="raise").to_numpy(np.float64)
    )
    return frame.sort_values(["date", "symbol"], kind="mergesort", ignore_index=True)


def build_historical_price_surface(
    market: pd.DataFrame,
    *,
    store: IntradayK1InputStore,
) -> PriceSurface:
    dates = pd.DatetimeIndex(sorted(pd.to_datetime(market["date"]).unique()))
    symbols = store.symbols.astype(str)
    day_map = pd.Series(np.arange(len(dates), dtype=np.int64), index=dates)
    symbol_map = pd.Series(np.arange(len(symbols), dtype=np.int64), index=symbols)
    day_position = market["date"].map(day_map).to_numpy(np.int64)
    symbol_position = market["symbol"].map(symbol_map)
    valid = symbol_position.notna().to_numpy()
    row = day_position[valid]
    column = symbol_position.loc[valid].to_numpy(np.int64)
    shape = (len(dates), len(symbols))

    def values(name: str) -> NDArray[np.float64]:
        output = np.full(shape, np.nan, dtype=np.float64)
        output[row, column] = pd.to_numeric(market.loc[valid, name], errors="coerce").to_numpy(np.float64)
        return output

    buy = np.zeros(shape, dtype=bool)
    buy[row, column] = market.loc[valid, "buy_ok"].astype(bool).to_numpy()
    return PriceSurface(
        dates=dates,
        previous_close=values("accounting_previous_close"),
        execution=values("accounting_execution_price"),
        close=values("accounting_close_price"),
        buy_ok=buy,
    )


def build_post_price_surface(
    *,
    target: base.ExtendedTargetSurfaces,
    factor_matrix: NDArray[np.float64],
    clock: str,
) -> PriceSurface:
    start = int(np.searchsorted(target.calendar, np.datetime64("2021-01-01", "ns"), side="left"))
    factor_start = int(np.searchsorted(target.calendar, np.datetime64("2020-01-01", "ns"), side="left"))
    suffix = CLOCK_SUFFIX[clock]
    raw_close = np.load(target.root / "raw_close.npy", mmap_mode="r")
    raw_execution = np.load(target.root / f"entry_open_{suffix}.npy", mmap_mode="r")
    factors = np.asarray(factor_matrix[start - factor_start :], dtype=np.float64)
    close = np.asarray(raw_close[start:], dtype=np.float64) * factors
    execution = np.asarray(raw_execution[start:], dtype=np.float64) * factors
    previous = np.vstack(
        [
            np.asarray(raw_close[start - 1], dtype=np.float64)
            * np.asarray(factor_matrix[start - 1 - factor_start], dtype=np.float64),
            close[:-1],
        ]
    )
    return PriceSurface(
        dates=pd.DatetimeIndex(target.calendar[start:]),
        previous_close=previous,
        execution=execution,
        close=close,
        buy_ok=np.isfinite(execution) & (execution > 0.0),
    )


def run_post2020_account_path(
    *,
    score_frame: pd.DataFrame,
    target: base.ExtendedTargetSurfaces,
    factor_matrix: NDArray[np.float64],
    clock: str,
    gates: Mapping[pd.Timestamp, Mapping[str, object]],
    end_date: str | None = None,
) -> AccountPath:
    suffix = CLOCK_SUFFIX[clock]
    raw_execution = np.load(target.root / f"entry_open_{suffix}.npy", mmap_mode="r")
    raw_close = np.load(target.root / "raw_close.npy", mmap_mode="r")
    factor_start = int(np.searchsorted(target.calendar, np.datetime64("2020-01-01", "ns"), side="left"))
    decisions = {
        pd.Timestamp(day).normalize(): rank_portfolio_table(group)
        for day, group in score_frame.groupby("decision_date", sort=True)
    }
    symbol_index = {str(value): position for position, value in enumerate(target.symbols)}
    policy = policy_by_id(COMMON_ROOT_POLICY_ID)
    shares: dict[str, float] = {}
    cash = float(INITIAL_NAV)
    nav = float(INITIAL_NAV)
    previous_marks: dict[str, float] = {}
    daily_rows: list[dict[str, object]] = []
    holding_rows: list[dict[str, object]] = []
    trade_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    start = int(np.searchsorted(target.calendar, np.datetime64("2021-01-01", "ns"), side="left"))
    end_ts = pd.Timestamp(end_date) if end_date else None
    for day_position in range(start, len(target.calendar)):
        day = pd.Timestamp(target.calendar[day_position]).normalize()
        if end_ts is not None and day > end_ts:
            break
        previous_nav = nav
        factor = np.asarray(factor_matrix[day_position - factor_start], dtype=np.float64)
        if day in decisions:
            ranked = decisions[day]
            candidate_symbols = set(ranked["symbol"].astype(str)) | set(shares)
            execution_prices = {
                symbol: float(raw_execution[day_position, symbol_index[symbol]] * factor[symbol_index[symbol]])
                for symbol in candidate_symbols
                if symbol in symbol_index
                and np.isfinite(raw_execution[day_position, symbol_index[symbol]])
                and raw_execution[day_position, symbol_index[symbol]] > 0.0
                and np.isfinite(factor[symbol_index[symbol]])
                and factor[symbol_index[symbol]] > 0.0
            }
            close_prices = {
                symbol: float(raw_close[day_position, symbol_index[symbol]] * factor[symbol_index[symbol]])
                for symbol in candidate_symbols
                if symbol in symbol_index
                and np.isfinite(raw_close[day_position, symbol_index[symbol]])
                and raw_close[day_position, symbol_index[symbol]] > 0.0
                and np.isfinite(factor[symbol_index[symbol]])
                and factor[symbol_index[symbol]] > 0.0
            }
            mark_execution = {
                symbol: execution_prices.get(symbol, previous_marks.get(symbol, float("nan")))
                for symbol in shares
            }
            current_weights, _ = current_weights_from_book(shares=shares, prices=mark_execution, cash=cash)
            target_weights, forced, blocked_buy, events = build_execution_target(
                ranked,
                policy=policy,
                previous_shares=shares,
                current_weights=current_weights,
                tradability=cast(Mapping[str, object], gates.get(day, {})),
                size_labels={},
            )
            result = apply_rebalance_day_conserving_forced_value(
                previous_shares=shares,
                previous_cash=cash,
                execution_prices=execution_prices,
                close_prices=close_prices,
                target_weights=target_weights,
                forced_symbols=forced,
                blocked_buy_symbols=blocked_buy,
                previous_mark_prices=previous_marks,
                slippage_multiplier=PRIMARY_SLIPPAGE,
            )
            shares = cast(dict[str, float], result["shares"])
            cash = float(result["cash"])
            nav = float(result["close_nav"])
            close_marks = cast(Mapping[str, float], result["close_mark_prices"])
            for event in events:
                event_rows.append({"date": day, **event})
            for direction in ("buy", "sell"):
                leg_weights = cast(Mapping[str, float], result[f"{direction}_legs"])
                for symbol, weight in sorted(leg_weights.items()):
                    price = float(execution_prices[symbol])
                    trade_value = float(weight) * float(result["overnight_nav"])
                    trade_rows.append(
                        {
                            "date": day,
                            "symbol": symbol,
                            "direction": direction,
                            "quantity": trade_value / price,
                            "execution_price": price,
                            "weight": float(weight),
                            "execution_nav": float(result["overnight_nav"]),
                            "daily_total_cost": float(result["cost"]),
                        }
                    )
        else:
            close_prices = {
                symbol: float(raw_close[day_position, symbol_index[symbol]] * factor[symbol_index[symbol]])
                for symbol in shares
                if symbol in symbol_index
                and np.isfinite(raw_close[day_position, symbol_index[symbol]])
                and raw_close[day_position, symbol_index[symbol]] > 0.0
                and np.isfinite(factor[symbol_index[symbol]])
                and factor[symbol_index[symbol]] > 0.0
            }
            nav = apply_non_rebalance_day(
                shares=shares,
                cash=cash,
                close_prices=close_prices,
                previous_mark_prices=previous_marks,
            )
            close_marks = {symbol: close_prices.get(symbol, previous_marks[symbol]) for symbol in shares}
        daily_rows.append(
            {
                "date": day,
                "nav": nav,
                "daily_return": nav / previous_nav - 1.0,
                "cash": cash,
                "cash_weight": cash / nav if nav > 0.0 else 0.0,
                "holding_count": len(shares),
                "is_rebalance": day in decisions,
            }
        )
        for symbol, quantity in sorted(shares.items()):
            mark = float(close_marks[symbol])
            holding_rows.append(
                {
                    "date": day,
                    "symbol": symbol,
                    "shares": quantity,
                    "mark_price": mark,
                    "market_value": quantity * mark,
                }
            )
        previous_marks.update({str(symbol): float(value) for symbol, value in close_marks.items()})
    daily = pd.DataFrame(daily_rows)
    return AccountPath(
        daily=daily,
        holdings=pd.DataFrame(holding_rows),
        trades=pd.DataFrame(trade_rows),
        events=pd.DataFrame(event_rows),
        metrics=account_metrics(daily["daily_return"].tolist()),
    )


def _path_trade_costs(path: AccountPath) -> dict[pd.Timestamp, float]:
    if path.trades.empty:
        return {}
    trades = path.trades.copy()
    trades["date"] = pd.to_datetime(trades["date"], errors="raise").dt.normalize()
    result: dict[pd.Timestamp, float] = {}
    for day, local in trades.groupby("date", sort=True):
        values = pd.to_numeric(local["daily_total_cost"], errors="raise").drop_duplicates()
        if len(values) != 1:
            raise ValueError(f"current_K1_ledger_daily_cost_not_unique:{pd.Timestamp(day).date()}")
        result[pd.Timestamp(day)] = float(values.iloc[0])
    return result


def standardize_account_path(
    *,
    path: AccountPath,
    clock: str,
    replay_segment_id: str,
    execution_price: Mapping[tuple[pd.Timestamp, str], float],
    strategy_id: str = STRATEGY_ID,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    account_id = f"{strategy_id}:{clock}:{replay_segment_id}"
    identity = {
        "account_id": account_id,
        "variant_id": clock,
        "policy_id": POLICY_ID,
        "cost_scenario_id": "slippage_1.0x",
    }
    daily = path.daily.copy()
    daily["date"] = pd.to_datetime(daily["date"], errors="raise").dt.normalize()
    for column, value in identity.items():
        daily[column] = value
    daily["replay_segment_id"] = replay_segment_id
    holdings = path.holdings.copy()
    holdings["date"] = pd.to_datetime(holdings["date"], errors="raise").dt.normalize()
    holdings = holdings.rename(columns={"symbol": "asset_id", "shares": "quantity"})
    for column, value in identity.items():
        holdings[column] = value
    holdings["replay_segment_id"] = replay_segment_id
    dates = pd.DatetimeIndex(daily["date"])
    holdings_by_day = {
        pd.Timestamp(day): {
            str(row.asset_id): float(row.quantity)
            for row in local.itertuples(index=False)
        }
        for day, local in holdings.groupby("date", sort=True)
    }
    expected_cost = _path_trade_costs(path)
    path_trades = path.trades.copy()
    if not path_trades.empty:
        path_trades["date"] = pd.to_datetime(path_trades["date"], errors="raise").dt.normalize()
    trade_rows: list[dict[str, object]] = []
    if not path_trades.empty and "weight" in path_trades.columns:
        for row in path_trades.itertuples(index=False):
            day = pd.Timestamp(row.date)
            symbol = str(row.symbol)
            direction = str(row.direction)
            price = execution_price.get((day, symbol))
            if price is None or not np.isfinite(price) or price <= 0.0:
                raise ValueError(f"current_K1_ledger_trade_execution_price_missing:{day.date()}:{symbol}")
            weight = float(row.weight)
            execution_nav = float(row.execution_nav)
            trade_value = weight * execution_nav
            quantity = trade_value / float(price)
            rate = buy_cost_bps(PRIMARY_SLIPPAGE) if direction == "buy" else sell_cost_bps(PRIMARY_SLIPPAGE)
            trade_rows.append(
                {
                    "date": pd.Timestamp(day),
                    **identity,
                    "asset_id": symbol,
                    "direction": direction,
                    "quantity": quantity,
                    "execution_price": float(price),
                    "trade_value": trade_value,
                    "transaction_cost": 0.0,
                    "_cost_allocation_weight": weight * rate,
                    "replay_segment_id": replay_segment_id,
                }
            )
    else:
        previous: dict[str, float] = {}
        for day in dates:
            current = holdings_by_day.get(pd.Timestamp(day), {})
            for symbol in sorted(set(previous) | set(current)):
                delta = float(current.get(symbol, 0.0) - previous.get(symbol, 0.0))
                if abs(delta) <= 1.0e-10:
                    continue
                price = execution_price.get((pd.Timestamp(day), symbol))
                if price is None or not np.isfinite(price) or price <= 0.0:
                    raise ValueError(f"current_K1_ledger_trade_execution_price_missing:{day.date()}:{symbol}")
                direction = "buy" if delta > 0.0 else "sell"
                quantity = abs(delta)
                trade_value = quantity * float(price)
                rate = buy_cost_bps(PRIMARY_SLIPPAGE) if direction == "buy" else sell_cost_bps(PRIMARY_SLIPPAGE)
                trade_rows.append(
                    {
                        "date": pd.Timestamp(day),
                        **identity,
                        "asset_id": symbol,
                        "direction": direction,
                        "quantity": quantity,
                        "execution_price": float(price),
                        "trade_value": trade_value,
                        "transaction_cost": 0.0,
                        "_cost_allocation_weight": trade_value * rate,
                        "replay_segment_id": replay_segment_id,
                    }
                )
            previous = current
    trades = pd.DataFrame(trade_rows)
    if trades.empty:
        trades = pd.DataFrame(
            columns=[
                "date",
                *identity,
                "asset_id",
                "direction",
                "quantity",
                "execution_price",
                "trade_value",
                "transaction_cost",
                "_cost_allocation_weight",
                "replay_segment_id",
            ]
        )
    for day, positions in trades.groupby("date", sort=True).groups.items():
        expected = float(expected_cost.get(pd.Timestamp(day), 0.0))
        weights = pd.to_numeric(trades.loc[positions, "_cost_allocation_weight"], errors="raise")
        denominator = float(weights.sum())
        if expected > 0.0 and denominator <= 0.0:
            raise RuntimeError(f"current_K1_ledger_trade_cost_allocation_weight_missing:{day}")
        if denominator > 0.0:
            trades.loc[positions, "transaction_cost"] = expected * weights / denominator
    trades = trades.drop(columns="_cost_allocation_weight")
    reconstructed_cost = trades.groupby("date", sort=True)["transaction_cost"].sum().to_dict()
    all_days = set(expected_cost) | {pd.Timestamp(day) for day in reconstructed_cost}
    maximum_cost_error = max(
        (
            abs(float(expected_cost.get(day, 0.0)) - float(reconstructed_cost.get(day, 0.0)))
            for day in all_days
        ),
        default=0.0,
    )
    if maximum_cost_error > max(float(daily["nav"].max()), 1.0) * 1.0e-10:
        raise RuntimeError(f"current_K1_ledger_trade_cost_reconstruction_failed:{maximum_cost_error}")
    events = path.events.copy()
    if events.empty:
        events = pd.DataFrame(columns=["date", "symbol", "event_type", "reason"])
    events["date"] = pd.to_datetime(events["date"], errors="raise").dt.normalize()
    events = events.rename(columns={"symbol": "asset_id"})
    for column, value in identity.items():
        events[column] = value
    events["replay_segment_id"] = replay_segment_id
    return daily, holdings, trades, events


def _execution_price_lookup_historical(surface: PriceSurface, symbols: NDArray[np.str_]) -> dict[tuple[pd.Timestamp, str], float]:
    output: dict[tuple[pd.Timestamp, str], float] = {}
    for row, day in enumerate(surface.dates):
        valid = np.flatnonzero(np.isfinite(surface.execution[row]) & (surface.execution[row] > 0.0))
        output.update(
            {
                (pd.Timestamp(day), str(symbols[position])): float(surface.execution[row, position])
                for position in valid
            }
        )
    return output


def _post_execution_price_lookup(
    path: AccountPath,
    *,
    surface: PriceSurface,
    symbols: NDArray[np.str_],
) -> dict[tuple[pd.Timestamp, str], float]:
    symbol_index = {str(value): position for position, value in enumerate(symbols)}
    needed = path.trades.loc[:, ["date", "symbol"]].drop_duplicates() if not path.trades.empty else pd.DataFrame()
    output: dict[tuple[pd.Timestamp, str], float] = {}
    for row in needed.itertuples(index=False):
        day = pd.Timestamp(row.date).normalize()
        position = surface.row(day)
        output[(day, str(row.symbol))] = float(surface.execution[position, symbol_index[str(row.symbol)]])
    return output


def build_fit_jobs(
    *,
    path: AccountPath,
    surface: PriceSurface,
    store: IntradayK1InputStore,
    clock: str,
) -> list[FitJob]:
    jobs: list[FitJob] = []
    clock_minute = 14 * 60 + (30 if clock == "14:30" else 45)
    calendar_index = {pd.Timestamp(value): position for position, value in enumerate(store.calendar)}
    rebalance_days = set(pd.to_datetime(path.daily.loc[path.daily["is_rebalance"], "date"]).dt.normalize())

    def available_at(exposure_index: int) -> pd.Timestamp:
        day_position = int(store.exposure_decision_positions[exposure_index])
        return pd.Timestamp(store.calendar[day_position]) + pd.Timedelta(minutes=clock_minute)

    for row in path.daily.itertuples(index=False):
        day = pd.Timestamp(row.date).normalize()
        surface_row = surface.row(day)
        store_day = calendar_index[day]
        previous_day = pd.Timestamp(store.calendar[store_day - 1])
        is_rebalance = day in rebalance_days
        pre_index = _exposure_index(store, day, before_current=is_rebalance)
        post_index = _exposure_index(store, day, before_current=False)
        full_return = surface.close[surface_row] / surface.previous_close[surface_row] - 1.0
        jobs.append(
            FitJob(
                date=day,
                variant_id=clock,
                segment_id=f"{clock}:{day.strftime('%Y%m%d')}:full",
                segment_kind="previous_close_to_close",
                segment_start_time=previous_day + pd.Timedelta(hours=15),
                segment_end_time=day + pd.Timedelta(hours=15),
                exposure_available_at=available_at(pre_index),
                exposure_index=pre_index,
                returns=full_return,
            )
        )
        if is_rebalance:
            minute = clock_minute + 1
            execution_time = day + pd.Timedelta(minutes=minute)
            jobs.extend(
                [
                    FitJob(
                        date=day,
                        variant_id=clock,
                        segment_id=f"{clock}:{day.strftime('%Y%m%d')}:pre",
                        segment_kind="previous_close_to_execution",
                        segment_start_time=previous_day + pd.Timedelta(hours=15),
                        segment_end_time=execution_time,
                        exposure_available_at=available_at(pre_index),
                        exposure_index=pre_index,
                        returns=surface.execution[surface_row] / surface.previous_close[surface_row] - 1.0,
                    ),
                    FitJob(
                        date=day,
                        variant_id=clock,
                        segment_id=f"{clock}:{day.strftime('%Y%m%d')}:post",
                        segment_kind="execution_to_close",
                        segment_start_time=execution_time,
                        segment_end_time=day + pd.Timedelta(hours=15),
                        exposure_available_at=available_at(post_index),
                        exposure_index=post_index,
                        returns=surface.close[surface_row] / surface.execution[surface_row] - 1.0,
                    ),
                ]
            )
    return jobs


def fit_factor_jobs_gpu(
    jobs: list[FitJob],
    *,
    store: IntradayK1InputStore,
    device: torch.device,
    batch_size: int = 32,
    parity_sample_count: int = 12,
) -> FitBatchResult:
    if not jobs:
        raise ValueError("current_K1_ledger_fit_jobs_empty")
    started = time.perf_counter()
    fits: dict[str, SegmentFit] = {}
    surface_rows: list[dict[str, object]] = []
    factor_count = len(store.factor_ids)
    if factor_count != 14:
        raise ValueError("current_K1_ledger_factor_count_invalid")
    for start in range(0, len(jobs), batch_size):
        batch = jobs[start : start + batch_size]
        exposures = np.stack(
            [np.asarray(store.stock_factor_exposures[job.exposure_index], dtype=np.float64) for job in batch]
        )
        returns = np.stack([np.asarray(job.returns, dtype=np.float64) for job in batch])
        available = np.stack(
            [
                np.asarray(store.exposure_available[job.exposure_index], dtype=bool).any(axis=1)
                for job in batch
            ]
        )
        valid = available & np.isfinite(returns) & np.isfinite(exposures).all(axis=2)
        x = torch.from_numpy(np.ascontiguousarray(exposures)).to(device=device, dtype=torch.float64)
        y = torch.from_numpy(np.ascontiguousarray(returns)).to(device=device, dtype=torch.float64)
        mask = torch.from_numpy(valid).to(device=device)
        x = torch.where(mask[:, :, None], x, 0.0)
        y = torch.where(mask, y, 0.0)
        singular = torch.linalg.svdvals(x)
        condition = singular[:, 0] / singular[:, -1]
        coefficient = torch.linalg.lstsq(x, y[:, :, None], driver="gels").solution.squeeze(2)
        coefficient_cpu = coefficient.detach().cpu().numpy()
        condition_cpu = condition.detach().cpu().numpy()
        rank_cpu = torch.linalg.matrix_rank(x).detach().cpu().numpy()
        observation_count = valid.sum(axis=1)
        for position, job in enumerate(batch):
            if int(rank_cpu[position]) != factor_count:
                raise ValueError(f"current_K1_ledger_factor_segment_rank_deficient:{job.segment_id}")
            local_condition = float(condition_cpu[position])
            if not np.isfinite(local_condition) or local_condition > 1.0e8:
                raise ValueError(f"current_K1_ledger_factor_segment_condition_failed:{job.segment_id}")
            fit = SegmentFit(
                coefficient=np.asarray(coefficient_cpu[position], dtype=np.float64),
                rank=int(rank_cpu[position]),
                condition_number=local_condition,
                observation_count=int(observation_count[position]),
            )
            fits[job.segment_id] = fit
            for factor_position, factor_id in enumerate(store.factor_ids):
                surface_rows.append(
                    {
                        "variant_id": job.variant_id,
                        "segment_id": job.segment_id,
                        "segment_start_time": job.segment_start_time,
                        "segment_end_time": job.segment_end_time,
                        "exposure_available_at": job.exposure_available_at,
                        "factor_id": str(factor_id),
                        "factor_return": float(fit.coefficient[factor_position]),
                        "observation_count": fit.observation_count,
                        "design_rank": fit.rank,
                        "condition_number": fit.condition_number,
                        "date": job.date,
                        "segment_kind": job.segment_kind,
                        "exposure_index": job.exposure_index,
                    }
                )
    torch.cuda.synchronize()
    parity_error = 0.0
    condition_relative_error = 0.0
    for job in jobs[: min(parity_sample_count, len(jobs))]:
        exposure = np.asarray(store.stock_factor_exposures[job.exposure_index], dtype=np.float64)
        returns = np.asarray(job.returns, dtype=np.float64).copy()
        available = np.asarray(store.exposure_available[job.exposure_index], dtype=bool).any(axis=1)
        returns[~available] = np.nan
        cpu = fit_factor_segment(exposure, returns)
        gpu_fit = fits[job.segment_id]
        parity_error = max(parity_error, float(np.max(np.abs(cpu.coefficient - gpu_fit.coefficient))))
        condition_relative_error = max(
            condition_relative_error,
            abs(cpu.condition_number - gpu_fit.condition_number) / max(cpu.condition_number, 1.0e-15),
        )
        if cpu.rank != gpu_fit.rank or cpu.observation_count != gpu_fit.observation_count:
            raise RuntimeError("current_K1_ledger_factor_fit_structural_parity_failed")
    if parity_error > 1.0e-10 or condition_relative_error > 1.0e-10:
        raise RuntimeError(
            f"current_K1_ledger_factor_fit_numeric_parity_failed:{parity_error}:{condition_relative_error}"
        )
    surface = pd.DataFrame(surface_rows).sort_values(
        ["variant_id", "segment_id", "factor_id"], kind="mergesort", ignore_index=True
    )
    validate_factor_return_surface(surface)
    return FitBatchResult(
        surface=surface,
        fits=fits,
        diagnostics={
            "job_count": len(jobs),
            "batch_size": batch_size,
            "backend": "pytorch_rocm_float64_batched_lstsq",
            "elapsed_seconds": time.perf_counter() - started,
            "parity_sample_count": min(parity_sample_count, len(jobs)),
            "coefficient_max_abs_parity_error": parity_error,
            "condition_max_relative_parity_error": condition_relative_error,
        },
    )


def _holding_symbols(path: AccountPath) -> dict[pd.Timestamp, set[str]]:
    if path.holdings.empty:
        return {}
    holdings = path.holdings.copy()
    holdings["date"] = pd.to_datetime(holdings["date"], errors="raise").dt.normalize()
    return {
        pd.Timestamp(day): set(local["symbol"].astype(str))
        for day, local in holdings.groupby("date", sort=True)
    }


def build_selection_opportunity_ledger(
    *,
    scores: pd.DataFrame,
    path: AccountPath,
    surface: PriceSurface,
    future_surface: PriceSurface,
    store: IntradayK1InputStore,
    target: base.ExtendedTargetSurfaces,
    clock: str,
    post_gates: Mapping[pd.Timestamp, Mapping[str, object]] | None,
    replay_segment_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    symbols = store.symbols.astype(str)
    symbol_index = {str(value): position for position, value in enumerate(symbols)}
    calendar_index = {pd.Timestamp(value): position for position, value in enumerate(target.calendar)}
    held = _holding_symbols(path)
    suffix = CLOCK_SUFFIX[clock]
    entry_minute = np.load(target.root / f"entry_minute_{suffix}.npy", mmap_mode="r")
    decision_minute = 14 * 60 + (30 if clock == "14:30" else 45)
    rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []

    def execution_vector(day: pd.Timestamp) -> NDArray[np.float64]:
        if day in surface.dates:
            return surface.execution[surface.row(day)]
        if day in future_surface.dates:
            return future_surface.execution[future_surface.row(day)]
        raise ValueError(f"current_K1_opportunity_execution_day_missing:{day.date()}")

    def buyable(day: pd.Timestamp, symbol: str, position: int) -> bool:
        if post_gates is not None and day in post_gates:
            gate = post_gates.get(day, {}).get(symbol)
            return bool(getattr(gate, "buy_ok", False))
        if day in surface.dates:
            return bool(surface.buy_ok[surface.row(day), position])
        return False

    for day, local in scores.groupby("decision_date", sort=True):
        decision_day = pd.Timestamp(day).normalize()
        day_position = calendar_index.get(decision_day)
        if day_position is None or day_position + HORIZON_DAYS >= len(target.calendar):
            continue
        exit_day = pd.Timestamp(target.calendar[day_position + HORIZON_DAYS]).normalize()
        if exit_day > future_surface.dates[-1]:
            continue
        work = local.loc[:, ["symbol", "score"]].copy()
        work["symbol"] = work["symbol"].astype(str).str.zfill(6)
        work["score"] = pd.to_numeric(work["score"], errors="coerce")
        work = work.drop_duplicates("symbol", keep=False)
        work["symbol_position"] = work["symbol"].map(symbol_index)
        work = work.dropna(subset=["symbol_position"])
        work["symbol_position"] = work["symbol_position"].astype(np.int64)
        start_prices = execution_vector(decision_day)
        end_prices = execution_vector(exit_day)
        position = work["symbol_position"].to_numpy(np.int64)
        start_price = start_prices[position]
        end_price = end_prices[position]
        eligible = np.asarray(
            [buyable(decision_day, str(symbol), int(pos)) for symbol, pos in zip(work["symbol"], position, strict=True)],
            dtype=bool,
        )
        eligible &= (
            np.isfinite(work["score"].to_numpy(np.float64))
            & np.isfinite(start_price)
            & (start_price > 0.0)
            & np.isfinite(end_price)
            & (end_price > 0.0)
        )
        eligible_positions = np.flatnonzero(eligible)
        if len(eligible_positions) < TOP_N:
            raise ValueError(f"current_K1_opportunity_eligible_below_topN:{decision_day.date()}:{clock}")
        local_symbols = work["symbol"].to_numpy(str)
        local_scores = work["score"].to_numpy(np.float64)
        realized = end_price / start_price - 1.0
        score_order = eligible_positions[
            np.lexsort((local_symbols[eligible_positions], -local_scores[eligible_positions]))
        ]
        opportunity_order = eligible_positions[
            np.lexsort((local_symbols[eligible_positions], -realized[eligible_positions]))
        ]
        selection_rank = {int(value): rank + 1 for rank, value in enumerate(score_order)}
        opportunity_rank = {int(value): rank + 1 for rank, value in enumerate(opportunity_order)}
        selected_positions = set(int(value) for value in score_order[:TOP_N])
        oracle_positions = set(int(value) for value in opportunity_order[:TOP_N])
        held_symbols = held.get(decision_day, set())
        row_by_symbol = {str(symbol): index for index, symbol in enumerate(local_symbols)}
        persisted = set(selected_positions) | set(oracle_positions)
        persisted.update(row_by_symbol[symbol] for symbol in held_symbols if symbol in row_by_symbol)
        selected_returns = realized[list(sorted(selected_positions))]
        oracle_returns = realized[list(sorted(oracle_positions))]
        overlap = len(selected_positions & oracle_positions)
        summary_rows.append(
            {
                "decision_id": f"{clock}:{decision_day.strftime('%Y%m%d')}",
                "decision_date": decision_day,
                "year": decision_day.year,
                "decision_clock": clock,
                "replay_segment_id": replay_segment_id,
                "eligible_count": len(eligible_positions),
                "selected_count": TOP_N,
                "oracle_count": TOP_N,
                "selected_oracle_overlap_count": overlap,
                "selected_oracle_overlap_share": overlap / TOP_N,
                "selected_mean_h20_return": float(np.mean(selected_returns)),
                "oracle_mean_h20_return": float(np.mean(oracle_returns)),
                "selection_gap_mean_h20_return": float(np.mean(selected_returns) - np.mean(oracle_returns)),
                "selected_median_opportunity_rank": float(
                    np.median([opportunity_rank[value] for value in selected_positions])
                ),
            }
        )
        for local_position in sorted(persisted, key=lambda value: local_symbols[value]):
            symbol = str(local_symbols[local_position])
            symbol_position = int(position[local_position])
            selected = local_position in selected_positions
            oracle = local_position in oracle_positions
            is_held = symbol in held_symbols
            if selected and oracle:
                bucket = "selected_and_oracle"
            elif selected:
                bucket = "selected_only"
            elif oracle:
                bucket = "oracle_only"
            else:
                bucket = "held_only"
            start_minute = int(entry_minute[day_position, symbol_position])
            end_minute = int(entry_minute[day_position + HORIZON_DAYS, symbol_position])
            if start_minute < 0 or end_minute < 0:
                if bool(eligible[local_position]):
                    raise ValueError("current_K1_opportunity_entry_minute_missing")
                start_minute = decision_minute + 1
                end_minute = decision_minute + 1
            rows.append(
                {
                    "decision_id": f"{clock}:{decision_day.strftime('%Y%m%d')}",
                    "decision_time": decision_day + pd.Timedelta(minutes=decision_minute),
                    "variant_id": clock,
                    "policy_id": POLICY_ID,
                    "asset_id": symbol,
                    "score": float(local_scores[local_position]),
                    "score_available_at": decision_day + pd.Timedelta(minutes=decision_minute),
                    "eligible": bool(eligible[local_position]),
                    "selected": selected,
                    "selection_rank": selection_rank.get(local_position, np.nan),
                    "label_start_time": decision_day + pd.Timedelta(minutes=start_minute),
                    "label_end_time": exit_day + pd.Timedelta(minutes=end_minute),
                    "realized_forward_return": float(realized[local_position]),
                    "opportunity_rank": opportunity_rank.get(local_position, np.nan),
                    "opportunity_bucket": bucket,
                    "oracle_top30": oracle,
                    "account_held_after_execution": is_held,
                    "forced_or_nonselected_holding": is_held and not selected,
                    "replay_segment_id": replay_segment_id,
                    "horizon_days": HORIZON_DAYS,
                }
            )
    ledger = pd.DataFrame(rows).sort_values(
        ["decision_id", "asset_id"], kind="mergesort", ignore_index=True
    )
    summary = pd.DataFrame(summary_rows).sort_values(
        ["decision_date", "decision_clock"], kind="mergesort", ignore_index=True
    )
    validate_selection_opportunity_ledger(ledger)
    return ledger, summary


def annual_selection_summary(decision_summary: pd.DataFrame) -> pd.DataFrame:
    return (
        decision_summary.groupby(["year", "decision_clock", "replay_segment_id"], sort=True)
        .agg(
            decision_count=("decision_id", "nunique"),
            mean_eligible_count=("eligible_count", "mean"),
            mean_selected_oracle_overlap_share=("selected_oracle_overlap_share", "mean"),
            mean_selected_h20_return=("selected_mean_h20_return", "mean"),
            mean_oracle_h20_return=("oracle_mean_h20_return", "mean"),
            mean_selection_gap_h20_return=("selection_gap_mean_h20_return", "mean"),
            median_selected_opportunity_rank=("selected_median_opportunity_rank", "median"),
        )
        .reset_index()
    )


def build_realized_pnl_ledger(
    *,
    path: AccountPath,
    standardized_daily: pd.DataFrame,
    standardized_trades: pd.DataFrame,
    surface: PriceSurface,
    store: IntradayK1InputStore,
    fits: Mapping[str, SegmentFit],
    clock: str,
    replay_segment_id: str,
    strategy_id: str = STRATEGY_ID,
) -> pd.DataFrame:
    account_id = f"{strategy_id}:{clock}:{replay_segment_id}"
    identity = {
        "account_id": account_id,
        "variant_id": clock,
        "policy_id": POLICY_ID,
        "cost_scenario_id": "slippage_1.0x",
    }
    daily = path.daily.copy().sort_values("date", kind="mergesort", ignore_index=True)
    daily["date"] = pd.to_datetime(daily["date"], errors="raise").dt.normalize()
    holdings = path.holdings.copy()
    holdings["date"] = pd.to_datetime(holdings["date"], errors="raise").dt.normalize()
    holdings_by_day = {
        pd.Timestamp(day): local.set_index("symbol")
        for day, local in holdings.groupby("date", sort=True)
    }
    trade_symbols = (
        {
            pd.Timestamp(day): set(local["asset_id"].astype(str))
            for day, local in standardized_trades.groupby("date", sort=True)
        }
        if not standardized_trades.empty
        else {}
    )
    trade_costs = (
        standardized_trades.groupby("date", sort=True)["transaction_cost"].sum().to_dict()
        if not standardized_trades.empty
        else {}
    )
    episode_lookup, _ = build_episode_lookup(pd.DatetimeIndex(daily["date"]), holdings)
    symbol_positions = {str(symbol): position for position, symbol in enumerate(store.symbols.astype(str))}
    rows: list[dict[str, object]] = []
    previous_holdings = pd.DataFrame()
    previous_day: pd.Timestamp | None = None
    previous_nav = float(INITIAL_NAV)
    for daily_row in daily.itertuples(index=False):
        day = pd.Timestamp(daily_row.date)
        current_holdings = holdings_by_day.get(day, pd.DataFrame())
        q0 = {
            str(symbol): float(value)
            for symbol, value in previous_holdings.get("shares", pd.Series(dtype=float)).items()
        }
        p0 = {
            str(symbol): float(value)
            for symbol, value in previous_holdings.get("mark_price", pd.Series(dtype=float)).items()
        }
        q1 = {
            str(symbol): float(value)
            for symbol, value in current_holdings.get("shares", pd.Series(dtype=float)).items()
        }
        p1 = {
            str(symbol): float(value)
            for symbol, value in current_holdings.get("mark_price", pd.Series(dtype=float)).items()
        }
        is_rebalance = bool(daily_row.is_rebalance)
        pre_index = _exposure_index(store, day, before_current=is_rebalance)
        post_index = _exposure_index(store, day, before_current=False)
        full_id = f"{clock}:{day.strftime('%Y%m%d')}:full"
        pre_id = f"{clock}:{day.strftime('%Y%m%d')}:pre"
        post_id = f"{clock}:{day.strftime('%Y%m%d')}:post"
        reallocated = trade_symbols.get(day, set()) | {
            symbol
            for symbol in set(q0) | set(q1)
            if not np.isclose(
                q0.get(symbol, 0.0),
                q1.get(symbol, 0.0),
                rtol=1.0e-12,
                atol=1.0e-8,
            )
        }
        day_rows: list[dict[str, object]] = []
        surface_row = surface.row(day)

        def append_piece(
            *,
            attribution_day: pd.Timestamp,
            nav_value: float,
            accumulator: list[dict[str, object]],
            symbol: str,
            quantity: float,
            start_price: float,
            end_price: float,
            fit: SegmentFit,
            exposure_index: int,
            segment_id: str,
            segment_kind: str,
            episode_day: pd.Timestamp,
        ) -> None:
            if quantity <= 0.0 or not (
                np.isfinite(start_price)
                and np.isfinite(end_price)
                and start_price > 0.0
                and end_price > 0.0
            ):
                return
            actual_return = end_price / start_price - 1.0
            start_weight = quantity * start_price / nav_value
            components = stock_factor_piece(
                symbol=symbol,
                actual_stock_return=actual_return,
                account_start_weight=start_weight,
                fit=fit,
                store=store,
                exposure_index=exposure_index,
                symbol_positions=symbol_positions,
            )
            episode_id = episode_lookup.get((episode_day, symbol))
            if episode_id is None:
                raise ValueError(
                    f"current_K1_ledger_episode_missing:{attribution_day.date()}:{symbol}"
                )
            values = {
                "index": (
                    components["stock_index_return"],
                    components["index_account_contribution"],
                ),
                "size": (
                    components["stock_size_return"],
                    components["size_account_contribution"],
                ),
                "industry": (
                    components["stock_industry_return"],
                    components["industry_account_contribution"],
                ),
                "other": (
                    components["stock_other_return"],
                    components["other_gross_account_contribution"],
                ),
            }
            for component_id, (component_return, contribution) in values.items():
                accumulator.append(
                    {
                        "date": attribution_day,
                        **identity,
                        "asset_id": symbol,
                        "trade_episode_id": episode_id,
                        "segment_id": segment_id,
                        "component_id": component_id,
                        "simple_contribution": float(contribution),
                        "linked_log_contribution": 0.0,
                        "year": attribution_day.year,
                        "decision_clock": clock,
                        "replay_segment_id": replay_segment_id,
                        "segment_kind": segment_kind,
                        "exposure_index": exposure_index,
                        "quantity": quantity,
                        "start_price": start_price,
                        "end_price": end_price,
                        "account_start_weight": start_weight,
                        "actual_stock_return": actual_return,
                        "stock_component_return": float(component_return),
                    }
                )

        for symbol in sorted(set(q0) | set(q1)):
            symbol_position = symbol_positions[symbol]
            start_price = p0.get(symbol, float("nan"))
            close_price = p1.get(symbol, float("nan"))
            if symbol in reallocated:
                execution_price = float(surface.execution[surface_row, symbol_position])
                if q0.get(symbol, 0.0) > 0.0:
                    if previous_day is None:
                        raise ValueError("current_K1_ledger_previous_day_missing")
                    append_piece(
                        attribution_day=day,
                        nav_value=previous_nav,
                        accumulator=day_rows,
                        symbol=symbol,
                        quantity=q0.get(symbol, 0.0),
                        start_price=start_price,
                        end_price=execution_price,
                        fit=fits[pre_id],
                        exposure_index=pre_index,
                        segment_id=pre_id,
                        segment_kind="previous_close_to_execution",
                        episode_day=previous_day,
                    )
                if q1.get(symbol, 0.0) > 0.0:
                    append_piece(
                        attribution_day=day,
                        nav_value=previous_nav,
                        accumulator=day_rows,
                        symbol=symbol,
                        quantity=q1.get(symbol, 0.0),
                        start_price=execution_price,
                        end_price=close_price,
                        fit=fits[post_id],
                        exposure_index=post_index,
                        segment_id=post_id,
                        segment_kind="execution_to_close",
                        episode_day=day,
                    )
            elif q0.get(symbol, 0.0) > 0.0:
                if previous_day is None:
                    raise ValueError("current_K1_ledger_previous_day_missing")
                append_piece(
                    attribution_day=day,
                    nav_value=previous_nav,
                    accumulator=day_rows,
                    symbol=symbol,
                    quantity=q0.get(symbol, 0.0),
                    start_price=start_price,
                    end_price=close_price,
                    fit=fits[full_id],
                    exposure_index=pre_index,
                    segment_id=full_id,
                    segment_kind="previous_close_to_close",
                    episode_day=previous_day,
                )
        transaction_cost = float(trade_costs.get(day, 0.0)) / previous_nav
        if transaction_cost > 0.0:
            day_rows.append(
                {
                    "date": day,
                    **identity,
                    "asset_id": "__ACCOUNT__",
                    "trade_episode_id": f"{account_id}:{day.strftime('%Y%m%d')}:cost",
                    "segment_id": pre_id if is_rebalance else full_id,
                    "component_id": "transaction_cost",
                    "simple_contribution": -transaction_cost,
                    "linked_log_contribution": 0.0,
                    "year": day.year,
                    "decision_clock": clock,
                    "replay_segment_id": replay_segment_id,
                    "segment_kind": "transaction_cost",
                    "exposure_index": pre_index,
                    "quantity": 0.0,
                    "start_price": 0.0,
                    "end_price": 0.0,
                    "account_start_weight": 0.0,
                    "actual_stock_return": 0.0,
                    "stock_component_return": 0.0,
                }
            )
        account_return = float(daily_row.daily_return)
        if not day_rows:
            day_rows.append(
                {
                    "date": day,
                    **identity,
                    "asset_id": "__CASH__",
                    "trade_episode_id": f"{account_id}:{day.strftime('%Y%m%d')}:cash",
                    "segment_id": full_id,
                    "component_id": "other",
                    "simple_contribution": 0.0,
                    "linked_log_contribution": 0.0,
                    "year": day.year,
                    "decision_clock": clock,
                    "replay_segment_id": replay_segment_id,
                    "segment_kind": "cash_only",
                    "exposure_index": pre_index,
                    "quantity": 0.0,
                    "start_price": 0.0,
                    "end_price": 0.0,
                    "account_start_weight": 0.0,
                    "actual_stock_return": 0.0,
                    "stock_component_return": 0.0,
                }
            )
        simple_sum = float(sum(float(value["simple_contribution"]) for value in day_rows))
        if abs(simple_sum - account_return) > 1.0e-10:
            raise RuntimeError(
                f"current_K1_ledger_daily_pnl_identity_failed:{day.date()}:{simple_sum-account_return}"
            )
        scale = math.log1p(account_return) / account_return if abs(account_return) > 1.0e-15 else 1.0
        for value in day_rows:
            value["linked_log_contribution"] = float(value["simple_contribution"]) * scale
        rows.extend(day_rows)
        previous_holdings = current_holdings
        previous_day = day
        previous_nav = float(daily_row.nav)
    ledger = pd.DataFrame(rows).sort_values(
        ["date", "account_id", "asset_id", "segment_id", "component_id"],
        kind="mergesort",
        ignore_index=True,
    )
    validate_realized_pnl_ledger(ledger, account_daily=standardized_daily)
    return ledger


def annual_pnl_summary(ledger: pd.DataFrame) -> pd.DataFrame:
    work = ledger.copy()
    work["component_group"] = work["component_id"].replace({"transaction_cost": "other"})
    return (
        work.groupby(
            ["year", "decision_clock", "replay_segment_id", "component_group"],
            sort=True,
        )
        .agg(
            simple_contribution_sum=("simple_contribution", "sum"),
            linked_log_contribution=("linked_log_contribution", "sum"),
            row_count=("component_id", "size"),
        )
        .reset_index()
    )


def _post_gates(
    *,
    scores: pd.DataFrame,
    target: base.ExtendedTargetSurfaces,
    factor_matrix: NDArray[np.float64],
    clock: str,
) -> dict[pd.Timestamp, dict[str, object]]:
    suffix = CLOCK_SUFFIX[clock]
    factor_start = int(np.searchsorted(target.calendar, np.datetime64("2020-01-01", "ns"), side="left"))
    raw_execution = np.load(target.root / f"entry_open_{suffix}.npy", mmap_mode="r")
    raw_close = np.load(target.root / "raw_close.npy", mmap_mode="r")
    gates = base.build_tradability_maps(
        decision_dates=[pd.Timestamp(value) for value in scores["decision_date"].unique()],
        calendar=target.calendar,
        symbols=target.symbols,
        raw_close=raw_close,
        raw_execution=raw_execution,
        factor_matrix=factor_matrix,
        factor_start=factor_start,
    )
    return cast(dict[pd.Timestamp, dict[str, object]], gates)


def _historical_path(
    *,
    scores: pd.DataFrame,
    market: pd.DataFrame,
    clock: str,
) -> AccountPath:
    prepared = prepare_account_inputs(scores=scores, market=market, clock=clock, end_year=2020)
    return run_corrected_account_path(prepared=prepared, slippage_multiplier=PRIMARY_SLIPPAGE)


def _annual_replay_checks(
    *,
    tree: str,
    account_daily: pd.DataFrame,
    pnl_annual: pd.DataFrame,
) -> dict[str, float]:
    daily = account_daily.copy()
    daily["date"] = pd.to_datetime(daily["date"], errors="raise")
    daily["year"] = daily["date"].dt.year
    daily_log = (
        daily.groupby(["year", "variant_id", "replay_segment_id"], sort=True)["daily_return"]
        .apply(lambda values: float(np.log1p(values.to_numpy(np.float64)).sum()))
        .rename("daily_net_log_return")
        .reset_index()
    )
    pnl_log = (
        pnl_annual.groupby(["year", "decision_clock", "replay_segment_id"], sort=True)[
            "linked_log_contribution"
        ]
        .sum()
        .rename("pnl_net_log_return")
        .reset_index()
    )
    identity = daily_log.merge(
        pnl_log,
        left_on=["year", "variant_id", "replay_segment_id"],
        right_on=["year", "decision_clock", "replay_segment_id"],
        validate="one_to_one",
    )
    pnl_identity_error = float(
        np.max(
            np.abs(
                identity["daily_net_log_return"].to_numpy(np.float64)
                - identity["pnl_net_log_return"].to_numpy(np.float64)
            )
        )
    )
    historical = pd.read_csv(HISTORICAL_ANNUAL_ROOT / tree / "annual_four_group.csv")
    historical = historical.loc[:, ["year", "decision_clock", "group", "linked_log_contribution"]]
    current_historical = pnl_annual.loc[pnl_annual["replay_segment_id"].eq("2011_2020")].rename(
        columns={"component_group": "group"}
    )
    historical_compare = current_historical.merge(
        historical,
        on=["year", "decision_clock", "group"],
        suffixes=("_current", "_sealed"),
        validate="one_to_one",
    )
    historical_error = float(
        np.max(
            np.abs(
                historical_compare["linked_log_contribution_current"].to_numpy(np.float64)
                - historical_compare["linked_log_contribution_sealed"].to_numpy(np.float64)
            )
        )
    )
    post2020 = pd.read_csv(POST2020_ANNUAL_ROOT / tree / "annual_four_group.csv")
    post2020 = post2020.loc[:, ["year", "decision_clock", "group", "linked_log_contribution"]]
    current_post = pnl_annual.loc[pnl_annual["replay_segment_id"].eq("2021_2026")].rename(
        columns={"component_group": "group"}
    )
    post_compare = current_post.merge(
        post2020,
        on=["year", "decision_clock", "group"],
        suffixes=("_current", "_sealed"),
        validate="one_to_one",
    )
    post_error = float(
        np.max(
            np.abs(
                post_compare["linked_log_contribution_current"].to_numpy(np.float64)
                - post_compare["linked_log_contribution_sealed"].to_numpy(np.float64)
            )
        )
    )
    if pnl_identity_error > 1.0e-10 or max(historical_error, post_error) > 1.0e-8:
        raise RuntimeError(
            f"current_K1_ledger_sealed_annual_replay_failed:{pnl_identity_error}:{historical_error}:{post_error}"
        )
    return {
        "account_to_pnl_annual_log_max_abs_error": pnl_identity_error,
        "historical_four_group_max_abs_error": historical_error,
        "post2020_four_group_max_abs_error": post_error,
    }


def _write_parquet(path: Path, frame: pd.DataFrame, sort_columns: list[str]) -> None:
    frame.sort_values(sort_columns, kind="mergesort", ignore_index=True).to_parquet(
        path,
        index=False,
        compression="zstd",
        use_dictionary=False,
    )


def execute_tree(
    *,
    tree: str,
    output_root: Path,
    factor_batch_size: int = 32,
) -> dict[str, object]:
    if tree not in {"formal", "isolated"}:
        raise ValueError("current_K1_account_ledgers_tree_invalid")
    if output_root.exists():
        raise FileExistsError(output_root)
    contract = _load_contract()
    if not torch.cuda.is_available() or getattr(torch.version, "hip", None) is None:
        raise RuntimeError("current_K1_account_ledgers_rocm_required")
    started = time.perf_counter()
    output_root.mkdir(parents=True)
    target, factor_matrix = gpu.load_gpu_cache(root=CACHE_ROOT, tree=tree)
    device = torch.device("cuda:0")
    daily_parts: list[pd.DataFrame] = []
    holdings_parts: list[pd.DataFrame] = []
    trades_parts: list[pd.DataFrame] = []
    events_parts: list[pd.DataFrame] = []
    opportunity_parts: list[pd.DataFrame] = []
    opportunity_summary_parts: list[pd.DataFrame] = []
    factor_surface_parts: list[pd.DataFrame] = []
    pnl_parts: list[pd.DataFrame] = []
    fit_diagnostics: dict[str, object] = {}
    prefix_checks: dict[str, object] = {}
    input_digests: dict[str, str] = {}
    for clock in CLOCKS:
        suffix = CLOCK_SUFFIX[clock]
        historical_scores = _load_historical_scores(tree, clock)
        historical_market = _load_historical_market(tree, clock)
        historical_store_path = gpu.OLD_STORE_ROOT / tree / suffix
        historical_path = _historical_path(
            scores=historical_scores,
            market=historical_market,
            clock=clock,
        )
        post_scores, extended_store, checks = post.build_scores_and_store(
            tree=tree,
            clock=clock,
            target=target,
            device=device,
        )
        prefix_checks[clock] = checks
        historical_surface = build_historical_price_surface(
            historical_market,
            store=extended_store,
        )
        gates = _post_gates(
            scores=post_scores,
            target=target,
            factor_matrix=factor_matrix,
            clock=clock,
        )
        post_surface = build_post_price_surface(
            target=target,
            factor_matrix=factor_matrix,
            clock=clock,
        )
        post_path = run_post2020_account_path(
            score_frame=post_scores,
            target=target,
            factor_matrix=factor_matrix,
            clock=clock,
            gates=gates,
        )
        historical_execution = _execution_price_lookup_historical(
            historical_surface,
            extended_store.symbols,
        )
        post_execution = _post_execution_price_lookup(
            post_path,
            surface=post_surface,
            symbols=extended_store.symbols,
        )
        historical_standard = standardize_account_path(
            path=historical_path,
            clock=clock,
            replay_segment_id="2011_2020",
            execution_price=historical_execution,
        )
        post_standard = standardize_account_path(
            path=post_path,
            clock=clock,
            replay_segment_id="2021_2026",
            execution_price=post_execution,
        )
        for target_list, position in (
            (daily_parts, 0),
            (holdings_parts, 1),
            (trades_parts, 2),
            (events_parts, 3),
        ):
            target_list.extend([historical_standard[position], post_standard[position]])
        jobs = [
            *build_fit_jobs(
                path=historical_path,
                surface=historical_surface,
                store=extended_store,
                clock=clock,
            ),
            *build_fit_jobs(
                path=post_path,
                surface=post_surface,
                store=extended_store,
                clock=clock,
            ),
        ]
        fit_batch = fit_factor_jobs_gpu(
            jobs,
            store=extended_store,
            device=device,
            batch_size=factor_batch_size,
        )
        fit_diagnostics[clock] = fit_batch.diagnostics
        factor_surface_parts.append(fit_batch.surface)
        historical_ledger, historical_decisions = build_selection_opportunity_ledger(
            scores=historical_scores,
            path=historical_path,
            surface=historical_surface,
            future_surface=post_surface,
            store=extended_store,
            target=target,
            clock=clock,
            post_gates=gates,
            replay_segment_id="2011_2020",
        )
        post_ledger, post_decisions = build_selection_opportunity_ledger(
            scores=post_scores,
            path=post_path,
            surface=post_surface,
            future_surface=post_surface,
            store=extended_store,
            target=target,
            clock=clock,
            post_gates=gates,
            replay_segment_id="2021_2026",
        )
        opportunity_parts.extend([historical_ledger, post_ledger])
        opportunity_summary_parts.extend([historical_decisions, post_decisions])
        pnl_parts.extend(
            [
                build_realized_pnl_ledger(
                    path=historical_path,
                    standardized_daily=historical_standard[0],
                    standardized_trades=historical_standard[2],
                    surface=historical_surface,
                    store=extended_store,
                    fits=fit_batch.fits,
                    clock=clock,
                    replay_segment_id="2011_2020",
                ),
                build_realized_pnl_ledger(
                    path=post_path,
                    standardized_daily=post_standard[0],
                    standardized_trades=post_standard[2],
                    surface=post_surface,
                    store=extended_store,
                    fits=fit_batch.fits,
                    clock=clock,
                    replay_segment_id="2021_2026",
                ),
            ]
        )
        for path in (
            HISTORICAL_SCORE_ROOT / tree / f"bounded_score_panel_{suffix}.parquet",
            INPUT_ROOT / tree / f"daily_market_panel_{suffix}.parquet",
            historical_store_path / "manifest.json",
        ):
            input_digests[str(path.relative_to(ROOT))] = file_digest(path)
    torch.cuda.synchronize()
    account_daily = pd.concat(daily_parts, ignore_index=True)
    holdings = pd.concat(holdings_parts, ignore_index=True)
    trades = pd.concat(trades_parts, ignore_index=True)
    events = pd.concat(events_parts, ignore_index=True)
    opportunity = pd.concat(opportunity_parts, ignore_index=True)
    opportunity_decisions = pd.concat(opportunity_summary_parts, ignore_index=True)
    factor_surface = pd.concat(factor_surface_parts, ignore_index=True)
    pnl = pd.concat(pnl_parts, ignore_index=True)
    snapshot_identity = AccountSnapshotIdentity(
        strategy_id=STRATEGY_ID,
        model_or_score_digest="sha256:ea35bd38660a074fe70fc577d0e8de1501cd71dfa63471197a86673e32db173a",
        account_policy_family_digest="sha256:89fc1bbcdabb291252182f2f938009e301b636516d9458e216705476154a0d60",
        market_data_digest=canonical_digest(dict(sorted(input_digests.items()))),
        adapter_digest=file_digest(ROOT / "src/factor_lab/factor_rotation/reaka_current_k1_account_ledgers_v1.py"),
        data_usage_digest=str(contract["canonical_digest"]),
        tree=tree,
        execution_semantics="next_tradable_after_bar_close_raw_PIT_then_HFQ_accounting",
    )
    snapshot = materialize_account_snapshot(
        output_root=output_root / "account_snapshot",
        identity=snapshot_identity,
        daily=account_daily,
        holdings=holdings,
        trades=trades,
        events=events,
        snapshot_profile="complete_account",
        initial_nav=INITIAL_NAV,
        source_closure=source_closure(),
    )
    snapshot_scientific_digest = canonical_digest(
        {
            name: file_digest(output_root / "account_snapshot" / name)
            for name in ("portfolio_daily.parquet", "holdings.parquet", "trades.parquet", "events.parquet")
        }
    )
    _write_parquet(
        output_root / "selection_opportunity_ledger.parquet",
        opportunity,
        ["decision_id", "asset_id"],
    )
    write_csv(
        output_root / "selection_opportunity_decision_summary.csv",
        opportunity_decisions.sort_values(
            ["decision_date", "decision_clock"], kind="mergesort", ignore_index=True
        ),
    )
    selection_annual = annual_selection_summary(opportunity_decisions)
    write_csv(output_root / "selection_opportunity_annual.csv", selection_annual)
    _write_parquet(
        output_root / "factor_return_surface.parquet",
        factor_surface,
        ["variant_id", "segment_id", "factor_id"],
    )
    _write_parquet(
        output_root / "realized_pnl_ledger.parquet",
        pnl,
        ["date", "account_id", "asset_id", "segment_id", "component_id"],
    )
    pnl_annual = annual_pnl_summary(pnl)
    write_csv(output_root / "realized_pnl_annual.csv", pnl_annual)
    opportunity_diagnostics = validate_selection_opportunity_ledger(opportunity)
    factor_diagnostics = validate_factor_return_surface(factor_surface)
    pnl_diagnostics = validate_realized_pnl_ledger(pnl, account_daily=account_daily)
    replay_checks = _annual_replay_checks(
        tree=tree,
        account_daily=account_daily,
        pnl_annual=pnl_annual,
    )
    scientific_fit_diagnostics = {
        clock: {key: value for key, value in cast(dict[str, object], local).items() if key != "elapsed_seconds"}
        for clock, local in fit_diagnostics.items()
    }
    result = write_json(
        output_root / "result.json",
        {
            "schema_id": "factorlab.reaka_current_K1_account_ledgers_result@1.0",
            "status": "completed_current_strategy_two_ledgers",
            "strategy_id": STRATEGY_ID,
            "model_identity": MODEL_IDENTITY,
            "account_policy_id": POLICY_ID,
            "decision_clocks": list(CLOCKS),
            "slippage_multiplier": PRIMARY_SLIPPAGE,
            "replay_segments": ["2011_2020", "2021_2026"],
            "selection_opportunity_diagnostics": opportunity_diagnostics,
            "factor_return_surface_diagnostics": factor_diagnostics,
            "realized_pnl_diagnostics": pnl_diagnostics,
            "factor_fit_diagnostics": scientific_fit_diagnostics,
            "sealed_annual_replay_checks": replay_checks,
            "account_snapshot_scientific_digest": snapshot_scientific_digest,
            "prefix_checks": prefix_checks,
            "model_or_parameter_change": False,
            "result_backflow_allowed": False,
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    scientific_paths = [
        output_root / "account_snapshot/portfolio_daily.parquet",
        output_root / "account_snapshot/holdings.parquet",
        output_root / "account_snapshot/trades.parquet",
        output_root / "account_snapshot/events.parquet",
        output_root / "selection_opportunity_ledger.parquet",
        output_root / "selection_opportunity_decision_summary.csv",
        output_root / "selection_opportunity_annual.csv",
        output_root / "factor_return_surface.parquet",
        output_root / "realized_pnl_ledger.parquet",
        output_root / "realized_pnl_annual.csv",
        output_root / "result.json",
    ]
    scientific_digests = {
        str(path.relative_to(output_root)): file_digest(path) for path in scientific_paths
    }
    return write_json(
        output_root / "execution_receipt.json",
        {
            "schema_id": "factorlab.reaka_current_K1_account_ledgers_execution@1.0",
            "status": "completed",
            "tree": tree,
            "contract_digest": contract["canonical_digest"],
            "backend": "ROCm_batched_factor_surface_plus_CPU_sequential_account",
            "elapsed_seconds": time.perf_counter() - started,
            "result_digest": result["canonical_digest"],
            "account_snapshot_manifest_digest": snapshot["canonical_digest"],
            "factor_fit_runtime_diagnostics": fit_diagnostics,
            "scientific_file_digests": scientific_digests,
            "input_digests": dict(sorted(input_digests.items())),
            "source_closure": source_closure(),
            "model_or_parameter_change": False,
            "result_backflow_allowed": False,
            "fresh_oos": False,
            "production_authority": False,
        },
    )


__all__ = [
    "COMPONENTS",
    "FitBatchResult",
    "FitJob",
    "PriceSurface",
    "annual_pnl_summary",
    "annual_selection_summary",
    "build_fit_jobs",
    "build_historical_price_surface",
    "build_post_price_surface",
    "build_realized_pnl_ledger",
    "build_selection_opportunity_ledger",
    "execute_tree",
    "fit_factor_jobs_gpu",
    "run_post2020_account_path",
    "source_closure",
    "standardize_account_path",
]
