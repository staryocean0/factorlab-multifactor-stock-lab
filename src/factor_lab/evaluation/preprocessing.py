"""Preprocessing utilities for factor evaluation."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from math import sqrt
from pathlib import Path
from typing import cast

from factor_lab.core.errors import NotFoundError, ValidationError


def _float_from_object(value: object) -> float:
    return float(str(value))


def _load_preprocess_spec(
    preprocess_spec_version: str,
    fixture_root: Path,
) -> dict[str, object]:
    version = preprocess_spec_version.strip()
    if not version:
        return {
            "name": "",
            "description": "No preprocessing applied",
            "transforms": [],
        }

    spec_path = fixture_root / f"{version}.json"
    if not spec_path.exists():
        raise NotFoundError(f"Preprocess spec not found: {preprocess_spec_version}")

    payload = cast(object, json.loads(spec_path.read_text(encoding="utf-8")))
    if not isinstance(payload, dict):
        raise ValidationError(
            f"Preprocess spec payload is invalid: {preprocess_spec_version}"
        )

    transforms = payload.get("transforms", [])
    if not isinstance(transforms, list):
        raise ValidationError(
            f"Preprocess spec transforms are invalid: {preprocess_spec_version}"
        )

    spec = dict(payload)
    spec["transforms"] = transforms
    return spec


def _clip_rows(
    rows: Iterable[dict[str, object]],
    *,
    min_value: float,
    max_value: float,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    clipped_rows: list[dict[str, object]] = []
    changed_row_count = 0
    for row in rows:
        next_row = dict(row)
        original_value = _float_from_object(next_row["factor_value"])
        clipped_value = max(min(original_value, max_value), min_value)
        if round(clipped_value, 6) != round(original_value, 6):
            changed_row_count += 1
        next_row["factor_value"] = round(clipped_value, 6)
        clipped_rows.append(next_row)
    return clipped_rows, {
        "kind": "clip",
        "min_value": min_value,
        "max_value": max_value,
        "changed_row_count": changed_row_count,
    }


def _zscore_rows_by_timestamp(
    rows: Iterable[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    indexed_rows = [dict(row) for row in rows]
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(indexed_rows):
        grouped[str(row["timestamp"])].append(index)

    changed_row_count = 0
    standardized_group_count = 0
    for indices in grouped.values():
        values = [
            _float_from_object(indexed_rows[index]["factor_value"]) for index in indices
        ]
        mean_value = sum(values) / len(values)
        variance = sum((value - mean_value) ** 2 for value in values) / len(values)
        std_value = sqrt(variance)
        if std_value > 0.0:
            standardized_group_count += 1
        for index, original_value in zip(indices, values, strict=False):
            zscore_value = (
                0.0
                if std_value == 0.0
                else (original_value - mean_value) / std_value
            )
            if round(zscore_value, 6) != round(original_value, 6):
                changed_row_count += 1
            indexed_rows[index]["factor_value"] = round(zscore_value, 6)

    return indexed_rows, {
        "kind": "zscore_by_timestamp",
        "group_count": len(grouped),
        "standardized_group_count": standardized_group_count,
        "changed_row_count": changed_row_count,
    }


def apply_preprocess_spec(
    factor_rows: list[dict[str, object]],
    *,
    preprocess_spec_version: str,
    fixture_root: Path,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Apply a fixture-backed preprocessing pipeline to factor rows."""
    spec = _load_preprocess_spec(preprocess_spec_version, fixture_root)
    transforms = cast(list[object], spec.get("transforms", []))
    processed_rows = [dict(row) for row in factor_rows]
    applied_transforms: list[dict[str, object]] = []

    for transform in transforms:
        if not isinstance(transform, dict):
            raise ValidationError(
                f"Preprocess transform is invalid: {preprocess_spec_version}"
            )
        transform_config = cast(dict[str, object], transform)
        kind = str(transform_config.get("kind", "")).strip()
        if kind == "clip":
            processed_rows, summary = _clip_rows(
                processed_rows,
                min_value=_float_from_object(transform_config.get("min_value", -1.0)),
                max_value=_float_from_object(transform_config.get("max_value", 1.0)),
            )
        elif kind in {"zscore_by_timestamp", "zscore"}:
            processed_rows, summary = _zscore_rows_by_timestamp(processed_rows)
        elif kind in {"winsorize_by_timestamp", "winsorize"}:
            processed_rows, summary = _winsorize_rows_by_timestamp(
                processed_rows,
                lower_quantile=_float_from_object(
                    transform_config.get("lower_quantile", 0.01)
                ),
                upper_quantile=_float_from_object(
                    transform_config.get("upper_quantile", 0.99)
                ),
            )
        elif kind in {"rank_by_timestamp", "rank"}:
            processed_rows, summary = _rank_rows_by_timestamp(processed_rows)
        else:
            raise ValidationError(
                "Unsupported preprocess transform "
                f"'{kind}' in {preprocess_spec_version}"
            )
        applied_transforms.append(summary)

    return processed_rows, {
        "preprocess_spec_version": preprocess_spec_version,
        "name": str(spec.get("name", preprocess_spec_version)),
        "description": str(spec.get("description", "")),
        "transform_count": len(applied_transforms),
        "applied_transforms": applied_transforms,
        "row_count": len(processed_rows),
        "timestamp_count": len({str(row["timestamp"]) for row in processed_rows}),
        "noop": len(applied_transforms) == 0,
    }


def _percentile(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        return 0.0
    clipped_quantile = max(0.0, min(1.0, quantile))
    position = clipped_quantile * (len(sorted_values) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    weight = position - lower_index
    return (
        sorted_values[lower_index] * (1.0 - weight)
        + sorted_values[upper_index] * weight
    )


def _winsorize_rows_by_timestamp(
    rows: Iterable[dict[str, object]],
    *,
    lower_quantile: float,
    upper_quantile: float,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    indexed_rows = [dict(row) for row in rows]
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(indexed_rows):
        grouped[str(row["timestamp"])].append(index)

    changed_row_count = 0
    for indices in grouped.values():
        values = sorted(
            _float_from_object(indexed_rows[index]["factor_value"])
            for index in indices
        )
        lower = _percentile(values, lower_quantile)
        upper = _percentile(values, upper_quantile)
        for index in indices:
            original_value = _float_from_object(indexed_rows[index]["factor_value"])
            winsorized_value = max(lower, min(original_value, upper))
            if round(winsorized_value, 6) != round(original_value, 6):
                changed_row_count += 1
            indexed_rows[index]["factor_value"] = round(winsorized_value, 6)
    return indexed_rows, {
        "kind": "winsorize_by_timestamp",
        "lower_quantile": lower_quantile,
        "upper_quantile": upper_quantile,
        "group_count": len(grouped),
        "changed_row_count": changed_row_count,
    }


def _rank_rows_by_timestamp(
    rows: Iterable[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    indexed_rows = [dict(row) for row in rows]
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(indexed_rows):
        grouped[str(row["timestamp"])].append(index)

    changed_row_count = 0
    for indices in grouped.values():
        if len(indices) == 1:
            ranked_values = {indices[0]: 0.5}
        else:
            ordered = sorted(
                indices,
                key=lambda item: _float_from_object(indexed_rows[item]["factor_value"]),
            )
            ranked_values = {
                row_index: rank / (len(indices) - 1)
                for rank, row_index in enumerate(ordered)
            }
        for index in indices:
            original_value = _float_from_object(indexed_rows[index]["factor_value"])
            ranked_value = round(ranked_values[index], 6)
            if round(original_value, 6) != ranked_value:
                changed_row_count += 1
            indexed_rows[index]["factor_value"] = ranked_value
    return indexed_rows, {
        "kind": "rank_by_timestamp",
        "group_count": len(grouped),
        "changed_row_count": changed_row_count,
    }


def _demean_indices(
    rows: list[dict[str, object]],
    indices: list[int],
) -> int:
    if not indices:
        return 0
    values = [_float_from_object(rows[index]["factor_value"]) for index in indices]
    mean_value = sum(values) / len(values)
    changed = 0
    for index, original_value in zip(indices, values, strict=False):
        neutral_value = round(original_value - mean_value, 6)
        if neutral_value != round(original_value, 6):
            changed += 1
        rows[index]["factor_value"] = neutral_value
    return changed


def _neutralize_market(
    rows: Iterable[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    indexed_rows = [dict(row) for row in rows]
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(indexed_rows):
        grouped[str(row["timestamp"])].append(index)
    changed = sum(
        _demean_indices(indexed_rows, indices) for indices in grouped.values()
    )
    return indexed_rows, {
        "kind": "neutralize_market",
        "group_count": len(grouped),
        "changed_row_count": changed,
    }


def _neutralize_industry(
    rows: Iterable[dict[str, object]],
    *,
    industry_field: str,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    indexed_rows = [dict(row) for row in rows]
    grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
    missing_count = 0
    for index, row in enumerate(indexed_rows):
        industry = row.get(industry_field)
        if industry is None:
            missing_count += 1
            continue
        grouped[(str(row["timestamp"]), str(industry))].append(index)
    changed = sum(
        _demean_indices(indexed_rows, indices) for indices in grouped.values()
    )
    return indexed_rows, {
        "kind": "neutralize_industry",
        "industry_field": industry_field,
        "group_count": len(grouped),
        "missing_count": missing_count,
        "changed_row_count": changed,
    }


def _neutralize_size(
    rows: Iterable[dict[str, object]],
    *,
    size_field: str,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    indexed_rows = [dict(row) for row in rows]
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(indexed_rows):
        grouped[str(row["timestamp"])].append(index)

    changed = 0
    neutralized_groups = 0
    for indices in grouped.values():
        pairs = [
            (
                index,
                _float_from_object(indexed_rows[index]["factor_value"]),
                _float_from_object(indexed_rows[index][size_field]),
            )
            for index in indices
            if size_field in indexed_rows[index]
        ]
        if len(pairs) < 2:
            continue
        mean_factor = sum(pair[1] for pair in pairs) / len(pairs)
        mean_size = sum(pair[2] for pair in pairs) / len(pairs)
        variance_size = sum((pair[2] - mean_size) ** 2 for pair in pairs)
        if variance_size <= 0.0:
            continue
        beta = sum(
            (factor - mean_factor) * (size - mean_size)
            for _, factor, size in pairs
        )
        beta /= variance_size
        neutralized_groups += 1
        for index, original_value, size_value in pairs:
            fitted = mean_factor + beta * (size_value - mean_size)
            neutral_value = round(original_value - fitted, 6)
            if neutral_value != round(original_value, 6):
                changed += 1
            indexed_rows[index]["factor_value"] = neutral_value
    return indexed_rows, {
        "kind": "neutralize_size",
        "size_field": size_field,
        "group_count": len(grouped),
        "neutralized_group_count": neutralized_groups,
        "changed_row_count": changed,
    }


def _bool_from_config(config: dict[str, object], key: str) -> bool:
    value = config.get(key)
    return bool(value) if value is not None else False


def apply_preprocess_config(
    factor_rows: list[dict[str, object]],
    *,
    preprocessing_config: dict[str, object] | None = None,
    neutralization_config: dict[str, object] | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Apply request-level validation-kernel transforms.

    This is intentionally config-dict based so API schemas can evolve without
    creating a second fixture format. Supported preprocessing keys are
    `winsorize`, `zscore`, and `rank`; supported neutralization methods are
    `market`, `industry`, and `size`.
    """
    processed_rows = [dict(row) for row in factor_rows]
    applied_transforms: list[dict[str, object]] = []
    preprocessing = preprocessing_config or {}
    neutralization = neutralization_config or {}

    winsorize_config = preprocessing.get("winsorize")
    if isinstance(winsorize_config, dict):
        winsorize = cast(dict[str, object], winsorize_config)
        processed_rows, summary = _winsorize_rows_by_timestamp(
            processed_rows,
            lower_quantile=_float_from_object(
                winsorize.get("lower_quantile", 0.01)
            ),
            upper_quantile=_float_from_object(
                winsorize.get("upper_quantile", 0.99)
            ),
        )
        applied_transforms.append(summary)
    elif _bool_from_config(preprocessing, "winsorize"):
        processed_rows, summary = _winsorize_rows_by_timestamp(
            processed_rows,
            lower_quantile=0.01,
            upper_quantile=0.99,
        )
        applied_transforms.append(summary)

    if _bool_from_config(preprocessing, "zscore"):
        processed_rows, summary = _zscore_rows_by_timestamp(processed_rows)
        applied_transforms.append(summary)

    if _bool_from_config(preprocessing, "rank"):
        processed_rows, summary = _rank_rows_by_timestamp(processed_rows)
        applied_transforms.append(summary)

    methods_value = neutralization.get("methods", [])
    methods = (
        [str(item) for item in cast(list[object], methods_value)]
        if isinstance(methods_value, list)
        else []
    )
    if "market" in methods:
        processed_rows, summary = _neutralize_market(processed_rows)
        applied_transforms.append(summary)
    if "industry" in methods:
        processed_rows, summary = _neutralize_industry(
            processed_rows,
            industry_field=str(neutralization.get("industry_field", "industry")),
        )
        applied_transforms.append(summary)
    if "size" in methods:
        processed_rows, summary = _neutralize_size(
            processed_rows,
            size_field=str(neutralization.get("size_field", "market_cap")),
        )
        applied_transforms.append(summary)

    return processed_rows, {
        "preprocessing_config": preprocessing,
        "neutralization_config": neutralization,
        "transform_count": len(applied_transforms),
        "applied_transforms": applied_transforms,
        "row_count": len(processed_rows),
        "timestamp_count": len({str(row["timestamp"]) for row in processed_rows}),
        "noop": len(applied_transforms) == 0,
    }
