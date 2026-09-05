# pyright: reportAny=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false, reportAttributeAccessIssue=false
# pyright: reportIndexIssue=false, reportArgumentType=false
# pyright: reportReturnType=false, reportOperatorIssue=false
# pyright: reportCallIssue=false, reportGeneralTypeIssues=false
# pyright: reportUnusedCallResult=false
"""P6.3 intraday K1/r0 input store and result-free parameter preflight."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import numpy as np
import pandas as pd
import torch
from numpy.typing import NDArray

from factor_lab.factor_rotation.orthogonal_index_timing_transport_ot1_v1 import (
    MARKET_FACTOR_ID,
    SIZE_FACTOR_ID,
    variant_ids,
)
from factor_lab.factor_rotation.reaka_paper_v1 import ReakaPaperConfig
from factor_lab.factor_rotation.reaka_stage6_daily_engine import Stage6ReakaModel
from factor_lab.factor_rotation.reaka_stage6_parameter_calibration import (
    apply_declared_initialization,
)
from factor_lab.governance.canonicalization import canonical_digest

SCHEMA_ID: Final = "factorlab.reaka_intraday_K1_preflight@1.0"
STORE_SCHEMA_ID: Final = "factorlab.reaka_intraday_K1_input_store@1.0"
VALIDATION_SCHEMA_ID: Final = "factorlab.reaka_intraday_K1_preflight_validation@1.0"
CLOCKS: Final = ("14:30", "14:45")
CLOCK_SUFFIX: Final = {"14:30": "1430", "14:45": "1445"}
FEATURE_DIM: Final = 71
FACTOR_COUNT: Final = 14
SEQUENCE_POINTS: Final = 10
HORIZON_DAYS: Final = 20
LR_GRID: Final = (1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1, 3e-1, 1.0)
CAPACITY_ROOTS: Final = ((8, 8), (16, 16), (16, 32))
SEED: Final = 11
COMPATIBILITY_REQUIRED_FIELDS: Final = (
    "Delta_x_days",
    "Delta_y_days",
    "H_days",
    "L_points",
    "W_days",
    "tau_x_method",
    "tau_s_method",
    "q_h",
    "q_w",
    "q_x",
    "q_s",
    "q_x_status",
    "q_s_status",
    "r_eff",
    "latent_dimension",
    "operator_count",
    "n_eff_method",
    "n_k_eff_method",
    "capacity_support",
    "overlap_inference",
    "post_training_operator_obligations",
)
STORE_FILES: Final = (
    "calendar.npy",
    "symbols.npy",
    "factor_ids.json",
    "variant_ids.json",
    "epsilon_history.npy",
    "epsilon_future.npy",
    "state_values.npy",
    "state_available.npy",
    "exposure_decision_positions.npy",
    "stock_factor_exposures.npy",
    "exposure_reliability.npy",
    "exposure_available.npy",
    "inference_rows.npy",
    "labelled_row_indices.npy",
    "feature_registry.json",
    "manifest.json",
)


@dataclass(frozen=True, slots=True)
class IntradayK1InputStore:
    root: Path
    calendar: NDArray[np.datetime64]
    symbols: NDArray[np.str_]
    factor_ids: tuple[str, ...]
    epsilon_history: NDArray[np.float32]
    epsilon_future: NDArray[np.float32]
    state_values: NDArray[np.float32]
    state_available: NDArray[np.uint8]
    exposure_decision_positions: NDArray[np.int64]
    stock_factor_exposures: NDArray[np.float32]
    exposure_reliability: NDArray[np.float32]
    exposure_available: NDArray[np.uint8]
    inference_rows: NDArray[np.int64]
    labelled_row_indices: NDArray[np.int64]

    @classmethod
    def load(cls, root: Path) -> IntradayK1InputStore:
        factor_payload = read_json(root / "factor_ids.json")
        return cls(
            root=root,
            calendar=np.load(root / "calendar.npy", mmap_mode="r"),
            symbols=np.load(root / "symbols.npy", mmap_mode="r").astype(str),
            factor_ids=tuple(str(value) for value in factor_payload["factor_ids"]),
            epsilon_history=np.load(root / "epsilon_history.npy", mmap_mode="r"),
            epsilon_future=np.load(root / "epsilon_future.npy", mmap_mode="r"),
            state_values=np.load(root / "state_values.npy", mmap_mode="r"),
            state_available=np.load(root / "state_available.npy", mmap_mode="r"),
            exposure_decision_positions=np.load(root / "exposure_decision_positions.npy", mmap_mode="r"),
            stock_factor_exposures=np.load(root / "stock_factor_exposures.npy", mmap_mode="r"),
            exposure_reliability=np.load(root / "exposure_reliability.npy", mmap_mode="r"),
            exposure_available=np.load(root / "exposure_available.npy", mmap_mode="r"),
            inference_rows=np.load(root / "inference_rows.npy", mmap_mode="r"),
            labelled_row_indices=np.load(root / "labelled_row_indices.npy", mmap_mode="r"),
        )

    def assemble_inputs(
        self,
        indices: NDArray[np.int64],
    ) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
        take = np.asarray(indices, dtype=np.int64)
        rows = np.asarray(self.inference_rows[take], dtype=np.int64)
        endpoints = (
            rows[:, 0, None]
            + np.arange(
                -(SEQUENCE_POINTS - 1) * HORIZON_DAYS,
                1,
                HORIZON_DAYS,
                dtype=np.int64,
            )[None, :]
        )
        symbols = np.broadcast_to(rows[:, 1, None], endpoints.shape)
        variants = np.broadcast_to((rows[:, 1] % 5 + 1)[:, None], endpoints.shape)
        history = np.asarray(self.epsilon_history[endpoints, symbols], dtype=np.float32)
        state = np.asarray(self.state_values[variants, endpoints], dtype=np.float32)
        state_mask = np.asarray(self.state_available[variants, endpoints], dtype=np.float32)
        exposure_index = np.searchsorted(
            self.exposure_decision_positions,
            endpoints,
            side="left",
        )
        if (exposure_index >= len(self.exposure_decision_positions)).any() or not np.array_equal(
            self.exposure_decision_positions[exposure_index], endpoints
        ):
            raise ValueError("reaka_K1_exposure_endpoint_not_exact_D5")
        beta = np.asarray(
            self.stock_factor_exposures[exposure_index, symbols],
            dtype=np.float32,
        )
        reliability = np.asarray(
            self.exposure_reliability[exposure_index, symbols],
            dtype=np.float32,
        )
        exposure_mask = np.asarray(
            self.exposure_available[exposure_index, symbols],
            dtype=np.float32,
        )
        beta *= exposure_mask
        reliability *= exposure_mask
        age = np.zeros((*endpoints.shape, 1), dtype=np.float32)
        features = np.concatenate(
            (state, state_mask, beta, reliability, exposure_mask, age),
            axis=2,
        )
        if features.shape[1:] != (SEQUENCE_POINTS, FEATURE_DIM):
            raise AssertionError("reaka_K1_feature_shape_invalid")
        return history, features

    def assemble_batch(
        self,
        indices: NDArray[np.int64],
    ) -> tuple[
        NDArray[np.float32],
        NDArray[np.float32],
        NDArray[np.float32],
    ]:
        history, features = self.assemble_inputs(indices)
        rows = np.asarray(self.inference_rows[indices], dtype=np.int64)
        target = np.asarray(
            self.epsilon_future[rows[:, 0], rows[:, 1]],
            dtype=np.float32,
        )
        return history, features, target


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


def factor_order(states: pd.DataFrame) -> tuple[str, ...]:
    observed = set(states["factor_id"].astype(str))
    industries = sorted(observed - {MARKET_FACTOR_ID, SIZE_FACTOR_ID})
    result = (MARKET_FACTOR_ID, SIZE_FACTOR_ID, *industries)
    if len(result) != FACTOR_COUNT or set(result) != observed:
        raise ValueError("reaka_K1_factor_identity_invalid")
    return result


def build_state_store(
    states: pd.DataFrame,
    calendar: NDArray[np.datetime64],
    factor_ids: Sequence[str],
) -> tuple[NDArray[np.float32], NDArray[np.uint8]]:
    variants = variant_ids()
    day_index = {pd.Timestamp(value): index for index, value in enumerate(calendar)}
    variant_index = {value: index for index, value in enumerate(variants)}
    factor_index = {value: index for index, value in enumerate(factor_ids)}
    values = np.zeros((len(variants), len(calendar), len(factor_ids)), dtype=np.float32)
    available = np.zeros_like(values, dtype=np.uint8)
    local = states.loc[states["available"]].copy()
    vi = local["variant_id"].map(variant_index).to_numpy(np.int64)
    di = pd.to_datetime(local["decision_date"]).map(day_index)
    fi = local["factor_id"].map(factor_index).to_numpy(np.int64)
    if di.isna().any():
        raise ValueError("reaka_K1_state_date_outside_calendar")
    values[vi, di.to_numpy(np.int64), fi] = local["timing_state"].to_numpy(np.float32)
    available[vi, di.to_numpy(np.int64), fi] = 1
    return values, available


def build_exposure_store(
    *,
    exposures: pd.DataFrame,
    industry_exposures: pd.DataFrame,
    calendar: NDArray[np.datetime64],
    symbol_count: int,
    factor_ids: Sequence[str],
    decision_positions: NDArray[np.int64],
) -> tuple[
    NDArray[np.float32],
    NDArray[np.float32],
    NDArray[np.uint8],
]:
    day_index = {pd.Timestamp(value): index for index, value in enumerate(calendar)}
    decision_index = {int(day): index for index, day in enumerate(decision_positions)}
    factor_index = {value: index for index, value in enumerate(factor_ids)}
    shape = (len(decision_positions), symbol_count, len(factor_ids))
    beta = np.zeros(shape, dtype=np.float32)
    reliability = np.zeros(shape, dtype=np.float32)
    available = np.zeros(shape, dtype=np.uint8)
    local = exposures.loc[exposures["available"]].copy()
    day = pd.to_datetime(local["asof_date"]).map(day_index).map(decision_index)
    if day.isna().any():
        raise ValueError("reaka_K1_exposure_date_not_D5")
    di = day.to_numpy(np.int64)
    si = local["symbol_position"].to_numpy(np.int64)
    rel = local["reliability"].to_numpy(np.float32)
    for column, factor in (
        ("beta_market", MARKET_FACTOR_ID),
        ("beta_size", SIZE_FACTOR_ID),
    ):
        fi = factor_index[factor]
        values = local[column].to_numpy(np.float32)
        valid = np.isfinite(values) & np.isfinite(rel)
        beta[di[valid], si[valid], fi] = values[valid]
        reliability[di[valid], si[valid], fi] = rel[valid]
        available[di[valid], si[valid], fi] = 1
    industry = industry_exposures.loc[industry_exposures["available"]].copy()
    industry_day = pd.to_datetime(industry["asof_date"]).map(day_index).map(decision_index)
    if industry_day.isna().any():
        raise ValueError("reaka_K1_industry_exposure_date_not_D5")
    idi = industry_day.to_numpy(np.int64)
    isi = industry["symbol_position"].to_numpy(np.int64)
    ifi = industry["industry_factor_id"].map(factor_index).to_numpy(np.int64)
    values = industry["beta_industry"].to_numpy(np.float32)
    rel = industry["reliability"].to_numpy(np.float32)
    valid = np.isfinite(values) & np.isfinite(rel)
    beta[idi[valid], isi[valid], ifi[valid]] = values[valid]
    reliability[idi[valid], isi[valid], ifi[valid]] = rel[valid]
    available[idi[valid], isi[valid], ifi[valid]] = 1
    return beta, reliability, available


def build_inference_rows(
    *,
    calendar: NDArray[np.datetime64],
    epsilon_history: NDArray[np.float32],
    epsilon_future: NDArray[np.float32],
    decision_positions: NDArray[np.int64],
    exposure_available: NDArray[np.uint8],
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    parts: list[NDArray[np.int64]] = []
    offsets = np.arange(
        -(SEQUENCE_POINTS - 1) * HORIZON_DAYS,
        1,
        HORIZON_DAYS,
        dtype=np.int64,
    )
    anchor_matches = np.flatnonzero(calendar == np.datetime64("2008-12-01", "ns"))
    if len(anchor_matches) != 1:
        raise ValueError("reaka_K1_D5_anchor_missing")
    anchor = int(anchor_matches[0])
    for decision_index, day in enumerate(decision_positions):
        endpoints = day + offsets
        if (endpoints < 0).any():
            continue
        history_ok = np.isfinite(epsilon_history[endpoints]).all(axis=0)
        current_support = exposure_available[decision_index].any(axis=1)
        symbols = np.flatnonzero(history_ok & current_support).astype(np.int64)
        if not len(symbols):
            continue
        year = int(calendar[day].astype("datetime64[Y]").astype(int) + 1970)
        phase = int(((day - anchor) // 5) % 4)
        parts.append(
            np.column_stack(
                (
                    np.full(len(symbols), day, dtype=np.int64),
                    symbols,
                    np.full(len(symbols), year, dtype=np.int64),
                    np.full(len(symbols), phase, dtype=np.int64),
                )
            )
        )
    rows = np.vstack(parts) if parts else np.empty((0, 4), dtype=np.int64)
    label_ok = np.isfinite(epsilon_future[rows[:, 0], rows[:, 1]]) if len(rows) else np.zeros(0, dtype=bool)
    return rows, np.flatnonzero(label_ok).astype(np.int64)


def feature_registry(factor_ids: Sequence[str]) -> dict[str, object]:
    channels: list[dict[str, object]] = []

    def add(name: str, role: str) -> None:
        channels.append({"position": len(channels), "name": name, "role": role})

    for factor in factor_ids:
        add(f"state:{factor}", "selected_signal_state")
    for factor in factor_ids:
        add(f"state_mask:{factor}", "state_availability")
    for factor in factor_ids:
        add(f"beta:{factor}", "stock_factor_exposure")
    for factor in factor_ids:
        add(f"reliability:{factor}", "exposure_reliability")
    for factor in factor_ids:
        add(f"exposure_mask:{factor}", "exposure_availability")
    add("exposure_age_fraction", "exact_D5_refresh_age_zero")
    if len(channels) != FEATURE_DIM:
        raise AssertionError("reaka_K1_feature_registry_width_invalid")
    return _with_digest(
        {
            "schema_id": "factorlab.reaka_intraday_K1_feature_registry@1.0",
            "feature_dim": FEATURE_DIM,
            "channels": channels,
            "price_volume_channels": [],
            "LAT_channels": [],
            "oracle_or_target_channels": [],
            "production_authority": False,
        }
    )


def materialize_store(
    *,
    output_root: Path,
    ot_root: Path,
    p6_root: Path,
    contract_digest: str,
    decision_clock: str,
) -> dict[str, object]:
    if output_root.exists():
        raise FileExistsError(f"reaka_K1_store_exists:{output_root}")
    with np.load(ot_root / "ot1/stock_residual_surfaces.npz", allow_pickle=False) as payload:
        calendar = np.asarray(payload["calendar"], dtype="datetime64[ns]")
        symbols = np.asarray(payload["symbols"], dtype=str)
        epsilon_history = np.asarray(payload["epsilon_history"], dtype=np.float32)
        epsilon_future = np.asarray(payload["epsilon_future"], dtype=np.float32)
    states = pd.read_parquet(ot_root / "ot2/selected_factor_states.parquet")
    factor_ids = factor_order(states)
    state_values, state_available = build_state_store(states, calendar, factor_ids)
    decisions = np.load(p6_root / "decision_positions.npy", mmap_mode="r")
    exposures = pd.read_parquet(ot_root / "ot1/d5_stock_exposures.parquet")
    industries = pd.read_parquet(ot_root / "ot1/d5_stock_industry_exposures.parquet")
    beta, reliability, exposure_available = build_exposure_store(
        exposures=exposures,
        industry_exposures=industries,
        calendar=calendar,
        symbol_count=len(symbols),
        factor_ids=factor_ids,
        decision_positions=decisions,
    )
    rows, labelled = build_inference_rows(
        calendar=calendar,
        epsilon_history=epsilon_history,
        epsilon_future=epsilon_future,
        decision_positions=decisions,
        exposure_available=exposure_available,
    )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.", dir=output_root.parent))
    try:
        arrays: dict[str, NDArray[np.generic]] = {
            "calendar.npy": calendar,
            "symbols.npy": symbols,
            "epsilon_history.npy": epsilon_history,
            "epsilon_future.npy": epsilon_future,
            "state_values.npy": state_values,
            "state_available.npy": state_available,
            "exposure_decision_positions.npy": np.asarray(decisions),
            "stock_factor_exposures.npy": beta,
            "exposure_reliability.npy": reliability,
            "exposure_available.npy": exposure_available,
            "inference_rows.npy": rows,
            "labelled_row_indices.npy": labelled,
        }
        for name, values in arrays.items():
            np.save(temporary / name, values, allow_pickle=False)
        factor_payload = write_json(
            temporary / "factor_ids.json",
            {"factor_ids": list(factor_ids)},
        )
        variant_payload = write_json(
            temporary / "variant_ids.json",
            {"variant_ids": list(variant_ids())},
        )
        registry = write_json(temporary / "feature_registry.json", feature_registry(factor_ids))
        artifact_names = [
            *arrays,
            "factor_ids.json",
            "variant_ids.json",
            "feature_registry.json",
        ]
        manifest = write_json(
            temporary / "manifest.json",
            {
                "schema_id": STORE_SCHEMA_ID,
                "status": "materialized_result_free_intraday_K1_input",
                "contract_digest": contract_digest,
                "decision_clock": decision_clock,
                "calendar_start": str(calendar[0].astype("datetime64[D]")),
                "calendar_end": str(calendar[-1].astype("datetime64[D]")),
                "calendar_days": len(calendar),
                "symbol_count": len(symbols),
                "factor_count": len(factor_ids),
                "feature_dim": FEATURE_DIM,
                "sequence_points": SEQUENCE_POINTS,
                "H_days": HORIZON_DAYS,
                "inference_row_count": len(rows),
                "labelled_row_count": len(labelled),
                "inference_without_label_count": len(rows) - len(labelled),
                "inference_year_min": int(rows[:, 2].min()),
                "inference_year_max": int(rows[:, 2].max()),
                "phase_ids": sorted(np.unique(rows[:, 3]).astype(int).tolist()),
                "factor_ids_digest": factor_payload["canonical_digest"],
                "variant_ids_digest": variant_payload["canonical_digest"],
                "feature_registry_digest": registry["canonical_digest"],
                "artifact_digests": {name: file_digest(temporary / name) for name in artifact_names},
                "target_used_to_filter_inference": False,
                "entry_used_to_filter_inference": False,
                "post_2020_rows_read": 0,
                "model_training_run": False,
                "score_run": False,
                "account_run": False,
                "production_authority": False,
            },
        )
        temporary.rename(output_root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def normalizer_from_store(store: IntradayK1InputStore) -> dict[str, object]:
    train = np.flatnonzero(store.inference_rows[:, 2] <= 2016).astype(np.int64)
    sample = train[np.unique(np.linspace(0, len(train) - 1, min(65536, len(train)), dtype=np.int64))]
    returns_parts: list[NDArray[np.float64]] = []
    beta_parts: list[NDArray[np.float64]] = []
    reliability_parts: list[NDArray[np.float64]] = []
    for start in range(0, len(sample), 4096):
        history, features = store.assemble_inputs(sample[start : start + 4096])
        returns_parts.append(history.ravel().astype(np.float64))
        mask = features[:, :, 56:70].astype(bool)
        beta_parts.append(features[:, :, 28:42][mask].astype(np.float64))
        reliability_parts.append(features[:, :, 42:56][mask].astype(np.float64))
    returns = np.concatenate(returns_parts)
    beta = np.concatenate(beta_parts)
    reliability = np.concatenate(reliability_parts)
    return _with_digest(
        {
            "schema_id": "factorlab.reaka_intraday_K1_normalizer@1.0",
            "fit_end_year": 2016,
            "sample_rows": len(sample),
            "return_mean": float(returns.mean()),
            "return_scale": float(max(returns.std(), 1e-6)),
            "beta_mean": float(beta.mean()),
            "beta_scale": float(max(beta.std(), 1e-6)),
            "reliability_mean": float(reliability.mean()),
            "reliability_scale": float(max(reliability.std(), 1e-6)),
            "state_values_kept_native": True,
            "masks_kept_native": True,
            "target_used": False,
            "production_authority": False,
        }
    )


def normalize_batch(
    history: NDArray[np.float32],
    features: NDArray[np.float32],
    normalizer: Mapping[str, object],
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    returns = ((history - float(normalizer["return_mean"])) / float(normalizer["return_scale"])).astype(np.float32)
    output = features.copy()
    mask = output[:, :, 56:70]
    output[:, :, 28:42] = ((output[:, :, 28:42] - float(normalizer["beta_mean"])) / float(normalizer["beta_scale"])) * mask
    output[:, :, 42:56] = ((output[:, :, 42:56] - float(normalizer["reliability_mean"])) / float(normalizer["reliability_scale"])) * mask
    return returns, output


def effective_rank(features: NDArray[np.float32]) -> float:
    values = np.asarray(features, dtype=np.float64).reshape(-1, features.shape[-1])
    values -= values.mean(axis=0, keepdims=True)
    covariance = values.T @ values / max(len(values) - 1, 1)
    eigenvalues = np.linalg.eigvalsh(covariance)
    eigenvalues = eigenvalues[eigenvalues > 1e-12]
    if not len(eigenvalues):
        return 0.0
    return float(eigenvalues.sum() ** 2 / np.square(eigenvalues).sum())


def _run_lengths(values: NDArray[np.float64]) -> list[int]:
    finite = np.isfinite(values)
    output: list[int] = []
    start = 0
    while start < len(values):
        while start < len(values) and not finite[start]:
            start += 1
        if start >= len(values):
            break
        end = start + 1
        while end < len(values) and finite[end] and values[end] == values[start]:
            end += 1
        output.append(end - start)
        start = end
    return output


def feature_half_life(features: NDArray[np.float32]) -> tuple[float, str, list[float]]:
    channels = [*range(14), *range(28, 56)]
    values = np.asarray(features[:, :, channels], dtype=np.float64)
    correlations: list[float] = []
    for lag in range(1, SEQUENCE_POINTS):
        left = values[:, :-lag].reshape(-1, values.shape[-1])
        right = values[:, lag:].reshape(-1, values.shape[-1])
        per_channel: list[float] = []
        for channel in range(values.shape[-1]):
            x = left[:, channel]
            y = right[:, channel]
            valid = np.isfinite(x) & np.isfinite(y)
            if int(valid.sum()) < 128:
                continue
            x = x[valid] - x[valid].mean()
            y = y[valid] - y[valid].mean()
            denominator = float(np.linalg.norm(x) * np.linalg.norm(y))
            if denominator > 1e-12:
                per_channel.append(abs(float(x @ y / denominator)))
        correlations.append(float(np.median(per_channel)) if per_channel else np.nan)
    for lag, value in enumerate(correlations, start=1):
        if np.isfinite(value) and value <= 0.5:
            return float(lag * HORIZON_DAYS), "measured", correlations
    return (
        float((SEQUENCE_POINTS - 1) * HORIZON_DAYS),
        "right_censored_at_sequence_window",
        correlations,
    )


def compatibility_certificate(
    store: IntradayK1InputStore,
    *,
    decision_clock: str,
) -> dict[str, object]:
    train = np.flatnonzero(store.inference_rows[:, 2] <= 2016).astype(np.int64)
    sample = train[np.unique(np.linspace(0, len(train) - 1, min(32768, len(train)), dtype=np.int64))]
    _, features = store.assemble_inputs(sample)
    r_eff = effective_rank(features)
    tau_x_days, q_x_status, feature_autocorrelation = feature_half_life(features)
    decision_dates = np.unique(store.inference_rows[train, 0])
    state_runs: list[int] = []
    for factor in range(len(store.factor_ids)):
        values = np.asarray(store.state_values[0, decision_dates, factor], dtype=np.float64)
        state_runs.extend(_run_lengths(values))
    tau_s_days = float(np.median(state_runs) * 5.0) if state_runs else 0.0
    labelled_train = store.labelled_row_indices[store.inference_rows[store.labelled_row_indices, 2] <= 2016]
    unique_labelled_decisions, cross_section_counts = np.unique(store.inference_rows[labelled_train, 0], return_counts=True)
    n_eff_time = float(len(unique_labelled_decisions) / 4.0)
    median_cross_section = float(np.median(cross_section_counts))
    n_eff_design = float(n_eff_time * math.sqrt(median_cross_section))
    n_eff_upper = float(len(labelled_train) / 4.0)
    latent_candidates = [value for value in (8, 16, 32) if value <= max(r_eff, 8.0)]
    if 8 not in latent_candidates:
        latent_candidates.insert(0, 8)
    capacity = [{"latent_dimension": d, "hidden_dimension": h} for d, h in CAPACITY_ROOTS if d in latent_candidates]
    capacity_support = [
        {
            **item,
            "d_squared": int(item["latent_dimension"]) ** 2,
            "n_k_eff_time_lower_over_d_squared": n_eff_time / (int(item["latent_dimension"]) ** 2),
            "n_k_eff_design_over_d_squared": n_eff_design / (int(item["latent_dimension"]) ** 2),
            "n_k_eff_upper_over_d_squared": n_eff_upper / (int(item["latent_dimension"]) ** 2),
            "support_diagnostic": ("comfortable" if n_eff_time / (int(item["latent_dimension"]) ** 2) >= 1.0 else "thin_claim_limited"),
        }
        for item in capacity
    ]
    return _with_digest(
        {
            "schema_id": "factorlab.reaka_intraday_K1_input_compatibility@1.0",
            "status": "compatible_with_claim_limitations",
            "decision_clock": decision_clock,
            "Delta_x_days": 20,
            "Delta_y_days": 20,
            "H_days": 20,
            "L_points": 10,
            "W_days": 200,
            "decision_interval_days": 5,
            "rebalance_interval_days": 5,
            "q_h": 1.0,
            "q_w": 10.0,
            "tau_x_method": "median_abs_autocorrelation_half_life_across_state_beta_reliability_at_H20_lags",
            "tau_s_method": "selected_state_D5_run_length_median",
            "tau_x_days": tau_x_days,
            "tau_s_days": tau_s_days,
            "q_x": tau_x_days / HORIZON_DAYS,
            "q_s": tau_s_days / HORIZON_DAYS,
            "q_x_status": q_x_status,
            "q_s_status": "measured",
            "feature_median_abs_autocorrelation_by_H20_lag": feature_autocorrelation,
            "r_eff": r_eff,
            "latent_dimension": sorted({int(item["latent_dimension"]) for item in capacity}),
            "latent_dimension_candidates": latent_candidates,
            "capacity_root_candidates": capacity,
            "capacity_support": capacity_support,
            "operator_count": 1,
            "n_eff_method": "four_phase_time_lower_time_x_sqrt_cross_section_design_and_cross_section_upper",
            "n_eff_time": n_eff_time,
            "median_labelled_cross_section": median_cross_section,
            "n_eff_design_time_x_sqrt_cross_section": n_eff_design,
            "n_eff_cross_section_upper_bound": n_eff_upper,
            "n_k_eff_method": "K1_inherits_each_n_eff_bound_pretraining",
            "n_k_eff": n_eff_time,
            "post_training_operator_obligations": [
                "actual_n_k_eff_and_n_k_eff_over_d_squared",
                "koopman_matrix_condition_number",
                "member_and_input_perturbation_stability",
            ],
            "operator_identifiability_claimed": False,
            "overlap_inference": "four_phase_block_or_HAC_required",
            "inference_rows": len(store.inference_rows),
            "labelled_rows": len(store.labelled_row_indices),
            "training_prefix_rows": len(train),
            "target_value_used_for_capacity_measurement": False,
            "target_availability_used_only_for_labelled_n_eff": True,
            "production_authority": False,
        }
    )


def build_model(*, latent_dim: int, hidden_dim: int, learning_rate: float) -> Stage6ReakaModel:
    torch.manual_seed(SEED)
    config = ReakaPaperConfig(
        window_length=SEQUENCE_POINTS,
        latent_dim=latent_dim,
        network_hidden_dim=hidden_dim,
        operator_count=1,
        training_epochs=1,
        diffusion_steps=1,
        batch_size=4096,
        learning_rate=learning_rate,
        gumbel_temperature=1.0,
        time_embedding_dim=latent_dim,
        denoiser_hidden_dim=latent_dim,
        gradient_clip_norm=1e12,
        inference_draws=1,
        torch_num_threads=16,
    )
    model = Stage6ReakaModel(
        feature_dim=FEATURE_DIM,
        config=config,
        arm_id="fixed_k_no_residual",
    )
    apply_declared_initialization(model, seed=SEED)
    return model


def initialize_dmd(
    model: Stage6ReakaModel,
    returns: torch.Tensor,
    features: torch.Tensor,
) -> dict[str, float]:
    model.eval()
    with torch.no_grad():
        output = model.training_objective(returns, features)
        latent = output.latent.reshape(-1, model.config.latent_dim).double()
        next_latent = output.next_latent.reshape(-1, model.config.latent_dim).double()
        gram = latent.T @ latent
        cross = next_latent.T @ latent
        ridge = max(
            1e-6,
            1e-4 * float(torch.trace(gram)) / model.config.latent_dim,
        )
        operator = torch.linalg.solve(
            gram + ridge * torch.eye(model.config.latent_dim, dtype=torch.float64),
            cross.T,
        ).T
        radius = float(torch.linalg.eigvals(operator).abs().max())
        if radius > 1.0:
            operator /= radius
        model.operators[0].copy_(operator.float())
    return {"ridge": ridge, "pre_projection_radius": radius}


def lr_probe(
    store: IntradayK1InputStore,
    normalizer: Mapping[str, object],
    capacity: Sequence[Mapping[str, int]],
) -> dict[str, object]:
    train = np.flatnonzero(store.inference_rows[:, 2] <= 2016).astype(np.int64)
    sample = train[: min(2048, len(train))]
    history, features = store.assemble_inputs(sample)
    returns_np, features_np = normalize_batch(history, features, normalizer)
    returns = torch.from_numpy(returns_np)
    feature_tensor = torch.from_numpy(features_np)
    rows: list[dict[str, object]] = []
    selected: dict[str, float | None] = {}
    for item in capacity:
        latent = int(item["latent_dimension"])
        hidden = int(item["hidden_dimension"])
        identity = f"d{latent}_h{hidden}"
        last_healthy: float | None = None
        first_unhealthy: float | None = None
        for learning_rate in LR_GRID:
            model = build_model(
                latent_dim=latent,
                hidden_dim=hidden,
                learning_rate=learning_rate,
            )
            dmd = initialize_dmd(model, returns, feature_tensor)
            optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate, weight_decay=0.0)
            losses: list[float] = []
            gradient_maxima: list[float] = []
            parameter_before = torch.cat([parameter.detach().flatten() for parameter in model.parameters()])
            model.train()
            for _ in range(4):
                optimizer.zero_grad(set_to_none=True)
                output = model.training_objective(returns, feature_tensor)
                if not bool(torch.isfinite(output.total_loss)):
                    break
                output.total_loss.backward()
                gradients = [parameter.grad.detach().abs().max() for parameter in model.parameters() if parameter.grad is not None]
                gradient_maxima.append(float(torch.stack(gradients).max()) if gradients else np.nan)
                optimizer.step()
                losses.append(float(output.total_loss.detach()))
            parameter_after = torch.cat([parameter.detach().flatten() for parameter in model.parameters()])
            update_ratio = float(
                torch.linalg.vector_norm(parameter_after - parameter_before)
                / torch.clamp(torch.linalg.vector_norm(parameter_before), min=1e-12)
            )
            healthy = bool(
                len(losses) == 4
                and np.isfinite(losses).all()
                and losses[-1] < losses[0]
                and np.isfinite(gradient_maxima).all()
                and max(gradient_maxima) < 1e6
                and math.isfinite(update_ratio)
                and update_ratio < 10.0
            )
            rows.append(
                {
                    "identity": identity,
                    "latent_dimension": latent,
                    "hidden_dimension": hidden,
                    "learning_rate": learning_rate,
                    "losses": losses,
                    "gradient_maxima": gradient_maxima,
                    "update_parameter_ratio": update_ratio,
                    "DMD": dmd,
                    "healthy": healthy,
                }
            )
            if healthy:
                last_healthy = learning_rate
            else:
                first_unhealthy = learning_rate
                break
        selected[identity] = last_healthy if first_unhealthy is not None else None
    right_censored = [identity for identity, value in selected.items() if value is None]
    return _with_digest(
        {
            "schema_id": "factorlab.reaka_intraday_K1_LR_probe@1.0",
            "status": "passed" if not right_censored else "blocked_right_censored",
            "rows": rows,
            "selected_learning_rates": selected,
            "right_censored_identities": right_censored,
            "target_read": False,
            "production_authority": False,
        }
    )


def select_backend(
    *,
    parity_passed: bool,
    cpu_seconds: float,
    rocm_seconds: float | None,
    minimum_rocm_speedup: float = 1.10,
) -> tuple[str, float | None]:
    speedup = cpu_seconds / rocm_seconds if rocm_seconds is not None else None
    selected = "rocm" if parity_passed and speedup is not None and speedup >= minimum_rocm_speedup else "cpu"
    return selected, speedup


def backend_benchmark(
    store: IntradayK1InputStore,
    normalizer: Mapping[str, object],
) -> dict[str, object]:
    train = np.flatnonzero(store.inference_rows[:, 2] <= 2016).astype(np.int64)
    sample = train[: min(4096, len(train))]
    history, features = store.assemble_inputs(sample)
    returns_np, features_np = normalize_batch(history, features, normalizer)
    cpu_model = build_model(latent_dim=16, hidden_dim=16, learning_rate=1e-3)
    returns_cpu = torch.from_numpy(returns_np)
    features_cpu = torch.from_numpy(features_np)
    initialize_dmd(cpu_model, returns_cpu, features_cpu)
    state = {key: value.detach().clone() for key, value in cpu_model.state_dict().items()}

    def prepare(
        device: torch.device,
    ) -> tuple[Stage6ReakaModel, torch.Tensor, torch.Tensor]:
        model = build_model(latent_dim=16, hidden_dim=16, learning_rate=1e-3).to(device)
        model.load_state_dict(state)
        returns = returns_cpu.to(device)
        feature_tensor = features_cpu.to(device)
        model.eval()
        with torch.no_grad():
            _ = model.training_objective(returns, feature_tensor)
            _ = model.forecast(returns, feature_tensor).scores
        model.train()
        model.zero_grad(set_to_none=True)
        model.training_objective(returns, feature_tensor).total_loss.backward()
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        return model, returns, feature_tensor

    def run_block(
        context: tuple[Stage6ReakaModel, torch.Tensor, torch.Tensor],
    ) -> tuple[float, float, NDArray[np.float32], float]:
        model, returns, feature_tensor = context
        device = returns.device
        started = time.perf_counter()
        scores = None
        loss = np.nan
        for _ in range(4):
            model.zero_grad(set_to_none=True)
            output = model.training_objective(returns, feature_tensor)
            output.total_loss.backward()
            loss = float(output.total_loss.detach().cpu())
            with torch.no_grad():
                scores = model.forecast(returns, feature_tensor).scores.detach().cpu()
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        elapsed = time.perf_counter() - started
        assert scores is not None
        gradient_max = max(
            float(parameter.grad.detach().abs().max().cpu()) for parameter in model.parameters() if parameter.grad is not None
        )
        return elapsed, loss, scores.numpy().astype(np.float32), gradient_max

    rocm_available = bool(torch.cuda.is_available() and torch.cuda.device_count() > 0)
    cpu_context = prepare(torch.device("cpu"))
    rocm_context = prepare(torch.device("cuda:0")) if rocm_available else None
    cpu_blocks: list[float] = []
    rocm_blocks: list[float] = []
    cpu_loss = np.nan
    cpu_gradient = np.nan
    cpu_scores = np.empty(0, dtype=np.float32)
    rocm_loss: float | None = None
    rocm_gradient: float | None = None
    rocm_scores: NDArray[np.float32] | None = None
    for block in range(5):
        order = ("cpu", "rocm") if block % 2 == 0 else ("rocm", "cpu")
        for backend in order:
            if backend == "rocm" and rocm_context is None:
                continue
            context = cpu_context if backend == "cpu" else rocm_context
            assert context is not None
            elapsed, loss, scores, gradient = run_block(context)
            if backend == "cpu":
                cpu_blocks.append(elapsed)
                cpu_loss = loss
                cpu_scores = scores
                cpu_gradient = gradient
            else:
                rocm_blocks.append(elapsed)
                rocm_loss = loss
                rocm_scores = scores
                rocm_gradient = gradient
    cpu_elapsed = float(np.median(cpu_blocks))
    rocm_elapsed = float(np.median(rocm_blocks)) if rocm_blocks else None
    parity_max_abs: float | None = None
    score_spearman: float | None = None
    if rocm_scores is not None:
        parity_max_abs = float(np.max(np.abs(cpu_scores - rocm_scores)))
        score_spearman = float(pd.Series(cpu_scores).corr(pd.Series(rocm_scores), method="spearman"))
    parity_passed = bool(
        rocm_available
        and rocm_loss is not None
        and abs(cpu_loss - rocm_loss) <= 1e-5
        and parity_max_abs is not None
        and parity_max_abs <= 1e-4
        and score_spearman is not None
        and score_spearman >= 0.999999
    )
    selected, rocm_speedup = select_backend(
        parity_passed=parity_passed,
        cpu_seconds=cpu_elapsed,
        rocm_seconds=rocm_elapsed,
    )
    return _with_digest(
        {
            "schema_id": "factorlab.reaka_intraday_K1_backend_benchmark@1.0",
            "status": "passed",
            "representative_identity": "d16_h16_K1_r0",
            "batch_rows": len(sample),
            "timing_blocks": 5,
            "repetitions_per_block": 4,
            "timing_statistic": "median_of_alternating_blocks",
            "minimum_rocm_speedup": 1.10,
            "cpu_block_seconds": cpu_blocks,
            "cpu_seconds": cpu_elapsed,
            "cpu_loss": cpu_loss,
            "cpu_gradient_max": cpu_gradient,
            "rocm_available": rocm_available,
            "rocm_block_seconds": rocm_blocks,
            "rocm_seconds": rocm_elapsed,
            "rocm_speedup": rocm_speedup,
            "rocm_loss": rocm_loss,
            "rocm_gradient_max": rocm_gradient,
            "parity_max_abs": parity_max_abs,
            "score_spearman": score_spearman,
            "parity_passed": parity_passed,
            "selected_backend": selected,
            "target_read": False,
            "production_authority": False,
        }
    )


def parameter_instantiation(
    *,
    compatibility: Mapping[str, object],
    lr_receipt: Mapping[str, object],
    backend_receipt: Mapping[str, object],
    governance_receipts: Mapping[str, str],
) -> dict[str, object]:
    values: dict[str, object] = {
        "data.stock_universe": "intraday_OT1_available_full_A_share_PIT",
        "encoder.layer_count": 1,
        "network.hidden_dimension": compatibility["capacity_root_candidates"],
        "koopman.initialization": "training_prefix_regularized_DMD_radius_le_1",
        "selector.gumbel_temperature": "not_applicable_K1",
        "selector.gumbel_schedule": "not_applicable_K1",
        "selector.straight_through": False,
        "residual.target_gradient_attachment": "not_applicable_r0",
        "residual.denoiser_architecture": "not_applicable_r0",
        "residual.time_embedding_dimension": "not_applicable_r0",
        "residual.x0_mapping": "not_applicable_r0",
        "decoder.architecture": "shared_one_hidden_layer_follows_capacity_root",
        "loss.scale_normalization": "per_element_mean_Lrec_plus_Lkoop",
        "optimizer.family": "adam",
        "optimizer.learning_rate": lr_receipt["selected_learning_rates"],
        "optimizer.weight_decay": 0.0,
        "training.coverage_budget": "P6_4_convergence_cycles_max_budget_preregistered_before_fit",
        "training.early_stopping": "after_health_gate_internal_2017_rankic_platform",
        "training.gradient_clip_norm": "disabled_if_unclipped_gradient_receipt_finite",
        "training.general_initialization": "xavier_orthogonal_chrono_plus_DMD",
        "portfolio.rebalance_frequency": "D5_R5_at_1430_or_1445",
        "portfolio.weighting": "post_training_Top10_Top30_equal_weight_not_executed",
    }
    return _with_digest(
        {
            "schema_id": "factorlab.reaka_intraday_K1_run_instantiation@1.0",
            "status": ("passed_preflight_formal_training_closed" if lr_receipt.get("status") == "passed" else "blocked"),
            "parameter_values": values,
            "parameter_count": len(values),
            "compatibility_digest": compatibility["canonical_digest"],
            "LR_receipt_digest": lr_receipt["canonical_digest"],
            "backend_receipt_digest": backend_receipt["canonical_digest"],
            "workflow_gate_digest": governance_receipts["workflow_gate_digest"],
            "financial_alignment_gate_digest": governance_receipts["financial_alignment_gate_digest"],
            "root_scope_gate_digest": governance_receipts["root_scope_gate_digest"],
            "selected_backend": backend_receipt["selected_backend"],
            "user_math_inputs_required": [],
            "formal_training_allowed": False,
            "production_authority": False,
        }
    )


def validate_contract(payload: Mapping[str, object]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema_id") != SCHEMA_ID:
        blockers.append("K1_preflight_contract_schema_invalid")
    if not canonical_valid(payload):
        blockers.append("K1_preflight_contract_digest_invalid")
    if payload.get("decision_clocks") != list(CLOCKS):
        blockers.append("K1_preflight_clock_identity_invalid")
    if payload.get("operator_count") != 1:
        blockers.append("K1_preflight_operator_count_invalid")
    if payload.get("residual_identity") != "r0_exact_zero":
        blockers.append("K1_preflight_residual_identity_invalid")
    if payload.get("formal_training_allowed") is not False:
        blockers.append("K1_preflight_formal_training_must_be_closed")
    return blockers


__all__ = [
    "CAPACITY_ROOTS",
    "COMPATIBILITY_REQUIRED_FIELDS",
    "CLOCKS",
    "CLOCK_SUFFIX",
    "FACTOR_COUNT",
    "FEATURE_DIM",
    "HORIZON_DAYS",
    "IntradayK1InputStore",
    "LR_GRID",
    "SCHEMA_ID",
    "SEQUENCE_POINTS",
    "SEED",
    "STORE_FILES",
    "STORE_SCHEMA_ID",
    "VALIDATION_SCHEMA_ID",
    "backend_benchmark",
    "build_exposure_store",
    "build_inference_rows",
    "build_model",
    "build_state_store",
    "canonical_valid",
    "compatibility_certificate",
    "effective_rank",
    "factor_order",
    "feature_half_life",
    "feature_registry",
    "file_digest",
    "initialize_dmd",
    "lr_probe",
    "materialize_store",
    "normalize_batch",
    "normalizer_from_store",
    "parameter_instantiation",
    "read_json",
    "select_backend",
    "validate_contract",
    "write_json",
]
