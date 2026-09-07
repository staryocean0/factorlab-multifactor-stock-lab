"""R3 direct-X decomposition views and monthly-condition timing helpers.

This module defines information interventions only. It is not a feature-importance
estimator and does not identify economic causality. All projections are applied
*after* the original fit-prefix normalizer. The current 71-channel K1 layout is
kept fixed so same-topology comparisons remain possible.

The proposed monthly CloudRidge formula is intentionally NOT implemented here:
its exact S_obs / 1-sigma definition was not recovered from repository or prior
context. The monthly helper only enforces causal timing for an already encoded
monthly scalar supplied by a separately identified source.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Iterable

import numpy as np

FEATURE_DIM: Final = 71
SEQUENCE_POINTS: Final = 10
CHANNEL_GROUPS: Final = {
    "state_values": (0, 14),
    "state_available": (14, 28),
    "stock_factor_exposures": (28, 42),
    "exposure_reliability": (42, 56),
    "exposure_available": (56, 70),
    "experimental_slot": (70, 71),
}

# Coarse stage is authorized next. Fine arms are pre-registered only.
ARM_KEEP_RANGES: Final = {
    "H": (),
    "E": ((28, 70),),
    "F": ((0, 70),),
    # Fine follow-ups; do not execute automatically after seeing coarse results.
    "STATE_VALUE_PLUS_E": ((0, 14), (28, 70)),
    "BETA_ONLY": ((28, 42),),
    "BETA_RELIABILITY": ((28, 56),),
}


def _validate_original_features(features: np.ndarray) -> np.ndarray:
    values = np.asarray(features)
    if values.ndim != 3 or values.shape[0] == 0 or values.shape[2] != FEATURE_DIM:
        raise ValueError("expected nonempty batch x sequence x 71 features")
    if not 1 <= values.shape[1] <= SEQUENCE_POINTS:
        raise ValueError("sequence must contain 1..10 points")
    if values.dtype.kind != "f" or not np.isfinite(values).all():
        raise ValueError("features must be finite floating-point values")
    for lo, hi in ((14, 28), (56, 70)):
        mask = values[:, :, lo:hi]
        if not np.isin(mask, (0.0, 1.0)).all():
            raise ValueError("availability masks must retain binary encoding")
    if np.any(values[:, :, 70] != 0.0):
        raise ValueError("channel 70 must be zero in the incumbent K1 schema")
    return values


def project_x_view(normalized_features: np.ndarray, arm: str) -> np.ndarray:
    """Project direct-X information while preserving width and topology.

    Input must be the incumbent *normalized* 71-channel tensor. Channel 70 stays
    zero for every decomposition arm. F/H/E are the primary hierarchy; the
    other arms are only pre-registered follow-ups.
    """
    if arm not in ARM_KEEP_RANGES:
        raise ValueError(f"unknown X decomposition arm: {arm}")
    values = _validate_original_features(normalized_features)
    out = np.zeros_like(values)
    for lo, hi in ARM_KEEP_RANGES[arm]:
        out[:, :, lo:hi] = values[:, :, lo:hi]
    return np.ascontiguousarray(out)


def x_view_model_class(base_model_class: type, arm: str) -> type:
    """Return a same-topology model subclass applying the chosen X view."""
    if arm not in ARM_KEEP_RANGES:
        raise ValueError(f"unknown X decomposition arm: {arm}")
    if not isinstance(base_model_class, type) or not callable(getattr(base_model_class, "_encode_and_gate", None)):
        raise TypeError("base model must expose _encode_and_gate")
    import torch

    keep = ARM_KEEP_RANGES[arm]

    class R3XViewModel(base_model_class):
        r3_x_arm = arm

        def _encode_and_gate(self, returns, features):
            if not isinstance(features, torch.Tensor) or features.ndim != 3 or features.shape[0] == 0:
                raise ValueError("expected nonempty tensor features")
            if not 1 <= features.shape[1] <= SEQUENCE_POINTS or features.shape[2] != FEATURE_DIM:
                raise ValueError("expected sequence x 71 features")
            if not features.is_floating_point() or not bool(torch.isfinite(features).all()):
                raise ValueError("feature tensor must be finite float")
            for lo, hi in ((14, 28), (56, 70)):
                masks = features[:, :, lo:hi]
                if not bool(((masks == 0) | (masks == 1)).all()):
                    raise ValueError("availability mask encoding drift")
            if bool((features[:, :, 70] != 0).any()):
                raise ValueError("incumbent channel 70 drift")
            projected = torch.zeros_like(features)
            for lo, hi in keep:
                projected[:, :, lo:hi] = features[:, :, lo:hi]
            return super()._encode_and_gate(returns, projected)

    R3XViewModel.__name__ = f"R3_{arm}_{base_model_class.__name__}"
    return R3XViewModel


def coarse_contrasts() -> dict[str, str]:
    return {
        "E_minus_H": "exposure + reliability + exposure-mask package conditional on history-only",
        "F_minus_E": "state values + state-availability package conditional on exposure package",
        "F_minus_H": "whole incumbent direct-X package conditional on history-only; already accepted TIMEISO reference",
    }


def fine_contrasts_preregistered() -> tuple[dict[str, str], ...]:
    """Pre-registered order only; caller must not auto-run from coarse outcomes."""
    return (
        {"contrast": "STATE_VALUE_PLUS_E_minus_E", "meaning": "state values conditional on exposure package"},
        {"contrast": "F_minus_STATE_VALUE_PLUS_E", "meaning": "state availability conditional on state values + exposure package"},
        {"contrast": "BETA_ONLY_minus_H", "meaning": "exposure values conditional on history-only"},
        {"contrast": "BETA_RELIABILITY_minus_BETA_ONLY", "meaning": "reliability conditional on exposure values"},
        {"contrast": "E_minus_BETA_RELIABILITY", "meaning": "exposure availability conditional on exposure values + reliability"},
    )


@dataclass(frozen=True)
class MonthlyEncodedValue:
    source_month: str  # YYYY-MM, the completed month whose statistic was computed
    available_at: date
    value: float


def _month_key(value: np.datetime64 | date | datetime | str) -> tuple[int, int]:
    if isinstance(value, np.datetime64):
        text = str(value.astype("datetime64[D]"))
        y, m, _ = map(int, text.split("-"))
        return y, m
    if isinstance(value, datetime):
        return value.year, value.month
    if isinstance(value, date):
        return value.year, value.month
    text = str(value)[:10]
    y, m, _ = map(int, text.split("-"))
    return y, m


def previous_calendar_month(value: np.datetime64 | date | datetime | str) -> str:
    y, m = _month_key(value)
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


def _to_date(value: np.datetime64 | date | datetime | str) -> date:
    if isinstance(value, np.datetime64):
        return date.fromisoformat(str(value.astype("datetime64[D]")))
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def map_previous_month_values(
    endpoint_dates: Iterable[np.datetime64 | date | datetime | str],
    records: Iterable[MonthlyEncodedValue],
) -> np.ndarray:
    """Map each sequence endpoint to its previous *completed calendar month*.

    The scalar is assumed already encoded by an externally bound formula. This
    function refuses missing months, duplicate months, non-finite values, or a
    record whose availability timestamp is after the endpoint. No neutral/missing
    encoding is invented here.
    """
    by_month: dict[str, MonthlyEncodedValue] = {}
    for row in records:
        if row.source_month in by_month:
            raise ValueError(f"duplicate monthly condition: {row.source_month}")
        if len(row.source_month) != 7 or row.source_month[4] != "-":
            raise ValueError("source_month must be YYYY-MM")
        if not np.isfinite(row.value):
            raise ValueError("monthly condition must be finite")
        by_month[row.source_month] = row
    out: list[float] = []
    for endpoint in endpoint_dates:
        key = previous_calendar_month(endpoint)
        if key not in by_month:
            raise ValueError(f"missing previous-month condition for {key}")
        row = by_month[key]
        if row.available_at > _to_date(endpoint):
            raise ValueError(f"monthly condition {key} not available by endpoint")
        out.append(float(row.value))
    return np.asarray(out, dtype=np.float32)


def inject_monthly_experimental_slot(
    normalized_features: np.ndarray,
    endpoint_dates: np.ndarray,
    records: Iterable[MonthlyEncodedValue],
) -> np.ndarray:
    """Populate channel 70 only, preserving incumbent channels 0:70 byte-for-value.

    endpoint_dates must have shape batch x sequence. This is an experimental
    capacity-matched F+M interface, not an incumbent schema migration.
    """
    values = _validate_original_features(normalized_features)
    dates = np.asarray(endpoint_dates)
    if dates.shape != values.shape[:2]:
        raise ValueError("endpoint dates must match batch x sequence")
    mapped = map_previous_month_values(dates.reshape(-1), records).reshape(dates.shape)
    out = np.array(values, copy=True, order="C")
    out[:, :, 70] = mapped
    if not np.array_equal(out[:, :, :70], values[:, :, :70]):
        raise AssertionError("monthly injection changed incumbent channels")
    return out


def design_metadata() -> dict[str, object]:
    return {
        "design_id": "R3-X-DECOMP-MONTHLY-DESIGN-20260907-01",
        "coarse_stage": {
            "arms": ["H", "E", "F"],
            "new_fits": "E only: 2 clocks x 3 seeds = 6",
            "max_cycles": 18,
            "reuse_F_H": True,
            "rerun_F_H": False,
            "contrasts": coarse_contrasts(),
        },
        "fine_stage": {
            "status": "preregistered_not_authorized",
            "arms": ["STATE_VALUE_PLUS_E", "BETA_ONLY", "BETA_RELIABILITY"],
            "contrasts": list(fine_contrasts_preregistered()),
        },
        "monthly": {
            "status": "timing_interface_implemented_formula_identity_unbound",
            "comparison": "F_plus_monthly_minus_F",
            "channel": 70,
            "feature_dim_unchanged": True,
            "timing": "each sequence endpoint uses encoded statistic from its own previous completed calendar month",
            "missing_policy": "error_no_invented_neutral_value",
            "exact_S_obs_1sigma_formula_recovered": False,
        },
        "fresh_oos": False,
        "full_pit_certified": False,
        "production_authority": False,
    }


class MonthlyConditionStoreView:
    """Read-only view that populates experimental channel 70 causally.

    It delegates every attribute to the incumbent K1 store and changes only the
    feature array returned by ``assemble_inputs``. The endpoint for each of the
    10 sequence positions is the same H20-spaced endpoint used by K1 history.
    No target is read by ``assemble_inputs``.
    """

    def __init__(self, base_store: object, records: Iterable[MonthlyEncodedValue]):
        self._base = base_store
        self._records = tuple(records)
        calendar = np.asarray(getattr(base_store, "calendar"))
        if calendar.ndim != 1 or not len(calendar):
            raise ValueError("base store must expose a nonempty calendar")
        self._calendar = calendar

    def __getattr__(self, name: str):
        return getattr(self._base, name)

    def assemble_inputs(self, indices: np.ndarray):
        historical, features = self._base.assemble_inputs(indices)
        rows = np.asarray(getattr(self._base, "inference_rows")[indices], dtype=np.int64)
        offsets = np.arange(-(SEQUENCE_POINTS - 1) * 20, 1, 20, dtype=np.int64)
        points = rows[:, 0, None] + offsets[None, :]
        if (points < 0).any() or (points >= len(self._calendar)).any():
            raise ValueError("monthly condition endpoint outside calendar")
        dates = self._calendar[points]
        return historical, inject_monthly_experimental_slot(features, dates, self._records)
