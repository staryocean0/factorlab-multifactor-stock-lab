"""Causal arithmetic reference for a declared three-factor return decomposition.

This module neither estimates coefficients nor constructs a prediction signal.
It checks the supplied identities and timestamps; those declarations do not
prove the point-in-time lineage of an external dataset or fitted model.  The
financial return residual here is distinct from a latent Koopman residual and
from an account's ``other`` contribution.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from numbers import Real
from types import MappingProxyType
from typing import Final

FINANCIAL_FACTOR_KEYS: Final = frozenset({"market", "size", "industry"})
SIMPLE_RETURN_UNIT: Final = "simple_decimal_return"


def _identity(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be an explicit nonempty identity")
    return value


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite real number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite real number")
    return result


def _factor_keys(values: Mapping[str, object], name: str) -> None:
    if not isinstance(values, Mapping) or set(values) != FINANCIAL_FACTOR_KEYS:
        raise ValueError(f"{name} must contain exactly market, size, industry")


@dataclass(frozen=True, slots=True)
class FinancialReturnConvention:
    """Explicit common estimand; 0.01 denotes a one-percent simple return.

    ``horizon_id`` identifies the declared horizon, such as one trading day;
    actual interval endpoints must also match at calculation. ``return_basis``
    identifies the declared return construction, not an executable price feed.
    Neither percentage-point returns nor log returns are accepted by this
    calculator. Currency and return basis must be the same across all series.
    """

    horizon_id: str
    return_basis: str
    currency: str
    unit: str = SIMPLE_RETURN_UNIT

    def __post_init__(self) -> None:
        for name in ("horizon_id", "return_basis", "currency"):
            _identity(getattr(self, name), name)
        if self.unit != SIMPLE_RETURN_UNIT:
            raise ValueError("unit must be simple_decimal_return")


@dataclass(frozen=True, slots=True)
class RealizedFinancialReturn:
    """One already-realized series observation, with explicit availability."""

    series_id: str
    period_id: str
    convention: FinancialReturnConvention
    start_at: datetime
    end_at: datetime
    available_at: datetime
    value: float

    def __post_init__(self) -> None:
        _identity(self.series_id, "series_id")
        _identity(self.period_id, "period_id")
        if not isinstance(self.convention, FinancialReturnConvention):
            raise ValueError("convention must be a FinancialReturnConvention")
        for name in ("start_at", "end_at", "available_at"):
            object.__setattr__(self, name, _utc(getattr(self, name), name))
        if not self.start_at < self.end_at <= self.available_at:
            raise ValueError("return requires start_at < end_at <= available_at")
        object.__setattr__(self, "value", _finite(self.value, "value"))


@dataclass(frozen=True, slots=True)
class FrozenFinancialCoefficients:
    """Previously frozen coefficients, with declared estimation timing.

    ``intercept=None`` explicitly means a no-intercept decomposition; a finite
    number means that fitted/frozen intercept is subtracted. ``industry`` is
    one explicitly identified industry-return series for this stock. A vector
    industry design requires a separately declared successor convention.

    The latest estimation-label timestamps bound all labels declared as used
    in estimation. ``information_available_at`` bounds all other estimation
    inputs as well. This object records that claim; it does not inspect fitting
    code, recover training rows, or certify an external model's source lineage.
    """

    stock_id: str
    convention: FinancialReturnConvention
    factor_ids: Mapping[str, str]
    betas: Mapping[str, float]
    intercept: float | None
    latest_estimation_label_end_at: datetime
    latest_estimation_label_available_at: datetime
    information_available_at: datetime
    frozen_at: datetime

    def __post_init__(self) -> None:
        _identity(self.stock_id, "stock_id")
        if not isinstance(self.convention, FinancialReturnConvention):
            raise ValueError("convention must be a FinancialReturnConvention")
        _factor_keys(self.factor_ids, "factor_ids")
        _factor_keys(self.betas, "betas")
        object.__setattr__(self, "factor_ids", MappingProxyType({
            key: _identity(self.factor_ids[key], f"factor_ids.{key}") for key in sorted(FINANCIAL_FACTOR_KEYS)
        }))
        object.__setattr__(self, "betas", MappingProxyType({
            key: _finite(self.betas[key], f"betas.{key}") for key in sorted(FINANCIAL_FACTOR_KEYS)
        }))
        if self.intercept is not None:
            object.__setattr__(self, "intercept", _finite(self.intercept, "intercept"))
        for name in (
            "latest_estimation_label_end_at", "latest_estimation_label_available_at",
            "information_available_at", "frozen_at",
        ):
            object.__setattr__(self, name, _utc(getattr(self, name), name))
        if not (
            self.latest_estimation_label_end_at <= self.latest_estimation_label_available_at
            <= self.information_available_at <= self.frozen_at
        ):
            raise ValueError("estimation labels and all inputs must be available before coefficient freeze")


@dataclass(frozen=True, slots=True)
class FinancialReturnResidual:
    """Bookkeeping result, available only after every realized input is visible.

    A zero value is valid. Nonzero epsilon can contain omitted common risks,
    coefficient error and noise; this result makes no alpha or predictability
    claim, and contains no latent-state or account-cost attribution.
    """

    stock_id: str
    period_id: str
    convention: FinancialReturnConvention
    observed_return: float
    intercept_contribution: float
    factor_contributions: Mapping[str, float]
    explained_return: float
    epsilon_return: float
    available_at: datetime
    calculated_at: datetime


def calculate_financial_return_residual(
    stock: RealizedFinancialReturn,
    factors: Mapping[str, RealizedFinancialReturn],
    coefficients: FrozenFinancialCoefficients,
    *,
    prediction_at: datetime,
    as_of: datetime,
) -> FinancialReturnResidual:
    """Return ``r - intercept - sum(beta_j * F_j)`` on one common interval.

    The coefficient freeze must precede or coincide with prediction, and the
    prediction must precede or coincide with the return interval's beginning.
    The realized inputs are never claimed as available at that prediction.
    ``as_of`` must be at least the latest stock/factor availability timestamp.
    Arithmetic and time consistency are necessary checks, not a PIT receipt.
    """
    if not isinstance(stock, RealizedFinancialReturn) or not isinstance(coefficients, FrozenFinancialCoefficients):
        raise ValueError("stock and coefficients must use the declared frozen input types")
    _factor_keys(factors, "factors")
    prediction_at = _utc(prediction_at, "prediction_at")
    as_of = _utc(as_of, "as_of")
    if stock.series_id != coefficients.stock_id:
        raise ValueError("stock identity does not match the frozen coefficients")
    if stock.convention != coefficients.convention:
        raise ValueError("stock horizon/units/return basis do not match the coefficient convention")
    if not coefficients.frozen_at <= prediction_at <= stock.start_at:
        raise ValueError("require coefficient frozen_at <= prediction_at <= return start_at")
    for key in sorted(FINANCIAL_FACTOR_KEYS):
        factor = factors[key]
        if not isinstance(factor, RealizedFinancialReturn):
            raise ValueError(f"factors.{key} must be a RealizedFinancialReturn")
        if factor.series_id != coefficients.factor_ids[key]:
            raise ValueError(f"factor identity mismatch: {key}")
        if (
            factor.period_id != stock.period_id or factor.start_at != stock.start_at
            or factor.end_at != stock.end_at or factor.convention != stock.convention
        ):
            raise ValueError(f"factor period/horizon/units/return basis mismatch: {key}")
    available_at = max(stock.available_at, *(factor.available_at for factor in factors.values()))
    if as_of < available_at:
        raise ValueError("financial return residual is unavailable before all realized labels are available")
    intercept = coefficients.intercept if coefficients.intercept is not None else 0.0
    contributions = {
        key: _finite(coefficients.betas[key] * factors[key].value, f"factor contribution {key}")
        for key in sorted(FINANCIAL_FACTOR_KEYS)
    }
    try:
        explained = _finite(math.fsum([intercept, *contributions.values()]), "explained_return")
        epsilon = _finite(math.fsum([stock.value, -intercept, *(-x for x in contributions.values())]), "epsilon_return")
    except OverflowError as exc:
        raise ValueError("return decomposition overflowed finite arithmetic") from exc
    return FinancialReturnResidual(
        stock_id=stock.series_id,
        period_id=stock.period_id,
        convention=stock.convention,
        observed_return=stock.value,
        intercept_contribution=intercept,
        factor_contributions=MappingProxyType(contributions),
        explained_return=explained,
        epsilon_return=epsilon,
        available_at=available_at,
        calculated_at=as_of,
    )
