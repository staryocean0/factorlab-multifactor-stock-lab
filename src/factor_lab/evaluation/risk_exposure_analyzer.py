"""Risk exposure analyzer for factor evaluation governance.

Provides repo-native risk exposure evidence layer so that
evaluation/backtest/governance/L7 can see candidate factor exposure
relative to industry, size, style, volatility, liquidity and other
standardized market risk dimensions.

Only uses REQ-001 in-scope standardized market data fields or existing
FactorFrame / evaluation observations. No external Barra/third-party
risk model dependency. When fields are insufficient, outputs
insufficient/unavailable rather than fabricating exposure.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(slots=True)
class IndustryExposure:
    """Industry exposure summary for a single industry bucket."""

    industry: str
    weight: float
    factor_mean: float
    count: int


@dataclass(slots=True)
class RiskExposureSummary:
    """Summary of risk exposure analysis for a candidate factor.

    All style exposure fields are optional hints; when the underlying
    data does not support computation they are set to ``unavailable``.
    """

    governance_verdict: Literal["pass", "review_required", "high_risk", "insufficient"]
    warning_flags: list[str]
    industry_exposure: list[IndustryExposure]
    industry_concentration_hhi: float
    size_exposure_beta: float
    size_exposure_status: Literal["computed", "unavailable"]
    style_value_hint: str
    style_momentum_hint: str
    style_low_volatility_hint: str
    style_liquidity_hint: str
    style_quality_hint: str
    residualization_status: Literal["computed", "unavailable"]
    residual_ic_vs_raw_ic: float | None
    observation_count: int
    period_count: int
    enhancement_type: str = "post_req001_risk_exposure_v1"

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for artifact storage."""
        payload = asdict(self)
        payload["industry_exposure"] = [
            asdict(ie) for ie in self.industry_exposure
        ]
        return payload


def _hhi(weights: list[float]) -> float:
    """Compute Herfindahl-Hirschman Index for concentration."""
    return sum(w * w for w in weights)


def _safe_mean(values: list[float]) -> float:
    """Compute mean, returning 0.0 for empty list."""
    return statistics.mean(values) if values else 0.0


def _compute_size_exposure(
    rows: list[dict[str, object]],
    size_field: str,
) -> tuple[float, Literal["computed", "unavailable"]]:
    """Compute size exposure as cross-sectional regression beta of factor on size.

    Returns (beta, status). If size_field is missing or insufficient
    data, returns (0.0, "unavailable").
    """
    pairs: list[tuple[float, float]] = []
    for row in rows:
        size_val = row.get(size_field)
        if size_val is None:
            continue
        try:
            s = float(str(size_val))
            f = float(str(row["factor_value"]))
        except (TypeError, ValueError):
            continue
        if math.isfinite(s) and math.isfinite(f):
            pairs.append((f, s))

    if len(pairs) < 10:
        return 0.0, "unavailable"

    factor_values = [p[0] for p in pairs]
    size_values = [p[1] for p in pairs]
    mean_f = _safe_mean(factor_values)
    mean_s = _safe_mean(size_values)
    var_f = sum((f - mean_f) ** 2 for f in factor_values)
    var_s = sum((s - mean_s) ** 2 for s in size_values)

    if var_f <= 0.0:
        return 0.0, "computed"
    if var_s <= 0.0:
        return 0.0, "unavailable"

    cov_fs = sum((f - mean_f) * (s - mean_s) for f, s in pairs)
    beta = cov_fs / math.sqrt(var_f * var_s)
    return beta, "computed"


def _compute_industry_exposure(
    rows: list[dict[str, object]],
    industry_field: str,
) -> tuple[list[IndustryExposure], float]:
    """Compute industry exposure and concentration HHI.

    Returns (industry_exposures, hhi). If industry_field is missing,
    returns empty list and HHI=0.0.
    """
    grouped: dict[str, list[float]] = {}
    for row in rows:
        industry = row.get(industry_field)
        if industry is None:
            continue
        try:
            fv = float(str(row["factor_value"]))
        except (TypeError, ValueError):
            continue
        if math.isfinite(fv):
            grouped.setdefault(str(industry), []).append(fv)

    if not grouped:
        return [], 0.0

    total_count = sum(len(v) for v in grouped.values())
    if total_count == 0:
        return [], 0.0

    exposures: list[IndustryExposure] = []
    weights: list[float] = []

    for industry, values in sorted(grouped.items()):
        count = len(values)
        weight = count / total_count
        factor_mean = _safe_mean(values)
        exposures.append(
            IndustryExposure(
                industry=industry,
                weight=round(weight, 6),
                factor_mean=round(factor_mean, 6),
                count=count,
            )
        )
        weights.append(weight)

    return exposures, _hhi(weights)


def _check_style_hints(
    rows: list[dict[str, object]],
) -> dict[str, str]:
    """Check for style exposure fields and produce hints.

    Style fields are optional. When present, produce a brief hint;
    when absent, mark as ``unavailable``.
    """
    hints: dict[str, str] = {}

    # Value style: PE/PB inverse or book-to-market
    value_fields = ("pe_ratio", "pb_ratio", "book_to_market", "ep_ratio", "bp_ratio")
    has_value = any(
        any(row.get(f) is not None for row in rows[:100]) for f in value_fields
    )
    hints["style_value_hint"] = "data_present" if has_value else "unavailable"

    # Momentum style: past return fields
    momentum_fields = ("past_return_1m", "past_return_3m", "past_return_12m")
    has_momentum = any(
        any(row.get(f) is not None for row in rows[:100]) for f in momentum_fields
    )
    hints["style_momentum_hint"] = "data_present" if has_momentum else "unavailable"

    # Low volatility style: realized vol or rolling vol
    vol_fields = ("realized_vol", "rolling_vol_20d", "volatility_20d")
    has_vol = any(
        any(row.get(f) is not None for row in rows[:100]) for f in vol_fields
    )
    hints["style_low_volatility_hint"] = "data_present" if has_vol else "unavailable"

    # Liquidity style: turnover, amihud, volume-based
    liq_fields = ("turnover", "amihud_illiquidity", "avg_turnover_20d")
    has_liq = any(
        any(row.get(f) is not None for row in rows[:100]) for f in liq_fields
    )
    hints["style_liquidity_hint"] = "data_present" if has_liq else "unavailable"

    # Quality style: ROE, profitability
    quality_fields = ("roe", "roa", "gross_margin", "operating_margin")
    has_quality = any(
        any(row.get(f) is not None for row in rows[:100]) for f in quality_fields
    )
    hints["style_quality_hint"] = "data_present" if has_quality else "unavailable"

    return hints


def _compute_residualization(
    rows: list[dict[str, object]],
    _industry_field: str,
    _size_field: str,
) -> tuple[Literal["computed", "unavailable"], float | None]:
    """Compare residual IC vs raw IC if neutralization data is available.

    Returns (status, ratio). ratio = residual_ic / raw_ic when both
    are available and raw_ic != 0. Otherwise returns
    ("unavailable", None).
    """
    # Check if neutralized factor values are available
    has_neutral = any("neutralized_factor_value" in row for row in rows[:50])
    if not has_neutral:
        return "unavailable", None

    # Compute raw IC proxy (mean factor_value * forward_return correlation)
    raw_pairs: list[tuple[float, float]] = []
    neutral_pairs: list[tuple[float, float]] = []
    for row in rows:
        try:
            raw_fv = float(str(row["factor_value"]))
            ret = float(str(row.get("forward_return", math.nan)))
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(raw_fv) and math.isfinite(ret)):
            continue
        raw_pairs.append((raw_fv, ret))
        neutral_fv = row.get("neutralized_factor_value")
        if neutral_fv is not None:
            try:
                nf = float(str(neutral_fv))
                if math.isfinite(nf):
                    neutral_pairs.append((nf, ret))
            except (TypeError, ValueError):
                pass

    if len(raw_pairs) < 10 or len(neutral_pairs) < 10:
        return "unavailable", None

    def _ic_proxy(pairs: list[tuple[float, float]]) -> float:
        """Simple IC proxy as correlation."""
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        n = len(xs)
        if n < 2:
            return 0.0
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        cov = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
        var_x = sum((x - mean_x) ** 2 for x in xs)
        var_y = sum((y - mean_y) ** 2 for y in ys)
        if var_x <= 0 or var_y <= 0:
            return 0.0
        return cov / (math.sqrt(var_x) * math.sqrt(var_y))

    raw_ic = _ic_proxy(raw_pairs)
    neutral_ic = _ic_proxy(neutral_pairs)

    if abs(raw_ic) < 1e-8:
        return "computed", None

    return "computed", round(neutral_ic / raw_ic, 6)


def analyze_risk_exposure(
    factor_rows: list[dict[str, object]],
    *,
    industry_field: str = "industry",
    size_field: str = "market_cap",
    industry_concentration_threshold: float = 0.25,
    size_exposure_threshold: float = 0.5,
) -> RiskExposureSummary:
    """Analyze risk exposure of a candidate factor.

    Args:
        factor_rows: Factor frame rows with factor_value and optional
            industry/size/style fields.
        industry_field: Field name for industry classification.
        size_field: Field name for market cap / size.
        industry_concentration_threshold: HHI threshold above which
            industry concentration triggers a warning.
        size_exposure_threshold: Absolute beta threshold above which
            size exposure triggers a warning.

    Returns:
        RiskExposureSummary with exposure analysis and governance verdict.
    """
    if not factor_rows:
        return RiskExposureSummary(
            governance_verdict="insufficient",
            warning_flags=["risk_model_input_insufficient"],
            industry_exposure=[],
            industry_concentration_hhi=0.0,
            size_exposure_beta=0.0,
            size_exposure_status="unavailable",
            style_value_hint="unavailable",
            style_momentum_hint="unavailable",
            style_low_volatility_hint="unavailable",
            style_liquidity_hint="unavailable",
            style_quality_hint="unavailable",
            residualization_status="unavailable",
            residual_ic_vs_raw_ic=None,
            observation_count=0,
            period_count=0,
        )

    warning_flags: list[str] = []

    # Observation / period counts
    timestamps = {str(row.get("timestamp", "")) for row in factor_rows}
    observation_count = len(factor_rows)
    period_count = len(timestamps)

    # Industry exposure
    industry_exposures, industry_hhi = _compute_industry_exposure(
        factor_rows, industry_field
    )
    if not industry_exposures:
        warning_flags.append("style_exposure_unavailable")
    elif industry_hhi > industry_concentration_threshold:
        warning_flags.append("concentrated_industry_exposure")

    # Size exposure
    size_beta, size_status = _compute_size_exposure(factor_rows, size_field)
    if size_status == "unavailable":
        warning_flags.append("style_exposure_unavailable")
    elif abs(size_beta) > size_exposure_threshold:
        warning_flags.append("excessive_size_exposure")

    # Style hints
    style_hints = _check_style_hints(factor_rows)

    # Residualization
    residualization_status, residual_ratio = _compute_residualization(
        factor_rows, industry_field, size_field
    )
    if residualization_status == "unavailable":
        warning_flags.append("residualization_unavailable")

    # Governance verdict
    if not industry_exposures and size_status == "unavailable":
        verdict: Literal["pass", "review_required", "high_risk", "insufficient"] = (
            "insufficient"
        )
        if "risk_model_input_insufficient" not in warning_flags:
            warning_flags.append("risk_model_input_insufficient")
    elif (
        "concentrated_industry_exposure" in warning_flags
        and "excessive_size_exposure" in warning_flags
    ):
        verdict = "high_risk"
    elif warning_flags:
        verdict = "review_required"
    else:
        verdict = "pass"

    return RiskExposureSummary(
        governance_verdict=verdict,
        warning_flags=warning_flags,
        industry_exposure=industry_exposures,
        industry_concentration_hhi=round(industry_hhi, 6),
        size_exposure_beta=round(size_beta, 6),
        size_exposure_status=size_status,
        style_value_hint=style_hints["style_value_hint"],
        style_momentum_hint=style_hints["style_momentum_hint"],
        style_low_volatility_hint=style_hints["style_low_volatility_hint"],
        style_liquidity_hint=style_hints["style_liquidity_hint"],
        style_quality_hint=style_hints["style_quality_hint"],
        residualization_status=residualization_status,
        residual_ic_vs_raw_ic=residual_ratio,
        observation_count=observation_count,
        period_count=period_count,
    )
