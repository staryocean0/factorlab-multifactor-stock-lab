# pyright: reportPrivateImportUsage=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
"""Source-family contract and hard source-universe gate helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Final, cast

from pydantic.json_schema import JsonDict

from factor_lab.core.errors import FactorLabError, JsonValue
from factor_lab.core.runtime_state import runtime_state_store
from factor_lab.core.storage import read_json_storage_uri
from factor_lab.governance.services.state_machine import RunStatus

STANDARDIZED_MARKET_SOURCE_FAMILIES: Final[tuple[str, ...]] = (
    "price_volume",
    "fundamental",
    "macro_industry",
    "microstructure",
    "cross_asset_derivatives",
)
STANDARDIZED_MARKET_SOURCE_FAMILY_SET: Final[frozenset[str]] = frozenset(
    STANDARDIZED_MARKET_SOURCE_FAMILIES
)
PRICE_VOLUME_SOURCE_FAMILY: Final[str] = "price_volume"
SOURCE_UNIVERSE_GATE_NAME: Final[str] = "source_universe_gate"
SOURCE_UNIVERSE_ERROR_CODE: Final[str] = "E_SOURCE_UNIVERSE_OUT_OF_SCOPE"
SELF_BUILT_MARKET_ASSET_NAME: Final[str] = "云脊A股Beta指数"
SELF_BUILT_MARKET_ASSET_ENGLISH_NAME: Final[str] = "CN-A CloudRidge Beta Index"
SELF_BUILT_MARKET_ASSET_SYMBOL: Final[str] = "CN_A_CLOUDRIDGE_BETA_EQW"
MARKET_ASSET_KIND_TRADABLE: Final[str] = "tradable_instrument"
MARKET_ASSET_KIND_MARKET_INDEX: Final[str] = "market_index"
MARKET_ASSET_KIND_SELF_BUILT_INDEX: Final[str] = "self_built_index"
MARKET_ASSET_KIND_SELF_BUILT_PORTFOLIO: Final[str] = "self_built_portfolio"
STANDARDIZED_MARKET_ASSET_KINDS: Final[tuple[str, ...]] = (
    MARKET_ASSET_KIND_TRADABLE,
    MARKET_ASSET_KIND_MARKET_INDEX,
    MARKET_ASSET_KIND_SELF_BUILT_INDEX,
    MARKET_ASSET_KIND_SELF_BUILT_PORTFOLIO,
)
STANDARDIZED_MARKET_ASSET_KIND_SET: Final[frozenset[str]] = frozenset(
    STANDARDIZED_MARKET_ASSET_KINDS
)
SELF_BUILT_MARKET_ASSET_KINDS: Final[frozenset[str]] = frozenset(
    {
        MARKET_ASSET_KIND_SELF_BUILT_INDEX,
        MARKET_ASSET_KIND_SELF_BUILT_PORTFOLIO,
    }
)
MARKET_ASSET_KIND_ALIASES: Final[dict[str, str]] = {
    "": MARKET_ASSET_KIND_TRADABLE,
    "stock": MARKET_ASSET_KIND_TRADABLE,
    "equity": MARKET_ASSET_KIND_TRADABLE,
    "a_share": MARKET_ASSET_KIND_TRADABLE,
    "etf": MARKET_ASSET_KIND_TRADABLE,
    "lof": MARKET_ASSET_KIND_TRADABLE,
    "fund": MARKET_ASSET_KIND_TRADABLE,
    "bond": MARKET_ASSET_KIND_TRADABLE,
    "convertible_bond": MARKET_ASSET_KIND_TRADABLE,
    "future": MARKET_ASSET_KIND_TRADABLE,
    "option": MARKET_ASSET_KIND_TRADABLE,
    "index": MARKET_ASSET_KIND_MARKET_INDEX,
    "market_index": MARKET_ASSET_KIND_MARKET_INDEX,
    "benchmark_index": MARKET_ASSET_KIND_MARKET_INDEX,
    "custom_index": MARKET_ASSET_KIND_SELF_BUILT_INDEX,
    "self_built_index": MARKET_ASSET_KIND_SELF_BUILT_INDEX,
    "synthetic_index": MARKET_ASSET_KIND_SELF_BUILT_INDEX,
    "derived_index": MARKET_ASSET_KIND_SELF_BUILT_INDEX,
    "custom_portfolio": MARKET_ASSET_KIND_SELF_BUILT_PORTFOLIO,
    "self_built_portfolio": MARKET_ASSET_KIND_SELF_BUILT_PORTFOLIO,
    "synthetic_portfolio": MARKET_ASSET_KIND_SELF_BUILT_PORTFOLIO,
}
SOURCE_FAMILY_JSON_SCHEMA: Final[JsonDict] = {
    "enum": list(STANDARDIZED_MARKET_SOURCE_FAMILIES),
    "description": (
        "Standardized market-data source family. Out-of-scope families such as "
        "analyst_expectation, event_alpha, alternative_data, and alternative_nlp "
        "are hard-blocked by source_universe_gate."
    ),
}
OUT_OF_SCOPE_SOURCE_FAMILY_EXAMPLES: Final[frozenset[str]] = frozenset(
    {
        "analyst_expectation",
        "analyst_expectations",
        "event_alpha",
        "alternative_data",
        "alternative_nlp",
        "alt_data",
        "alt_nlp",
        "news_nlp",
    }
)


class SourceUniverseGateStatus(StrEnum):
    """Result of the REQ-001 source universe hard gate."""

    PASSED = "passed"
    BLOCKED = "blocked"


class SourceUniverseError(FactorLabError):
    """Hard failure for source families outside the standardized market universe."""

    code: str
    details: dict[str, JsonValue]

    def __init__(
        self,
        message: str,
        *,
        value: object | None = None,
        context: str | None = None,
        details: dict[str, JsonValue] | None = None,
    ) -> None:
        payload: dict[str, JsonValue] = {
            "gate_name": SOURCE_UNIVERSE_GATE_NAME,
            "allowed_source_families": list(STANDARDIZED_MARKET_SOURCE_FAMILIES),
        }
        if value is not None:
            payload["source_family"] = str(value)
        if context is not None:
            payload["context"] = context
        if details:
            payload.update(details)
        super().__init__(
            SOURCE_UNIVERSE_ERROR_CODE,
            message,
            status_code=409,
            retryable=False,
            details=payload,
        )
        self.code = SOURCE_UNIVERSE_ERROR_CODE
        self.details = payload


def _string_or_none(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def validate_source_family(value: object, *, context: str | None = None) -> str:
    """Return a normalized source family or raise a hard universe error."""

    family = _string_or_none(value)
    if family is None:
        raise SourceUniverseError(
            "source_family is required for source-bearing operations",
            value=value,
            context=context,
        )
    if family not in STANDARDIZED_MARKET_SOURCE_FAMILY_SET:
        raise SourceUniverseError(
            (
                f"source_family '{family}' is outside the standardized "
                "market data universe"
            ),
            value=family,
            context=context,
        )
    return family


def normalize_market_asset_kind(value: object | None) -> str:
    """Normalize tradable and generated market assets into one asset universe.

    Factor Lab's source gate is about *data provenance* rather than exchange
    tradability.  A self-built index or self-built portfolio generated from
    standardized market data should therefore enter factor computation as a
    price/level time series, just like a listed stock, ETF, or external index.
    """

    raw = _string_or_none(value)
    normalized = MARKET_ASSET_KIND_ALIASES.get((raw or "").lower())
    if normalized is not None:
        return normalized
    if raw in STANDARDIZED_MARKET_ASSET_KIND_SET:
        return raw
    raise SourceUniverseError(
        "market asset kind is outside the standardized market asset universe",
        value=value,
        context="market_asset_kind",
        details={
            "allowed_market_asset_kinds": list(STANDARDIZED_MARKET_ASSET_KINDS),
        },
    )


def market_asset_kind_from_mapping(payload: Mapping[str, object]) -> str:
    return normalize_market_asset_kind(
        payload.get("asset_kind")
        or payload.get("instrument_type")
        or payload.get("asset_type")
    )


def is_self_built_market_asset_kind(asset_kind: object | None) -> bool:
    return normalize_market_asset_kind(asset_kind) in SELF_BUILT_MARKET_ASSET_KINDS


def market_asset_universe_gate_evidence(
    payload: Mapping[str, object],
    *,
    source_family: object | None,
    context: str | None = None,
) -> dict[str, object]:
    """Return gate evidence for tradable, index, and self-built market series."""

    resolved_source_family = validate_source_family(source_family, context=context)
    asset_kind = market_asset_kind_from_mapping(payload)
    return {
        "gate_name": SOURCE_UNIVERSE_GATE_NAME,
        "source_family": resolved_source_family,
        "asset_kind": asset_kind,
        "is_self_built_asset": asset_kind in SELF_BUILT_MARKET_ASSET_KINDS,
        "status": SourceUniverseGateStatus.PASSED.value,
        "acceptance_policy": (
            "self_built_indexes_and_portfolios_are_price_volume_market_series"
        ),
    }


def optional_source_family(
    value: object | None,
    *,
    context: str | None = None,
) -> str | None:
    family = _string_or_none(value)
    if family is None:
        return None
    return validate_source_family(family, context=context)


def source_family_from_mapping(
    payload: Mapping[str, object] | None,
    *,
    context: str,
) -> str | None:
    if payload is None:
        return None
    return optional_source_family(payload.get("source_family"), context=context)


def assert_consistent_source_family(
    *candidates: tuple[str, object | None],
    context: str,
) -> str:
    """Validate candidates and hard-block when multiple sources disagree."""

    resolved: list[tuple[str, str]] = []
    for label, value in candidates:
        family = optional_source_family(value, context=label)
        if family is not None:
            resolved.append((label, family))

    if not resolved:
        raise SourceUniverseError(
            "source_family is missing and cannot be inferred from lineage",
            context=context,
        )

    families = {family for _, family in resolved}
    if len(families) != 1:
        raise SourceUniverseError(
            "Conflicting source_family values across lineage inputs",
            context=context,
            details={
                "conflicts": [
                    {"source": label, "source_family": family}
                    for label, family in resolved
                ]
            },
        )
    return resolved[0][1]


def source_universe_gate_status(
    source_family: object | None,
) -> SourceUniverseGateStatus:
    return (
        SourceUniverseGateStatus.PASSED
        if optional_source_family(source_family) is not None
        else SourceUniverseGateStatus.BLOCKED
    )


def _mapping(value: object | None) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _columns_indicate_price_volume(value: object) -> bool:
    if not isinstance(value, list):
        return False
    column_names: set[str] = set()
    for item in value:
        if isinstance(item, Mapping):
            name = item.get("name")
            if name is not None:
                column_names.add(str(name))
        elif item is not None:
            column_names.add(str(item))
    return {"open", "high", "low", "close", "volume"}.issubset(column_names)


def looks_like_price_volume_asset(payload: Mapping[str, object]) -> bool:
    """Best-effort legacy fallback for historical price-volume records."""

    schema_version = str(payload.get("schema_version", "")).lower()
    layer = str(payload.get("layer", "")).lower()
    dataset_name = str(
        payload.get("dataset_name")
        or payload.get("name")
        or payload.get("dataset_version")
        or ""
    ).lower()
    source_id = str(payload.get("source_id", "")).lower()
    connector_type = str(payload.get("connector_type", "")).lower()
    field_dictionary = _mapping(payload.get("field_dictionary"))
    field_names = (
        {str(key).lower() for key in field_dictionary.keys()}
        if field_dictionary
        else set()
    )
    price_fields = {"open", "high", "low", "close", "volume"}

    return any(
        (
            "price" in dataset_name,
            "daily" in dataset_name
            and ("market" in dataset_name or "bar" in dataset_name),
            "bar" in dataset_name,
            "datahub" in source_id,
            "price" in source_id,
            "bar" in source_id,
            connector_type == "datahub",
            schema_version.startswith("ds_pit") and layer in {"pit", "adjusted"},
            price_fields.issubset(field_names),
            _columns_indicate_price_volume(payload.get("columns", [])),
        )
    )


def legacy_price_volume_source_family(
    payload: Mapping[str, object] | None,
    *,
    context: str | None = None,
) -> str | None:
    _ = context
    if payload is None:
        return None
    if looks_like_price_volume_asset(payload):
        return PRICE_VOLUME_SOURCE_FAMILY
    return None


def source_family_for_source_record(payload: Mapping[str, object]) -> str | None:
    explicit = optional_source_family(
        payload.get("source_family"),
        context="data_source",
    )
    if explicit is not None:
        return explicit
    return legacy_price_volume_source_family(payload, context="legacy_data_source")


def _artifact_payload(artifact: Mapping[str, object]) -> dict[str, object]:
    storage_uri = artifact.get("storage_uri")
    if not isinstance(storage_uri, str):
        return {}
    try:
        raw = read_json_storage_uri(storage_uri, allow_http=False)
    except (FileNotFoundError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return cast(dict[str, object], raw)


def find_dataset_manifest(dataset_version: str) -> dict[str, object] | None:
    state = runtime_state_store.load()
    for artifact in state["artifacts"].values():
        if str(artifact.get("artifact_type", "")) != "dataset_manifest":
            continue
        run_id = str(artifact.get("run_id", ""))
        source_run = state["runs"].get(run_id)
        if (
            source_run is not None
            and str(source_run.get("status", "")) != RunStatus.COMPLETED
        ):
            continue
        payload = _artifact_payload(artifact)
        if str(payload.get("dataset_version", "")) == dataset_version:
            return payload
    return None


def source_family_for_dataset_version(dataset_version: str) -> str:
    manifest = find_dataset_manifest(dataset_version)
    if manifest is None:
        raise SourceUniverseError(
            (
                "Published dataset manifest not found for source_family "
                f"resolution: {dataset_version}"
            ),
            context="dataset_manifest",
            details={"dataset_version": dataset_version},
        )
    explicit = source_family_from_mapping(manifest, context="dataset_manifest")
    if explicit is not None:
        return explicit
    fallback = legacy_price_volume_source_family(
        manifest,
        context="legacy_dataset_manifest",
    )
    if fallback is not None:
        return fallback
    raise SourceUniverseError(
        (
            "Dataset manifest is missing source_family and is not eligible "
            "for legacy price_volume fallback"
        ),
        context="dataset_manifest",
        details={"dataset_version": dataset_version},
    )


def source_refs_for_dataset_version(dataset_version: str) -> list[str]:
    manifest = find_dataset_manifest(dataset_version)
    if manifest is None:
        return [f"dataset:{dataset_version}"]
    refs = [f"dataset:{dataset_version}"]
    source_id = _string_or_none(manifest.get("source_id"))
    run_id = _string_or_none(manifest.get("run_id"))
    if source_id:
        refs.append(f"source:{source_id}")
    if run_id:
        refs.append(f"run:{run_id}")
    return refs


def source_family_for_run(run_id: str) -> str:
    state = runtime_state_store.load()
    run = state["runs"].get(run_id)
    if run is None:
        raise SourceUniverseError(
            f"Run not found for source_family resolution: {run_id}",
            context="run",
            details={"run_id": run_id},
        )
    explicit = optional_source_family(run.get("source_family"), context="run")
    if explicit is not None:
        return explicit
    snapshot = find_run_record_snapshot(run_id)
    snapshot_family = source_family_from_mapping(
        snapshot,
        context="run_record_snapshot",
    )
    if snapshot_family is not None:
        return snapshot_family
    dataset_version = _string_or_none(
        run.get("dataset_version") or run.get("source_dataset_version")
    )
    if dataset_version is not None:
        return source_family_for_dataset_version(dataset_version)
    raise SourceUniverseError(
        "Run is missing source_family and dataset lineage",
        context="run",
        details={"run_id": run_id},
    )


def find_run_record_snapshot(run_id: str) -> dict[str, object]:
    for artifact in runtime_state_store.list_artifacts_for_run(run_id):
        if artifact.get("artifact_type") == "run_record_snapshot":
            return _artifact_payload(artifact)
    return {}


def source_refs_for_run(run_id: str) -> list[str]:
    state = runtime_state_store.load()
    run = state["runs"].get(run_id) or {}
    refs = [f"run:{run_id}"]
    dataset_version = _string_or_none(
        run.get("dataset_version") or run.get("source_dataset_version")
    )
    if dataset_version is not None:
        refs.extend(source_refs_for_dataset_version(dataset_version))
    return list(dict.fromkeys(refs))


def assert_all_same_source_family(
    families: Sequence[tuple[str, object | None]],
    *,
    context: str,
) -> str:
    return assert_consistent_source_family(*families, context=context)
