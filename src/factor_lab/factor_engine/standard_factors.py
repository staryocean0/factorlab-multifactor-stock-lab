"""REQ-001 standard price/volume factor library.

The registry in this module is the authoritative in-code catalog for the first
standard factor library slice.  All specs are constrained to
`source_family=price_volume` and their calculators preserve PIT timestamps plus
input-field lineage on every generated factor-frame row.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from factor_lab.core.errors import NotFoundError, ValidationError
from factor_lab.core.source_universe import PRICE_VOLUME_SOURCE_FAMILY
from factor_lab.factor_engine.models.factor_spec import FactorSpec

_PRICE_VOLUME_FIELDS = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True, slots=True)
class StandardFactorDefinition:
    """Static catalog definition for a standard factor."""

    spec_version: str
    name: str
    description: str
    family: str
    window: int
    required_fields: tuple[str, ...]
    output_field: str

    def to_factor_spec(self) -> FactorSpec:
        return FactorSpec(
            spec_id=self.spec_version,
            spec_version=self.spec_version,
            name=self.name,
            description=self.description,
            factor_type="standard_price_volume",
            callable_ref=f"factor_lab.factor_engine.standard_factors:{self.family}",
            input_schema={
                "required_fields": list(self.required_fields),
                "pit_required": True,
                "timestamp_fields": ["timestamp", "asof_date", "available_at"],
            },
            output_schema={
                "factor_name": self.output_field,
                "factor_type": "float",
                "long_table": True,
            },
            parameters={"window": self.window, "family": self.family},
            source_family=PRICE_VOLUME_SOURCE_FAMILY,
            input_field_lineage={
                field: f"dataset.rows[].{field}" for field in self.required_fields
            },
            tags={
                "library": "standard_price_volume",
                "req": "REQ-001",
                "pit": "required",
            },
        )


STANDARD_FACTOR_DEFINITIONS: tuple[StandardFactorDefinition, ...] = (
    StandardFactorDefinition(
        spec_version="fac_mom_20d@1.0",
        name="momentum_20d",
        description="Close-to-close momentum with 20-bar lookback fallback.",
        family="momentum",
        window=20,
        required_fields=("open", "close"),
        output_field="momentum_20d",
    ),
    StandardFactorDefinition(
        spec_version="fac_return_1d@1.0",
        name="return_1d",
        description="One-bar close-to-close return.",
        family="return",
        window=1,
        required_fields=("open", "close"),
        output_field="return_1d",
    ),
    StandardFactorDefinition(
        spec_version="fac_reversal_5d@1.0",
        name="reversal_5d",
        description="Negative 5-bar momentum reversal signal.",
        family="reversal",
        window=5,
        required_fields=("open", "close"),
        output_field="reversal_5d",
    ),
    StandardFactorDefinition(
        spec_version="fac_vol_20d@1.0",
        name="volatility_20d",
        description="Rolling standard deviation of returns with range fallback.",
        family="rolling_volatility",
        window=20,
        required_fields=("high", "low", "close"),
        output_field="volatility_20d",
    ),
    StandardFactorDefinition(
        spec_version="fac_rolling_volatility_20d@1.0",
        name="rolling_volatility_20d",
        description="Alias for the standard 20-bar rolling volatility factor.",
        family="rolling_volatility",
        window=20,
        required_fields=("high", "low", "close"),
        output_field="rolling_volatility_20d",
    ),
    StandardFactorDefinition(
        spec_version="fac_volume_change_5d@1.0",
        name="volume_change_5d",
        description="Volume change versus the 5-bar lag or previous bar fallback.",
        family="volume_change",
        window=5,
        required_fields=("volume",),
        output_field="volume_change_5d",
    ),
    StandardFactorDefinition(
        spec_version="fac_liquidity_turnover_proxy_20d@1.0",
        name="liquidity_turnover_proxy_20d",
        description="Dollar-volume liquidity proxy normalized by rolling mean.",
        family="liquidity_turnover_proxy",
        window=20,
        required_fields=("close", "volume"),
        output_field="liquidity_turnover_proxy_20d",
    ),
    StandardFactorDefinition(
        spec_version="fac_ma_deviation_20d@1.0",
        name="ma_deviation_20d",
        description="Close deviation from the rolling moving average.",
        family="moving_average_deviation",
        window=20,
        required_fields=("close",),
        output_field="ma_deviation_20d",
    ),
    StandardFactorDefinition(
        spec_version="fac_rolling_range_20d@1.0",
        name="rolling_range_20d",
        description="Rolling high-low range scaled by close.",
        family="rolling_range",
        window=20,
        required_fields=("high", "low", "close"),
        output_field="rolling_range_20d",
    ),
)

_SPEC_BY_VERSION: dict[str, StandardFactorDefinition] = {
    definition.spec_version: definition for definition in STANDARD_FACTOR_DEFINITIONS
}
_SPEC_BY_NAME: dict[str, StandardFactorDefinition] = {
    definition.name: definition for definition in STANDARD_FACTOR_DEFINITIONS
}


def list_standard_factor_specs() -> list[FactorSpec]:
    """Return all standard factor specs in stable registry order."""

    return [definition.to_factor_spec() for definition in STANDARD_FACTOR_DEFINITIONS]


def get_standard_factor_spec(spec_version_or_name: str) -> FactorSpec | None:
    """Return a standard spec by version or factor name."""

    definition = _SPEC_BY_VERSION.get(spec_version_or_name) or _SPEC_BY_NAME.get(
        spec_version_or_name
    )
    return definition.to_factor_spec() if definition is not None else None


def require_standard_factor_definition(
    spec_version_or_name: str,
) -> StandardFactorDefinition:
    """Return a standard factor definition or raise a public not-found error."""

    definition = _SPEC_BY_VERSION.get(spec_version_or_name) or _SPEC_BY_NAME.get(
        spec_version_or_name
    )
    if definition is None:
        raise NotFoundError(f"Standard factor spec not found: {spec_version_or_name}")
    return definition


def _float_from_row(row: Mapping[str, object], field: str) -> float:
    value = row.get(field)
    if value is None:
        raise ValidationError(f"Missing required factor input field: {field}")
    return float(str(value))


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0.0 or not math.isfinite(denominator):
        return 0.0
    return numerator / denominator


def _window_start(index: int, window: int) -> int:
    return max(0, index - max(window, 1) + 1)


def _lag_value(values: Sequence[float], index: int, window: int) -> float | None:
    lag_index = index - max(window, 1)
    if lag_index >= 0:
        return values[lag_index]
    if index > 0:
        return values[index - 1]
    return None


def _pstdev(values: Sequence[float]) -> float:
    finite = [value for value in values if math.isfinite(value)]
    if len(finite) < 2:
        return 0.0
    return statistics.pstdev(finite)


def _mean(values: Sequence[float]) -> float:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return 0.0
    return statistics.mean(finite)


class StandardPriceVolumeFactorCalculator:
    """Compute standard price/volume factor frames from PIT bar rows."""

    @staticmethod
    def _factor_value(
        definition: StandardFactorDefinition,
        *,
        index: int,
        rows: Sequence[Mapping[str, object]],
        closes: Sequence[float],
        highs: Sequence[float],
        lows: Sequence[float],
        volumes: Sequence[float],
    ) -> float:
        row = rows[index]
        open_price = _float_from_row(row, "open") if "open" in row else closes[index]
        close_price = closes[index]
        window = definition.window
        lag_close = _lag_value(closes, index, window)

        if definition.family in {"momentum", "return"}:
            base = lag_close if lag_close is not None else open_price
            return _safe_ratio(close_price, base) - 1.0

        if definition.family == "reversal":
            base = lag_close if lag_close is not None else open_price
            return -((_safe_ratio(close_price, base)) - 1.0)

        if definition.family == "rolling_volatility":
            start = max(1, index - window + 1)
            returns = [
                _safe_ratio(closes[item], closes[item - 1]) - 1.0
                for item in range(start, index + 1)
            ]
            if len(returns) >= 2:
                return _pstdev(returns)
            return _safe_ratio(highs[index] - lows[index], close_price)

        if definition.family == "volume_change":
            lag_volume = _lag_value(volumes, index, window)
            base_volume = lag_volume if lag_volume is not None else volumes[index]
            return _safe_ratio(volumes[index], base_volume) - 1.0

        if definition.family == "liquidity_turnover_proxy":
            dollar_volume = [
                close * volume
                for close, volume in zip(closes, volumes, strict=False)
            ]
            start = _window_start(index, window)
            rolling_mean = _mean(dollar_volume[start : index + 1])
            return _safe_ratio(dollar_volume[index], rolling_mean) - 1.0

        if definition.family == "moving_average_deviation":
            start = _window_start(index, window)
            moving_average = _mean(closes[start : index + 1])
            return _safe_ratio(close_price, moving_average) - 1.0

        if definition.family == "rolling_range":
            start = _window_start(index, window)
            high_value = max(highs[start : index + 1])
            low_value = min(lows[start : index + 1])
            return _safe_ratio(high_value - low_value, close_price)

        raise ValidationError(
            f"Unsupported standard factor family: {definition.family}"
        )

    def build_frame(
        self,
        price_rows: Sequence[Mapping[str, object]],
        *,
        factor_spec_version: str,
        source_refs: Sequence[str],
    ) -> list[dict[str, object]]:
        """Build a long factor frame with row-level lineage."""

        definition = require_standard_factor_definition(factor_spec_version)
        by_symbol: dict[str, list[Mapping[str, object]]] = defaultdict(list)
        for row in price_rows:
            symbol = str(row.get("symbol") or row.get("asset_id") or "")
            if not symbol:
                raise ValidationError("Price row is missing symbol/asset_id")
            by_symbol[symbol].append(row)

        factor_rows: list[dict[str, object]] = []
        source_ref_list = list(dict.fromkeys(str(ref) for ref in source_refs))
        lineage = {
            field: f"{','.join(source_ref_list) or 'dataset'}.rows[].{field}"
            for field in definition.required_fields
        }
        for symbol, symbol_rows in sorted(by_symbol.items()):
            ordered_rows = sorted(symbol_rows, key=lambda row: str(row["timestamp"]))
            closes = [_float_from_row(row, "close") for row in ordered_rows]
            highs = [
                _float_from_row(row, "high") if "high" in row else closes[index]
                for index, row in enumerate(ordered_rows)
            ]
            lows = [
                _float_from_row(row, "low") if "low" in row else closes[index]
                for index, row in enumerate(ordered_rows)
            ]
            volumes = [
                _float_from_row(row, "volume") if "volume" in row else 0.0
                for row in ordered_rows
            ]
            for index, row in enumerate(ordered_rows):
                value = self._factor_value(
                    definition,
                    index=index,
                    rows=ordered_rows,
                    closes=closes,
                    highs=highs,
                    lows=lows,
                    volumes=volumes,
                )
                factor_rows.append(
                    {
                        "symbol": symbol,
                        "timestamp": str(row["timestamp"]),
                        "asof_date": str(row.get("asof_date", row["timestamp"])),
                        "available_at": str(
                            row.get("available_at", row.get("timestamp", ""))
                        ),
                        "factor_value": round(value, 6),
                        "factor_name": definition.name,
                        "factor_spec_version": definition.spec_version,
                        "source_family": PRICE_VOLUME_SOURCE_FAMILY,
                        "source_refs": source_ref_list,
                        "input_field_lineage": lineage,
                        "asset_kind": str(
                            row.get("asset_kind")
                            or row.get("instrument_type")
                            or "tradable_instrument"
                        ),
                        "is_self_built_asset": bool(
                            row.get("is_self_built_asset", False)
                        ),
                    }
                )
        return factor_rows


def build_standard_factor_frame(
    price_rows: Sequence[Mapping[str, object]],
    *,
    factor_spec_version: str,
    source_refs: Sequence[str],
) -> list[dict[str, object]]:
    """Convenience wrapper used by evaluation and tests."""

    return StandardPriceVolumeFactorCalculator().build_frame(
        price_rows,
        factor_spec_version=factor_spec_version,
        source_refs=source_refs,
    )
