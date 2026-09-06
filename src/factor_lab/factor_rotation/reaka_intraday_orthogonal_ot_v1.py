# pyright: reportAny=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false, reportAttributeAccessIssue=false
# pyright: reportIndexIssue=false, reportArgumentType=false
# pyright: reportReturnType=false, reportOperatorIssue=false
# pyright: reportCallIssue=false, reportGeneralTypeIssues=false
# pyright: reportUnusedCallResult=false, reportPrivateUsage=false
"""P6.2 intraday OT1--OT3 transparent orthogonal layer."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from factor_lab.factor_rotation import orthogonal_index_timing_transport_ot1_v1 as old_ot1
from factor_lab.factor_rotation.orthogonal_factor_timing_state_v1 import (
    ELIGIBLE_TOOL_IDS,
    NAKED_BASELINE_ID,
    family_naked_state,
    family_tool_state,
    pseudo_log_level,
    select_one_tool_per_family,
)
from factor_lab.factor_rotation.orthogonal_timing_stock_transport_v1 import (
    OUTPUT_COLUMNS,
    build_stock_transport,
)
from factor_lab.governance.canonicalization import canonical_digest

SCHEMA_ID: Final = "factorlab.reaka_intraday_orthogonal_OT1_OT3@1.0"
VALIDATION_SCHEMA_ID: Final = "factorlab.reaka_intraday_orthogonal_OT1_OT3_validation@1.0"
CLOCKS: Final = ("14:30", "14:45")
CLOCK_SUFFIX: Final = {"14:30": "1430", "14:45": "1445"}
LOOKBACK: Final = 120
MIN_OBSERVATIONS: Final = 96
HALF_MIN_OBSERVATIONS: Final = 40
COST_BPS: Final = 7.0
MARKET_FACTOR_ID: Final = old_ot1.MARKET_FACTOR_ID
SIZE_FACTOR_ID: Final = old_ot1.SIZE_FACTOR_ID
SMALL_TARGET_ID: Final = old_ot1.SMALL_TARGET_ID
LARGE_TARGET_ID: Final = old_ot1.LARGE_TARGET_ID

OT1_FILES: Final = (
    "factor_basis_history.parquet",
    "factor_basis_future.parquet",
    "basis_projection_receipts.parquet",
    "d5_stock_exposures.parquet",
    "d5_stock_industry_exposures.parquet",
    "exposure_decision_summary.parquet",
    "stock_residual_surfaces.npz",
    "manifest.json",
)
OT2_FILES: Final = (
    "candidate_states.parquet",
    "candidate_manifest.json",
    "selected_factor_states.parquet",
    "annual_candidate_metrics.parquet",
    "selected_family_tools.json",
    "manifest.json",
)


def json_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    """Return strict-JSON records with missing values mapped to null."""

    local = frame.astype(object).where(pd.notna(frame), None)
    return cast(list[dict[str, object]], local.to_dict(orient="records"))


OT3_FILES: Final = (
    "d5_stock_timing_transport.parquet",
    "manifest.json",
)


def _with_digest(payload: Mapping[str, object]) -> dict[str, object]:
    output = dict(payload)
    _ = output.pop("canonical_digest", None)
    output["canonical_digest"] = canonical_digest(output)
    return output


def read_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def write_json(path: Path, payload: Mapping[str, object]) -> dict[str, object]:
    output = _with_digest(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def canonical_valid(payload: Mapping[str, object]) -> bool:
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    return stored == canonical_digest(body)


def write_parquet(frame: pd.DataFrame, path: Path, sort_columns: Sequence[str]) -> None:
    local = frame.sort_values(list(sort_columns), kind="mergesort", ignore_index=True) if len(frame) else frame
    path.parent.mkdir(parents=True, exist_ok=True)
    local.to_parquet(
        path,
        index=False,
        compression="zstd",
        use_dictionary=False,
    )


def write_deterministic_npz(
    path: Path,
    arrays: Mapping[str, NDArray[np.generic]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        for name, values in sorted(arrays.items()):
            buffer = io.BytesIO()
            np.lib.format.write_array(buffer, np.asarray(values), allow_pickle=False)
            info = zipfile.ZipInfo(
                f"{name}.npy",
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(
                info,
                buffer.getvalue(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            )


def family_id(factor_id: str) -> str:
    if factor_id == MARKET_FACTOR_ID:
        return "market"
    if factor_id == SIZE_FACTOR_ID:
        return "size"
    return "industry"


def load_industry_ids(registry_path: Path) -> tuple[str, ...]:
    registry = read_json(registry_path)
    return tuple(
        sorted(
            str(item["target_id"])
            for item in cast(
                list[dict[str, object]],
                registry["accepted_research_proxies"],
            )
            if str(item["target_id"]).startswith("L1_FACTOR_CORE:")
        )
    )


def load_memberships(
    *,
    cloudridge_path: Path,
    core_path: Path,
    registry_path: Path,
    symbols: NDArray[np.str_],
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...]]:
    industries = load_industry_ids(registry_path)
    symbol_position = {str(symbol): index for index, symbol in enumerate(symbols)}
    cloudridge = pd.read_csv(
        cloudridge_path,
        usecols=["as_of_date", "effective_date", "symbol"],
        dtype={"symbol": str},
    )
    cloudridge["symbol"] = cloudridge["symbol"].str.zfill(6)
    cloudridge["symbol_position"] = cloudridge["symbol"].map(symbol_position)
    cloudridge = cloudridge.dropna(subset=["symbol_position"]).copy()
    cloudridge["symbol_position"] = cloudridge["symbol_position"].astype(np.int64)
    cloudridge = cloudridge.rename(columns={"as_of_date": "asof_date"})
    cloudridge["target_id"] = MARKET_FACTOR_ID
    core = pd.read_parquet(
        core_path,
        columns=[
            "asof_date",
            "effective_date",
            "target_id",
            "target_name",
            "symbol",
            "symbol_position",
        ],
    )
    allowed = {SMALL_TARGET_ID, LARGE_TARGET_ID, *industries}
    core = core.loc[core["target_id"].isin(allowed)].copy()
    for frame in (cloudridge, core):
        frame["asof_date"] = pd.to_datetime(frame["asof_date"], errors="raise")
        frame["effective_date"] = pd.to_datetime(frame["effective_date"], errors="raise")
        if frame["effective_date"].le(frame["asof_date"]).any():
            raise ValueError("reaka_intraday_membership_not_forward_effective")
    return cloudridge, core, industries


def _apply_projection(
    dependent: float,
    regressors: NDArray[np.float64],
    projection: old_ot1.Projection | None,
) -> float:
    if projection is None or not np.isfinite(dependent) or not np.isfinite(regressors).all():
        return np.nan
    return float(dependent - projection.intercept - regressors @ projection.coefficients)


def build_causal_basis_pair(
    history_carriers: NDArray[np.float64],
    future_carriers: NDArray[np.float64],
    calendar: NDArray[np.datetime64],
    industry_ids: Sequence[str],
    *,
    decision_clock: str,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.float64],
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    expected = 3 + len(industry_ids)
    if history_carriers.shape != future_carriers.shape:
        raise ValueError("reaka_intraday_carrier_role_shape_mismatch")
    if history_carriers.shape[2] != expected:
        raise ValueError("reaka_intraday_carrier_target_shape_mismatch")
    factor_ids = (MARKET_FACTOR_ID, SIZE_FACTOR_ID, *industry_ids)
    history_basis = np.full(
        (len(old_ot1.variant_ids()), len(calendar), len(factor_ids)),
        np.nan,
        dtype=np.float64,
    )
    future_basis = np.full_like(history_basis, np.nan)
    receipts: list[dict[str, object]] = []
    for variant_index, variant_id in enumerate(old_ot1.variant_ids()):
        market_h = history_carriers[variant_index, :, 0]
        market_f = future_carriers[variant_index, :, 0]
        small_h = history_carriers[variant_index, :, 1]
        small_f = future_carriers[variant_index, :, 1]
        large_h = history_carriers[variant_index, :, 2]
        large_f = future_carriers[variant_index, :, 2]
        history_basis[variant_index, :, 0] = market_h
        future_basis[variant_index, :, 0] = market_f
        for day in range(LOOKBACK, len(calendar)):
            history = slice(day - LOOKBACK, day)
            small_projection = old_ot1._fit_projection(
                small_h[history],
                market_h[history],
                small_h[day],
                np.asarray([market_h[day]]),
            )
            large_projection = old_ot1._fit_projection(
                large_h[history],
                market_h[history],
                large_h[day],
                np.asarray([market_h[day]]),
            )
            if small_projection is None or large_projection is None:
                continue
            history_basis[variant_index, day, 1] = small_projection.residual_current - large_projection.residual_current
            future_basis[variant_index, day, 1] = _apply_projection(
                small_f[day],
                np.asarray([market_f[day]], dtype=np.float64),
                small_projection,
            ) - _apply_projection(
                large_f[day],
                np.asarray([market_f[day]], dtype=np.float64),
                large_projection,
            )
            for leg, projection in (
                ("small_on_market", small_projection),
                ("large_on_market", large_projection),
            ):
                row = old_ot1._projection_row(
                    str(variant_id),
                    calendar,
                    day,
                    leg,
                    projection,
                    [MARKET_FACTOR_ID],
                )
                row["decision_clock"] = decision_clock
                receipts.append(row)
        size_h = history_basis[variant_index, :, 1]
        size_f = future_basis[variant_index, :, 1]
        for industry_offset, target_id in enumerate(industry_ids):
            raw_index = 3 + industry_offset
            basis_index = 2 + industry_offset
            industry_h = history_carriers[variant_index, :, raw_index]
            industry_f = future_carriers[variant_index, :, raw_index]
            for day in range(LOOKBACK, len(calendar)):
                history = slice(day - LOOKBACK, day)
                projection = old_ot1._fit_projection(
                    industry_h[history],
                    np.column_stack([market_h[history], size_h[history]]),
                    industry_h[day],
                    np.asarray([market_h[day], size_h[day]]),
                )
                if projection is None:
                    continue
                history_basis[variant_index, day, basis_index] = projection.residual_current
                future_basis[variant_index, day, basis_index] = _apply_projection(
                    industry_f[day],
                    np.asarray([market_f[day], size_f[day]], dtype=np.float64),
                    projection,
                )
                row = old_ot1._projection_row(
                    str(variant_id),
                    calendar,
                    day,
                    f"{target_id}_on_market_size",
                    projection,
                    [MARKET_FACTOR_ID, SIZE_FACTOR_ID],
                )
                row["decision_clock"] = decision_clock
                receipts.append(row)
    history_frame = basis_frame(
        history_basis,
        history_carriers,
        calendar,
        factor_ids,
        role="history",
        decision_clock=decision_clock,
    )
    future_frame = basis_frame(
        future_basis,
        future_carriers,
        calendar,
        factor_ids,
        role="future_target",
        decision_clock=decision_clock,
    )
    return (
        history_basis,
        future_basis,
        history_frame,
        future_frame,
        pd.DataFrame(receipts),
    )


def basis_frame(
    basis: NDArray[np.float64],
    raw_carriers: NDArray[np.float64],
    calendar: NDArray[np.datetime64],
    factor_ids: Sequence[str],
    *,
    role: str,
    decision_clock: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for variant_index, variant_id in enumerate(old_ot1.variant_ids()):
        for factor_index, factor_id in enumerate(factor_ids):
            if factor_index == 0:
                raw = raw_carriers[variant_index, :, 0]
            elif factor_index == 1:
                raw = raw_carriers[variant_index, :, 1] - raw_carriers[variant_index, :, 2]
            else:
                raw = raw_carriers[variant_index, :, factor_index + 1]
            values = basis[variant_index, :, factor_index]
            for day in np.flatnonzero(np.isfinite(values)):
                rows.append(
                    {
                        "decision_clock": decision_clock,
                        "return_role": role,
                        "variant_id": str(variant_id),
                        "trading_day": pd.Timestamp(calendar[day]),
                        "day_position": int(day),
                        "factor_id": str(factor_id),
                        "raw_return": float(raw[day]),
                        "orthogonal_return": float(values[day]),
                        "available": True,
                        "uses_future_in_fit": False,
                    }
                )
    return pd.DataFrame(rows)


def membership_for_decisions(
    core_membership: pd.DataFrame,
    industry_ids: Sequence[str],
    calendar: NDArray[np.datetime64],
    decision_positions: NDArray[np.int64],
) -> dict[int, dict[int, tuple[str, ...]]]:
    local = core_membership.loc[core_membership["target_id"].isin(industry_ids)].copy()
    snapshots: dict[pd.Timestamp, dict[int, tuple[str, ...]]] = {}
    for date, group in local.groupby("effective_date", sort=True):
        mapping: defaultdict[int, list[str]] = defaultdict(list)
        for row in group[["symbol_position", "target_id"]].itertuples(index=False):
            mapping[int(row.symbol_position)].append(str(row.target_id))
        snapshots[pd.Timestamp(date)] = {position: tuple(sorted(set(values))) for position, values in mapping.items()}
    dates = pd.DatetimeIndex(sorted(snapshots))
    output: dict[int, dict[int, tuple[str, ...]]] = {}
    for day in decision_positions:
        current = pd.Timestamp(calendar[day])
        index = int(dates.searchsorted(current, side="right") - 1)
        output[int(day)] = snapshots[dates[index]] if index >= 0 else {}
    return output


def fit_intraday_stock_exposures(
    *,
    history_returns: NDArray[np.float32],
    future_returns: NDArray[np.float32],
    decision_marks: NDArray[np.float32],
    history_basis: NDArray[np.float64],
    future_basis: NDArray[np.float64],
    calendar: NDArray[np.datetime64],
    symbols: NDArray[np.str_],
    decision_positions: NDArray[np.int64],
    industry_ids: Sequence[str],
    industry_membership: Mapping[int, Mapping[int, tuple[str, ...]]],
    decision_clock: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, NDArray[np.float32], NDArray[np.float32]]:
    factor_index = {factor_id: index for index, factor_id in enumerate((MARKET_FACTOR_ID, SIZE_FACTOR_ID, *industry_ids))}
    exposures: list[dict[str, object]] = []
    industry_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    epsilon_history = np.full_like(history_returns, np.nan, dtype=np.float32)
    epsilon_future = np.full_like(future_returns, np.nan, dtype=np.float32)
    folds = old_ot1.stock_fold(np.arange(len(symbols), dtype=np.int64))
    for decision_number, day in enumerate(decision_positions):
        if day < LOOKBACK:
            continue
        next_day = int(decision_positions[decision_number + 1]) if decision_number + 1 < len(decision_positions) else len(calendar)
        window = np.arange(day - LOOKBACK, day, dtype=np.int64)
        eligible = np.flatnonzero(np.isfinite(decision_marks[day]))
        memberships = industry_membership.get(int(day), {})
        groups: defaultdict[tuple[int, tuple[str, ...]], list[int]] = defaultdict(list)
        for position in eligible:
            groups[(int(folds[position]), tuple(memberships.get(int(position), ())))].append(int(position))
        available_count = 0
        reliability_values: list[float] = []
        for (fold, stock_industries), positions_list in sorted(groups.items()):
            positions = np.asarray(positions_list, dtype=np.int64)
            columns = [factor_index[MARKET_FACTOR_ID], factor_index[SIZE_FACTOR_ID]]
            columns.extend(factor_index[target_id] for target_id in stock_industries)
            factor_history = history_basis[fold + 1, window][:, columns]
            common = np.isfinite(factor_history).all(axis=1)
            design = np.column_stack([np.ones(len(window), dtype=np.float64), factor_history])
            valid_design = design[common]
            rank = int(np.linalg.matrix_rank(valid_design)) if len(valid_design) else 0
            condition = float(np.linalg.cond(valid_design)) if rank == design.shape[1] else np.inf
            coefficients_by_position: dict[int, tuple[NDArray[np.float64], int, float, float, float, float]] = {}
            if rank == design.shape[1] and np.isfinite(condition) and condition <= old_ot1.MAX_CONDITION_NUMBER:
                stock_valid = np.isfinite(history_returns[window][:, positions])
                valid_count = (stock_valid & common[:, None]).sum(axis=0)
                complete = valid_count == int(common.sum())
                if complete.any() and int(common.sum()) >= MIN_OBSERVATIONS:
                    complete_positions = positions[complete]
                    batch = old_ot1._fit_stock_batch(
                        design[common],
                        history_returns[window][:, complete_positions][common],
                        condition,
                    )
                    if batch is not None:
                        coeff, r2, stability, reliability, residual_scale = batch
                        for index, position in enumerate(complete_positions):
                            coefficients_by_position[int(position)] = (
                                coeff[:, index],
                                int(common.sum()),
                                float(r2[index]),
                                float(stability[index]),
                                float(reliability[index]),
                                float(residual_scale[index]),
                            )
                for position in positions[~complete]:
                    valid = common & np.isfinite(history_returns[window, position])
                    fitted = old_ot1._fit_stock_single(
                        design,
                        history_returns[window, position],
                        valid,
                    )
                    if fitted is not None:
                        coefficients_by_position[int(position)] = fitted
            apply_days = np.arange(day, min(next_day, len(calendar)), dtype=np.int64)
            for position in positions:
                fitted = coefficients_by_position.get(int(position))
                if fitted is None:
                    continue
                coeff, observations, r2, stability, reliability, residual_scale = fitted
                available_count += 1
                reliability_values.append(reliability)
                common_row = {
                    "decision_clock": decision_clock,
                    "asof_date": pd.Timestamp(calendar[day]),
                    "effective_date": pd.Timestamp(calendar[day]),
                    "effective_timestamp": (f"{str(calendar[day].astype('datetime64[D]'))}T{decision_clock}:00+08:00_after_bar_close"),
                    "fit_end_date": pd.Timestamp(calendar[day - 1]),
                    "symbol": str(symbols[position]),
                    "symbol_position": int(position),
                    "crossfit_fold": int(fold),
                    "intercept": float(coeff[0]),
                    "beta_market": float(coeff[1]),
                    "beta_size": float(coeff[2]),
                    "industry_exposure_count": len(stock_industries),
                    "observation_count": observations,
                    "design_rank": rank,
                    "condition_number": condition,
                    "r_squared": r2,
                    "beta_half_stability": stability,
                    "residual_scale": residual_scale,
                    "reliability": reliability,
                    "available": True,
                    "uses_future": False,
                }
                exposures.append(common_row)
                for offset, target_id in enumerate(stock_industries):
                    industry_rows.append(
                        {
                            **{
                                key: common_row[key]
                                for key in (
                                    "decision_clock",
                                    "asof_date",
                                    "effective_date",
                                    "effective_timestamp",
                                    "fit_end_date",
                                    "symbol",
                                    "symbol_position",
                                    "crossfit_fold",
                                    "reliability",
                                    "available",
                                    "uses_future",
                                )
                            },
                            "industry_factor_id": target_id,
                            "beta_industry": float(coeff[3 + offset]),
                            "family_vote_weight": 1.0 / len(stock_industries),
                        }
                    )
                if len(apply_days):
                    history_x = history_basis[fold + 1, apply_days][:, columns]
                    future_x = future_basis[fold + 1, apply_days][:, columns]
                    history_design = np.column_stack([np.ones(len(apply_days)), history_x])
                    future_design = np.column_stack([np.ones(len(apply_days)), future_x])
                    observed_h = history_returns[apply_days, position]
                    observed_f = future_returns[apply_days, position]
                    valid_h = np.isfinite(history_design).all(axis=1) & np.isfinite(observed_h)
                    valid_f = np.isfinite(future_design).all(axis=1) & np.isfinite(observed_f)
                    local_h = np.full(len(apply_days), np.nan, dtype=np.float64)
                    local_f = np.full(len(apply_days), np.nan, dtype=np.float64)
                    local_h[valid_h] = observed_h[valid_h] - history_design[valid_h] @ coeff
                    local_f[valid_f] = observed_f[valid_f] - future_design[valid_f] @ coeff
                    epsilon_history[apply_days, position] = local_h.astype(np.float32)
                    epsilon_future[apply_days, position] = local_f.astype(np.float32)
        summaries.append(
            {
                "decision_clock": decision_clock,
                "asof_date": pd.Timestamp(calendar[day]),
                "fit_end_date": pd.Timestamp(calendar[day - 1]),
                "eligible_stock_count": len(eligible),
                "available_exposure_count": available_count,
                "unavailable_exposure_count": len(eligible) - available_count,
                "coverage": available_count / len(eligible) if len(eligible) else 0.0,
                "mean_reliability": (float(np.mean(reliability_values)) if reliability_values else np.nan),
                "uses_future": False,
            }
        )
    return (
        pd.DataFrame(exposures),
        pd.DataFrame(industry_rows),
        pd.DataFrame(summaries),
        epsilon_history,
        epsilon_future,
    )


def build_candidate_states(
    history_basis: pd.DataFrame,
    *,
    decision_clock: str,
) -> pd.DataFrame:
    full = history_basis.loc[history_basis["variant_id"].eq("full_reference")]
    rows: list[pd.DataFrame] = []
    for factor_id, local in full.groupby("factor_id", sort=True):
        returns = local.set_index("trading_day")["orthogonal_return"].sort_index().astype(float)
        family = family_id(str(factor_id))
        level = pseudo_log_level(returns)
        for tool_id in (*ELIGIBLE_TOOL_IDS, NAKED_BASELINE_ID):
            state = (
                family_naked_state(returns, family) if tool_id == NAKED_BASELINE_ID else family_tool_state(level, returns, tool_id, family)
            )
            rows.append(
                pd.DataFrame(
                    {
                        "decision_clock": decision_clock,
                        "variant_id": "full_reference",
                        "decision_date": state.index,
                        "factor_id": str(factor_id),
                        "economic_family_id": family,
                        "tool_id": str(tool_id),
                        "timing_state": state.to_numpy(dtype=float),
                        "available": state.notna().to_numpy(dtype=bool),
                        "uses_forward_outcome": False,
                    }
                )
            )
    return pd.concat(rows, ignore_index=True).sort_values(
        ["economic_family_id", "factor_id", "tool_id", "decision_date"],
        kind="mergesort",
        ignore_index=True,
    )


def evaluate_annual_tools(
    *,
    candidate_states: pd.DataFrame,
    future_basis: pd.DataFrame,
    decision_dates: pd.DatetimeIndex,
    year: int,
) -> pd.DataFrame:
    target_map = {
        str(factor_id): (local.set_index("trading_day")["orthogonal_return"].sort_index().astype(float))
        for factor_id, local in future_basis.loc[future_basis["variant_id"].eq("full_reference")].groupby("factor_id", sort=True)
    }
    evaluations: list[pd.DataFrame] = []
    for (family, factor, tool), local in candidate_states.groupby(
        ["economic_family_id", "factor_id", "tool_id"],
        sort=True,
    ):
        state = local.set_index("decision_date")["timing_state"].sort_index().reindex(decision_dates)
        target = target_map[str(factor)].reindex(decision_dates)
        aligned = pd.concat(
            [state.rename("decision_state"), target.rename("factor_return")],
            axis=1,
        )
        aligned["turnover"] = aligned["decision_state"].diff().abs()
        aligned["gross"] = aligned["decision_state"] * aligned["factor_return"]
        aligned["cost"] = aligned["turnover"] * COST_BPS / 10_000.0
        aligned["net"] = aligned["gross"] - aligned["cost"]
        aligned = aligned.dropna(subset=["decision_state", "factor_return", "turnover", "net"])
        aligned = aligned.loc[aligned.index.year == year].copy()
        if aligned.empty:
            continue
        aligned["economic_family_id"] = str(family)
        aligned["factor_id"] = str(factor)
        aligned["tool_id"] = str(tool)
        aligned["decision_date"] = aligned.index
        evaluations.append(aligned.reset_index(drop=True))
    if not evaluations:
        return pd.DataFrame()
    joined = pd.concat(evaluations, ignore_index=True)
    daily = (
        joined.groupby(
            ["economic_family_id", "tool_id", "decision_date"],
            sort=True,
        )
        .agg(
            net=("net", "mean"),
            gross=("gross", "mean"),
            cost=("cost", "mean"),
            factor_count=("factor_id", "nunique"),
        )
        .reset_index()
    )
    baseline = daily.loc[
        daily["tool_id"].eq(NAKED_BASELINE_ID),
        ["economic_family_id", "decision_date", "net"],
    ].rename(columns={"net": "naked_net"})
    compared = daily.merge(
        baseline,
        on=["economic_family_id", "decision_date"],
        how="inner",
        validate="many_to_one",
    )
    rows: list[dict[str, object]] = []
    for (family, tool), local in compared.groupby(["economic_family_id", "tool_id"], sort=True):
        rows.append(
            {
                "year": year,
                "economic_family_id": str(family),
                "tool_id": str(tool),
                "observation_decisions": len(local),
                "mean_factor_count": float(local["factor_count"].mean()),
                "candidate_gross": float(local["gross"].mean()),
                "candidate_cost": float(local["cost"].mean()),
                "candidate_net": float(local["net"].mean()),
                "naked_net_same_support": float(local["naked_net"].mean()),
                "incremental_net_vs_naked": float((local["net"] - local["naked_net"]).mean()),
                "supported": len(local) >= 20,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["economic_family_id", "tool_id"],
        kind="mergesort",
        ignore_index=True,
    )


def build_selected_states(
    *,
    history_basis: pd.DataFrame,
    selections: pd.DataFrame,
    decision_clock: str,
) -> pd.DataFrame:
    selected_map = dict(
        zip(
            selections["economic_family_id"],
            selections["tool_id"],
            strict=True,
        )
    )
    rows: list[pd.DataFrame] = []
    for (variant, factor), local in history_basis.groupby(["variant_id", "factor_id"], sort=True):
        returns = local.set_index("trading_day")["orthogonal_return"].sort_index().astype(float)
        family = family_id(str(factor))
        tool = str(selected_map[family])
        state = (
            family_naked_state(returns, family)
            if tool == NAKED_BASELINE_ID
            else family_tool_state(pseudo_log_level(returns), returns, tool, family)
        )
        rows.append(
            pd.DataFrame(
                {
                    "decision_clock": decision_clock,
                    "variant_id": str(variant),
                    "decision_date": state.index,
                    "factor_id": str(factor),
                    "economic_family_id": family,
                    "selected_tool_id": tool,
                    "timing_state": state.to_numpy(dtype=float),
                    "available": state.notna().to_numpy(dtype=bool),
                    "signal_only": True,
                    "uses_forward_outcome": False,
                }
            )
        )
    return pd.concat(rows, ignore_index=True).sort_values(
        ["variant_id", "economic_family_id", "factor_id", "decision_date"],
        kind="mergesort",
        ignore_index=True,
    )


def build_intraday_transport(
    *,
    exposures: pd.DataFrame,
    industry_exposures: pd.DataFrame,
    selected_states: pd.DataFrame,
    decision_positions: NDArray[np.int64],
    calendar: NDArray[np.datetime64],
    decision_clock: str,
) -> pd.DataFrame:
    decision_dates = pd.DatetimeIndex(calendar[decision_positions])
    states = selected_states.loc[selected_states["decision_date"].isin(decision_dates)].copy()
    output = build_stock_transport(exposures, industry_exposures, states)
    output["decision_clock"] = decision_clock
    output["effective_timestamp"] = (
        pd.to_datetime(output["asof_date"]).dt.strftime("%Y-%m-%dT") + decision_clock + ":00+08:00_after_bar_close"
    )
    if output.duplicated(["decision_clock", "asof_date", "symbol"]).any():
        raise ValueError("reaka_intraday_OT3_duplicate_coordinate")
    if any(column not in output for column in OUTPUT_COLUMNS):
        raise ValueError("reaka_intraday_OT3_output_column_missing")
    if any(column in output for column in ("combined_score", "total_score", "tool_vote_sum")):
        raise ValueError("reaka_intraday_OT3_presum_forbidden")
    return output.sort_values(["asof_date", "symbol"], kind="mergesort", ignore_index=True)


def validate_contract(payload: Mapping[str, object]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema_id") != SCHEMA_ID:
        blockers.append("intraday_OT_contract_schema_invalid")
    if not canonical_valid(payload):
        blockers.append("intraday_OT_contract_digest_invalid")
    if payload.get("decision_clocks") != list(CLOCKS):
        blockers.append("intraday_OT_clock_identity_invalid")
    if payload.get("fit_end") != "strict_t_minus_1":
        blockers.append("intraday_OT_fit_end_not_t_minus_1")
    if payload.get("model_training_allowed") is not False:
        blockers.append("intraday_OT_training_must_be_closed")
    if payload.get("account_execution_allowed") is not False:
        blockers.append("intraday_OT_account_must_be_closed")
    return blockers


__all__ = [
    "CLOCKS",
    "CLOCK_SUFFIX",
    "COST_BPS",
    "ELIGIBLE_TOOL_IDS",
    "LOOKBACK",
    "MARKET_FACTOR_ID",
    "MIN_OBSERVATIONS",
    "NAKED_BASELINE_ID",
    "OT1_FILES",
    "OT2_FILES",
    "OT3_FILES",
    "OUTPUT_COLUMNS",
    "SCHEMA_ID",
    "SIZE_FACTOR_ID",
    "VALIDATION_SCHEMA_ID",
    "basis_frame",
    "build_candidate_states",
    "build_causal_basis_pair",
    "build_intraday_transport",
    "build_selected_states",
    "canonical_valid",
    "evaluate_annual_tools",
    "family_id",
    "file_digest",
    "fit_intraday_stock_exposures",
    "load_industry_ids",
    "load_memberships",
    "json_records",
    "membership_for_decisions",
    "read_json",
    "select_one_tool_per_family",
    "validate_contract",
    "write_deterministic_npz",
    "write_json",
    "write_parquet",
]
