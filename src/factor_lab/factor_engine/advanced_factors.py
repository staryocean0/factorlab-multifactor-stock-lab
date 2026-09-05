"""REQ-001 advanced standardized-market factor library.

The factors in this module close the non-price-volume source-family gap without
expanding the universe beyond REQ-001.  They are deliberately small,
deterministic calculators over structured PIT rows so the governance chain can
exercise fundamental, macro/industry, microstructure, and cross-asset/
derivatives inputs end to end.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from factor_lab.core.errors import NotFoundError, ValidationError
from factor_lab.factor_engine.models.factor_spec import FactorSpec


@dataclass(frozen=True, slots=True)
class AdvancedFactorDefinition:
    """Static catalog definition for an advanced source-family factor."""

    spec_version: str
    name: str
    description: str
    family: str
    source_family: str
    required_fields: tuple[str, ...]
    output_field: str
    frequency: str

    def to_factor_spec(self) -> FactorSpec:
        return FactorSpec(
            spec_id=self.spec_version,
            spec_version=self.spec_version,
            name=self.name,
            description=self.description,
            factor_type="advanced_standardized_market",
            callable_ref=f"factor_lab.factor_engine.advanced_factors:{self.family}",
            input_schema={
                "required_fields": list(self.required_fields),
                "pit_required": True,
                "timestamp_fields": ["timestamp", "asof_date", "available_at"],
                "frequency": self.frequency,
            },
            output_schema={
                "factor_name": self.output_field,
                "factor_type": "float",
                "long_table": True,
            },
            parameters={
                "family": self.family,
                "source_family": self.source_family,
            },
            source_family=self.source_family,
            input_field_lineage={
                field: f"dataset.rows[].{field}" for field in self.required_fields
            },
            tags={
                "library": "advanced_standardized_market",
                "req": "REQ-001",
                "pit": "required",
                "frequency": self.frequency,
            },
        )


ADVANCED_FACTOR_DEFINITIONS: tuple[AdvancedFactorDefinition, ...] = (
    AdvancedFactorDefinition(
        spec_version="fac_fundamental_quality@1.0",
        name="fundamental_quality",
        description=(
            "Quality composite using profitability, margin, cash-flow quality, "
            "growth, and leverage from structured fundamental rows."
        ),
        family="fundamental_quality",
        source_family="fundamental",
        required_fields=(
            "roe",
            "gross_margin",
            "operating_cash_flow_ratio",
            "revenue_growth",
            "leverage",
        ),
        output_field="fundamental_quality",
        frequency="quarterly",
    ),
    AdvancedFactorDefinition(
        spec_version="fac_macro_industry_relative_strength@1.0",
        name="macro_industry_relative_strength",
        description=(
            "Industry relative strength adjusted by macro sensitivity and "
            "style/size exposures."
        ),
        family="macro_industry_relative_strength",
        source_family="macro_industry",
        required_fields=(
            "industry_return",
            "benchmark_return",
            "macro_beta",
            "style_value",
            "size_exposure",
        ),
        output_field="macro_industry_relative_strength",
        frequency="daily",
    ),
    AdvancedFactorDefinition(
        spec_version="fac_microstructure_liquidity_pressure@1.0",
        name="microstructure_liquidity_pressure",
        description=(
            "Microstructure liquidity pressure from spread, depth imbalance, "
            "order-flow imbalance, trade intensity, and realized intraday vol."
        ),
        family="microstructure_liquidity_pressure",
        source_family="microstructure",
        required_fields=(
            "quoted_spread",
            "depth_imbalance",
            "order_flow_imbalance",
            "trade_intensity",
            "intraday_realized_vol",
        ),
        output_field="microstructure_liquidity_pressure",
        frequency="intraday",
    ),
    AdvancedFactorDefinition(
        spec_version="fac_cross_asset_derivative_carry@1.0",
        name="cross_asset_derivative_carry",
        description=(
            "Cross-asset/derivatives carry signal combining basis, term "
            "structure, implied-volatility skew, FX beta, and commodity beta."
        ),
        family="cross_asset_derivative_carry",
        source_family="cross_asset_derivatives",
        required_fields=(
            "futures_basis",
            "term_structure_slope",
            "implied_vol_skew",
            "fx_beta",
            "commodity_beta",
        ),
        output_field="cross_asset_derivative_carry",
        frequency="daily",
    ),
)

_SPEC_BY_VERSION: dict[str, AdvancedFactorDefinition] = {
    definition.spec_version: definition for definition in ADVANCED_FACTOR_DEFINITIONS
}
_SPEC_BY_NAME: dict[str, AdvancedFactorDefinition] = {
    definition.name: definition for definition in ADVANCED_FACTOR_DEFINITIONS
}


def list_advanced_factor_specs() -> list[FactorSpec]:
    """Return all advanced standardized-market factor specs."""

    return [
        definition.to_factor_spec() for definition in ADVANCED_FACTOR_DEFINITIONS
    ]


def get_advanced_factor_spec(spec_version_or_name: str) -> FactorSpec | None:
    """Return an advanced spec by version or factor name."""

    definition = _SPEC_BY_VERSION.get(spec_version_or_name) or _SPEC_BY_NAME.get(
        spec_version_or_name
    )
    return definition.to_factor_spec() if definition is not None else None


def require_advanced_factor_definition(
    spec_version_or_name: str,
) -> AdvancedFactorDefinition:
    """Return an advanced factor definition or raise a public not-found error."""

    definition = _SPEC_BY_VERSION.get(spec_version_or_name) or _SPEC_BY_NAME.get(
        spec_version_or_name
    )
    if definition is None:
        raise NotFoundError(f"Advanced factor spec not found: {spec_version_or_name}")
    return definition


def _float_from_row(row: Mapping[str, object], field: str) -> float:
    value = row.get(field)
    if value is None:
        raise ValidationError(f"Missing required advanced factor input field: {field}")
    return float(str(value))


def _finite(value: float) -> float:
    return value if math.isfinite(value) else 0.0


class AdvancedStandardizedFactorCalculator:
    """Compute advanced standardized-market factor frames from PIT rows."""

    @staticmethod
    def _factor_value(
        definition: AdvancedFactorDefinition,
        row: Mapping[str, object],
    ) -> float:
        if definition.family == "fundamental_quality":
            profitability = _float_from_row(row, "roe")
            margin = _float_from_row(row, "gross_margin")
            cash_quality = _float_from_row(row, "operating_cash_flow_ratio")
            growth = _float_from_row(row, "revenue_growth")
            leverage = _float_from_row(row, "leverage")
            return _finite(
                (profitability * 0.35)
                + (margin * 0.20)
                + (cash_quality * 0.20)
                + (growth * 0.15)
                - (leverage * 0.10)
            )

        if definition.family == "macro_industry_relative_strength":
            industry_return = _float_from_row(row, "industry_return")
            benchmark_return = _float_from_row(row, "benchmark_return")
            macro_beta = _float_from_row(row, "macro_beta")
            style_value = _float_from_row(row, "style_value")
            size_exposure = _float_from_row(row, "size_exposure")
            return _finite(
                (industry_return - benchmark_return)
                + (0.10 * macro_beta)
                + (0.05 * style_value)
                - (0.03 * size_exposure)
            )

        if definition.family == "microstructure_liquidity_pressure":
            quoted_spread = _float_from_row(row, "quoted_spread")
            depth_imbalance = _float_from_row(row, "depth_imbalance")
            order_flow_imbalance = _float_from_row(row, "order_flow_imbalance")
            trade_intensity = _float_from_row(row, "trade_intensity")
            intraday_vol = _float_from_row(row, "intraday_realized_vol")
            return _finite(
                order_flow_imbalance
                + (0.50 * depth_imbalance)
                + (0.02 * trade_intensity)
                - quoted_spread
                - (0.50 * intraday_vol)
            )

        if definition.family == "cross_asset_derivative_carry":
            futures_basis = _float_from_row(row, "futures_basis")
            term_structure_slope = _float_from_row(row, "term_structure_slope")
            implied_vol_skew = _float_from_row(row, "implied_vol_skew")
            fx_beta = _float_from_row(row, "fx_beta")
            commodity_beta = _float_from_row(row, "commodity_beta")
            return _finite(
                futures_basis
                + (0.50 * term_structure_slope)
                - (0.25 * implied_vol_skew)
                + (0.10 * fx_beta)
                + (0.10 * commodity_beta)
            )

        raise ValidationError(
            f"Unsupported advanced factor family: {definition.family}"
        )

    def build_frame(
        self,
        rows: Sequence[Mapping[str, object]],
        *,
        factor_spec_version: str,
        source_refs: Sequence[str],
    ) -> list[dict[str, object]]:
        """Build a long factor frame with row-level advanced lineage."""

        definition = require_advanced_factor_definition(factor_spec_version)
        by_symbol: dict[str, list[Mapping[str, object]]] = defaultdict(list)
        for row in rows:
            symbol = str(row.get("symbol") or row.get("asset_id") or "")
            if not symbol:
                raise ValidationError("Advanced source row is missing symbol/asset_id")
            by_symbol[symbol].append(row)

        source_ref_list = list(dict.fromkeys(str(ref) for ref in source_refs))
        lineage = {
            field: f"{','.join(source_ref_list) or 'dataset'}.rows[].{field}"
            for field in definition.required_fields
        }
        factor_rows: list[dict[str, object]] = []
        for symbol, symbol_rows in sorted(by_symbol.items()):
            ordered_rows = sorted(symbol_rows, key=lambda row: str(row["timestamp"]))
            for row in ordered_rows:
                factor_rows.append(
                    {
                        "symbol": symbol,
                        "timestamp": str(row["timestamp"]),
                        "asof_date": str(row.get("asof_date", row["timestamp"])),
                        "available_at": str(
                            row.get("available_at", row.get("timestamp", ""))
                        ),
                        "factor_value": round(self._factor_value(definition, row), 6),
                        "factor_name": definition.name,
                        "factor_spec_version": definition.spec_version,
                        "source_family": definition.source_family,
                        "source_refs": source_ref_list,
                        "input_field_lineage": lineage,
                    }
                )
        return factor_rows


def build_advanced_factor_frame(
    rows: Sequence[Mapping[str, object]],
    *,
    factor_spec_version: str,
    source_refs: Sequence[str],
) -> list[dict[str, object]]:
    """Convenience wrapper used by evaluation and tests."""

    return AdvancedStandardizedFactorCalculator().build_frame(
        rows,
        factor_spec_version=factor_spec_version,
        source_refs=source_refs,
    )
