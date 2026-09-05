"""Stage6 parameter-calibration preflight. No formal fit, Stage7, or production."""

# pyright: reportAny=false, reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportCallIssue=false, reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportMissingTypeStubs=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnusedCallResult=false, reportUnnecessaryComparison=false
# pyright: reportUnnecessaryContains=false, reportUnnecessaryCast=false
# pyright: reportPrivateImportUsage=false

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Final, Literal, cast

import numpy as np
import torch
from numpy.typing import NDArray
from torch import Tensor, nn

from factor_lab.factor_rotation.reaka_paper_v1 import (
    ReakaPaperConfig,
    ReakaPaperForecast,
    ReakaPaperTrainingOutput,
)
from factor_lab.factor_rotation.reaka_parameter_governance import (
    INITIAL_FACTORLAB_TRAINING_BLOCKERS,
    build_parameter_catalog,
    validate_training_parameter_instantiation,
)
from factor_lab.factor_rotation.reaka_prediction_root_routing import (
    build_current_root_resolution_receipt,
)
from factor_lab.factor_rotation.reaka_stage5_parameter_compiler import (
    compile_stage5_calibration_contract,
    validate_stage5_calibration_contract,
)
from factor_lab.factor_rotation.reaka_stage6_daily_engine import (
    Stage6ReakaModel,
    Stage6SharedTensor,
    load_shared_tensor,
    load_task_spec,
)
from factor_lab.factor_rotation.reaka_stage6_task_alignment import (
    AlignedInputArm,
    FactorEvidenceIdentity,
    build_aligned_task_spec,
    load_supplemented_shared_tensor,
)
from factor_lab.factor_rotation.reaka_stage6_temporal_coordinate import (
    Stage6TemporalWindowCache,
    build_or_load_temporal_cache,
    build_temporal_rows,
    filter_temporal_rows_by_exit_year,
    h20_periodic_coordinate_contract,
    temporalize_task_spec,
)
from factor_lab.governance.canonicalization import canonical_digest

HIDDEN_DIMENSIONS: Final[tuple[int, ...]] = (8, 16, 32)
LEARNING_RATES: Final[tuple[float, ...]] = (0.0001, 0.0003, 0.001)
SCREENING_SEED: Final = 11
CONFIRMATION_SEEDS: Final[tuple[int, ...]] = (11, 29, 47)
SCREENING_COVERAGE_CYCLES: Final = 4
CONFIRMATION_COVERAGE_CYCLES: Final = 12
CONFIRMATION_CHECKPOINTS: Final[tuple[int, ...]] = (4, 8, 12)
SCREENING_SAMPLE_ROWS: Final = 81_920
SMOKE_ROWS: Final = 8_192
LATENT_DIM: Final = 8
OPERATOR_COUNT: Final = 1
SEQUENCE_LENGTH: Final = 10
MAX_TOTAL_SECONDS: Final = 600.0
TRAIN_YEAR_MIN: Final = 2009
TRAIN_YEAR_MAX: Final = 2017
VALIDATION_YEAR: Final = 2018
POST_2020_YEAR: Final = 2021
TRANSPARENT_TRUNK_COEFFICIENT: Final = 1.0
WEIGHT_DECAY: Final = 0.0
STRAIGHT_THROUGH: Final = False
AMP_GRAD_SCALER_POLICY: Final = "disabled_unclipped_measurement"
ARM_ID: Final = "fixed_k_no_residual"
EXPECTED_CATALOG_DIGEST: Final = "sha256:59bb74b1c0fc48b5b22bd96c32c79f9a416d39b97144bd37666dae5956511485"
EXPECTED_ROOT_DIGEST: Final = "sha256:9b08903a663d135e99df81a86db103a7a278819f485a81bcb662cfbc2c5abfa2"
EXPECTED_STAGE5_DIGEST: Final = "sha256:416bdb9749e48f8af8aec2088896ea4d8fe3e8a2a1ff83ae89c62b39d60a3fce"
EXPECTED_TEMPORAL_DIGEST: Final = "sha256:82bb00c8620cdd39416f9139c8a94a665168ec6d311e02f2c9079802c76078a5"

REPO_ROOT: Final = Path(__file__).resolve().parents[3]
CONTRACT_PATHS: Final[dict[str, Path]] = {
    "catalog": REPO_ROOT / "docs/ops/reaka_paper_parameter_catalog@1.1.json",
    "root_routing": REPO_ROOT / "docs/ops/reaka_prediction_root_routing@1.0.json",
    "stage5": REPO_ROOT / "docs/ops/reaka_stage5_parameter_compilation@1.0.json",
    "stage5_capability": REPO_ROOT
    / "docs/ops/evidence/reaka_stage5_parameter_compilation_v1_20260825"
    / "whitepaper_capability_validation.json",
    "stage5_closeout": REPO_ROOT / "docs/ops/evidence/reaka_stage5_parameter_compilation_v1_20260825" / "stage5_closeout.json",
    "temporal_contract": REPO_ROOT / "docs/ops/reaka_stage6_temporal_coordinate@2.0.json",
    "portfolio_contract": REPO_ROOT / "docs/ops/reaka_stage6_portfolio_execution@1.0.json",
    "aligned_arms": REPO_ROOT / "docs/ops/evidence/reaka_stage6_task_alignment_freeze_20260825" / "aligned_input_arms.json",
}
DEFAULT_TENSOR_ROOT: Final = (
    REPO_ROOT / "output/factor-rotation/reaka_stage6_engineering_handoff_v1_20260817" / "reaka_stage6_daily_tensors_r1_20260817"
)
DEFAULT_SUPPLEMENT_ROOT: Final = REPO_ROOT / "output/factor-rotation/reaka_stage6_aligned_h20_factor_supplement_v1_20260825"
DEFAULT_EVIDENCE_ROOT: Final = REPO_ROOT / "docs/ops/evidence/reaka_stage6_parameter_calibration_v1_20260825"
DEFAULT_OUTPUT_ROOT: Final = REPO_ROOT / "output/factor-rotation/reaka_stage6_parameter_calibration_v1_20260825"
DEFAULT_CACHE_ROOT: Final = REPO_ROOT / "output/factor-rotation/reaka_stage6_parameter_calibration_cache_v1_20260825"


class CalibrationContractError(RuntimeError):
    """Frozen contract, digest, or data-boundary violation."""


class CalibrationBlocked(RuntimeError):
    """Legal stop that must be persisted as blocked, not patched."""


@dataclass(frozen=True, slots=True)
class CalibrationTrial:
    trial_id: str
    hidden_dimension: int
    learning_rate: float
    operator_count: int = OPERATOR_COUNT
    residual_mode: str = "disabled_until_authorized"
    gradient_clip: str = "disabled_measurement"
    seed: int = SCREENING_SEED

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TrialHealth:
    finite_loss: bool
    finite_gradients: bool
    finite_parameters: bool
    no_sustained_explosion: bool
    inner_metric_computable: bool

    @property
    def passed(self) -> bool:
        return all(
            (
                self.finite_loss,
                self.finite_gradients,
                self.finite_parameters,
                self.no_sustained_explosion,
                self.inner_metric_computable,
            )
        )

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["passed"] = self.passed
        return payload


@dataclass(slots=True)
class DataBoundaryLedger:
    latest_decision_date: str = ""
    train_row_count: int = 0
    validation_row_count: int = 0
    year_row_counts: dict[int, int] | None = None
    post_2020_rows_read: int = 0

    def record_years(self, years: NDArray[np.int64], *, role: str) -> None:
        if self.year_row_counts is None:
            self.year_row_counts = {}
        unique, counts = np.unique(years, return_counts=True)
        for year, count in zip(unique.tolist(), counts.tolist(), strict=True):
            year_i = int(year)
            self.year_row_counts[year_i] = self.year_row_counts.get(year_i, 0) + int(count)
            if year_i >= POST_2020_YEAR:
                self.post_2020_rows_read += int(count)
        if role == "train":
            self.train_row_count = int(years.size)
        elif role == "validation":
            self.validation_row_count = int(years.size)
        if self.post_2020_rows_read:
            raise CalibrationContractError("calibration_read_post_2020_rows")

    def as_dict(self) -> dict[str, object]:
        return {
            "latest_decision_date": self.latest_decision_date,
            "train_row_count": self.train_row_count,
            "validation_row_count": self.validation_row_count,
            "year_row_counts": dict(self.year_row_counts or {}),
            "post_2020_rows_read": self.post_2020_rows_read,
        }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def write_canonical_json(path: Path, payload: Mapping[str, object]) -> dict[str, object]:
    body = dict(payload)
    body.pop("canonical_digest", None)
    body["canonical_digest"] = canonical_digest(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return body


def read_canonical_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    observed = str(payload.pop("canonical_digest", ""))
    if observed and canonical_digest(payload) != observed:
        raise CalibrationContractError(f"digest_mismatch:{path}")
    if observed:
        payload["canonical_digest"] = observed
    return payload


def screening_trial_identities() -> tuple[CalibrationTrial, ...]:
    trials = tuple(
        CalibrationTrial(
            trial_id=f"h{hidden}_lr{str(rate).replace('.', 'p')}",
            hidden_dimension=hidden,
            learning_rate=rate,
        )
        for hidden in HIDDEN_DIMENSIONS
        for rate in LEARNING_RATES
    )
    ids = [trial.trial_id for trial in trials]
    if len(ids) != 9 or len(set(ids)) != 9:
        raise CalibrationContractError("screening_identity_not_unique")
    return trials


def k1_selector_values() -> dict[str, object]:
    return {
        "selector.gumbel_temperature": "not_applicable_operator_count_1",
        "selector.gumbel_schedule": "not_applicable_operator_count_1",
        "selector.straight_through": STRAIGHT_THROUGH,
        "selector_constructed": False,
    }


def diffusion_disabled_values() -> dict[str, object]:
    return {
        "residual.denoiser_architecture": "not_applicable_diffusion_not_authorized",
        "residual.time_embedding_dimension": "not_applicable_diffusion_not_authorized",
        "residual.x0_mapping": "identity",
        "residual.target_gradient_attachment": "stop_gradient",
        "denoiser_constructed": False,
        "time_embedding_constructed": False,
    }


def assert_k1_selector_not_applicable(values: Mapping[str, object]) -> None:
    expected = k1_selector_values()
    for key in (
        "selector.gumbel_temperature",
        "selector.gumbel_schedule",
        "selector.straight_through",
    ):
        if values.get(key) != expected[key]:
            raise CalibrationContractError(f"k1_selector_not_na:{key}")
    if values.get("selector_constructed") is True:
        raise CalibrationContractError("k1_selector_constructed")


def assert_diffusion_not_applicable(values: Mapping[str, object]) -> None:
    expected = diffusion_disabled_values()
    for key, value in expected.items():
        if values.get(key) != value:
            raise CalibrationContractError(f"diffusion_not_na:{key}")


def reject_old_checkpoint(path: Path | str | None) -> None:
    if path is None or str(path).strip() in {"", "none", "null"}:
        return
    raise CalibrationContractError(f"old_checkpoint_forbidden:{path}")


def reject_outer_year_rows(
    years: Sequence[int] | NDArray[np.integer],
    *,
    split: str,
) -> None:
    year_array = np.asarray(years, dtype=np.int64)
    if year_array.size == 0:
        raise CalibrationContractError(f"empty_split:{split}")
    if split == "train":
        allowed = set(range(TRAIN_YEAR_MIN, TRAIN_YEAR_MAX + 1))
    elif split == "validation":
        allowed = {VALIDATION_YEAR}
    else:
        raise CalibrationContractError(f"unknown_split:{split}")
    illegal = sorted({int(year) for year in year_array.tolist()} - allowed)
    if any(year >= POST_2020_YEAR for year in illegal):
        raise CalibrationContractError(f"post_2020_rows_in_split:{illegal}")
    if illegal:
        raise CalibrationContractError(f"illegal_{split}_years:{illegal}")


def stable_row_key(row: NDArray[np.int64], seed: int) -> int:
    payload = (
        int(seed).to_bytes(4, "little", signed=False)
        + int(row[0]).to_bytes(8, "little", signed=True)
        + int(row[1]).to_bytes(8, "little", signed=True)
        + int(row[2]).to_bytes(8, "little", signed=True)
    )
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "little", signed=False)


def freeze_stratified_sample(
    rows: NDArray[np.int64],
    *,
    years: NDArray[np.int64],
    phase_ids: NDArray[np.int64],
    sample_size: int = SCREENING_SAMPLE_ROWS,
    seed: int = SCREENING_SEED,
) -> tuple[NDArray[np.int64], dict[str, object]]:
    rows = np.asarray(rows, dtype=np.int64)
    years = np.asarray(years, dtype=np.int64)
    phase_ids = np.asarray(phase_ids, dtype=np.int64)
    if rows.shape[0] != years.size or years.size != phase_ids.size:
        raise CalibrationContractError("sample_freeze_length_mismatch")
    reject_outer_year_rows(years, split="train")
    if rows.shape[0] < sample_size:
        raise CalibrationContractError("training_prefix_smaller_than_screening_sample")
    strata = np.stack((years, phase_ids, rows[:, 0]), axis=1)
    _, inverse, stratum_sizes = np.unique(strata, axis=0, return_inverse=True, return_counts=True)
    targets = np.maximum(
        1,
        np.rint(sample_size * stratum_sizes / rows.shape[0]).astype(np.int64),
    )
    overflow = int(targets.sum() - sample_size)
    order = np.argsort(-stratum_sizes, kind="mergesort")
    step = -1 if overflow > 0 else 1
    remaining = abs(overflow)
    for index in order:
        if remaining == 0:
            break
        if targets[index] + step >= 1:
            targets[index] += step
            remaining -= 1
    selected: list[int] = []
    for stratum_id, target in enumerate(targets.tolist()):
        members = np.flatnonzero(inverse == stratum_id)
        keys = np.asarray(
            [stable_row_key(rows[index], seed) for index in members],
            dtype=np.uint64,
        )
        ranked = np.argsort(keys, kind="mergesort")
        selected.extend(members[ranked[: min(int(target), int(members.size))]].tolist())
    selected_array = np.asarray(sorted(set(selected)), dtype=np.int64)
    if selected_array.size < sample_size:
        leftover = np.setdiff1d(np.arange(rows.shape[0], dtype=np.int64), selected_array)
        keys = np.asarray(
            [stable_row_key(rows[index], seed) for index in leftover],
            dtype=np.uint64,
        )
        extra = leftover[np.argsort(keys, kind="mergesort")][: sample_size - selected_array.size]
        selected_array = np.sort(np.concatenate((selected_array, extra)))
    elif selected_array.size > sample_size:
        keys = np.asarray(
            [stable_row_key(rows[index], seed) for index in selected_array],
            dtype=np.uint64,
        )
        selected_array = np.sort(selected_array[np.argsort(keys, kind="mergesort")[:sample_size]])
    chosen = rows[selected_array]
    receipt: dict[str, object] = {
        "schema_id": "factorlab.reaka_stage6_sample_freeze@1.0",
        "status": "frozen_before_metrics",
        "seed": seed,
        "requested_rows": sample_size,
        "selected_rows": int(chosen.shape[0]),
        "source_rows": int(rows.shape[0]),
        "year_counts": {
            str(int(year)): int(count)
            for year, count in zip(
                *np.unique(years[selected_array], return_counts=True),
                strict=True,
            )
        },
        "phase_counts": {
            str(int(phase)): int(count)
            for phase, count in zip(
                *np.unique(phase_ids[selected_array], return_counts=True),
                strict=True,
            )
        },
        "rows_digest": "sha256:" + hashlib.sha256(np.ascontiguousarray(chosen).tobytes()).hexdigest(),
        "index_digest": "sha256:" + hashlib.sha256(np.ascontiguousarray(selected_array).tobytes()).hexdigest(),
        "metrics_seen_before_freeze": False,
        "production_authority": False,
    }
    receipt["canonical_digest"] = canonical_digest(receipt)
    return selected_array, receipt


def newey_west_mean_standard_error(
    values: Sequence[float],
    *,
    lags: int | None = None,
) -> float:
    series = np.asarray(values, dtype=np.float64)
    series = series[np.isfinite(series)]
    count = int(series.size)
    if count < 2:
        return math.inf
    centered = series - series.mean()
    max_lag = int(lags if lags is not None else math.floor(4 * (count / 100.0) ** (2 / 9)))
    max_lag = max(0, min(max_lag, count - 1))
    gamma0 = float(np.dot(centered, centered) / count)
    variance = gamma0
    for lag in range(1, max_lag + 1):
        weight = 1.0 - lag / (max_lag + 1)
        gamma = float(np.dot(centered[lag:], centered[:-lag]) / count)
        variance += 2.0 * weight * gamma
    return math.sqrt(max(variance, 0.0) / count)


def trial_is_numerically_healthy(health: Mapping[str, object] | TrialHealth) -> bool:
    if isinstance(health, TrialHealth):
        return health.passed
    return all(
        bool(health.get(name))
        for name in (
            "finite_loss",
            "finite_gradients",
            "finite_parameters",
            "no_sustained_explosion",
            "inner_metric_computable",
        )
    )


def select_largest_stable_learning_rate(
    hidden_dimension: int,
    trial_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    eligible = [
        row
        for row in trial_rows
        if int(row["hidden_dimension"]) == hidden_dimension and trial_is_numerically_healthy(dict(row.get("health", {})))
    ]
    if not eligible:
        return {
            "hidden_dimension": hidden_dimension,
            "status": "no_stable_learning_rate",
            "selected_learning_rate": None,
            "reason": "numerical_health_gate_failed",
        }
    selected = max(eligible, key=lambda row: float(row["learning_rate"]))
    return {
        "hidden_dimension": hidden_dimension,
        "status": "selected",
        "selected_learning_rate": float(selected["learning_rate"]),
        "selected_trial_id": selected["trial_id"],
        "eligible_learning_rates": sorted(float(row["learning_rate"]) for row in eligible),
        "rejected_higher_return_without_health": True,
    }


def select_smallest_hidden_within_one_se(
    confirmation_rows: Sequence[Mapping[str, object]],
    *,
    spread_harm_absolute: float = 0.001,
) -> dict[str, object]:
    healthy = [
        row
        for row in confirmation_rows
        if trial_is_numerically_healthy(dict(row.get("health", {}))) and math.isfinite(float(row.get("ensemble_rank_ic", math.nan)))
    ]
    if not healthy:
        return {
            "status": "candidate_family_insufficient",
            "selected_hidden_dimension": None,
            "reason": "no_hidden_passed_health_gates",
        }
    best = max(healthy, key=lambda row: float(row["ensemble_rank_ic"]))
    best_ic = float(best["ensemble_rank_ic"])
    best_se = float(best.get("rank_ic_hac_se", math.inf))
    if not math.isfinite(best_se):
        return {
            "status": "optimization_nonidentifiability",
            "selected_hidden_dimension": None,
            "reason": "best_model_hac_se_undefined",
        }
    threshold = best_ic - best_se
    within = [
        row
        for row in healthy
        if float(row["ensemble_rank_ic"]) >= threshold
        and not (float(row.get("ensemble_spread", 0.0)) < float(best.get("ensemble_spread", 0.0)) - spread_harm_absolute)
    ]
    if not within:
        return {
            "status": "candidate_family_insufficient",
            "selected_hidden_dimension": None,
            "reason": "one_se_band_empty_or_spread_harm",
            "best_hidden_dimension": int(best["hidden_dimension"]),
            "best_ensemble_rank_ic": best_ic,
            "best_rank_ic_hac_se": best_se,
        }
    selected = min(within, key=lambda row: int(row["hidden_dimension"]))
    return {
        "status": "selected",
        "selected_hidden_dimension": int(selected["hidden_dimension"]),
        "selected_learning_rate": selected.get("learning_rate"),
        "selected_ensemble_rank_ic": float(selected["ensemble_rank_ic"]),
        "best_hidden_dimension": int(best["hidden_dimension"]),
        "best_ensemble_rank_ic": best_ic,
        "best_rank_ic_hac_se": best_se,
        "one_se_threshold": threshold,
        "within_one_se_hiddens": [int(row["hidden_dimension"]) for row in within],
        "did_not_pick_worst_survivor": True,
    }


def multiplicity_receipt(
    *,
    screening_rows: Sequence[Mapping[str, object]],
    confirmation_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    screening_ids = [str(row["trial_id"]) for row in screening_rows]
    confirmation_keys = [f"{row['hidden_dimension']}:{row.get('seed')}" for row in confirmation_rows]
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_stage6_calibration_multiplicity@1.0",
        "candidate_count": 9,
        "screening_fit_count": len(screening_rows),
        "confirmation_fit_count": len(confirmation_rows),
        "confirmation_seed_count": len(CONFIRMATION_SEEDS),
        "screening_identities": screening_ids,
        "confirmation_identities": confirmation_keys,
        "failed_screening_retained": True,
        "failed_seeds_retained": True,
        "denominator_includes_all_attempts": True,
        "production_authority": False,
    }  # typed below
    if len(set(screening_ids)) != 9 or len(screening_rows) != 9:
        payload["status"] = "blocked"
        payload["reason"] = "screening_count_not_9"
    elif len(confirmation_rows) != 9 or len(set(confirmation_keys)) != 9:
        payload["status"] = "blocked"
        payload["reason"] = "confirmation_count_not_9"
    else:
        payload["status"] = "passed"
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def day_equal_rank_metrics(
    *,
    rows: NDArray[np.int64],
    scores: NDArray[np.float64],
    labels: NDArray[np.float64],
    phase_ids: NDArray[np.int64],
) -> dict[str, object]:
    rows = np.asarray(rows, dtype=np.int64)
    scores = np.asarray(scores, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.float64)
    phase_ids = np.asarray(phase_ids, dtype=np.int64)
    finite = np.isfinite(scores) & np.isfinite(labels)
    if not bool(finite.any()):
        return {
            "day_equal_rank_ic": math.nan,
            "rank_ic_hac_se": math.inf,
            "h20_spread": math.nan,
            "phase_rank_ics": {},
            "phase_stability": math.nan,
            "computable": False,
        }
    daily_ics: list[float] = []
    daily_spreads: list[float] = []
    for day in np.unique(rows[finite, 0]):
        mask = finite & (rows[:, 0] == day)
        if int(mask.sum()) < 2:
            continue
        left = scores[mask]
        right = labels[mask]
        left_rank = left.argsort(kind="mergesort").argsort(kind="mergesort")
        right_rank = right.argsort(kind="mergesort").argsort(kind="mergesort")
        if float(left_rank.std()) < 1e-12 or float(right_rank.std()) < 1e-12:
            continue
        daily_ics.append(float(np.corrcoef(left_rank, right_rank)[0, 1]))
        if int(mask.sum()) >= 20:
            order = np.argsort(left, kind="mergesort")
            tail = max(int(math.floor(int(mask.sum()) * 0.1)), 1)
            daily_spreads.append(float(right[order[-tail:]].mean() - right[order[:tail]].mean()))
    phase_ics: dict[str, float] = {}
    for phase in sorted(np.unique(phase_ids[finite]).tolist()):
        mask = finite & (phase_ids == phase)
        if int(mask.sum()) < 2:
            continue
        left = scores[mask]
        right = labels[mask]
        left_rank = left.argsort(kind="mergesort").argsort(kind="mergesort")
        right_rank = right.argsort(kind="mergesort").argsort(kind="mergesort")
        if float(left_rank.std()) < 1e-12 or float(right_rank.std()) < 1e-12:
            continue
        phase_ics[str(int(phase))] = float(np.corrcoef(left_rank, right_rank)[0, 1])
    phase_values = [value for value in phase_ics.values() if math.isfinite(value)]
    return {
        "day_equal_rank_ic": float(np.mean(daily_ics)) if daily_ics else math.nan,
        "rank_ic_hac_se": newey_west_mean_standard_error(daily_ics),
        "h20_spread": float(np.mean(daily_spreads)) if daily_spreads else math.nan,
        "phase_rank_ics": phase_ics,
        "phase_stability": float(np.min(phase_values)) if phase_values else math.nan,
        "day_count": len(daily_ics),
        "computable": bool(daily_ics),
    }


def build_calibration_model(
    *,
    feature_dim: int,
    hidden_dimension: int,
    sequence_length: int = SEQUENCE_LENGTH,
) -> Stage6ReakaModel:
    if hidden_dimension not in HIDDEN_DIMENSIONS:
        raise CalibrationContractError(f"hidden_not_in_family:{hidden_dimension}")
    config = ReakaPaperConfig(
        window_length=sequence_length,
        latent_dim=LATENT_DIM,
        network_hidden_dim=hidden_dimension,
        operator_count=1,
        training_epochs=1,
        diffusion_steps=1,
        batch_size=4096,
        learning_rate=LEARNING_RATES[0],
        gumbel_temperature=1.0,
        time_embedding_dim=LATENT_DIM,
        denoiser_hidden_dim=LATENT_DIM,
        inference_draws=1,
    )
    model = Stage6ReakaModel(
        feature_dim=feature_dim,
        config=config,
        arm_id=ARM_ID,
    )
    if int(model.config.operator_count) != 1:
        raise CalibrationContractError("k1_operator_count_not_forced")
    if model.ablation.adaptive_koopman_selector:
        raise CalibrationContractError("selector_constructed")
    if model.ablation.residual_mode != "none" or model.residual_mlp is not None:
        raise CalibrationContractError("residual_module_constructed")
    return model


def apply_declared_initialization(
    model: nn.Module,
    *,
    sequence_length: int = SEQUENCE_LENGTH,
    seed: int,
) -> dict[str, object]:
    torch.manual_seed(seed)
    chrono = math.log(sequence_length - 1)
    linear_count = 0
    lstm_count = 0
    for module in model.modules():
        if isinstance(module, nn.Linear):
            nn.init.xavier_uniform_(module.weight, gain=nn.init.calculate_gain("relu"))
            if module.bias is not None:
                nn.init.zeros_(module.bias)
            linear_count += 1
        elif isinstance(module, nn.LSTM):
            for name, parameter in module.named_parameters():
                if "weight_ih" in name:
                    nn.init.xavier_uniform_(parameter)
                elif "weight_hh" in name:
                    nn.init.orthogonal_(parameter)
                elif "bias" in name:
                    nn.init.zeros_(parameter)
                    hidden = parameter.numel() // 4
                    parameter.data[hidden : 2 * hidden] = chrono
            lstm_count += 1
    return {
        "input_affine": "activation_aware_Xavier",
        "recurrent": "orthogonal",
        "forget_bias": "log_T_minus_1_chrono",
        "chrono_value": chrono,
        "linear_modules": linear_count,
        "lstm_modules": lstm_count,
        "seed": seed,
    }


def regularized_dmd_operator(latent: Tensor, next_latent: Tensor) -> dict[str, object]:
    if latent.ndim != 2 or next_latent.shape != latent.shape:
        raise CalibrationContractError("dmd_latent_shape_invalid")
    if int(latent.shape[1]) != LATENT_DIM:
        raise CalibrationContractError("dmd_latent_dim_not_8")
    gram = latent.T @ latent
    ridge = max(1e-6, 1e-4 * float(torch.trace(gram)) / LATENT_DIM)
    identity = torch.eye(LATENT_DIM, dtype=latent.dtype, device=latent.device)
    operator = torch.linalg.solve(gram + ridge * identity, latent.T @ next_latent).T
    eigenvalues = torch.linalg.eigvals(operator)
    radius = float(eigenvalues.abs().max())
    condition = float(torch.linalg.cond(operator))
    projected = False
    if math.isfinite(radius) and radius > 1.0:
        operator = operator / radius
        projected = True
        radius = 1.0
    return {
        "operator": operator.detach(),
        "ridge": ridge,
        "spectral_radius": radius,
        "condition_number": condition,
        "stability_class": "unit_disk_spectral_radius_le_1",
        "projected_to_stability_class": projected,
        "all_finite": bool(torch.isfinite(operator).all()),
    }


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _finite_tensor(value: Tensor) -> bool:
    return bool(torch.isfinite(value.detach()).all())


def _optimizer_state_empty(optimizer: torch.optim.Optimizer) -> bool:
    return not any(state for state in optimizer.state.values())


def _load_arm(path: Path) -> AlignedInputArm:
    payload = read_canonical_json(path)
    selected = next(item for item in payload["arms"] if item["arm_id"] == "CORE_SPATIAL_H20")
    return AlignedInputArm(
        arm_id=str(selected["arm_id"]),
        evidence_horizon_days=int(selected["evidence_horizon_days"]),
        cadence_id=str(selected["cadence_id"]),
        sequence_length=int(selected["sequence_length"]),
        identities=tuple(
            FactorEvidenceIdentity(
                factor_id=str(item["factor_id"]),
                horizon_days=int(item["horizon_days"]),
                candidate_id=str(item["candidate_id"]),
                input_mode=str(item["input_mode"]),
                descriptor_id=str(item["descriptor_id"]),
                quantile_bins=tuple(int(value) for value in item["quantile_bins"]),
            )
            for item in selected["factor_identities"]
        ),
        common_support_factor_ids=tuple(str(value) for value in selected["common_support_factor_ids"]),
    )


def restrict_shared_tensor_to_calibration_end(
    shared: Stage6SharedTensor,
    *,
    end_inclusive: str = "2018-12-31",
) -> tuple[Stage6SharedTensor, dict[str, object]]:
    years = shared.calendar.astype("datetime64[Y]").astype(int) + 1970
    original_post = int(np.sum(years >= POST_2020_YEAR))
    keep = shared.calendar <= np.datetime64(end_inclusive)
    if not bool(keep.any()):
        raise CalibrationContractError("calibration_calendar_empty")
    stop = int(np.flatnonzero(keep)[-1]) + 1
    sliced = replace(
        shared,
        calendar=np.asarray(shared.calendar[:stop]),
        base_rank_centered=shared.base_rank_centered[:stop],
        base_available=shared.base_available[:stop],
        descriptor_bins=shared.descriptor_bins[:stop],
        labels=shared.labels[:stop],
        daily_returns=shared.daily_returns[:stop],
        entry_ok=shared.entry_ok[:stop],
        follow_weights=shared.follow_weights[:stop],
    )
    sliced_years = sliced.calendar.astype("datetime64[Y]").astype(int) + 1970
    if bool(np.any(sliced_years >= POST_2020_YEAR)):
        raise CalibrationContractError("truncated_tensor_still_has_post_2020")
    return sliced, {
        "end_inclusive": end_inclusive,
        "kept_days": int(stop),
        "original_post_2020_calendar_days": original_post,
        "used_post_2020_rows": 0,
        "latest_calendar_date": str(np.datetime_as_string(sliced.calendar[-1], unit="D")),
    }


def verify_frozen_contracts() -> dict[str, object]:
    missing = [name for name, path in CONTRACT_PATHS.items() if not path.is_file()]
    if missing:
        raise CalibrationContractError(f"required_contract_missing:{missing}")
    catalog = build_parameter_catalog()
    if catalog["canonical_digest"] != EXPECTED_CATALOG_DIGEST:
        raise CalibrationContractError("catalog_digest_drift")
    if read_canonical_json(CONTRACT_PATHS["catalog"]).get("canonical_digest") != EXPECTED_CATALOG_DIGEST:
        raise CalibrationContractError("catalog_file_digest_drift")
    root = build_current_root_resolution_receipt(catalog_digest=str(catalog["canonical_digest"]))
    if root["canonical_digest"] != EXPECTED_ROOT_DIGEST:
        raise CalibrationContractError("root_routing_digest_drift")
    if read_canonical_json(CONTRACT_PATHS["root_routing"]).get("canonical_digest") != EXPECTED_ROOT_DIGEST:
        raise CalibrationContractError("root_routing_file_digest_drift")
    compiled = compile_stage5_calibration_contract(catalog, root)
    if compiled["canonical_digest"] != EXPECTED_STAGE5_DIGEST:
        raise CalibrationContractError("stage5_recompile_digest_drift")
    file_stage5 = read_canonical_json(CONTRACT_PATHS["stage5"])
    if file_stage5.get("canonical_digest") != EXPECTED_STAGE5_DIGEST:
        raise CalibrationContractError("stage5_file_digest_drift")
    validation = validate_stage5_calibration_contract(catalog, root, file_stage5)
    if validation["status"] != "passed":
        raise CalibrationContractError(f"stage5_contract_blocked:{validation}")
    capability = read_canonical_json(CONTRACT_PATHS["stage5_capability"])
    closeout = read_canonical_json(CONTRACT_PATHS["stage5_closeout"])
    if capability.get("status") != "passed":
        raise CalibrationContractError("stage5_capability_not_passed")
    if closeout.get("next_legal_action") != "stage6_parameter_calibration_preflight":
        raise CalibrationContractError("stage5_next_action_not_calibration_preflight")
    temporal = h20_periodic_coordinate_contract().as_dict()
    if temporal["canonical_digest"] != EXPECTED_TEMPORAL_DIGEST:
        raise CalibrationContractError("temporal_contract_digest_drift")
    assert_k1_selector_not_applicable({**compiled["parameter_values"], "selector_constructed": False})
    assert_diffusion_not_applicable(
        {
            **compiled["parameter_values"],
            "denoiser_constructed": False,
            "time_embedding_constructed": False,
        }
    )
    if compiled["parameter_values"]["optimizer.weight_decay"] != 0.0:
        raise CalibrationContractError("weight_decay_not_zero")
    return {
        "schema_id": "factorlab.reaka_stage6_calibration_contract_gate@1.0",
        "status": "passed",
        "catalog_digest": EXPECTED_CATALOG_DIGEST,
        "root_resolution_digest": EXPECTED_ROOT_DIGEST,
        "stage5_digest": EXPECTED_STAGE5_DIGEST,
        "temporal_digest": EXPECTED_TEMPORAL_DIGEST,
        "stage5_validation_digest": validation["canonical_digest"],
        "capability_digest": capability["canonical_digest"],
        "closeout_digest": closeout["canonical_digest"],
        "production_authority": False,
    }


def source_digest_manifest(paths: Sequence[Path]) -> dict[str, object]:
    entries = [
        {
            "path": str(path.resolve(strict=True).relative_to(REPO_ROOT)),
            "sha256": file_sha256(path.resolve(strict=True)),
            "size_bytes": path.resolve(strict=True).stat().st_size,
        }
        for path in paths
    ]
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_stage6_calibration_source_digest@1.0",
        "entries": entries,
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def _decision_years(calendar: NDArray[np.datetime64], rows: NDArray[np.int64]) -> NDArray[np.int64]:
    return (calendar[rows[:, 0]].astype("datetime64[Y]").astype(int) + 1970).astype(np.int64)


def _phase_ids_from_rows(
    calendar: NDArray[np.datetime64],
    rows: NDArray[np.int64],
) -> NDArray[np.int64]:
    contract = h20_periodic_coordinate_contract()
    anchor = np.datetime64(contract.decision_grid_anchor)
    anchor_positions = np.flatnonzero(calendar == anchor)
    if anchor_positions.size != 1:
        raise CalibrationContractError("decision_grid_anchor_missing")
    relative = rows[:, 0] - int(anchor_positions[0])
    return ((relative // contract.decision_step_trading_days) % contract.phase_count).astype(np.int64)


def assemble_calibration_splits(
    *,
    shared: Stage6SharedTensor,
    spec_rows: dict[int, NDArray[np.int64]],
    ledger: DataBoundaryLedger,
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    illegal_years = [year for year in spec_rows if year >= 2019]
    if illegal_years:
        raise CalibrationContractError(f"row_builder_emitted_outer_years:{illegal_years}")
    train_parts = [
        filter_temporal_rows_by_exit_year(
            spec_rows[year],
            allowed_years=tuple(range(TRAIN_YEAR_MIN, TRAIN_YEAR_MAX + 1)),
            decision_year=year,
            calendar=shared.calendar,
        )
        for year in range(TRAIN_YEAR_MIN, TRAIN_YEAR_MAX + 1)
        if year in spec_rows
    ]
    if VALIDATION_YEAR not in spec_rows:
        raise CalibrationContractError("validation_year_missing")
    validation = filter_temporal_rows_by_exit_year(
        spec_rows[VALIDATION_YEAR],
        allowed_years=(VALIDATION_YEAR,),
        decision_year=VALIDATION_YEAR,
        calendar=shared.calendar,
    )
    train = np.concatenate(train_parts, axis=0)
    train_years = _decision_years(shared.calendar, train)
    val_years = _decision_years(shared.calendar, validation)
    reject_outer_year_rows(train_years, split="train")
    reject_outer_year_rows(val_years, split="validation")
    ledger.record_years(train_years, role="train")
    ledger.record_years(val_years, role="validation")
    ledger.latest_decision_date = str(np.datetime_as_string(shared.calendar[int(validation[:, 0].max())], unit="D"))
    return train, validation


def build_formal_fit_instantiation(
    *,
    selected: Mapping[str, object],
    receipts: Mapping[str, str],
    catalog: Mapping[str, object],
    root: Mapping[str, object],
    stage5: Mapping[str, object],
    clip_norm: object,
    coverage: int,
    dmd: Mapping[str, object],
) -> dict[str, object]:
    hidden = selected.get("selected_hidden_dimension")
    learning_rate = selected.get("selected_learning_rate")
    if hidden is None or learning_rate is None:
        raise CalibrationBlocked("formal_fit_requires_unique_selection")
    values = dict(stage5["parameter_values"])
    values["network.hidden_dimension"] = int(hidden)
    values["optimizer.learning_rate"] = float(learning_rate)
    values["training.coverage_budget"] = {
        "selected_full_cycles": int(coverage),
        "checkpoints_full_cycles": list(CONFIRMATION_CHECKPOINTS),
        "maximum_full_cycles": CONFIRMATION_COVERAGE_CYCLES,
    }
    values["training.gradient_clip_norm"] = clip_norm
    values["koopman.initialization"] = {
        "rule": "training_prefix_regularized_DMD_projected_to_declared_stability_class",
        "ridge": dmd.get("ridge"),
        "spectral_radius": dmd.get("spectral_radius"),
        "condition_number": dmd.get("condition_number"),
        "stability_class": dmd.get("stability_class"),
    }
    values["decoder.architecture"] = {
        "family": "shared_pointwise_one_hidden_layer_MLP",
        "input_dimension": LATENT_DIM,
        "hidden_width": int(hidden),
        "output_dimension": 1,
    }
    missing = [key for key in INITIAL_FACTORLAB_TRAINING_BLOCKERS if key not in values]
    if missing:
        raise CalibrationBlocked(f"formal_fit_missing_parameters:{missing}")
    payload = {
        "schema_id": "factorlab.reaka_training_parameter_instantiation@1.0",
        "status": "ready_for_formal_fit_gate",
        "catalog_digest": catalog["canonical_digest"],
        "root_resolution_digest": root["canonical_digest"],
        "stage5_digest": stage5["canonical_digest"],
        "parameter_values": values,
        "evidence_receipts": dict(receipts),
        "formal_fit_started": False,
        "fresh_oos": False,
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in keys})


def _writable_tensor(array: object, dtype: object) -> Tensor:
    return torch.from_numpy(np.array(np.ascontiguousarray(array, dtype=dtype), copy=True))


def _contiguous_split(
    cache: Stage6TemporalWindowCache,
    split: Literal["train", "validation"],
) -> dict[str, Tensor]:
    selected = cache.train if split == "train" else cache.validation
    return {
        "returns": _writable_tensor(selected.returns, np.float32),
        "features": _writable_tensor(selected.features, np.float32),
        "targets": _writable_tensor(selected.targets, np.float32),
        "phase_ids": _writable_tensor(selected.phase_ids, np.int64),
        "rows": _writable_tensor(selected.rows, np.int64),
    }


def _batch_slice(bundle: Mapping[str, Tensor], start: int, stop: int) -> tuple[Tensor, Tensor]:
    return bundle["returns"][start:stop], bundle["features"][start:stop]


def _measure_unclipped_gradients(model: nn.Module) -> dict[str, object]:
    norms: list[float] = []
    nonfinite_groups = 0
    for parameter in model.parameters():
        if parameter.grad is None:
            continue
        if not _finite_tensor(parameter.grad):
            nonfinite_groups += 1
            continue
        norms.append(float(parameter.grad.detach().float().norm()))
    return {
        "finite": nonfinite_groups == 0,
        "nonfinite_parameter_groups": nonfinite_groups,
        "grad_norm_mean": float(np.mean(norms)) if norms else math.nan,
        "grad_norm_max": float(np.max(norms)) if norms else math.nan,
        "grad_norm_p99": float(np.quantile(norms, 0.99)) if norms else math.nan,
        "parameter_group_count": len(norms) + nonfinite_groups,
    }


def _predict_scores(
    model: Stage6ReakaModel,
    bundle: Mapping[str, Tensor],
    *,
    device: torch.device,
    batch_size: int,
    use_amp: bool,
    seed: int,
) -> NDArray[np.float64]:
    model.eval()
    scores = np.zeros((int(bundle["targets"].shape[0]),), dtype=np.float64)
    with torch.no_grad():
        for start in range(0, scores.size, batch_size):
            stop = min(start + batch_size, scores.size)
            returns = bundle["returns"][start:stop].to(device, non_blocking=True)
            features = bundle["features"][start:stop].to(device, non_blocking=True)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=use_amp):
                forecast = cast(ReakaPaperForecast, model.forecast(returns, features))
            scores[start:stop] = forecast.scores.detach().float().cpu().numpy().astype(np.float64)
    if not np.isfinite(scores).all():
        raise CalibrationContractError(f"nonfinite_scores:{seed}")
    return scores


def run_declared_fit(
    *,
    hidden_dimension: int,
    learning_rate: float,
    seed: int,
    train_bundle: Mapping[str, Tensor],
    validation_bundle: Mapping[str, Tensor],
    feature_dim: int,
    device: torch.device,
    batch_size: int,
    use_amp: bool,
    coverage_cycles: int,
    checkpoints: tuple[int, ...],
    reconstruction_warmup_cycles: int = 1,
) -> dict[str, object]:
    started = time.perf_counter()
    _seed_everything(seed)
    model = build_calibration_model(feature_dim=feature_dim, hidden_dimension=hidden_dimension).to(device)
    init_receipt = apply_declared_initialization(model, seed=seed)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate, weight_decay=WEIGHT_DECAY)
    train_count = int(train_bundle["returns"].shape[0])

    def _cycle(objective: Literal["reconstruction", "joint"]) -> dict[str, object]:
        model.train()
        starts = np.arange(0, train_count, batch_size, dtype=np.int64)
        np.random.default_rng(seed).shuffle(starts)
        totals = {"total": 0.0, "rec": 0.0, "koop": 0.0}
        seen = 0
        loss_finite = True
        grad_finite = True
        exploded = False
        last_grad: dict[str, object] = {}
        for raw_start in starts:
            start = int(raw_start)
            stop = min(start + batch_size, train_count)
            returns, features = _batch_slice(train_bundle, start, stop)
            returns = returns.to(device, non_blocking=True)
            features = features.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(
                device_type=device.type,
                dtype=torch.float16,
                enabled=use_amp and device.type == "cuda",
            ):
                output = cast(ReakaPaperTrainingOutput, model.training_objective(returns, features))
                loss = output.reconstruction_loss if objective == "reconstruction" else output.total_loss
            if not _finite_tensor(loss):
                loss_finite = False
                break
            # Unscaled backward: GradScaler overflowed some ROCm batches while
            # unscaled AMP/float32 grads on the same batch stayed finite.
            loss.backward()
            last_grad = _measure_unclipped_gradients(model)
            if not bool(last_grad["finite"]):
                grad_finite = False
                break
            optimizer.step()
            size = stop - start
            totals["total"] += float(output.total_loss.detach()) * size
            totals["rec"] += float(output.reconstruction_loss.detach()) * size
            totals["koop"] += float(output.koopman_loss.detach()) * size
            seen += size
            if float(last_grad["grad_norm_max"]) > 1e6:
                exploded = True
        return {
            "finite": loss_finite and grad_finite,
            "loss_finite": loss_finite,
            "grad_finite": grad_finite,
            "exploded": exploded,
            "loss_total": totals["total"] / max(seen, 1),
            "loss_rec": totals["rec"] / max(seen, 1),
            "loss_koop": totals["koop"] / max(seen, 1),
            "grad": last_grad,
        }

    warmup = _cycle("reconstruction")
    if not bool(warmup["finite"]):
        parameters_finite = all(_finite_tensor(parameter) for parameter in model.parameters())
        warmup_grad = dict(warmup.get("grad", {}))
        return {
            "status": "nonfinite_trial",
            "elapsed_seconds": time.perf_counter() - started,
            "health": TrialHealth(
                finite_loss=bool(warmup["loss_finite"]),
                finite_gradients=bool(warmup["grad_finite"]),
                finite_parameters=parameters_finite,
                no_sustained_explosion=not bool(warmup["exploded"]),
                inner_metric_computable=False,
            ).as_dict(),
            "initialization": init_receipt,
            "dmd": {"status": "skipped_nonfinite_warmup"},
            "optimizer_reset_after_dmd": False,
            "warmup": {key: warmup[key] for key in ("loss_rec", "finite", "loss_finite", "grad_finite")},
            "gradient_audit": [{"coverage_cycle": 0, "phase": "reconstruction_warmup", **warmup_grad}],
            "amp_grad_scaler": AMP_GRAD_SCALER_POLICY,
            "final_metrics": {"computable": False},
        }
    model.eval()
    latents: list[Tensor] = []
    next_latents: list[Tensor] = []
    with torch.no_grad():
        for start in range(0, train_count, batch_size):
            stop = min(start + batch_size, train_count)
            returns, features = _batch_slice(train_bundle, start, stop)
            output = cast(
                ReakaPaperTrainingOutput,
                model.training_objective(
                    returns.to(device, non_blocking=True),
                    features.to(device, non_blocking=True),
                ),
            )
            latents.append(output.latent[:, -1].float().cpu())
            next_latents.append(output.next_latent[:, -1].float().cpu())
    dmd = regularized_dmd_operator(torch.cat(latents, dim=0), torch.cat(next_latents, dim=0))
    if not bool(dmd["all_finite"]):
        raise CalibrationContractError("dmd_operator_nonfinite")
    with torch.no_grad():
        model.operators.data.copy_(dmd["operator"].to(device=model.operators.device, dtype=model.operators.dtype))
    del dmd["operator"]
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate, weight_decay=WEIGHT_DECAY)
    if not _optimizer_state_empty(optimizer):
        raise CalibrationContractError("optimizer_not_reset_after_dmd")
    cycle_losses: list[dict[str, object]] = []
    checkpoint_metrics: list[dict[str, object]] = []
    gradient_rows: list[dict[str, object]] = []
    finite = True
    exploded = False
    for cycle in range(1, coverage_cycles + 1):
        stats = _cycle("joint")
        cycle_losses.append({"coverage_cycle": cycle, **stats})
        gradient_rows.append({"coverage_cycle": cycle, **stats["grad"]})
        if not bool(stats["finite"]):
            finite = False
            break
        exploded = exploded or bool(stats["exploded"])
        if cycle in checkpoints:
            scores = _predict_scores(
                model,
                validation_bundle,
                device=device,
                batch_size=batch_size,
                use_amp=use_amp and device.type == "cuda",
                seed=seed,
            )
            metrics = day_equal_rank_metrics(
                rows=validation_bundle["rows"].numpy(),
                scores=scores,
                labels=validation_bundle["targets"].numpy().astype(np.float64),
                phase_ids=validation_bundle["phase_ids"].numpy(),
            )
            checkpoint_metrics.append({"coverage_cycle": cycle, **metrics})
    parameters_finite = all(_finite_tensor(parameter) for parameter in model.parameters())
    final_metrics = checkpoint_metrics[-1] if checkpoint_metrics else {"computable": False}
    health = TrialHealth(
        finite_loss=finite,
        finite_gradients=finite,
        finite_parameters=parameters_finite,
        no_sustained_explosion=not exploded,
        inner_metric_computable=bool(final_metrics.get("computable")),
    )
    return {
        "status": "completed" if health.passed else "nonfinite_trial",
        "elapsed_seconds": time.perf_counter() - started,
        "health": health.as_dict(),
        "initialization": init_receipt,
        "dmd": dmd,
        "optimizer_reset_after_dmd": True,
        "warmup": {key: warmup[key] for key in ("loss_rec", "finite")},
        "cycle_losses": cycle_losses,
        "checkpoint_metrics": checkpoint_metrics,
        "gradient_audit": gradient_rows,
        "final_metrics": final_metrics,
        "reconstruction_warmup_cycles": reconstruction_warmup_cycles,
        "weight_decay": WEIGHT_DECAY,
        "straight_through": STRAIGHT_THROUGH,
        "gradient_clip": "disabled_measurement",
        "amp_grad_scaler": AMP_GRAD_SCALER_POLICY,
    }


def estimate_runtime(
    *,
    rows_per_second: float,
    screening_rows: int,
    confirmation_rows: int,
) -> dict[str, object]:
    screening = 9 * screening_rows * SCREENING_COVERAGE_CYCLES / max(rows_per_second, 1.0)
    one_confirmation = confirmation_rows * CONFIRMATION_COVERAGE_CYCLES / max(rows_per_second, 1.0)
    confirmation = 9 * one_confirmation
    warmup = 18 * confirmation_rows / max(rows_per_second, 1.0)
    total = screening + confirmation + warmup
    return {
        "screening_seconds": screening,
        "one_full_confirmation_seconds": one_confirmation,
        "all_confirmation_seconds": confirmation,
        "dmd_warmup_seconds": warmup,
        "predicted_total_seconds": total,
        "limit_seconds": MAX_TOTAL_SECONDS,
        "may_execute": total <= MAX_TOTAL_SECONDS,
    }


def resolve_device(preferred: str = "cuda:0") -> tuple[torch.device, str]:
    if preferred.startswith("cuda") and torch.cuda.is_available():
        return torch.device(preferred), torch.cuda.get_device_name(0)
    return torch.device("cpu"), "cpu"


def _precision_parity(
    *,
    feature_dim: int,
    train_bundle: Mapping[str, Tensor],
    device: torch.device,
    batch_size: int,
) -> dict[str, object]:
    if device.type != "cuda":
        return {
            "status": "cpu_only",
            "float32_amp_compared": False,
            "loss_relative_delta": 0.0,
            "score_rank_correlation": 1.0,
            "selection_consistent": True,
        }
    losses: dict[str, float] = {}
    scores: dict[str, NDArray[np.float64]] = {}
    for precision in ("float32", "autocast_float16"):
        _seed_everything(SCREENING_SEED)
        model = build_calibration_model(feature_dim=feature_dim, hidden_dimension=8).to(device)
        apply_declared_initialization(model, seed=SCREENING_SEED)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.0003, weight_decay=0.0)
        use_amp = precision == "autocast_float16"
        returns, features = _batch_slice(train_bundle, 0, batch_size)
        returns = returns.to(device)
        features = features.to(device)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_amp):
            output = cast(ReakaPaperTrainingOutput, model.training_objective(returns, features))
        output.total_loss.backward()
        optimizer.step()
        losses[precision] = float(output.total_loss.detach())
        scores[precision] = _predict_scores(
            model,
            {
                "returns": train_bundle["returns"][:batch_size],
                "features": train_bundle["features"][:batch_size],
                "targets": train_bundle["targets"][:batch_size],
            },
            device=device,
            batch_size=batch_size,
            use_amp=use_amp,
            seed=SCREENING_SEED,
        )
    delta = abs(losses["autocast_float16"] - losses["float32"]) / max(abs(losses["float32"]), 1e-12)
    left = scores["float32"]
    right = scores["autocast_float16"]
    rank = float(
        np.corrcoef(
            left.argsort(kind="mergesort").argsort(kind="mergesort"),
            right.argsort(kind="mergesort").argsort(kind="mergesort"),
        )[0, 1]
    )
    passed = delta <= 5e-3 and rank >= 0.999
    return {
        "status": "passed" if passed else "blocked",
        "float32_amp_compared": True,
        "loss_relative_delta": delta,
        "score_rank_correlation": rank,
        "selection_consistent": bool(np.argmax(left) == np.argmax(right) or rank >= 0.999),
        "float32_loss": losses["float32"],
        "amp_loss": losses["autocast_float16"],
    }


def load_runtime_assets(
    *,
    tensor_root: Path,
    supplement_root: Path,
    cache_root: Path,
    evidence_root: Path,
    sample_size: int | None = None,
) -> dict[str, object]:
    reject_old_checkpoint(None)
    gate = verify_frozen_contracts()
    arm = _load_arm(CONTRACT_PATHS["aligned_arms"])
    shared = load_shared_tensor(tensor_root, verify=False)
    shared = load_supplemented_shared_tensor(base=shared, supplement_root=supplement_root)
    shared, truncation = restrict_shared_tensor_to_calibration_end(shared)
    temporal = h20_periodic_coordinate_contract()
    spec = temporalize_task_spec(
        spec=build_aligned_task_spec(
            base_spec=load_task_spec(tensor_root, "weekly::h20"),
            shared=shared,
            arm=arm,
        ),
        contract=temporal,
    )
    packed = build_temporal_rows(
        shared=shared,
        spec=spec,
        contract=temporal,
        common_support_factor_ids=arm.common_support_factor_ids,
    )
    ledger = DataBoundaryLedger()
    train_rows, validation_rows = assemble_calibration_splits(shared=shared, spec_rows=packed, ledger=ledger)
    train_years = _decision_years(shared.calendar, train_rows)
    train_phases = _phase_ids_from_rows(shared.calendar, train_rows)
    sample_receipt_path = evidence_root / "sample_freeze_receipt.json"
    cache_root.mkdir(parents=True, exist_ok=True)
    if sample_receipt_path.exists() and (cache_root / "screening_indices.npy").exists():
        sample_receipt = read_canonical_json(sample_receipt_path)
        sample_index = np.load(cache_root / "screening_indices.npy")
    else:
        sample_index, sample_receipt = freeze_stratified_sample(
            train_rows,
            years=train_years,
            phase_ids=train_phases,
            sample_size=sample_size or SCREENING_SAMPLE_ROWS,
        )
        np.save(cache_root / "screening_indices.npy", sample_index)
        write_canonical_json(sample_receipt_path, sample_receipt)
    cache = build_or_load_temporal_cache(
        cache_root=cache_root / "temporal",
        shared=shared,
        spec=spec,
        contract=temporal,
        train_rows=train_rows,
        validation_rows=validation_rows,
        chunk_size=8192,
    )
    return {
        "gate": gate,
        "shared": shared,
        "spec": spec,
        "temporal": temporal,
        "train_rows": train_rows,
        "validation_rows": validation_rows,
        "sample_index": sample_index,
        "sample_receipt": sample_receipt,
        "cache": cache,
        "ledger": ledger,
        "truncation": truncation,
        "feature_dim": spec.model_feature_dim,
        "arm": arm,
    }


def preregister(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> dict[str, object]:
    gate = verify_frozen_contracts()
    trials = [trial.as_dict() for trial in screening_trial_identities()]
    written = write_canonical_json(
        evidence_root / "preregistration.json",
        {
            "schema_id": "factorlab.reaka_stage6_parameter_calibration_preregistration@1.0",
            "status": "frozen_before_metrics",
            "route": "external_executor",
            "controller": "codex",
            "task": "stage6_parameter_calibration_preflight_only",
            "financial_identity": {
                "target": "next_nonoverlapping_h20_period_return",
                "horizon_trading_days": 20,
                "decision_cadence_trading_days": 5,
                "sequence_points": SEQUENCE_LENGTH,
                "latent_dim": LATENT_DIM,
                "operator_count": OPERATOR_COUNT,
                "transparent_trunk_coefficient": TRANSPARENT_TRUNK_COEFFICIENT,
                "universe": "full_A_effective_dated_PIT_tradable",
                "factor_identity_count": 48,
                "approved_context_state_count": 2,
            },
            "splits": {
                "train": "2009-01-01/2017-12-31",
                "internal_validation": "2018-01-01/2018-12-31",
                "selection_forbidden": ["2019", "2020"],
                "read_forbidden": ["2021-2026"],
            },
            "screening": {
                "seed": SCREENING_SEED,
                "sample_rows": SCREENING_SAMPLE_ROWS,
                "coverage_cycles": SCREENING_COVERAGE_CYCLES,
                "trials": trials,
            },
            "confirmation": {
                "seeds": list(CONFIRMATION_SEEDS),
                "coverage_cycles": CONFIRMATION_COVERAGE_CYCLES,
                "checkpoints": list(CONFIRMATION_CHECKPOINTS),
            },
            "selection_rule": "per_hidden_largest_stable_lr_then_smallest_hidden_within_one_HAC_SE",
            "old_checkpoints": "historical_only_not_continuable",
            "formal_fit_authorized": False,
            "stage7": "closed",
            "fresh_oos": False,
            "production_authority": False,
            "contract_gate": gate,
        },
    )
    usage = write_canonical_json(
        evidence_root / "data_usage_declaration.json",
        {
            "schema_id": "factorlab.data_usage_declaration@1.0",
            "development_material": ["2009-01-01/2020-12-31"],
            "calibration_train": ["2009-01-01/2017-12-31"],
            "repeat_audit_internal_validation": ["2018-01-01/2018-12-31"],
            "consumed_not_for_selection": ["2019-01-01/2020-12-31"],
            "aggregate_lockbox_and_fresh_challenge": [],
            "post_2020_rows_authorized": 0,
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    sources = write_canonical_json(
        evidence_root / "source_digest_manifest.json",
        source_digest_manifest(
            [
                CONTRACT_PATHS["catalog"],
                CONTRACT_PATHS["root_routing"],
                CONTRACT_PATHS["stage5"],
                CONTRACT_PATHS["temporal_contract"],
                CONTRACT_PATHS["portfolio_contract"],
                Path(__file__),
            ]
        ),
    )
    return {"preregistration": written, "data_usage": usage, "source_digest_manifest": sources}


def preflight(
    *,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    tensor_root: Path = DEFAULT_TENSOR_ROOT,
    supplement_root: Path = DEFAULT_SUPPLEMENT_ROOT,
    device_name: str = "cuda:0",
) -> dict[str, object]:
    started = time.perf_counter()
    preregister(evidence_root)
    device, hardware = resolve_device(device_name)
    assets = load_runtime_assets(
        tensor_root=tensor_root,
        supplement_root=supplement_root,
        cache_root=cache_root,
        evidence_root=evidence_root,
    )
    cache = cast(Stage6TemporalWindowCache, assets["cache"])
    smoke_stop = min(SMOKE_ROWS, int(cache.train.rows.shape[0]))
    smoke = {
        "returns": _writable_tensor(cache.train.returns[:smoke_stop], np.float32),
        "features": _writable_tensor(cache.train.features[:smoke_stop], np.float32),
        "targets": _writable_tensor(cache.train.targets[:smoke_stop], np.float32),
    }
    batch_size = 4096 if smoke_stop >= 4096 else max(256, smoke_stop // 2)
    parity = _precision_parity(
        feature_dim=int(assets["feature_dim"]),
        train_bundle=smoke,
        device=device,
        batch_size=min(batch_size, smoke_stop),
    )
    use_amp = device.type == "cuda" and parity.get("status") in {"passed", "cpu_only"}
    _seed_everything(SCREENING_SEED)
    model = build_calibration_model(feature_dim=int(assets["feature_dim"]), hidden_dimension=8).to(device)
    apply_declared_initialization(model, seed=SCREENING_SEED)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.0003, weight_decay=0.0)
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    tick = time.perf_counter()
    steps = max(1, smoke_stop // batch_size)
    for index in range(steps):
        start = index * batch_size
        stop = min(start + batch_size, smoke_stop)
        returns, features = _batch_slice(smoke, start, stop)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(
            device_type=device.type,
            dtype=torch.float16,
            enabled=use_amp and device.type == "cuda",
        ):
            output = cast(
                ReakaPaperTrainingOutput,
                model.training_objective(returns.to(device), features.to(device)),
            )
        output.total_loss.backward()
        optimizer.step()
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    elapsed = time.perf_counter() - tick
    rows_per_second = steps * batch_size / max(elapsed, 1e-9)
    runtime = estimate_runtime(
        rows_per_second=rows_per_second,
        screening_rows=int(np.asarray(assets["sample_index"]).size),
        confirmation_rows=int(cache.train.rows.shape[0]),
    )
    if device.type != "cuda" and float(runtime["predicted_total_seconds"]) > MAX_TOTAL_SECONDS:
        runtime["may_execute"] = False
        runtime["blocker"] = "rocm_unavailable_cpu_over_budget"
    peak_memory = int(torch.cuda.max_memory_allocated(device)) if device.type == "cuda" else None
    ledger = cast(DataBoundaryLedger, assets["ledger"])
    performance = write_canonical_json(
        evidence_root / "performance_preflight.json",
        {
            "schema_id": "factorlab.reaka_stage6_calibration_performance@1.0",
            "status": "passed" if runtime["may_execute"] else "blocked",
            "device": str(device),
            "device_name": hardware,
            "batch_size": batch_size,
            "precision_policy": "autocast_float16" if use_amp and device.type == "cuda" else "float32",
            "amp_grad_scaler": AMP_GRAD_SCALER_POLICY,
            "rows_per_second": rows_per_second,
            "smoke_rows": smoke_stop,
            "screening_rows": int(np.asarray(assets["sample_index"]).size),
            "confirmation_rows": int(cache.train.rows.shape[0]),
            "peak_memory_bytes": peak_memory,
            "preflight_wall_seconds": time.perf_counter() - started,
            "data_boundary": ledger.as_dict(),
            "truncation": assets["truncation"],
            **runtime,
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    write_canonical_json(
        evidence_root / "precision_parity.json",
        {
            **parity,
            "amp_grad_scaler": AMP_GRAD_SCALER_POLICY,
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    output_root.mkdir(parents=True, exist_ok=True)
    return {"performance": performance, "precision_parity": parity, "may_execute": bool(runtime["may_execute"])}


def _flatten_metric_row(row: Mapping[str, object]) -> dict[str, object]:
    metrics = dict(row.get("final_metrics", {}))
    health = dict(row.get("health", {}))
    return {
        "trial_id": row.get("trial_id"),
        "hidden_dimension": row.get("hidden_dimension"),
        "learning_rate": row.get("learning_rate"),
        "seed": row.get("seed"),
        "status": row.get("status"),
        "elapsed_seconds": row.get("elapsed_seconds"),
        "day_equal_rank_ic": metrics.get("day_equal_rank_ic"),
        "rank_ic_hac_se": metrics.get("rank_ic_hac_se"),
        "h20_spread": metrics.get("h20_spread"),
        "phase_stability": metrics.get("phase_stability"),
        "finite_loss": health.get("finite_loss"),
        "finite_gradients": health.get("finite_gradients"),
        "finite_parameters": health.get("finite_parameters"),
        "no_sustained_explosion": health.get("no_sustained_explosion"),
        "inner_metric_computable": health.get("inner_metric_computable"),
        "health_passed": health.get("passed"),
    }


def _maybe_stop_for_wall(started: float) -> bool:
    return (time.perf_counter() - started) > MAX_TOTAL_SECONDS


def execute(
    *,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    tensor_root: Path = DEFAULT_TENSOR_ROOT,
    supplement_root: Path = DEFAULT_SUPPLEMENT_ROOT,
    device_name: str = "cuda:0",
) -> dict[str, object]:
    performance_path = evidence_root / "performance_preflight.json"
    if not performance_path.exists():
        raise CalibrationBlocked("preflight_required_before_execute")
    performance = read_canonical_json(performance_path)
    if performance.get("may_execute") is not True:
        raise CalibrationBlocked("performance_preflight_forbids_execute")
    started = time.perf_counter()
    device, _hardware = resolve_device(device_name)
    assets = load_runtime_assets(
        tensor_root=tensor_root,
        supplement_root=supplement_root,
        cache_root=cache_root,
        evidence_root=evidence_root,
    )
    cache = cast(Stage6TemporalWindowCache, assets["cache"])
    train_full = _contiguous_split(cache, "train")
    validation = _contiguous_split(cache, "validation")
    sample_index = np.asarray(assets["sample_index"], dtype=np.int64)
    train_sample = {key: value[sample_index] for key, value in train_full.items()}
    batch_size = int(performance["batch_size"])
    use_amp = str(performance.get("precision_policy")) == "autocast_float16"
    feature_dim = int(assets["feature_dim"])
    wall_limit_hit = False
    screening_rows: list[dict[str, object]] = []
    for trial in screening_trial_identities():
        if wall_limit_hit:
            screening_rows.append(
                {
                    **trial.as_dict(),
                    "status": "not_started_wall_clock",
                    "health": TrialHealth(False, False, False, True, False).as_dict(),
                    "final_metrics": {"computable": False},
                }
            )
            continue
        result = run_declared_fit(
            hidden_dimension=trial.hidden_dimension,
            learning_rate=trial.learning_rate,
            seed=SCREENING_SEED,
            train_bundle=train_sample,
            validation_bundle=validation,
            feature_dim=feature_dim,
            device=device,
            batch_size=batch_size,
            use_amp=use_amp,
            coverage_cycles=SCREENING_COVERAGE_CYCLES,
            checkpoints=(SCREENING_COVERAGE_CYCLES,),
        )
        screening_rows.append({**trial.as_dict(), **result})
        if _maybe_stop_for_wall(started):
            wall_limit_hit = True
    lr_choices = [select_largest_stable_learning_rate(hidden, screening_rows) for hidden in HIDDEN_DIMENSIONS]
    confirmation_rows: list[dict[str, object]] = []
    for choice in lr_choices:
        hidden = int(choice["hidden_dimension"])
        rate = choice.get("selected_learning_rate")
        for seed in CONFIRMATION_SEEDS:
            if rate is None or wall_limit_hit:
                confirmation_rows.append(
                    {
                        "trial_id": f"h{hidden}_confirm",
                        "hidden_dimension": hidden,
                        "learning_rate": rate,
                        "seed": seed,
                        "status": "not_started" if rate is None else "not_started_wall_clock",
                        "health": TrialHealth(False, False, False, True, False).as_dict(),
                        "final_metrics": {"computable": False},
                        "ensemble_rank_ic": math.nan,
                    }
                )
                continue
            result = run_declared_fit(
                hidden_dimension=hidden,
                learning_rate=float(rate),
                seed=seed,
                train_bundle=train_full,
                validation_bundle=validation,
                feature_dim=feature_dim,
                device=device,
                batch_size=batch_size,
                use_amp=use_amp,
                coverage_cycles=CONFIRMATION_COVERAGE_CYCLES,
                checkpoints=CONFIRMATION_CHECKPOINTS,
            )
            metrics = dict(result.get("final_metrics", {}))
            confirmation_rows.append(
                {
                    "trial_id": f"h{hidden}_confirm",
                    "hidden_dimension": hidden,
                    "learning_rate": float(rate),
                    "seed": seed,
                    **result,
                    "ensemble_rank_ic": metrics.get("day_equal_rank_ic", math.nan),
                    "ensemble_spread": metrics.get("h20_spread", math.nan),
                    "rank_ic_hac_se": metrics.get("rank_ic_hac_se", math.inf),
                }
            )
            if _maybe_stop_for_wall(started):
                wall_limit_hit = True
    grouped: list[dict[str, object]] = []
    for hidden in HIDDEN_DIMENSIONS:
        members = [row for row in confirmation_rows if int(row["hidden_dimension"]) == hidden]
        ics = [float(row.get("ensemble_rank_ic", math.nan)) for row in members]
        spreads = [float(row.get("ensemble_spread", math.nan)) for row in members]
        health_ok = all(trial_is_numerically_healthy(dict(row.get("health", {}))) for row in members)
        health_payload = (
            TrialHealth(True, True, True, True, True).as_dict() if health_ok else TrialHealth(False, False, False, True, False).as_dict()
        )
        grouped.append(
            {
                "hidden_dimension": hidden,
                "learning_rate": members[0].get("learning_rate") if members else None,
                "ensemble_rank_ic": float(np.nanmean(ics)) if ics else math.nan,
                "ensemble_spread": float(np.nanmean(spreads)) if spreads else math.nan,
                "rank_ic_hac_se": float(np.nanmean([float(row.get("rank_ic_hac_se", math.inf)) for row in members]))
                if members
                else math.inf,
                "health": health_payload,
                "seed_results_retained": True,
            }
        )
    selection = select_smallest_hidden_within_one_se(grouped)
    ledger = cast(DataBoundaryLedger, assets["ledger"])
    multiplicity = multiplicity_receipt(screening_rows=screening_rows, confirmation_rows=confirmation_rows)
    dmd_rows = [
        {"trial_id": row.get("trial_id"), "seed": row.get("seed"), **dict(row.get("dmd", {}))}
        for row in [*screening_rows, *confirmation_rows]
        if isinstance(row.get("dmd"), dict)
    ]
    gradient_rows = []
    for row in [*screening_rows, *confirmation_rows]:
        for item in list(row.get("gradient_audit", [])):
            gradient_rows.append(
                {
                    "trial_id": row.get("trial_id"),
                    "seed": row.get("seed"),
                    **dict(item),
                }
            )
    write_canonical_json(
        evidence_root / "screening_trial_manifest.json",
        {
            "schema_id": "factorlab.reaka_stage6_screening_manifest@1.0",
            "trials": screening_rows,
            "learning_rate_choices": lr_choices,
            "wall_clock_stop": wall_limit_hit,
            "production_authority": False,
        },
    )
    _write_csv(evidence_root / "screening_metrics.csv", [_flatten_metric_row(row) for row in screening_rows])
    write_canonical_json(
        evidence_root / "confirmation_trial_manifest.json",
        {
            "schema_id": "factorlab.reaka_stage6_confirmation_manifest@1.0",
            "fits": confirmation_rows,
            "grouped": grouped,
            "wall_clock_stop": wall_limit_hit,
            "production_authority": False,
        },
    )
    _write_csv(
        evidence_root / "confirmation_metrics.csv",
        [_flatten_metric_row(row) for row in confirmation_rows],
    )
    write_canonical_json(evidence_root / "learning_rate_range_test.json", {"choices": lr_choices, "production_authority": False})
    write_canonical_json(
        evidence_root / "capacity_ablation.json", {"grouped": grouped, "selection": selection, "production_authority": False}
    )
    write_canonical_json(
        evidence_root / "dmd_initialization_receipt.json",
        {"fits": dmd_rows, "train_years_only": "2009-2017", "production_authority": False},
    )
    write_canonical_json(
        evidence_root / "initialization_variance_receipt.json",
        {
            "rule": "activation_aware_Xavier_orthogonal_chrono",
            "seeds": list(CONFIRMATION_SEEDS),
            "production_authority": False,
        },
    )
    write_canonical_json(
        evidence_root / "gradient_scale_audit.json",
        {
            "rows": gradient_rows,
            "clip": "disabled_measurement",
            "amp_grad_scaler": AMP_GRAD_SCALER_POLICY,
            "scaler_disabled_reason": (
                "rocm_gradscaler_overflowed_unclipped_grads_on_some_batches_while_unscaled_amp_and_float32_stayed_finite"
            ),
            "production_authority": False,
        },
    )
    write_canonical_json(
        evidence_root / "unclipped_gradient_distribution.json",
        {
            "rows": gradient_rows,
            "clip_applied": False,
            "amp_grad_scaler": AMP_GRAD_SCALER_POLICY,
            "production_authority": False,
        },
    )
    write_canonical_json(
        evidence_root / "coverage_convergence_receipt.json",
        {
            "checkpoints": list(CONFIRMATION_CHECKPOINTS),
            "confirmation": [
                {"trial_id": row.get("trial_id"), "seed": row.get("seed"), "curve": row.get("checkpoint_metrics")}
                for row in confirmation_rows
            ],
            "production_authority": False,
        },
    )
    write_canonical_json(evidence_root / "multiplicity_receipt.json", multiplicity)
    write_canonical_json(
        evidence_root / "selected_calibration.json",
        {**selection, "data_boundary": ledger.as_dict(), "fresh_oos": False, "production_authority": False},
    )
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "runtime_summary.json").write_text(
        json.dumps(
            {
                "elapsed_seconds": time.perf_counter() - started,
                "wall_clock_stop": wall_limit_hit,
                "device": str(device),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "selection": selection,
        "multiplicity": multiplicity,
        "wall_clock_stop": wall_limit_hit,
        "elapsed_seconds": time.perf_counter() - started,
        "ledger": ledger.as_dict(),
    }


def _selected_confirmation_dmd(
    fits: Sequence[Mapping[str, object]],
    selected: Mapping[str, object],
) -> dict[str, object]:
    hidden = selected.get("selected_hidden_dimension")
    wanted = f"h{hidden}_confirm"
    matches = [dict(row) for row in fits if str(row.get("trial_id")) == wanted]
    if not matches:
        raise CalibrationBlocked("selected_confirmation_dmd_missing")
    for row in matches:
        if int(row.get("seed", -1)) == SCREENING_SEED:
            return row
    return matches[0]


def _receipt_digest(path: Path, fallback: str) -> str:
    if not path.exists():
        return fallback
    payload = read_canonical_json(path)
    digest = payload.get("canonical_digest")
    return str(digest) if digest else file_sha256(path)


def validate_run(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> dict[str, object]:
    catalog = build_parameter_catalog()
    root = build_current_root_resolution_receipt(catalog_digest=str(catalog["canonical_digest"]))
    stage5 = read_canonical_json(CONTRACT_PATHS["stage5"])
    selected = read_canonical_json(evidence_root / "selected_calibration.json")
    dmd = read_canonical_json(evidence_root / "dmd_initialization_receipt.json")
    fits = [dict(row) for row in list(dmd.get("fits", []))]
    selected_dmd = _selected_confirmation_dmd(fits, selected) if selected.get("status") == "selected" else {}
    receipts = {
        "capacity_ablation": _receipt_digest(evidence_root / "capacity_ablation.json", "missing"),
        "checkpoint_attempt_receipt": _receipt_digest(evidence_root / "confirmation_trial_manifest.json", "missing"),
        "coverage_convergence_receipt": _receipt_digest(evidence_root / "coverage_convergence_receipt.json", "missing"),
        "cross_fitted_residual_predictability": "not_applicable_diffusion_not_authorized",
        "decoder_reconstruction_noise_floor": _receipt_digest(evidence_root / "coverage_convergence_receipt.json", "missing"),
        "dmd_initialization_receipt": _receipt_digest(evidence_root / "dmd_initialization_receipt.json", "missing"),
        "effective_dated_universe": EXPECTED_STAGE5_DIGEST,
        "effective_rank": EXPECTED_TEMPORAL_DIGEST,
        "gradient_scale_audit": _receipt_digest(evidence_root / "gradient_scale_audit.json", "missing"),
        "initialization_variance_receipt": _receipt_digest(evidence_root / "initialization_variance_receipt.json", "missing"),
        "latent_gauge_receipt": _receipt_digest(evidence_root / "dmd_initialization_receipt.json", "missing"),
        "learning_rate_range_test": _receipt_digest(evidence_root / "learning_rate_range_test.json", "missing"),
        "multiplicity_receipt": _receipt_digest(evidence_root / "multiplicity_receipt.json", "missing"),
        "portfolio_execution_contract": file_sha256(CONTRACT_PATHS["portfolio_contract"]),
        "prefix_invariance": EXPECTED_TEMPORAL_DIGEST,
        "residual_capacity_ablation": "not_applicable_diffusion_not_authorized",
        "residual_target_gradient_test": "stop_gradient_and_residual_module_na",
        "selector_entropy_gradient_surface": "not_applicable_operator_count_1",
        "solver_equivalence_preflight": _receipt_digest(evidence_root / "precision_parity.json", "missing"),
        "spectral_stability": _receipt_digest(evidence_root / "dmd_initialization_receipt.json", "missing"),
        "unclipped_gradient_distribution": _receipt_digest(evidence_root / "unclipped_gradient_distribution.json", "missing"),
    }
    instantiation: dict[str, object]
    if selected.get("status") != "selected":
        instantiation = {
            "schema_id": "factorlab.reaka_training_parameter_instantiation@1.0",
            "status": "blocked",
            "reason": selected.get("status"),
            "parameter_values": {},
            "evidence_receipts": receipts,
            "formal_fit_started": False,
            "production_authority": False,
        }
        instantiation["canonical_digest"] = canonical_digest(instantiation)
        validation = {
            "schema_id": "factorlab.reaka_training_parameter_instantiation_validation@1.0",
            "status": "blocked",
            "blockers": ["calibration_selection_not_unique"],
            "production_authority": False,
        }
        validation["canonical_digest"] = canonical_digest(validation)
    else:
        instantiation = build_formal_fit_instantiation(
            selected=selected,
            receipts=receipts,
            catalog=catalog,
            root=root,
            stage5=stage5,
            clip_norm="disabled_unclipped_preflight_finite",
            coverage=CONFIRMATION_COVERAGE_CYCLES,
            dmd=selected_dmd,
        )
        validation = validate_training_parameter_instantiation(
            catalog,
            instantiation,
            root_resolution_receipt=root,
        )
    write_canonical_json(evidence_root / "formal_fit_instantiation.json", instantiation)
    write_canonical_json(evidence_root / "formal_fit_instantiation_validation.json", validation)
    ledger = dict(selected.get("data_boundary", {}))
    report = write_canonical_json(
        evidence_root / "validation_report.json",
        {
            "schema_id": "factorlab.reaka_stage6_calibration_validation@1.0",
            "status": validation.get("status"),
            "formal_fit_gate_ready": validation.get("status") == "passed",
            "formal_fit_started": False,
            "selection": selected,
            "data_boundary": ledger,
            "post_2020_rows_read": ledger.get("post_2020_rows_read", 0),
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    return {
        "instantiation": instantiation,
        "validation": validation,
        "report": report,
    }


__all__ = [
    "CalibrationBlocked",
    "CalibrationContractError",
    "CalibrationTrial",
    "DataBoundaryLedger",
    "TrialHealth",
    "AMP_GRAD_SCALER_POLICY",
    "assert_diffusion_not_applicable",
    "assert_k1_selector_not_applicable",
    "build_calibration_model",
    "build_formal_fit_instantiation",
    "day_equal_rank_metrics",
    "execute",
    "freeze_stratified_sample",
    "k1_selector_values",
    "load_runtime_assets",
    "multiplicity_receipt",
    "newey_west_mean_standard_error",
    "preflight",
    "preregister",
    "regularized_dmd_operator",
    "reject_old_checkpoint",
    "reject_outer_year_rows",
    "run_declared_fit",
    "screening_trial_identities",
    "select_largest_stable_learning_rate",
    "select_smallest_hidden_within_one_se",
    "validate_run",
    "verify_frozen_contracts",
]
