# pyright: reportAny=false
# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportMissingImports=false
# pyright: reportMissingTypeStubs=false
# pyright: reportOperatorIssue=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnusedCallResult=false
"""GPU-first append-only OT/K1 core for the current REAKA blackbox."""

from __future__ import annotations

import math
import time
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import numpy as np
import pandas as pd
import torch
from numpy.typing import NDArray
from scripts.factor_rotation.build_reaka_intraday_portfolio_mapping_inputs_v1 import (
    FIXED_K1_CONFIG,
    _ensemble_seed_scores,
    _rankz_by_decision,
)

from factor_lab.factor_rotation import orthogonal_index_timing_transport_ot1_v1 as old_ot1
from factor_lab.factor_rotation.reaka_current_generation_aggregate_blackbox_v1 import (
    CHECKPOINT_ROOT,
    EXTENSION_ROOT,
    FACTOR_REGISTRY,
    NORMALIZER_ROOT,
    OLD_STORE_ROOT,
    ExtendedTargetSurfaces,
    _append_only_cloudridge_path,
    _frozen_selections,
    _prefix_store_checks,
    blackbox_plan,
    build_adjustment_factor_matrix,
    build_extended_target_surfaces,
    build_tradability_maps,
    canonical_valid,
    file_digest,
    run_account_aggregate,
    write_json,
)
from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    IntradayK1InputStore,
    build_inference_rows,
    build_state_store,
    factor_order,
    normalize_batch,
    read_json,
)
from factor_lab.factor_rotation.reaka_intraday_k1_training_v1 import (
    SEEDS_FORMAL,
    build_model,
    load_state_tree,
)
from factor_lab.factor_rotation.reaka_intraday_orthogonal_ot_v1 import (
    LARGE_TARGET_ID,
    MARKET_FACTOR_ID,
    SMALL_TARGET_ID,
    basis_frame,
    build_selected_states,
    load_memberships,
    membership_for_decisions,
)
from factor_lab.factor_rotation.reaka_intraday_portfolio_mapping_v1 import (
    CLOCK_SUFFIX,
)
from factor_lab.factor_rotation.reaka_intraday_target_fill_v1 import (
    _h20_surfaces,
)

GPU_BATCH_SIZE: Final = 65_536
ROOT: Final = Path(__file__).resolve().parents[3]
CACHE_SCHEMA_ID: Final = "factorlab.reaka_current_generation_blackbox_gpu_cache@2.0"
CONTRACT_RELATIVE: Final = Path(
    "docs/ops/reaka_current_generation_aggregate_blackbox_gpu@2.1.json"
)
SOURCE_FILES: Final[tuple[str, ...]] = (
    "AGENTS.md",
    "ai-readme.md",
    ".codex/skills/strategy-slice-rebuild/SKILL.md",
    ".codex/skills/strategy-slice-rebuild/references/project-contract.md",
    "docs/ops/factorlab_gpu_runtime_whitepaper.md",
    "docs/user/factorlab_gpu_acceleration_workflow.md",
    "docs/ops/reaka_current_generation_aggregate_blackbox_whitepaper.md",
    "docs/user/reaka_current_generation_aggregate_blackbox_workflow.md",
    "src/factor_lab/factor_rotation/reaka_current_generation_aggregate_blackbox_v1.py",
    "src/factor_lab/factor_rotation/reaka_current_generation_aggregate_blackbox_gpu_v2.py",
    "scripts/factor_rotation/materialize_reaka_current_generation_blackbox_gpu_cache_v2.py",
    "scripts/factor_rotation/run_reaka_current_generation_aggregate_blackbox_gpu_v2.py",
    "scripts/factor_rotation/validate_reaka_current_generation_aggregate_blackbox_gpu_v2.py",
    "tests/unit/test_reaka_current_generation_aggregate_blackbox_gpu_v2.py",
)


def _solver_dtype(device: torch.device) -> torch.dtype:
    return torch.float64


@dataclass(frozen=True, slots=True)
class ExposureBatchJob:
    decision_number: int
    fold: int
    columns: tuple[int, ...]
    positions: NDArray[np.int64]
    apply_days: NDArray[np.int64]
    design: NDArray[np.float64]
    dependent: NDArray[np.float64]
    condition_number: float


def _rolling_projection_gpu(
    *,
    dependent_history: NDArray[np.float64],
    regressor_history: NDArray[np.float64],
    dependent_future: NDArray[np.float64],
    regressor_future: NDArray[np.float64],
    device: torch.device,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    dtype = _solver_dtype(device)
    y = torch.from_numpy(np.ascontiguousarray(dependent_history)).to(device, dtype=dtype)
    x_np = np.asarray(regressor_history, dtype=np.float64)
    if x_np.ndim == 1:
        x_np = x_np[:, None]
    x = torch.from_numpy(np.ascontiguousarray(x_np)).to(device, dtype=dtype)
    yf = torch.from_numpy(np.ascontiguousarray(dependent_future)).to(device, dtype=dtype)
    xf_np = np.asarray(regressor_future, dtype=np.float64)
    if xf_np.ndim == 1:
        xf_np = xf_np[:, None]
    xf = torch.from_numpy(np.ascontiguousarray(xf_np)).to(device, dtype=dtype)
    lookback = old_ot1.LOOKBACK
    windows = len(y) - lookback
    output_h = torch.full_like(y, torch.nan)
    output_f = torch.full_like(yf, torch.nan)
    if windows <= 0:
        return output_h.cpu().numpy(), output_f.cpu().numpy()
    yw = y.unfold(0, lookback, 1)[:windows]
    xw = x.unfold(0, lookback, 1)[:windows].permute(0, 2, 1)
    valid_rows = torch.isfinite(yw) & torch.isfinite(xw).all(dim=2)
    design = torch.cat(
        [torch.ones((*xw.shape[:2], 1), dtype=dtype, device=device), xw],
        dim=2,
    )
    design = torch.where(valid_rows[:, :, None], design, 0.0)
    target = torch.where(valid_rows, yw, 0.0)[:, :, None]
    singular = torch.linalg.svdvals(design)
    smallest = singular[:, -1]
    tiny = 1.0e-30 if dtype == torch.float32 else 1.0e-300
    condition = singular[:, 0] / torch.clamp(smallest, min=tiny)
    current_y = y[lookback:]
    current_x = x[lookback:]
    admitted = (
        (valid_rows.sum(dim=1) >= old_ot1.MIN_OBSERVATIONS)
        & torch.isfinite(current_y)
        & torch.isfinite(current_x).all(dim=1)
        & torch.isfinite(condition)
        & (condition <= old_ot1.MAX_CONDITION_NUMBER)
        & (smallest > 0.0)
    )
    safe_design = design.clone()
    safe_target = target.clone()
    rejected = torch.nonzero(~admitted, as_tuple=False).flatten()
    if len(rejected):
        safe_design[rejected] = 0.0
        safe_target[rejected] = 0.0
        parameter_count = safe_design.shape[2]
        identity = torch.eye(parameter_count, dtype=dtype, device=device)
        safe_design[rejected[:, None], torch.arange(parameter_count, device=device), :] = identity
    coefficients = torch.linalg.lstsq(safe_design, safe_target, driver="gels").solution.squeeze(2)
    current_design = torch.cat(
        [torch.ones((windows, 1), dtype=dtype, device=device), current_x], dim=1
    )
    future_design = torch.cat(
        [torch.ones((windows, 1), dtype=dtype, device=device), xf[lookback:]], dim=1
    )
    residual_h = current_y - torch.sum(current_design * coefficients, dim=1)
    residual_f = yf[lookback:] - torch.sum(future_design * coefficients, dim=1)
    valid_future = admitted & torch.isfinite(yf[lookback:]) & torch.isfinite(xf[lookback:]).all(dim=1)
    output_h[lookback:] = torch.where(admitted, residual_h, torch.nan)
    output_f[lookback:] = torch.where(valid_future, residual_f, torch.nan)
    return output_h.cpu().numpy(), output_f.cpu().numpy()


def build_causal_basis_pair_gpu(
    *,
    history_carriers: NDArray[np.float64],
    future_carriers: NDArray[np.float64],
    calendar: NDArray[np.datetime64],
    industry_ids: tuple[str, ...],
    decision_clock: str,
    device: torch.device,
) -> tuple[NDArray[np.float64], NDArray[np.float64], pd.DataFrame]:
    factor_ids = (MARKET_FACTOR_ID, old_ot1.SIZE_FACTOR_ID, *industry_ids)
    basis_h = np.full(
        (history_carriers.shape[0], history_carriers.shape[1], len(factor_ids)),
        np.nan,
        dtype=np.float64,
    )
    basis_f = np.full_like(basis_h, np.nan)
    for variant in range(history_carriers.shape[0]):
        market_h = history_carriers[variant, :, 0]
        market_f = future_carriers[variant, :, 0]
        basis_h[variant, :, 0] = market_h
        basis_f[variant, :, 0] = market_f
        small_h, small_f = _rolling_projection_gpu(
            dependent_history=history_carriers[variant, :, 1],
            regressor_history=market_h,
            dependent_future=future_carriers[variant, :, 1],
            regressor_future=market_f,
            device=device,
        )
        large_h, large_f = _rolling_projection_gpu(
            dependent_history=history_carriers[variant, :, 2],
            regressor_history=market_h,
            dependent_future=future_carriers[variant, :, 2],
            regressor_future=market_f,
            device=device,
        )
        size_h = small_h - large_h
        size_f = small_f - large_f
        basis_h[variant, :, 1] = size_h
        basis_f[variant, :, 1] = size_f
        regressors_h = np.column_stack([market_h, size_h])
        regressors_f = np.column_stack([market_f, size_f])
        for offset, _ in enumerate(industry_ids):
            industry_h, industry_f = _rolling_projection_gpu(
                dependent_history=history_carriers[variant, :, 3 + offset],
                regressor_history=regressors_h,
                dependent_future=future_carriers[variant, :, 3 + offset],
                regressor_future=regressors_f,
                device=device,
            )
            basis_h[variant, :, 2 + offset] = industry_h
            basis_f[variant, :, 2 + offset] = industry_f
    history_frame = basis_frame(
        basis_h,
        history_carriers,
        calendar,
        factor_ids,
        role="history",
        decision_clock=decision_clock,
    )
    return basis_h, basis_f, history_frame


def solve_complete_group_torch(
    design: NDArray[np.float64],
    dependent: NDArray[np.float64],
    *,
    condition_number: float,
    device: torch.device,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
] | None:
    if (
        len(design) < old_ot1.MIN_OBSERVATIONS
        or dependent.ndim != 2
        or dependent.shape[0] != len(design)
    ):
        return None
    split = len(design) // 2
    if split < old_ot1.HALF_MIN_OBSERVATIONS or len(design) - split < old_ot1.HALF_MIN_OBSERVATIONS:
        return None
    dtype = _solver_dtype(device)
    x = torch.from_numpy(np.ascontiguousarray(design)).to(device=device, dtype=dtype)
    y = torch.from_numpy(np.ascontiguousarray(dependent)).to(device=device, dtype=dtype)
    coefficients = torch.linalg.lstsq(x, y, driver="gels").solution
    residual = y - x @ coefficients
    centered = y - torch.mean(y, dim=0, keepdim=True)
    total_ss = torch.sum(centered * centered, dim=0)
    residual_ss = torch.sum(residual * residual, dim=0)
    r_squared = torch.where(total_ss > 0.0, (total_ss - residual_ss) / total_ss, 0.0)
    first = torch.linalg.lstsq(x[:split], y[:split], driver="gels").solution
    second = torch.linalg.lstsq(x[split:], y[split:], driver="gels").solution
    denominator = torch.clamp(torch.linalg.vector_norm(coefficients[1:], dim=0), min=1.0e-6)
    drift = torch.linalg.vector_norm(first[1:] - second[1:], dim=0) / denominator
    stability = 1.0 / (1.0 + drift)
    coverage = min(len(design) / old_ot1.LOOKBACK, 1.0)
    condition_reliability = 1.0 / (
        1.0 + max(math.log10(max(condition_number, 1.0)), 0.0)
    )
    reliability = torch.minimum(
        torch.minimum(torch.full_like(stability, coverage), stability),
        torch.full_like(stability, condition_reliability),
    )
    residual_scale = torch.std(residual, dim=0, correction=0)
    return (
        coefficients.detach().cpu().numpy().astype(np.float64, copy=False),
        r_squared.detach().cpu().numpy().astype(np.float64, copy=False),
        stability.detach().cpu().numpy().astype(np.float64, copy=False),
        reliability.detach().cpu().numpy().astype(np.float64, copy=False),
        residual_scale.detach().cpu().numpy().astype(np.float64, copy=False),
    )


def solve_exposure_jobs_batched(
    jobs: list[ExposureBatchJob],
    *,
    device: torch.device,
    maximum_batch_jobs: int = 64,
) -> list[tuple[ExposureBatchJob, NDArray[np.float64], NDArray[np.float64]]]:
    buckets: defaultdict[tuple[int, int, int], list[ExposureBatchJob]] = defaultdict(list)
    for job in jobs:
        width = int(2 ** math.ceil(math.log2(max(len(job.positions), 1))))
        buckets[(len(job.design), job.design.shape[1], width)].append(job)
    output: list[tuple[ExposureBatchJob, NDArray[np.float64], NDArray[np.float64]]] = []
    for (observations, _parameters, width), local_jobs in sorted(buckets.items()):
        for start in range(0, len(local_jobs), maximum_batch_jobs):
            batch = local_jobs[start : start + maximum_batch_jobs]
            design = np.stack([job.design for job in batch]).astype(np.float64, copy=False)
            dependent = np.zeros((len(batch), observations, width), dtype=np.float64)
            for position, job in enumerate(batch):
                dependent[position, :, : len(job.positions)] = job.dependent
            dtype = _solver_dtype(device)
            x = torch.from_numpy(np.ascontiguousarray(design)).to(device, dtype=dtype)
            y = torch.from_numpy(np.ascontiguousarray(dependent)).to(device, dtype=dtype)
            coefficients = torch.linalg.lstsq(x, y, driver="gels").solution
            split = observations // 2
            first = torch.linalg.lstsq(x[:, :split], y[:, :split], driver="gels").solution
            second = torch.linalg.lstsq(x[:, split:], y[:, split:], driver="gels").solution
            denominator = torch.clamp(
                torch.linalg.vector_norm(coefficients[:, 1:], dim=1), min=1.0e-6
            )
            drift = torch.linalg.vector_norm(first[:, 1:] - second[:, 1:], dim=1) / denominator
            stability = 1.0 / (1.0 + drift)
            coverage = min(observations / old_ot1.LOOKBACK, 1.0)
            condition_values = torch.tensor(
                [job.condition_number for job in batch], dtype=dtype, device=device
            )
            condition_reliability = 1.0 / (
                1.0 + torch.clamp(torch.log10(torch.clamp(condition_values, min=1.0)), min=0.0)
            )
            reliability = torch.minimum(
                torch.minimum(torch.full_like(stability, coverage), stability),
                condition_reliability[:, None],
            )
            coeff_cpu = coefficients.detach().cpu().numpy()
            reliability_cpu = reliability.detach().cpu().numpy()
            for position, job in enumerate(batch):
                count = len(job.positions)
                output.append(
                    (
                        job,
                        coeff_cpu[position, :, :count].astype(np.float64, copy=False),
                        reliability_cpu[position, :count].astype(np.float64, copy=False),
                    )
                )
    return output


def fit_post2020_exposures_gpu(
    *,
    tree: str,
    suffix: str,
    history_returns: NDArray[np.float32],
    decision_marks: NDArray[np.float32],
    history_basis: NDArray[np.float64],
    calendar: NDArray[np.datetime64],
    symbols: NDArray[np.str_],
    decision_positions: NDArray[np.int64],
    factor_ids: tuple[str, ...],
    industry_membership: Mapping[int, Mapping[int, tuple[str, ...]]],
    device: torch.device,
) -> tuple[
    NDArray[np.float32],
    NDArray[np.float32],
    NDArray[np.uint8],
    NDArray[np.float32],
]:
    old = IntradayK1InputStore.load(OLD_STORE_ROOT / tree / suffix)
    shape = (len(decision_positions), len(symbols), len(factor_ids))
    beta = np.zeros(shape, dtype=np.float32)
    reliability = np.zeros(shape, dtype=np.float32)
    available = np.zeros(shape, dtype=np.uint8)
    epsilon = np.full(history_returns.shape, np.nan, dtype=np.float32)
    old_days = len(old.calendar)
    old_symbols = len(old.symbols)
    old_decisions = len(old.exposure_decision_positions)
    beta[:old_decisions, :old_symbols] = old.stock_factor_exposures
    reliability[:old_decisions, :old_symbols] = old.exposure_reliability
    available[:old_decisions, :old_symbols] = old.exposure_available
    epsilon[:old_days, :old_symbols] = old.epsilon_history
    factor_index = {value: index for index, value in enumerate(factor_ids)}
    folds = old_ot1.stock_fold(np.arange(len(symbols), dtype=np.int64))
    complete_jobs: list[ExposureBatchJob] = []

    def apply_coefficients(
        *,
        decision_number: int,
        fold: int,
        columns: tuple[int, ...],
        positions: NDArray[np.int64],
        apply_days: NDArray[np.int64],
        coefficients: NDArray[np.float64],
        reliability_values: NDArray[np.float64],
    ) -> None:
        beta[decision_number][np.ix_(positions, np.asarray(columns))] = coefficients[1:].T.astype(
            np.float32
        )
        reliability[decision_number][np.ix_(positions, np.asarray(columns))] = np.broadcast_to(
            reliability_values[:, None], (len(positions), len(columns))
        ).astype(np.float32)
        available[decision_number][np.ix_(positions, np.asarray(columns))] = 1
        apply_x = history_basis[fold + 1, apply_days][:, columns]
        apply_design = np.column_stack([np.ones(len(apply_days)), apply_x])
        observed = history_returns[np.ix_(apply_days, positions)]
        predicted = apply_design @ coefficients
        valid_apply = np.isfinite(apply_design).all(axis=1)[:, None] & np.isfinite(observed)
        values = np.where(valid_apply, observed - predicted, np.nan)
        epsilon[np.ix_(apply_days, positions)] = values.astype(np.float32)

    for decision_number, day in enumerate(decision_positions):
        if calendar[day] < np.datetime64("2021-01-01", "ns"):
            continue
        if day < old_ot1.LOOKBACK:
            continue
        next_day = (
            int(decision_positions[decision_number + 1])
            if decision_number + 1 < len(decision_positions)
            else len(calendar)
        )
        window = np.arange(day - old_ot1.LOOKBACK, day, dtype=np.int64)
        eligible = np.flatnonzero(np.isfinite(decision_marks[day]))
        memberships = industry_membership.get(int(day), {})
        groups: defaultdict[tuple[int, tuple[str, ...]], list[int]] = defaultdict(list)
        for position in eligible:
            groups[(int(folds[position]), tuple(memberships.get(int(position), ())))].append(
                int(position)
            )
        for (fold, stock_industries), positions_list in sorted(groups.items()):
            positions = np.asarray(positions_list, dtype=np.int64)
            columns = [factor_index[MARKET_FACTOR_ID], factor_index[old_ot1.SIZE_FACTOR_ID]]
            columns.extend(factor_index[value] for value in stock_industries)
            x = history_basis[fold + 1, window][:, columns]
            common = np.isfinite(x).all(axis=1)
            design = np.column_stack([np.ones(len(window), dtype=np.float64), x])
            design_valid = design[common]
            rank = int(np.linalg.matrix_rank(design_valid)) if len(design_valid) else 0
            condition = (
                float(np.linalg.cond(design_valid))
                if rank == design.shape[1]
                else np.inf
            )
            if (
                rank != design.shape[1]
                or not np.isfinite(condition)
                or condition > old_ot1.MAX_CONDITION_NUMBER
            ):
                continue
            stock_valid = np.isfinite(history_returns[window][:, positions])
            valid_count = (stock_valid & common[:, None]).sum(axis=0)
            complete = valid_count == int(common.sum())
            if complete.any() and int(common.sum()) >= old_ot1.MIN_OBSERVATIONS:
                complete_positions = positions[complete]
                complete_jobs.append(
                    ExposureBatchJob(
                        decision_number=decision_number,
                        fold=fold,
                        columns=tuple(columns),
                        positions=complete_positions,
                        apply_days=np.arange(day, min(next_day, len(calendar)), dtype=np.int64),
                        design=design_valid,
                        dependent=history_returns[window][:, complete_positions][common].astype(
                            np.float64
                        ),
                        condition_number=condition,
                    )
                )
            for position in positions[~complete]:
                valid = common & np.isfinite(history_returns[window, position])
                local = old_ot1._fit_stock_single(design, history_returns[window, position], valid)
                if local is not None:
                    coefficients, _, _, _, value, _ = local
                    apply_coefficients(
                        decision_number=decision_number,
                        fold=fold,
                        columns=tuple(columns),
                        positions=np.asarray([position], dtype=np.int64),
                        apply_days=np.arange(day, min(next_day, len(calendar)), dtype=np.int64),
                        coefficients=coefficients[:, None],
                        reliability_values=np.asarray([value], dtype=np.float64),
                    )
    for job, coefficients, values in solve_exposure_jobs_batched(
        complete_jobs, device=device
    ):
        apply_coefficients(
            decision_number=job.decision_number,
            fold=job.fold,
            columns=job.columns,
            positions=job.positions,
            apply_days=job.apply_days,
            coefficients=coefficients,
            reliability_values=values,
        )
    return beta, reliability, available, epsilon


def ensemble_seed_scores_gpu(
    *,
    store: IntradayK1InputStore,
    normalizer: Mapping[str, object],
    checkpoint_root: Path,
    indices: NDArray[np.int64],
    device: torch.device,
    batch_size: int = GPU_BATCH_SIZE,
) -> pd.DataFrame:
    rows = np.asarray(store.inference_rows[indices], dtype=np.int64)
    decision_days = rows[:, 0]
    rank_parts: list[NDArray[np.float64]] = []
    for seed in SEEDS_FORMAL:
        model = build_model(FIXED_K1_CONFIG, seed=seed).to(device).eval()
        load_state_tree(model, checkpoint_root / f"checkpoints/seed_{seed}")
        scores = np.empty(len(indices), dtype=np.float64)
        with torch.no_grad():
            for start in range(0, len(indices), batch_size):
                take = indices[start : start + batch_size]
                historical, features = store.assemble_inputs(take)
                returns, normalized = normalize_batch(historical, features, normalizer)
                forecast = model.forecast(
                    torch.from_numpy(returns).to(device, non_blocking=False),
                    torch.from_numpy(normalized).to(device, non_blocking=False),
                )
                scores[start : start + len(take)] = (
                    forecast.scores.detach().cpu().numpy().astype(np.float64)
                )
        rank_parts.append(_rankz_by_decision(scores, decision_days))
    ensemble = np.mean(np.vstack(rank_parts), axis=0)
    return pd.DataFrame(
        {
            "symbol": store.symbols[rows[:, 1]].astype(str),
            "decision_position": decision_days,
            "decision_date": pd.to_datetime(store.calendar[decision_days]).normalize(),
            "score": ensemble,
        }
    )


def build_current_scores_gpu(
    *,
    tree: str,
    clock: str,
    target: ExtendedTargetSurfaces,
    device: torch.device,
) -> tuple[pd.DataFrame, dict[str, bool]]:
    suffix = CLOCK_SUFFIX[clock]
    history_raw, future_raw = _h20_surfaces(
        np.load(target.root / f"decision_close_{suffix}.npy", mmap_mode="r"),
        np.load(target.root / f"entry_open_{suffix}.npy", mmap_mode="r"),
    )
    cloudridge = _append_only_cloudridge_path(tree=tree, target_root=target.root)
    core = EXTENSION_ROOT / tree / "condensation/extended_weekly_membership.parquet"
    cloudridge_frame, core_frame, industry_ids = load_memberships(
        cloudridge_path=cloudridge,
        core_path=core,
        registry_path=FACTOR_REGISTRY,
        symbols=target.symbols,
    )
    market_h, _ = old_ot1.materialize_equal_weight_carriers(
        history_raw, target.calendar, cloudridge_frame, [MARKET_FACTOR_ID], minimum_members=12
    )
    market_f, _ = old_ot1.materialize_equal_weight_carriers(
        future_raw, target.calendar, cloudridge_frame, [MARKET_FACTOR_ID], minimum_members=12
    )
    target_order = [SMALL_TARGET_ID, LARGE_TARGET_ID, *industry_ids]
    core_h, _ = old_ot1.materialize_equal_weight_carriers(
        history_raw, target.calendar, core_frame, target_order, minimum_members=5
    )
    core_f, _ = old_ot1.materialize_equal_weight_carriers(
        future_raw, target.calendar, core_frame, target_order, minimum_members=5
    )
    raw_h = np.concatenate([market_h, core_h], axis=2)
    raw_f = np.concatenate([market_f, core_f], axis=2)
    basis_h, _, basis_history = build_causal_basis_pair_gpu(
        history_carriers=raw_h,
        future_carriers=raw_f,
        calendar=target.calendar,
        industry_ids=industry_ids,
        decision_clock=clock,
        device=device,
    )
    states = build_selected_states(
        history_basis=basis_history,
        selections=_frozen_selections(tree, suffix),
        decision_clock=clock,
    )
    factor_ids = factor_order(states)
    state_values, state_available = build_state_store(states, target.calendar, factor_ids)
    old = IntradayK1InputStore.load(OLD_STORE_ROOT / tree / suffix)
    state_values[:, : len(old.calendar)] = old.state_values
    state_available[:, : len(old.calendar)] = old.state_available
    memberships = membership_for_decisions(
        core_frame, industry_ids, target.calendar, target.decision_positions
    )
    beta, reliability, available, epsilon_h = fit_post2020_exposures_gpu(
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
    rows, labelled = build_inference_rows(
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
    checks = _prefix_store_checks(tree=tree, suffix=suffix, store=store)
    if not all(checks.values()):
        raise ValueError(
            f"reaka_blackbox_gpu_store_prefix_failed:{clock}:"
            + ",".join(key for key, value in checks.items() if not value)
        )
    years = np.asarray(rows[:, 2], dtype=np.int64)
    indices = np.flatnonzero(years >= 2021).astype(np.int64)
    _, frame = _ensemble_seed_scores(
        store=store,
        normalizer=read_json(NORMALIZER_ROOT / suffix / "normalizer.json"),
        checkpoint_root=CHECKPOINT_ROOT / tree / suffix,
        indices=indices,
    )
    frame["decision_clock"] = clock
    return frame.sort_values(
        ["decision_date", "symbol"], kind="mergesort", ignore_index=True
    ), checks


def source_closure() -> dict[str, str]:
    return {
        relative: file_digest(ROOT / relative)
        for relative in SOURCE_FILES
    }


def materialize_gpu_cache(
    *,
    output_root: Path,
    workers: int,
) -> dict[str, object]:
    if output_root.exists():
        raise FileExistsError(output_root)
    started = time.perf_counter()
    target = build_extended_target_surfaces(
        tree="formal",
        output_root=output_root,
        workers=workers,
    )
    factor_matrix = build_adjustment_factor_matrix(
        calendar=target.calendar,
        symbols=target.symbols,
    )
    np.save(output_root / "hfq_factor_matrix_from_2020.npy", factor_matrix, allow_pickle=False)
    scientific = {
        path.name: file_digest(path)
        for path in sorted(output_root.iterdir())
        if path.is_file() and path.name != "cache_manifest.json"
    }
    return write_json(
        output_root / "cache_manifest.json",
        {
            "schema_id": CACHE_SCHEMA_ID,
            "status": "materialized_candidate_independent_causal_coordinate_cache",
            "calendar_start": str(target.calendar[0]),
            "calendar_end": str(target.calendar[-1]),
            "calendar_days": len(target.calendar),
            "symbol_count": len(target.symbols),
            "decision_count": len(target.decision_positions),
            "prefix_checks": target.prefix_checks,
            "artifact_digests": scientific,
            "elapsed_seconds": time.perf_counter() - started,
            "score_or_account_result_created": False,
            "production_authority": False,
        },
    )


def load_gpu_cache(*, root: Path, tree: str) -> tuple[ExtendedTargetSurfaces, NDArray[np.float64]]:
    manifest = read_json(root / "cache_manifest.json")
    if not canonical_valid(manifest) or manifest.get("schema_id") != CACHE_SCHEMA_ID:
        raise ValueError("reaka_blackbox_gpu_cache_manifest_invalid")
    digests = cast(Mapping[str, str], manifest["artifact_digests"])
    if any(file_digest(root / name) != digest for name, digest in digests.items()):
        raise ValueError("reaka_blackbox_gpu_cache_artifact_drift")
    prefix = cast(dict[str, bool], manifest["prefix_checks"])
    if not prefix or not all(prefix.values()):
        raise ValueError("reaka_blackbox_gpu_cache_prefix_failed")
    target = ExtendedTargetSurfaces(
        tree=tree,
        root=root,
        calendar=np.load(root / "calendar.npy", mmap_mode="r"),
        symbols=np.load(root / "symbols.npy", mmap_mode="r").astype(str),
        decision_positions=np.load(root / "decision_positions.npy", mmap_mode="r"),
        prefix_checks=prefix,
    )
    factors = np.load(root / "hfq_factor_matrix_from_2020.npy", mmap_mode="r")
    return target, factors


def load_contract() -> dict[str, object]:
    payload = read_json(ROOT / CONTRACT_RELATIVE)
    if not canonical_valid(payload):
        raise ValueError("reaka_blackbox_gpu_contract_digest_invalid")
    if payload.get("status") != "frozen_gpu_execution_open":
        raise ValueError("reaka_blackbox_gpu_contract_not_open")
    if payload.get("source_closure") != source_closure():
        raise ValueError("reaka_blackbox_gpu_source_closure_drift")
    return payload


def execute_tree_gpu(
    *,
    tree: str,
    cache_root: Path,
    output_root: Path,
) -> dict[str, object]:
    if output_root.exists():
        raise FileExistsError(output_root)
    contract = load_contract()
    plan = blackbox_plan()
    if not torch.cuda.is_available() or getattr(torch.version, "hip", None) is None:
        raise RuntimeError("reaka_blackbox_gpu_rocm_not_available")
    device = torch.device("cuda:0")
    target, factors = load_gpu_cache(root=cache_root, tree=tree)
    started = time.perf_counter()
    accounts: list[dict[str, object]] = []
    checks: dict[str, dict[str, bool]] = {}
    decision_counts: list[int] = []
    for clock in ("14:30", "14:45"):
        scores, clock_checks = build_current_scores_gpu(
            tree=tree,
            clock=clock,
            target=target,
            device=device,
        )
        checks[clock] = clock_checks
        decision_counts.append(int(scores["decision_date"].nunique()))
        suffix = CLOCK_SUFFIX[clock]
        raw_execution = np.load(target.root / f"entry_open_{suffix}.npy", mmap_mode="r")
        raw_close = np.load(target.root / "raw_close.npy", mmap_mode="r")
        factor_start = int(
            np.searchsorted(target.calendar, np.datetime64("2020-01-01", "ns"), side="left")
        )
        gates = build_tradability_maps(
            decision_dates=[pd.Timestamp(value) for value in scores["decision_date"].unique()],
            calendar=target.calendar,
            symbols=target.symbols,
            raw_close=raw_close,
            raw_execution=raw_execution,
            factor_matrix=factors,
            factor_start=factor_start,
        )
        for multiplier in (1.0, 2.0, 3.0):
            accounts.append(
                run_account_aggregate(
                    score_frame=scores,
                    target=target,
                    clock=clock,
                    factor_matrix=factors,
                    slippage_multiplier=multiplier,
                    tradability_maps=gates,
                    raw_close_override=raw_close,
                )
            )
    torch.cuda.synchronize()
    result = write_json(
        output_root / "aggregate_result.json",
        {
            "schema_id": "factorlab.reaka_current_generation_aggregate_blackbox_result@1.0",
            "query_id": plan.query_id,
            "candidate_fingerprint": plan.candidate_fingerprint,
            "evidence_role": plan.evidence_role,
            "detail_state_before": plan.detail_state_before,
            "detail_state_after": plan.detail_state_before,
            "aggregate_answer_state_before": "aggregate_unopened",
            "aggregate_answer_state_after": "aggregate_opened_once",
            "interval_start": "2021-01-01",
            "interval_end": "2026-08-25",
            "partial_endpoint": True,
            "trading_day_count": int((target.calendar >= np.datetime64("2021-01-01")).sum()),
            "decision_count": min(decision_counts),
            "attempt_count": len(accounts),
            "accounts": sorted(
                accounts,
                key=lambda row: (str(row["account_identity"]), str(row["cost_identity"])),
            ),
            "model_or_parameter_update": False,
            "result_backflow_allowed": False,
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    from factor_lab.governance.aggregate_blackbox_evaluation import validate_aggregate_result

    validate_aggregate_result(result, plan=plan)
    return write_json(
        output_root / "execution_receipt.json",
        {
            "schema_id": "factorlab.reaka_current_generation_aggregate_blackbox_gpu_execution@2.0",
            "status": "completed_rocm_aggregate_only",
            "contract_digest": contract["canonical_digest"],
            "query_id": plan.query_id,
            "candidate_fingerprint": plan.candidate_fingerprint,
            "backend": "pytorch_rocm_cuda_0",
            "aggregate_result_digest": result["canonical_digest"],
            "prefix_checks": checks,
            "elapsed_seconds": time.perf_counter() - started,
            "source_digests": source_closure(),
            "model_or_parameter_update": False,
            "result_backflow_allowed": False,
            "fresh_oos": False,
            "production_authority": False,
        },
    )


__all__ = [
    "GPU_BATCH_SIZE",
    "build_current_scores_gpu",
    "build_causal_basis_pair_gpu",
    "ensemble_seed_scores_gpu",
    "execute_tree_gpu",
    "fit_post2020_exposures_gpu",
    "solve_exposure_jobs_batched",
    "load_gpu_cache",
    "materialize_gpu_cache",
    "solve_complete_group_torch",
    "source_closure",
]
