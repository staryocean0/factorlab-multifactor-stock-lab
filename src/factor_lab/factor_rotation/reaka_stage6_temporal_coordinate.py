"""Time-coordinate contracts for mathematically coherent REAKA adapters."""

# pyright: reportArgumentType=false, reportCallIssue=false

from __future__ import annotations

import hashlib
import json
import math
import shutil
from collections.abc import Iterator
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Final, Literal

import numpy as np
import torch
from numpy.typing import NDArray
from torch import Tensor

from factor_lab.factor_rotation.reaka_stage6_daily_engine import (
    ROW_WIDTH,
    Stage6SharedTensor,
    Stage6TaskSpec,
    _channel_value_matrix,
    decision_day_positions,
)
from factor_lab.governance.canonicalization import canonical_digest

TemporalAdapterMode = Literal["paper_one_step", "periodic_one_step"]
TEMPORAL_CONTRACT_SCHEMA_ID: Final = "factorlab.reaka_stage6_temporal_coordinate@2.0"
TEMPORAL_CACHE_SCHEMA_ID: Final = "factorlab.reaka_stage6_temporal_cache@1.0"


def _rows_digest(rows: NDArray[np.int64]) -> str:
    return "sha256:" + hashlib.sha256(np.ascontiguousarray(rows, dtype=np.int64).tobytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class Stage6TemporalCoordinateContract:
    """Physical time and random-variable identity for one REAKA task."""

    adapter_id: str
    mode: TemporalAdapterMode
    decision_step_trading_days: int
    feature_step_trading_days: int
    historical_return_period_trading_days: int
    latent_transition_step_trading_days: int
    decoder_reconstruction_step_trading_days: int
    residual_step_trading_days: int
    forecast_horizon_trading_days: int
    sequence_length_points: int
    historical_return_definition: str
    forecast_target_definition: str
    target_transform: str
    decision_grid_anchor: str = "2008-12-01"

    def validate(self) -> None:
        if not self.adapter_id:
            raise ValueError("stage6_temporal_adapter_id_empty")
        positive = {
            "decision_step": self.decision_step_trading_days,
            "feature_step": self.feature_step_trading_days,
            "historical_return_period": self.historical_return_period_trading_days,
            "latent_transition_step": self.latent_transition_step_trading_days,
            "decoder_reconstruction_step": self.decoder_reconstruction_step_trading_days,
            "residual_step": self.residual_step_trading_days,
            "forecast_horizon": self.forecast_horizon_trading_days,
            "sequence_length": self.sequence_length_points,
        }
        for name, value in positive.items():
            if value <= 0:
                raise ValueError(f"stage6_temporal_{name}_must_be_positive")
        dynamic_steps = {
            self.feature_step_trading_days,
            self.historical_return_period_trading_days,
            self.latent_transition_step_trading_days,
            self.decoder_reconstruction_step_trading_days,
            self.residual_step_trading_days,
            self.forecast_horizon_trading_days,
        }
        if len(dynamic_steps) != 1:
            raise ValueError("stage6_temporal_random_process_step_mismatch")
        if self.latent_transition_step_trading_days % self.decision_step_trading_days != 0:
            raise ValueError("stage6_temporal_decision_step_not_phase_divisor")
        if self.sequence_length_points < 2:
            raise ValueError("stage6_temporal_sequence_too_short")
        if self.target_transform not in {
            "training_prefix_standardized_period_return",
            "training_prefix_standardized_period_return_plus_cross_sectional_rank_audit",
        }:
            raise ValueError("stage6_temporal_target_transform_unknown")
        if self.mode == "paper_one_step" and (self.decision_step_trading_days != self.latent_transition_step_trading_days):
            raise ValueError("stage6_temporal_paper_one_step_decision_mismatch")

    @property
    def phase_count(self) -> int:
        self.validate()
        return self.latent_transition_step_trading_days // self.decision_step_trading_days

    @property
    def endpoint_span_trading_days(self) -> int:
        return (self.sequence_length_points - 1) * self.feature_step_trading_days

    @property
    def required_history_trading_days(self) -> int:
        return self.sequence_length_points * self.historical_return_period_trading_days

    @property
    def adjacent_decision_label_overlap_fraction(self) -> float:
        return max(
            0.0,
            1.0 - self.decision_step_trading_days / self.forecast_horizon_trading_days,
        )

    def as_dict(self) -> dict[str, object]:
        self.validate()
        payload: dict[str, object] = {
            "schema_id": TEMPORAL_CONTRACT_SCHEMA_ID,
            **asdict(self),
            "phase_count": self.phase_count,
            "endpoint_span_trading_days": self.endpoint_span_trading_days,
            "required_history_trading_days": self.required_history_trading_days,
            "adjacent_decision_label_overlap_fraction": (self.adjacent_decision_label_overlap_fraction),
            "hard_invariants": {
                "return_feature_koopman_decoder_residual_forecast_same_step": True,
                "historical_returns_mature_before_decision": True,
                "future_target_absent_from_model_input": True,
                "phase_lanes_are_correlated_boundary_views": True,
                "label_only_horizon_substitution_forbidden": True,
            },
            "fresh_oos": False,
            "production_authority": False,
        }
        payload["canonical_digest"] = canonical_digest(payload)
        return payload


def h20_periodic_coordinate_contract() -> Stage6TemporalCoordinateContract:
    """H20 as a one-step 20-session process launched every five sessions."""

    contract = Stage6TemporalCoordinateContract(
        adapter_id="reaka_h20_periodic_one_step_v2",
        mode="periodic_one_step",
        decision_step_trading_days=5,
        feature_step_trading_days=20,
        historical_return_period_trading_days=20,
        latent_transition_step_trading_days=20,
        decoder_reconstruction_step_trading_days=20,
        residual_step_trading_days=20,
        forecast_horizon_trading_days=20,
        sequence_length_points=10,
        historical_return_definition=("matured_t_plus_1_open_to_period_end_close_return_ending_at_feature_endpoint"),
        forecast_target_definition=("t_plus_1_open_to_twentieth_trading_day_close_after_decision"),
        target_transform=("training_prefix_standardized_period_return_plus_cross_sectional_rank_audit"),
    )
    contract.validate()
    return contract


def old_h20_hybrid_contract_for_rejection() -> Stage6TemporalCoordinateContract:
    """Historical invalid shape retained only as a regression counterexample."""

    return Stage6TemporalCoordinateContract(
        adapter_id="historical_invalid_daily_latent_h20_label",
        mode="periodic_one_step",
        decision_step_trading_days=5,
        feature_step_trading_days=1,
        historical_return_period_trading_days=1,
        latent_transition_step_trading_days=1,
        decoder_reconstruction_step_trading_days=20,
        residual_step_trading_days=1,
        forecast_horizon_trading_days=20,
        sequence_length_points=40,
        historical_return_definition="daily_open_to_close",
        forecast_target_definition="forward_twenty_session_return",
        target_transform="training_prefix_standardized_period_return",
    )


def _phase_ids(
    shared: Stage6SharedTensor,
    decision_positions: NDArray[np.int64],
    contract: Stage6TemporalCoordinateContract,
) -> NDArray[np.int64]:
    anchor = np.datetime64(contract.decision_grid_anchor)
    anchor_positions = np.flatnonzero(shared.calendar == anchor)
    if anchor_positions.size != 1:
        raise RuntimeError("stage6_temporal_anchor_missing")
    relative = decision_positions - int(anchor_positions[0])
    return (relative // contract.decision_step_trading_days) % contract.phase_count


def build_temporal_rows(
    *,
    shared: Stage6SharedTensor,
    spec: Stage6TaskSpec,
    contract: Stage6TemporalCoordinateContract,
    common_support_factor_ids: tuple[str, ...],
) -> dict[int, NDArray[np.int64]]:
    """Build weekly decisions backed by matured non-overlapping H20 chains."""

    contract.validate()
    if spec.horizon_days != contract.forecast_horizon_trading_days:
        raise ValueError("stage6_temporal_spec_horizon_mismatch")
    if spec.cadence_id != "weekly":
        raise ValueError("stage6_temporal_h20_requires_weekly_decision_grid")
    factor_positions = {name: index for index, name in enumerate(shared.factor_ids)}
    try:
        support_indices = np.asarray(
            [factor_positions[name] for name in common_support_factor_ids],
            dtype=np.int64,
        )
    except KeyError as exc:
        raise ValueError(f"stage6_temporal_support_factor_missing:{exc.args[0]}") from exc
    decisions = decision_day_positions(shared, spec.cadence_id)
    history = contract.required_history_trading_days
    horizon = contract.forecast_horizon_trading_days
    decisions = decisions[(decisions >= history) & (decisions + horizon < shared.day_count)]
    _ = _phase_ids(shared, decisions, contract)
    years = shared.calendar.astype("datetime64[Y]").astype(int) + 1970
    result: dict[int, list[NDArray[np.int64]]] = {}
    endpoint_offsets = np.arange(
        -(contract.sequence_length_points - 1) * contract.feature_step_trading_days,
        1,
        contract.feature_step_trading_days,
        dtype=np.int64,
    )
    for decision in decisions:
        endpoints = decision + endpoint_offsets
        return_starts = endpoints - contract.historical_return_period_trading_days
        historical = shared.labels[
            return_starts,
            :,
            spec.horizon_index,
        ]
        historical_ok = np.isfinite(historical).all(axis=0)
        target_ok = np.isfinite(shared.labels[decision, :, spec.horizon_index])
        support_ok = shared.base_available[decision][:, support_indices].any(axis=1)
        usable = historical_ok & target_ok & shared.entry_ok[decision].astype(bool) & support_ok
        symbols = np.flatnonzero(usable).astype(np.int64)
        if symbols.size == 0:
            continue
        exit_year = int(years[decision + horizon])
        rows = np.column_stack(
            (
                np.full(symbols.size, decision, dtype=np.int64),
                symbols,
                np.full(symbols.size, exit_year, dtype=np.int64),
            )
        )
        result.setdefault(int(years[decision]), []).append(rows)
    packed = {year: np.concatenate(parts, axis=0) for year, parts in sorted(result.items()) if parts}
    if not packed:
        raise ValueError("stage6_temporal_rows_empty")
    return packed


def temporalize_task_spec(
    *,
    spec: Stage6TaskSpec,
    contract: Stage6TemporalCoordinateContract,
) -> Stage6TaskSpec:
    """Bind an input-channel identity to the temporal adapter's point count."""

    contract.validate()
    if spec.horizon_days != contract.forecast_horizon_trading_days:
        raise ValueError("stage6_temporal_spec_horizon_mismatch")
    if spec.cadence_id != "weekly":
        raise ValueError("stage6_temporal_h20_requires_weekly_decision_grid")
    return replace(
        spec,
        sequence_length_candidates=(contract.sequence_length_points,),
        tensor_digest=canonical_digest(
            {
                "base_tensor_digest": spec.tensor_digest,
                "temporal_contract_digest": contract.as_dict()["canonical_digest"],
            }
        ),
    )


def filter_temporal_rows_by_exit_year(
    rows: NDArray[np.int64],
    *,
    allowed_years: tuple[int, ...],
    decision_year: int,
    calendar: NDArray[np.datetime64],
) -> NDArray[np.int64]:
    rows = np.asarray(rows, dtype=np.int64)
    if rows.ndim != 2 or rows.shape[1] != ROW_WIDTH:
        raise ValueError("stage6_temporal_rows_shape_invalid")
    years = calendar[rows[:, 0]].astype("datetime64[Y]").astype(int) + 1970
    if not bool((years == decision_year).all()):
        raise ValueError("stage6_temporal_decision_year_mismatch")
    return rows[np.isin(rows[:, 2], np.asarray(allowed_years, dtype=np.int64))]


def temporal_return_stats(
    *,
    shared: Stage6SharedTensor,
    spec: Stage6TaskSpec,
    rows: NDArray[np.int64],
    contract: Stage6TemporalCoordinateContract,
) -> tuple[float, float]:
    endpoints = (
        rows[:, 0, None]
        + np.arange(
            -(contract.sequence_length_points - 1) * contract.feature_step_trading_days,
            1,
            contract.feature_step_trading_days,
            dtype=np.int64,
        )[None, :]
    )
    starts = endpoints - contract.historical_return_period_trading_days
    symbols = np.broadcast_to(rows[:, 1, None], starts.shape)
    values = shared.labels[starts, symbols, spec.horizon_index]
    if not np.isfinite(values).all():
        raise ValueError("stage6_temporal_historical_return_nonfinite")
    mean = float(values.mean(dtype=np.float64))
    scale = float(values.std(dtype=np.float64))
    if not math.isfinite(mean) or not math.isfinite(scale) or scale < 1e-8:
        raise ValueError("stage6_temporal_return_stats_invalid")
    return mean, scale


def assemble_temporal_windows(
    *,
    shared: Stage6SharedTensor,
    spec: Stage6TaskSpec,
    rows: NDArray[np.int64],
    contract: Stage6TemporalCoordinateContract,
    return_mean: float,
    return_scale: float,
) -> tuple[Tensor, Tensor, Tensor, Tensor, Tensor]:
    """Assemble aligned H20 histories and the unseen next-period target."""

    contract.validate()
    rows = np.asarray(rows, dtype=np.int64)
    if rows.size == 0 or rows.ndim != 2 or rows.shape[1] != ROW_WIDTH:
        raise ValueError("stage6_temporal_window_rows_invalid")
    offsets = np.arange(
        -(contract.sequence_length_points - 1) * contract.feature_step_trading_days,
        1,
        contract.feature_step_trading_days,
        dtype=np.int64,
    )
    endpoints = rows[:, 0, None] + offsets[None, :]
    starts = endpoints - contract.historical_return_period_trading_days
    symbols = np.broadcast_to(rows[:, 1, None], endpoints.shape)
    returns = shared.labels[starts, symbols, spec.horizon_index]
    if not np.isfinite(returns).all():
        raise ValueError("stage6_temporal_input_contains_unmatured_return")
    standardized = ((returns.astype(np.float64) - return_mean) / return_scale).astype(np.float32)
    values, availability = _channel_value_matrix(
        shared,
        spec.channels,
        endpoints,
        symbols,
    )
    features = np.concatenate((values, availability.astype(np.float32)), axis=-1)
    forecast_target = shared.labels[rows[:, 0], rows[:, 1], spec.horizon_index]
    target_finite = np.isfinite(forecast_target)
    if not bool(target_finite.all()):
        raise ValueError("stage6_temporal_forecast_target_nonfinite")
    phase_ids = _phase_ids(shared, rows[:, 0], contract)
    return (
        torch.from_numpy(np.ascontiguousarray(standardized)),
        torch.from_numpy(np.ascontiguousarray(features)),
        torch.from_numpy(np.ascontiguousarray(availability)),
        torch.from_numpy(np.ascontiguousarray(forecast_target.astype(np.float32))),
        torch.from_numpy(np.ascontiguousarray(phase_ids.astype(np.int64))),
    )


def _open_memmap(path: Path, *, dtype: object, shape: tuple[int, ...]) -> np.memmap:
    return np.lib.format.open_memmap(path, mode="w+", dtype=dtype, shape=shape)


@dataclass(slots=True)
class _TemporalCachedSplit:
    rows: NDArray[np.int64]
    returns: np.memmap
    features: np.memmap
    targets: np.memmap
    phase_ids: np.memmap

    @classmethod
    def load(cls, root: Path, name: str) -> _TemporalCachedSplit:
        return cls(
            rows=np.load(root / f"{name}_rows.npy", mmap_mode="r"),
            returns=np.load(root / f"{name}_returns.npy", mmap_mode="r"),
            features=np.load(root / f"{name}_features.npy", mmap_mode="r"),
            targets=np.load(root / f"{name}_targets.npy", mmap_mode="r"),
            phase_ids=np.load(root / f"{name}_phase_ids.npy", mmap_mode="r"),
        )

    def tensors(self, indices: NDArray[np.int64] | slice) -> tuple[Tensor, Tensor, Tensor, Tensor]:
        def _copy(array: np.ndarray | np.memmap, dtype: object) -> np.ndarray:
            return np.array(array[indices], dtype=dtype, order="C", copy=True)

        return (
            torch.from_numpy(_copy(self.returns, np.float32)),
            torch.from_numpy(_copy(self.features, np.float32)),
            torch.from_numpy(_copy(self.targets, np.float32)),
            torch.from_numpy(_copy(self.phase_ids, np.int64)),
        )


@dataclass(slots=True)
class Stage6TemporalWindowCache:
    root: Path
    manifest: dict[str, object]
    train: _TemporalCachedSplit
    validation: _TemporalCachedSplit

    @classmethod
    def load(cls, root: Path) -> Stage6TemporalWindowCache:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        observed = str(manifest.pop("canonical_digest", ""))
        if canonical_digest(manifest) != observed:
            raise RuntimeError("stage6_temporal_cache_manifest_digest_mismatch")
        manifest["canonical_digest"] = observed
        if manifest.get("schema_id") != TEMPORAL_CACHE_SCHEMA_ID:
            raise RuntimeError("stage6_temporal_cache_schema_mismatch")
        return cls(
            root=root,
            manifest=manifest,
            train=_TemporalCachedSplit.load(root, "train"),
            validation=_TemporalCachedSplit.load(root, "validation"),
        )

    def load_split_indices(
        self,
        split: Literal["train", "validation"],
        indices: NDArray[np.int64] | slice,
    ) -> tuple[Tensor, Tensor, Tensor, Tensor]:
        selected = self.train if split == "train" else self.validation
        return selected.tensors(indices)

    def split_row_count(self, split: Literal["train", "validation"]) -> int:
        """Return a split size without materializing cached arrays."""

        selected = self.train if split == "train" else self.validation
        return int(selected.rows.shape[0])

    def split_storage_bytes(self, split: Literal["train", "validation"]) -> int:
        """Return mmap-backed bytes for performance admission receipts."""

        selected = self.train if split == "train" else self.validation
        return int(
            selected.rows.nbytes + selected.returns.nbytes + selected.features.nbytes + selected.targets.nbytes + selected.phase_ids.nbytes
        )

    def batch_slices(
        self,
        split: Literal["train", "validation"],
        *,
        batch_size: int,
        seed: int | None = None,
    ) -> tuple[slice, ...]:
        """Plan contiguous batches, optionally shuffling only batch order."""

        if batch_size <= 0:
            raise ValueError("stage6_temporal_batch_size_must_be_positive")
        count = self.split_row_count(split)
        batches = [slice(start, min(start + batch_size, count)) for start in range(0, count, batch_size)]
        if seed is not None:
            np.random.default_rng(seed).shuffle(batches)
        return tuple(batches)

    def iter_split_batches(
        self,
        split: Literal["train", "validation"],
        *,
        batch_size: int,
        seed: int | None = None,
    ) -> Iterator[tuple[slice, tuple[Tensor, Tensor, Tensor, Tensor]]]:
        """Yield one copied batch while the full split remains mmap-backed."""

        for batch_slice in self.batch_slices(
            split,
            batch_size=batch_size,
            seed=seed,
        ):
            yield batch_slice, self.load_split_indices(split, batch_slice)


def _write_temporal_split(
    *,
    root: Path,
    name: str,
    rows: NDArray[np.int64],
    shared: Stage6SharedTensor,
    spec: Stage6TaskSpec,
    contract: Stage6TemporalCoordinateContract,
    return_mean: float,
    return_scale: float,
    chunk_size: int,
) -> None:
    count = rows.shape[0]
    np.save(root / f"{name}_rows.npy", rows.astype(np.int64, copy=False))
    returns = _open_memmap(
        root / f"{name}_returns.npy",
        dtype=np.float32,
        shape=(count, contract.sequence_length_points),
    )
    features = _open_memmap(
        root / f"{name}_features.npy",
        dtype=np.float32,
        shape=(count, contract.sequence_length_points, spec.model_feature_dim),
    )
    targets = _open_memmap(root / f"{name}_targets.npy", dtype=np.float32, shape=(count,))
    phases = _open_memmap(root / f"{name}_phase_ids.npy", dtype=np.int64, shape=(count,))
    for start in range(0, count, chunk_size):
        stop = min(start + chunk_size, count)
        batch = assemble_temporal_windows(
            shared=shared,
            spec=spec,
            rows=rows[start:stop],
            contract=contract,
            return_mean=return_mean,
            return_scale=return_scale,
        )
        returns[start:stop] = batch[0].numpy()
        features[start:stop] = batch[1].numpy()
        targets[start:stop] = batch[3].numpy()
        phases[start:stop] = batch[4].numpy()
    for array in (returns, features, targets, phases):
        array.flush()


def build_or_load_temporal_cache(
    *,
    cache_root: Path,
    shared: Stage6SharedTensor,
    spec: Stage6TaskSpec,
    contract: Stage6TemporalCoordinateContract,
    train_rows: NDArray[np.int64],
    validation_rows: NDArray[np.int64],
    chunk_size: int = 4096,
) -> Stage6TemporalWindowCache:
    """Materialize one exact temporal coordinate once for all model arms."""

    contract.validate()
    return_mean, return_scale = temporal_return_stats(
        shared=shared,
        spec=spec,
        rows=train_rows,
        contract=contract,
    )
    identity: dict[str, object] = {
        "schema_id": TEMPORAL_CACHE_SCHEMA_ID,
        "temporal_contract_digest": contract.as_dict()["canonical_digest"],
        "task_spec_digest": spec.as_dict()["canonical_digest"],
        "shared_tensor_digest": shared.manifest_digest,
        "train_row_count": int(train_rows.shape[0]),
        "validation_row_count": int(validation_rows.shape[0]),
        "train_rows_digest": _rows_digest(train_rows),
        "validation_rows_digest": _rows_digest(validation_rows),
        "return_mean": return_mean,
        "return_scale": return_scale,
        "feature_dim": spec.model_feature_dim,
        "sequence_length_points": contract.sequence_length_points,
        "future_target_stored_separately_from_model_inputs": True,
        "post_2020_rows_read": 0,
        "fresh_oos": False,
        "production_authority": False,
    }
    expected = canonical_digest(identity)
    if (cache_root / "manifest.json").exists():
        cached = Stage6TemporalWindowCache.load(cache_root)
        if cached.manifest["canonical_digest"] == expected:
            return cached
        raise RuntimeError("stage6_temporal_cache_identity_conflict")
    estimated = (train_rows.shape[0] + validation_rows.shape[0]) * contract.sequence_length_points * (4 + 4 * spec.model_feature_dim)
    cache_root.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(cache_root.parent).free < int(estimated * 1.2):
        raise RuntimeError("stage6_temporal_cache_insufficient_disk")
    building = cache_root.with_name(cache_root.name + ".building")
    if building.exists():
        shutil.rmtree(building)
    building.mkdir(parents=True, exist_ok=False)
    _write_temporal_split(
        root=building,
        name="train",
        rows=train_rows,
        shared=shared,
        spec=spec,
        contract=contract,
        return_mean=return_mean,
        return_scale=return_scale,
        chunk_size=chunk_size,
    )
    _write_temporal_split(
        root=building,
        name="validation",
        rows=validation_rows,
        shared=shared,
        spec=spec,
        contract=contract,
        return_mean=return_mean,
        return_scale=return_scale,
        chunk_size=chunk_size,
    )
    identity["canonical_digest"] = expected
    (building / "manifest.json").write_text(
        json.dumps(identity, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    building.rename(cache_root)
    return Stage6TemporalWindowCache.load(cache_root)


__all__ = [
    "TEMPORAL_CONTRACT_SCHEMA_ID",
    "TEMPORAL_CACHE_SCHEMA_ID",
    "Stage6TemporalWindowCache",
    "Stage6TemporalCoordinateContract",
    "assemble_temporal_windows",
    "build_temporal_rows",
    "build_or_load_temporal_cache",
    "filter_temporal_rows_by_exit_year",
    "h20_periodic_coordinate_contract",
    "old_h20_hybrid_contract_for_rejection",
    "temporal_return_stats",
    "temporalize_task_spec",
]
