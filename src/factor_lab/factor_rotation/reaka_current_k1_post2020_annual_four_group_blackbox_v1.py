# pyright: reportAny=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false, reportGeneralTypeIssues=false
# pyright: reportAttributeAccessIssue=false, reportIndexIssue=false
# pyright: reportArgumentType=false, reportReturnType=false
# pyright: reportCallIssue=false, reportOperatorIssue=false
"""Corrected 2021-2026 annual four-group aggregate-only blackbox."""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Final, cast

import numpy as np
import pandas as pd
import torch
from numpy.typing import NDArray

from factor_lab.factor_rotation import reaka_current_generation_aggregate_blackbox_gpu_v2 as gpu
from factor_lab.factor_rotation import reaka_current_generation_aggregate_blackbox_v1 as base
from factor_lab.factor_rotation.reaka_current_k1_factor_attribution_v1 import (
    SegmentFit,
    factor_input_inventory,
    file_digest,
    fit_factor_segment,
    write_csv,
    write_json,
)
from factor_lab.factor_rotation.reaka_current_k1_factor_attribution_v2 import (
    apply_rebalance_day_conserving_forced_value,
)
from factor_lab.factor_rotation.reaka_current_k1_transaction_pnl_attribution_v1 import stock_factor_piece
from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    CLOCK_SUFFIX,
    IntradayK1InputStore,
    read_json,
)
from factor_lab.factor_rotation.reaka_intraday_portfolio_mapping_v1 import (
    COMMON_ROOT_POLICY_ID,
    INITIAL_NAV,
    account_metrics,
    apply_non_rebalance_day,
    build_execution_target,
    current_weights_from_book,
    policy_by_id,
    rank_portfolio_table,
)
from factor_lab.governance.canonicalization import canonical_digest

ROOT: Final = Path(__file__).resolve().parents[3]
CONTRACT_PATH: Final = ROOT / "docs/ops/reaka_current_k1_2021_2026_annual_four_group_blackbox@1.0.json"
CACHE_ROOT: Final = ROOT / "output/factor-rotation/reaka_current_generation_blackbox_gpu_cache_v2_2007_2026"
YEARS: Final = tuple(range(2021, 2027))
CLOCKS: Final = ("14:30", "14:45")
PRIMARY_SLIPPAGE: Final = 1.0
GROUPS: Final = ("index", "size", "industry", "other")
SCIENTIFIC_FILES: Final = ("annual_four_group.csv", "annual_account.csv", "year_high_low.json", "result.json")


def _load_contract() -> dict[str, object]:
    payload = read_json(CONTRACT_PATH)
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    if stored != canonical_digest(body) or payload.get("formal_execution_allowed") is not True:
        raise ValueError("post2020_annual_four_group_contract_invalid")
    return payload


def build_scores_and_store(
    *,
    tree: str,
    clock: str,
    target: base.ExtendedTargetSurfaces,
    device: torch.device,
) -> tuple[pd.DataFrame, IntradayK1InputStore, dict[str, bool]]:
    suffix = CLOCK_SUFFIX[clock]
    history_raw, future_raw = gpu._h20_surfaces(
        np.load(target.root / f"decision_close_{suffix}.npy", mmap_mode="r"),
        np.load(target.root / f"entry_open_{suffix}.npy", mmap_mode="r"),
    )
    cloudridge = gpu._append_only_cloudridge_path(tree=tree, target_root=target.root)
    core = gpu.EXTENSION_ROOT / tree / "condensation/extended_weekly_membership.parquet"
    cloudridge_frame, core_frame, industry_ids = gpu.load_memberships(
        cloudridge_path=cloudridge,
        core_path=core,
        registry_path=gpu.FACTOR_REGISTRY,
        symbols=target.symbols,
    )
    market_h, _ = gpu.old_ot1.materialize_equal_weight_carriers(
        history_raw, target.calendar, cloudridge_frame, [gpu.MARKET_FACTOR_ID], minimum_members=12
    )
    market_f, _ = gpu.old_ot1.materialize_equal_weight_carriers(
        future_raw, target.calendar, cloudridge_frame, [gpu.MARKET_FACTOR_ID], minimum_members=12
    )
    target_order = [gpu.SMALL_TARGET_ID, gpu.LARGE_TARGET_ID, *industry_ids]
    core_h, _ = gpu.old_ot1.materialize_equal_weight_carriers(
        history_raw, target.calendar, core_frame, target_order, minimum_members=5
    )
    core_f, _ = gpu.old_ot1.materialize_equal_weight_carriers(
        future_raw, target.calendar, core_frame, target_order, minimum_members=5
    )
    basis_h, _, basis_history = gpu.build_causal_basis_pair_gpu(
        history_carriers=np.concatenate([market_h, core_h], axis=2),
        future_carriers=np.concatenate([market_f, core_f], axis=2),
        calendar=target.calendar,
        industry_ids=industry_ids,
        decision_clock=clock,
        device=device,
    )
    states = gpu.build_selected_states(
        history_basis=basis_history,
        selections=gpu._frozen_selections(tree, suffix),
        decision_clock=clock,
    )
    factor_ids = gpu.factor_order(states)
    state_values, state_available = gpu.build_state_store(states, target.calendar, factor_ids)
    old = IntradayK1InputStore.load(gpu.OLD_STORE_ROOT / tree / suffix)
    state_values[:, : len(old.calendar)] = old.state_values
    state_available[:, : len(old.calendar)] = old.state_available
    memberships = gpu.membership_for_decisions(
        core_frame, industry_ids, target.calendar, target.decision_positions
    )
    beta, reliability, available, epsilon_h = gpu.fit_post2020_exposures_gpu(
        tree=tree,
        suffix=suffix,
        history_returns=history_raw,
        decision_marks=np.load(target.root / f"decision_close_{suffix}.npy", mmap_mode="r"),
        history_basis=basis_h,
        calendar=target.calendar,
        symbols=target.symbols,
        decision_positions=target.decision_positions,
        factor_ids=tuple(factor_ids),
        industry_membership=memberships,
        device=device,
    )
    epsilon_f = np.full_like(epsilon_h, np.nan, dtype=np.float32)
    epsilon_f[: len(old.calendar), : len(old.symbols)] = old.epsilon_future
    rows, labelled = gpu.build_inference_rows(
        calendar=target.calendar,
        epsilon_history=epsilon_h,
        epsilon_future=epsilon_f,
        decision_positions=target.decision_positions,
        exposure_available=available,
    )
    store = IntradayK1InputStore(
        root=target.root,
        calendar=target.calendar,
        symbols=target.symbols,
        factor_ids=tuple(factor_ids),
        epsilon_history=epsilon_h,
        epsilon_future=epsilon_f,
        state_values=state_values,
        state_available=state_available,
        exposure_decision_positions=target.decision_positions,
        stock_factor_exposures=beta,
        exposure_reliability=reliability,
        exposure_available=available,
        inference_rows=rows,
        labelled_row_indices=labelled,
    )
    checks = gpu._prefix_store_checks(tree=tree, suffix=suffix, store=store)
    if not all(checks.values()):
        raise ValueError("post2020_annual_four_group_prefix_store_failed")
    years = np.asarray(rows[:, 2], dtype=np.int64)
    indices = np.flatnonzero(years >= 2021).astype(np.int64)
    _, scores = gpu._ensemble_seed_scores(
        store=store,
        normalizer=read_json(gpu.NORMALIZER_ROOT / suffix / "normalizer.json"),
        checkpoint_root=gpu.CHECKPOINT_ROOT / tree / suffix,
        indices=indices,
    )
    scores["decision_clock"] = clock
    return scores.sort_values(["decision_date", "symbol"], kind="mergesort", ignore_index=True), store, checks


def _fit_array_segment(
    *,
    start_prices: NDArray[np.float64],
    end_prices: NDArray[np.float64],
    store: IntradayK1InputStore,
    exposure_index: int,
) -> SegmentFit:
    returns = np.divide(
        end_prices,
        start_prices,
        out=np.full_like(end_prices, np.nan, dtype=np.float64),
        where=np.isfinite(start_prices) & np.isfinite(end_prices) & (start_prices > 0.0) & (end_prices > 0.0),
    ) - 1.0
    exposures = np.asarray(store.stock_factor_exposures[exposure_index], dtype=np.float64)
    available = np.asarray(store.exposure_available[exposure_index], dtype=bool).any(axis=1)
    returns[~available] = np.nan
    return fit_factor_segment(exposures, returns)


def _exposure_index(store: IntradayK1InputStore, day_position: int, *, before_current: bool) -> int:
    side = "left" if before_current else "right"
    index = int(np.searchsorted(store.exposure_decision_positions, day_position, side=side) - 1)
    if index < 0:
        raise ValueError("post2020_annual_four_group_exposure_missing")
    return index


def run_corrected_annual_attribution(
    *,
    score_frame: pd.DataFrame,
    target: base.ExtendedTargetSurfaces,
    store: IntradayK1InputStore,
    clock: str,
    factor_matrix: NDArray[np.float64],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    suffix = CLOCK_SUFFIX[clock]
    raw_execution = np.load(target.root / f"entry_open_{suffix}.npy", mmap_mode="r")
    raw_close = np.load(target.root / "raw_close.npy", mmap_mode="r")
    factor_start = int(np.searchsorted(target.calendar, np.datetime64("2020-01-01", "ns"), side="left"))
    decisions = {
        pd.Timestamp(day): rank_portfolio_table(group)
        for day, group in score_frame.groupby("decision_date", sort=True)
    }
    gates = base.build_tradability_maps(
        decision_dates=list(decisions),
        calendar=target.calendar,
        symbols=target.symbols,
        raw_close=raw_close,
        raw_execution=raw_execution,
        factor_matrix=factor_matrix,
        factor_start=factor_start,
    )
    symbol_index = {str(value): position for position, value in enumerate(target.symbols)}
    policy = policy_by_id(COMMON_ROOT_POLICY_ID)
    shares: dict[str, float] = {}
    cash = float(INITIAL_NAV)
    nav = float(INITIAL_NAV)
    previous_marks: dict[str, float] = {}
    group_log = {(year, group): 0.0 for year in YEARS for group in GROUPS}
    daily_returns = {year: [] for year in YEARS}
    max_identity_error = 0.0
    min_rank = 14
    max_condition = 0.0
    start = int(np.searchsorted(target.calendar, np.datetime64("2021-01-01", "ns"), side="left"))
    previous_all = (
        np.asarray(raw_close[start - 1], dtype=np.float64)
        * np.asarray(factor_matrix[start - 1 - factor_start], dtype=np.float64)
    )
    for di in range(start, len(target.calendar)):
        day = pd.Timestamp(target.calendar[di])
        year = day.year
        factor = np.asarray(factor_matrix[di - factor_start], dtype=np.float64)
        close_all = np.asarray(raw_close[di], dtype=np.float64) * factor
        execution_all = np.asarray(raw_execution[di], dtype=np.float64) * factor
        previous_nav = nav
        q0 = dict(shares)
        p0 = dict(previous_marks)
        is_rebalance = day in decisions
        pre_index = _exposure_index(store, di, before_current=is_rebalance)
        post_index = _exposure_index(store, di, before_current=False)
        full_fit = _fit_array_segment(
            start_prices=previous_all,
            end_prices=close_all,
            store=store,
            exposure_index=pre_index,
        )
        pre_fit = full_fit
        post_fit = full_fit
        if is_rebalance:
            pre_fit = _fit_array_segment(
                start_prices=previous_all,
                end_prices=execution_all,
                store=store,
                exposure_index=pre_index,
            )
            post_fit = _fit_array_segment(
                start_prices=execution_all,
                end_prices=close_all,
                store=store,
                exposure_index=post_index,
            )
        for fit in (full_fit, pre_fit, post_fit):
            min_rank = min(min_rank, fit.rank)
            max_condition = max(max_condition, fit.condition_number)
        cost = 0.0
        buy_legs: Mapping[str, float] = {}
        sell_legs: Mapping[str, float] = {}
        if is_rebalance:
            ranked = decisions[day]
            candidate_symbols = set(ranked["symbol"].astype(str)) | set(shares)
            execution_prices = {
                symbol: float(execution_all[symbol_index[symbol]])
                for symbol in candidate_symbols
                if symbol in symbol_index
                and np.isfinite(execution_all[symbol_index[symbol]])
                and execution_all[symbol_index[symbol]] > 0.0
            }
            close_prices = {
                symbol: float(close_all[symbol_index[symbol]])
                for symbol in candidate_symbols
                if symbol in symbol_index
                and np.isfinite(close_all[symbol_index[symbol]])
                and close_all[symbol_index[symbol]] > 0.0
            }
            mark_execution = {
                symbol: execution_prices.get(symbol, previous_marks.get(symbol, float("nan")))
                for symbol in shares
            }
            current_weights, _ = current_weights_from_book(shares=shares, prices=mark_execution, cash=cash)
            target_weights, forced, blocked_buy, _ = build_execution_target(
                ranked,
                policy=policy,
                previous_shares=shares,
                current_weights=current_weights,
                tradability=gates.get(day, {}),
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
            cost = float(result["cost"]) / previous_nav
            buy_legs = cast(Mapping[str, float], result["buy_legs"])
            sell_legs = cast(Mapping[str, float], result["sell_legs"])
            close_marks = cast(Mapping[str, float], result["close_mark_prices"])
        else:
            close_prices = {
                symbol: float(close_all[symbol_index[symbol]])
                for symbol in shares
                if symbol in symbol_index
                and np.isfinite(close_all[symbol_index[symbol]])
                and close_all[symbol_index[symbol]] > 0.0
            }
            nav = apply_non_rebalance_day(
                shares=shares,
                cash=cash,
                close_prices=close_prices,
                previous_mark_prices=previous_marks,
            )
            close_marks = {
                symbol: close_prices.get(symbol, previous_marks[symbol]) for symbol in shares
            }
        q1 = dict(shares)
        p1 = {symbol: float(value) for symbol, value in close_marks.items()}
        reallocated = set(buy_legs) | set(sell_legs) | {
            symbol
            for symbol in set(q0) | set(q1)
            if not np.isclose(q0.get(symbol, 0.0), q1.get(symbol, 0.0), rtol=1.0e-12, atol=1.0e-8)
        }
        simple = {group: 0.0 for group in GROUPS}

        def add_piece(
            symbol: str,
            quantity: float,
            start_price: float,
            end_price: float,
            fit: SegmentFit,
            exposure_index: int,
            nav_value: float,
            accumulator: dict[str, float],
        ) -> None:
            if quantity <= 0.0 or not (
                math.isfinite(start_price)
                and math.isfinite(end_price)
                and start_price > 0.0
                and end_price > 0.0
            ):
                return
            components = stock_factor_piece(
                symbol=symbol,
                actual_stock_return=end_price / start_price - 1.0,
                account_start_weight=quantity * start_price / nav_value,
                fit=fit,
                store=store,
                exposure_index=exposure_index,
                symbol_positions=symbol_index,
            )
            accumulator["index"] += components["index_account_contribution"]
            accumulator["size"] += components["size_account_contribution"]
            accumulator["industry"] += components["industry_account_contribution"]
            accumulator["other"] += components["other_gross_account_contribution"]

        for symbol in sorted(set(q0) | set(q1)):
            start_price = p0.get(symbol, float("nan"))
            close_price = p1.get(symbol, float("nan"))
            if symbol in reallocated:
                position = symbol_index[symbol]
                execution_price = (
                    float(execution_all[position])
                    if np.isfinite(execution_all[position]) and execution_all[position] > 0.0
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
        simple["other"] -= cost
        daily_return = nav / previous_nav - 1.0
        identity_error = abs(sum(simple.values()) - daily_return)
        max_identity_error = max(max_identity_error, identity_error)
        if identity_error > 1.0e-10:
            raise RuntimeError(f"post2020_annual_four_group_daily_identity_failed:{day.date()}:{identity_error}")
        scale = math.log1p(daily_return) / daily_return if abs(daily_return) > 1.0e-15 else 1.0
        for group in GROUPS:
            group_log[(year, group)] += simple[group] * scale
        daily_returns[year].append(daily_return)
        previous_marks.update(p1)
        previous_all = close_all
    annual_rows: list[dict[str, object]] = []
    account_rows: list[dict[str, object]] = []
    for year in YEARS:
        values = group_log[(year, "index")], group_log[(year, "size")], group_log[(year, "industry")], group_log[(year, "other")]
        net = float(sum(values))
        absolute = max(float(sum(abs(value) for value in values)), 1.0e-15)
        for group, value in zip(GROUPS, values, strict=True):
            annual_rows.append(
                {
                    "year": year,
                    "decision_clock": clock,
                    "group": group,
                    "linked_log_contribution": value,
                    "signed_contribution_rate": value / net if abs(net) > 1.0e-15 else np.nan,
                    "absolute_contribution_share": abs(value) / absolute,
                    "annual_net_log_return": net,
                    "partial_year": year == 2026,
                }
            )
        metrics = account_metrics(daily_returns[year])
        account_rows.append(
            {
                "year": year,
                "decision_clock": clock,
                **metrics,
                "trading_day_count": len(daily_returns[year]),
                "partial_year": year == 2026,
            }
        )
    diagnostics = {
        "maximum_daily_identity_error": max_identity_error,
        "minimum_factor_design_rank": min_rank,
        "maximum_factor_condition_number": max_condition,
        "annual_row_count": len(annual_rows),
        "post_2020_detail_output_rows": 0,
    }
    return pd.DataFrame(annual_rows), pd.DataFrame(account_rows), diagnostics


def _high_low(annual: pd.DataFrame) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    complete = annual.loc[annual["year"].le(2025)]
    for (clock, group), local in complete.groupby(["decision_clock", "group"], sort=True):
        high = local.sort_values(["linked_log_contribution", "year"], ascending=[False, True])
        low = local.sort_values(["linked_log_contribution", "year"], ascending=[True, True])
        rows.append(
            {
                "decision_clock": str(clock),
                "group": str(group),
                "highest_year": int(high.iloc[0]["year"]),
                "lowest_year": int(low.iloc[0]["year"]),
                "top_three_years": [int(value) for value in high.head(3)["year"]],
                "bottom_three_years": [int(value) for value in low.head(3)["year"]],
                "positive_years": [int(value) for value in local.loc[local["linked_log_contribution"] > 0.0, "year"]],
                "negative_years": [int(value) for value in local.loc[local["linked_log_contribution"] < 0.0, "year"]],
            }
        )
    return {
        "schema_id": "factorlab.reaka_current_K1_post2020_annual_four_group_high_low@1.0",
        "status": "completed",
        "complete_years": [2021, 2022, 2023, 2024, 2025],
        "partial_2026_excluded_from_high_low_ranking": True,
        "rows": rows,
        "production_authority": False,
    }


def execute_post2020_blackbox(*, tree: str, output_root: Path) -> dict[str, object]:
    if tree not in {"formal", "isolated"}:
        raise ValueError("post2020_annual_four_group_tree_invalid")
    contract = _load_contract()
    if not torch.cuda.is_available() or getattr(torch.version, "hip", None) is None:
        raise RuntimeError("post2020_annual_four_group_rocm_required")
    output_root.mkdir(parents=True, exist_ok=False)
    target, factor_matrix = gpu.load_gpu_cache(root=CACHE_ROOT, tree=tree)
    annual_parts: list[pd.DataFrame] = []
    account_parts: list[pd.DataFrame] = []
    diagnostics: dict[str, object] = {}
    inventories: list[dict[str, object]] = []
    for clock in CLOCKS:
        scores, store, checks = build_scores_and_store(
            tree=tree,
            clock=clock,
            target=target,
            device=torch.device("cuda:0"),
        )
        inventories.append(factor_input_inventory(store.factor_ids))
        annual, account, local = run_corrected_annual_attribution(
            score_frame=scores,
            target=target,
            store=store,
            clock=clock,
            factor_matrix=factor_matrix,
        )
        annual_parts.append(annual)
        account_parts.append(account)
        diagnostics[CLOCK_SUFFIX[clock]] = {"prefix_checks": checks, **local}
    if len({item["canonical_digest"] for item in inventories}) != 1:
        raise RuntimeError("post2020_annual_four_group_inventory_mismatch")
    annual_frame = pd.concat(annual_parts, ignore_index=True).sort_values(
        ["year", "decision_clock", "group"], kind="mergesort", ignore_index=True
    )
    account_frame = pd.concat(account_parts, ignore_index=True).sort_values(
        ["year", "decision_clock"], kind="mergesort", ignore_index=True
    )
    write_csv(output_root / "annual_four_group.csv", annual_frame)
    write_csv(output_root / "annual_account.csv", account_frame)
    high_low = write_json(output_root / "year_high_low.json", _high_low(annual_frame))
    result = write_json(
        output_root / "result.json",
        {
            "schema_id": "factorlab.reaka_current_K1_post2020_annual_four_group_blackbox@1.0",
            "status": "completed_corrected_annual_four_group_aggregate_only",
            "years": list(YEARS),
            "partial_endpoint": "2026-08-25",
            "decision_clocks": list(CLOCKS),
            "groups": list(GROUPS),
            "primary_slippage_multiplier": PRIMARY_SLIPPAGE,
            "factor_inventory_digest": inventories[0]["canonical_digest"],
            "high_low_digest": high_low["canonical_digest"],
            "diagnostics": diagnostics,
            "public_stock_trade_holding_daily_or_event_rows": 0,
            "next_factor_development_started": False,
            "result_backflow_allowed": False,
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    scientific = {name: file_digest(output_root / name) for name in SCIENTIFIC_FILES}
    return write_json(
        output_root / "execution_receipt.json",
        {
            "schema_id": "factorlab.reaka_current_K1_post2020_annual_four_group_execution@1.0",
            "status": "completed",
            "tree": tree,
            "backend": "ROCm_factor_exposure_plus_CPU_exact_K1_ranking_and_conservation_account",
            "contract_digest": contract["canonical_digest"],
            "result_digest": result["canonical_digest"],
            "scientific_file_digests": scientific,
            "source_digests": cast(Mapping[str, object], contract["source_closure"]),
            "cache_manifest_digest": "sha256:e9e8744c9cd014dae71e843d29e5ba3fbba403ec2cc6046f10585ac3133c4e36",
            "public_detail_rows": 0,
            "training_run": False,
            "production_authority": False,
        },
    )


__all__ = [
    "SCIENTIFIC_FILES",
    "build_scores_and_store",
    "execute_post2020_blackbox",
    "run_corrected_annual_attribution",
]
