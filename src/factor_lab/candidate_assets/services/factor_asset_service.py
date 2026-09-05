# pyright: reportAny=false, reportExplicitAny=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnusedCallResult=false
"""Factor asset taxonomy, tags, lineage, and card services.

The candidate/effective/admitted lifecycle owns promotion state.  This module owns
asset-management metadata around that lifecycle: taxonomy dimensions, tag
assignments, lineage edges, searchable inventory rows, and durable factor cards.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Final, Literal, cast

from factor_lab.core.errors import NotFoundError, ValidationError
from factor_lab.core.hashing import sha256_hash
from factor_lab.core.runtime_records import get_record, upsert_record, utcnow
from factor_lab.core.runtime_state import runtime_state_store
from factor_lab.factor_engine.repositories.spec_registry import spec_registry
from factor_lab.governance.services.event_store import event_store

LineageDirection = Literal["ancestors", "descendants", "both"]

ASSET_TYPE_TO_COLLECTION: Final[dict[str, str]] = {
    "candidate_factor": "candidate_pool_factors",
    "effective_factor": "effective_factors",
    "admitted_factor": "admitted_factors",
}
ASSET_TYPE_TO_ID_FIELD: Final[dict[str, str]] = {
    "candidate_factor": "candidate_factor_id",
    "effective_factor": "effective_factor_id",
    "admitted_factor": "admitted_factor_id",
}
ASSET_TYPE_TO_STAGE: Final[dict[str, str]] = {
    "factor_spec": "factor_spec",
    "candidate_factor": "candidate",
    "effective_factor": "effective",
    "admitted_factor": "admitted",
}
TAG_SOURCE_PRIORITY: Final[dict[str, int]] = {
    "inferred": 10,
    "factor_spec": 20,
    "lifecycle": 30,
    "legacy_record": 40,
    "manual": 100,
}

TAXONOMY_DIMENSIONS: Final[tuple[dict[str, object], ...]] = (
    {
        "dimension": "style",
        "description": "Economic or empirical style bucket used for grouping factors.",
        "allowed_values": [
            "momentum",
            "value",
            "quality",
            "volatility",
            "liquidity",
            "size",
            "reversal",
            "carry",
            "seasonality",
            "microstructure",
            "event",
            "alternative",
            "other",
        ],
    },
    {
        "dimension": "source_family",
        "description": (
            "Primary data source family; macro_industry is retained for this "
            "repo's standardized market universe."
        ),
        "allowed_values": [
            "price_volume",
            "fundamental",
            "macro_industry",
            "microstructure",
            "cross_asset_derivatives",
            "event_alpha",
        ],
    },
    {
        "dimension": "construction_method",
        "description": "How the factor specification was constructed.",
        "allowed_values": [
            "standard_library",
            "formulaic_dsl",
            "template",
            "symbolic",
            "ml",
            "deep",
            "latent_cluster",
            "manual",
        ],
    },
    {
        "dimension": "horizon",
        "description": "Dominant holding or observation horizon.",
        "allowed_values": ["intraday", "short", "medium", "long"],
    },
    {
        "dimension": "economic_rationale",
        "description": "Why the factor might earn returns or improve risk control.",
        "allowed_values": [
            "risk_premium",
            "behavioral",
            "structural",
            "technical",
            "unknown",
        ],
    },
    {
        "dimension": "lifecycle_stage",
        "description": "Current asset lifecycle object represented by the asset_ref.",
        "allowed_values": ["factor_spec", "candidate", "effective", "admitted"],
    },
)
TAXONOMY_VERSION: Final[str] = "factor_asset_taxonomy@1.0"


@dataclass(slots=True)
class FactorTagAssignmentRecord:
    assignment_id: str
    asset_ref: str
    tag_key: str
    tag_value: str
    source: str
    assigned_by: str
    assigned_at: str
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class FactorLineageEdgeRecord:
    edge_id: str
    source_ref: str
    target_ref: str
    relation_type: str
    created_by: str
    created_at: str
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in cast(list[object], value)]


def _string_tags(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(item)
        for key, item in cast(dict[object, object], value).items()
        if str(key).strip() and str(item).strip()
    }


def _parse_asset_ref(asset_ref: str) -> tuple[str, str]:
    raw = asset_ref.strip()
    if ":" not in raw:
        raise ValidationError("asset_ref must use '<asset_type>:<id>' format")
    asset_type, asset_id = raw.split(":", 1)
    asset_type = asset_type.strip()
    asset_id = asset_id.strip()
    if not asset_type or not asset_id:
        raise ValidationError("asset_ref must include both asset type and id")
    if asset_type not in ASSET_TYPE_TO_STAGE:
        raise ValidationError(f"Unsupported factor asset type: {asset_type}")
    return asset_type, asset_id


def _asset_ref(asset_type: str, asset_id: object) -> str:
    return f"{asset_type}:{asset_id}"


def _assignment_id(asset_ref: str, tag_key: str, source: str) -> str:
    digest = sha256_hash({"asset_ref": asset_ref, "tag_key": tag_key, "source": source})
    return f"fta_{digest[:20]}"


def _edge_id(source_ref: str, target_ref: str, relation_type: str) -> str:
    digest = sha256_hash(
        {
            "source_ref": source_ref,
            "target_ref": target_ref,
            "relation_type": relation_type,
        }
    )
    return f"fle_{digest[:20]}"


def _safe_int(value: object) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def _lower_corpus(*values: object) -> str:
    fragments: list[str] = []
    for value in values:
        if isinstance(value, Mapping):
            fragments.extend(f"{key} {item}" for key, item in value.items())
        elif isinstance(value, Iterable) and not isinstance(value, str):
            fragments.extend(str(item) for item in value)
        elif value is not None:
            fragments.append(str(value))
    return " ".join(fragments).lower()


def _style_from_metadata(
    spec: Mapping[str, object], record: Mapping[str, object]
) -> str:
    tags = {**_string_tags(spec.get("tags")), **_string_tags(record.get("tags"))}
    tagged_style = tags.get("style", "").strip()
    if tagged_style:
        return tagged_style
    corpus = _lower_corpus(
        spec.get("spec_version"),
        spec.get("name"),
        spec.get("description"),
        spec.get("callable_ref"),
        spec.get("dsl_expression"),
        spec.get("parameters"),
        spec.get("field_refs"),
        spec.get("operator_list"),
        record.get("candidate_name"),
        record.get("effective_name"),
        record.get("admitted_name"),
        record.get("dsl_expression_snapshot"),
        record.get("field_refs"),
        record.get("operator_list"),
    )
    if any(
        token in corpus
        for token in ("microstructure", "spread", "depth", "order_flow", "order-flow")
    ):
        return "microstructure"
    if any(token in corpus for token in ("reversal", "contrarian")):
        return "reversal"
    if any(
        token in corpus
        for token in ("quality", "roe", "margin", "cash_flow", "cash-flow", "leverage")
    ):
        return "quality"
    if any(
        token in corpus
        for token in ("liquidity", "turnover", "volume", "dollar-volume")
    ):
        return "liquidity"
    if any(
        token in corpus
        for token in ("volatility", " vol", "_vol", "std", "range", "variance")
    ):
        return "volatility"
    if any(
        token in corpus
        for token in ("carry", "basis", "term_structure", "term structure")
    ):
        return "carry"
    if any(token in corpus for token in ("value", "book", "earnings", "yield")):
        return "value"
    if any(token in corpus for token in ("size", "market_cap", "market cap")):
        return "size"
    if any(token in corpus for token in ("season", "calendar", "month")):
        return "seasonality"
    if any(token in corpus for token in ("event", "announcement")):
        return "event"
    if any(token in corpus for token in ("alternative", "alt_")):
        return "alternative"
    if any(
        token in corpus
        for token in (
            "momentum",
            "mom",
            "return",
            "relative_strength",
            "relative strength",
            "rank(close",
        )
    ):
        return "momentum"
    return "other"


def _construction_method(
    spec: Mapping[str, object], record: Mapping[str, object]
) -> str:
    explicit = _string_tags(spec.get("tags")).get("construction_method", "").strip()
    if explicit:
        return explicit
    factor_type = str(spec.get("factor_type") or record.get("factor_type") or "")
    search_kind = str(
        record.get("search_kind") or record.get("first_seen_run_id") or ""
    )
    if factor_type in {"standard_price_volume", "advanced_standardized_market"}:
        return "standard_library"
    if factor_type == "formulaic_dsl":
        return "formulaic_dsl"
    if "symbolic" in search_kind.lower():
        return "symbolic"
    if "template" in factor_type.lower():
        return "template"
    if "deep" in factor_type.lower():
        return "deep"
    if "ml" in factor_type.lower() or "model" in factor_type.lower():
        return "ml"
    if str(record.get("first_seen_run_id", "")).startswith("manual:"):
        return "manual"
    return "manual" if str(record.get("created_by", "")) else "standard_library"


def _horizon(spec: Mapping[str, object], record: Mapping[str, object]) -> str:
    explicit = (
        _string_tags(spec.get("tags")).get("horizon")
        or _string_tags(record.get("tags")).get("horizon")
        or ""
    ).strip()
    if explicit:
        return explicit
    corpus = _lower_corpus(
        spec.get("name"),
        spec.get("description"),
        spec.get("parameters"),
        spec.get("input_schema"),
        record.get("candidate_name"),
        record.get("field_refs"),
    )
    source_family = str(record.get("source_family") or spec.get("source_family") or "")
    if source_family == "microstructure" or "intraday" in corpus:
        return "intraday"
    windows = []
    raw_windows = record.get("window_refs") or spec.get("window_refs")
    if isinstance(raw_windows, list):
        windows = [_safe_int(item) for item in raw_windows]
    parameters = _object_dict(spec.get("parameters"))
    if not windows and parameters.get("window") is not None:
        windows = [_safe_int(parameters.get("window"))]
    max_window = max(windows or [0])
    if 0 < max_window <= 5:
        return "short"
    if 5 < max_window <= 63:
        return "medium"
    if max_window > 63:
        return "long"
    if any(token in corpus for token in ("1d", "5d", "short")):
        return "short"
    if any(token in corpus for token in ("quarter", "annual", "long")):
        return "long"
    return "medium"


def _economic_rationale(style: str, source_family: str, method: str) -> str:
    if style in {"momentum", "reversal", "seasonality"}:
        return "behavioral"
    if style in {"value", "quality", "size", "carry", "volatility"}:
        return "risk_premium"
    if style in {"liquidity", "microstructure", "event", "alternative"}:
        return "structural"
    if source_family in {"fundamental", "microstructure", "cross_asset_derivatives"}:
        return "structural"
    if method in {"formulaic_dsl", "symbolic", "template"}:
        return "technical"
    return "unknown"


class FactorAssetTaxonomyService:
    """Taxonomy and tag assignment operations."""

    def taxonomy(self) -> dict[str, object]:
        definitions: dict[str, dict[str, object]] = {}
        for dimension in TAXONOMY_DIMENSIONS:
            dimension_name = str(dimension["dimension"])
            definitions[dimension_name] = dict(dimension)
            upsert_record("factor_tag_definitions", dimension_name, dimension)
        return {
            "taxonomy_version": TAXONOMY_VERSION,
            "dimensions": list(TAXONOMY_DIMENSIONS),
            "dimension_map": definitions,
        }

    def resolve_asset(self, asset_ref: str) -> dict[str, object]:
        asset_type, asset_id = _parse_asset_ref(asset_ref)
        if asset_type == "factor_spec":
            spec = spec_registry.get_factor_spec_sync(asset_id)
            if spec is None:
                raise NotFoundError(f"Factor spec not found: {asset_id}")
            return spec.to_dict()
        collection = ASSET_TYPE_TO_COLLECTION[asset_type]
        record = get_record(collection, asset_id)
        if record is None:
            raise NotFoundError(f"Factor asset not found: {asset_ref}")
        return dict(record)

    def _spec_for_record(self, record: Mapping[str, object]) -> dict[str, object]:
        spec_version = str(record.get("factor_spec_version", "")).strip()
        if not spec_version:
            return {}
        spec = spec_registry.get_factor_spec_sync(spec_version)
        return spec.to_dict() if spec is not None else {"spec_version": spec_version}

    def infer_tags(
        self,
        asset_ref: str,
        *,
        record: Mapping[str, object] | None = None,
    ) -> dict[str, str]:
        asset_type, asset_id = _parse_asset_ref(asset_ref)
        asset_record = (
            dict(record) if record is not None else self.resolve_asset(asset_ref)
        )
        if asset_type == "factor_spec":
            spec = asset_record
        elif asset_type == "candidate_factor":
            spec = self._spec_for_record(asset_record)
        elif asset_type == "effective_factor":
            parent_ref = _asset_ref(
                "candidate_factor", asset_record.get("candidate_factor_id", "")
            )
            inherited = self.effective_tags(parent_ref, strict=False)
            spec = self._spec_for_record(asset_record)
            asset_record = {
                **asset_record,
                "tags": {
                    **inherited,
                    **_string_tags(asset_record.get("tags")),
                },
                "source_family": asset_record.get("source_family")
                or inherited.get("source_family", ""),
            }
        else:
            parent_ref = _asset_ref(
                "effective_factor", asset_record.get("effective_factor_id", "")
            )
            inherited = self.effective_tags(parent_ref, strict=False)
            spec = self._spec_for_record(asset_record)
            asset_record = {
                **asset_record,
                "tags": {
                    **inherited,
                    **_string_tags(asset_record.get("tags")),
                },
                "source_family": asset_record.get("source_family")
                or inherited.get("source_family", ""),
            }

        raw_tags: dict[str, str] = {}
        if asset_type != "factor_spec":
            raw_tags.update(_string_tags(spec.get("tags")))
        raw_tags.update(_string_tags(asset_record.get("tags")))
        if asset_type == "factor_spec":
            raw_tags.update(_string_tags(spec.get("tags")))

        source_family = str(
            asset_record.get("source_family")
            or spec.get("source_family")
            or raw_tags.get("source_family")
            or "price_volume"
        )
        method = _construction_method(spec, asset_record)
        style = _style_from_metadata(spec, asset_record)
        horizon = _horizon(spec, asset_record)
        inferred = {
            **raw_tags,
            "style": raw_tags.get("style", style),
            "source_family": raw_tags.get("source_family", source_family),
            "construction_method": raw_tags.get("construction_method", method),
            "horizon": raw_tags.get("horizon", horizon),
            "economic_rationale": raw_tags.get(
                "economic_rationale",
                _economic_rationale(style, source_family, method),
            ),
            "lifecycle_stage": ASSET_TYPE_TO_STAGE[asset_type],
        }
        _ = asset_id
        return {key: value for key, value in inferred.items() if key and value}

    def _assignments_for_asset(self, asset_ref: str) -> list[dict[str, object]]:
        assignments: list[dict[str, object]] = []
        for record in runtime_state_store.load()["factor_tag_assignments"].values():
            if str(record.get("asset_ref")) == asset_ref:
                assignments.append(dict(record))
        return assignments

    def _upsert_tag_assignments(
        self,
        *,
        asset_ref: str,
        tags: Mapping[str, str],
        source: str,
        assigned_by: str,
        reason: str = "",
    ) -> list[dict[str, object]]:
        if not tags:
            return []
        _ = _parse_asset_ref(asset_ref)
        now = utcnow()
        assignments: list[dict[str, object]] = []
        for key, value in tags.items():
            tag_key = str(key).strip()
            tag_value = str(value).strip()
            if not tag_key or not tag_value:
                continue
            record = FactorTagAssignmentRecord(
                assignment_id=_assignment_id(asset_ref, tag_key, source),
                asset_ref=asset_ref,
                tag_key=tag_key,
                tag_value=tag_value,
                source=source,
                assigned_by=assigned_by,
                assigned_at=now,
                reason=reason,
            )
            upsert_record(
                "factor_tag_assignments",
                record.assignment_id,
                record.to_dict(),
            )
            assignments.append(record.to_dict())
        return assignments

    def ensure_inferred_tags(
        self,
        asset_ref: str,
        *,
        record: Mapping[str, object] | None = None,
        assigned_by: str = "system",
    ) -> dict[str, str]:
        asset_record = (
            dict(record) if record is not None else self.resolve_asset(asset_ref)
        )
        asset_type, _ = _parse_asset_ref(asset_ref)
        spec_tags: dict[str, str] = {}
        if asset_type == "factor_spec":
            spec_tags = _string_tags(asset_record.get("tags"))
        else:
            spec_tags = _string_tags(self._spec_for_record(asset_record).get("tags"))
        inferred = self.infer_tags(asset_ref, record=asset_record)
        _ = self._upsert_tag_assignments(
            asset_ref=asset_ref,
            tags=inferred,
            source="inferred",
            assigned_by=assigned_by,
            reason="automatic factor asset taxonomy inference",
        )
        if spec_tags:
            _ = self._upsert_tag_assignments(
                asset_ref=asset_ref,
                tags=spec_tags,
                source="factor_spec",
                assigned_by=assigned_by,
                reason="FactorSpec.tags compatibility import",
            )
        return self.effective_tags(asset_ref, record=asset_record, strict=False)

    def effective_tags(
        self,
        asset_ref: str,
        *,
        record: Mapping[str, object] | None = None,
        strict: bool = True,
    ) -> dict[str, str]:
        try:
            asset_record = (
                dict(record) if record is not None else self.resolve_asset(asset_ref)
            )
            fallback_tags = self.infer_tags(asset_ref, record=asset_record)
        except (NotFoundError, ValidationError):
            if strict:
                raise
            fallback_tags = {}
        assignments = self._assignments_for_asset(asset_ref)
        if not assignments:
            return fallback_tags
        chosen: dict[str, tuple[int, str, str]] = {
            key: (0, "", value) for key, value in fallback_tags.items()
        }
        for assignment in assignments:
            key = str(assignment.get("tag_key", ""))
            value = str(assignment.get("tag_value", ""))
            source = str(assignment.get("source", ""))
            assigned_at = str(assignment.get("assigned_at", ""))
            if not key or not value:
                continue
            priority = TAG_SOURCE_PRIORITY.get(source, 50)
            previous = chosen.get(key)
            if previous is None or (priority, assigned_at) >= (
                previous[0],
                previous[1],
            ):
                chosen[key] = (priority, assigned_at, value)
        return {key: item[2] for key, item in chosen.items()}

    def assignment_summary(self, asset_ref: str) -> dict[str, object]:
        return {
            "asset_ref": asset_ref,
            "tags": self.effective_tags(asset_ref),
            "assignments": sorted(
                self._assignments_for_asset(asset_ref),
                key=lambda item: (
                    str(item.get("tag_key", "")),
                    str(item.get("source", "")),
                ),
            ),
        }

    def _update_asset_tag_snapshot(
        self, asset_ref: str, tags: Mapping[str, str]
    ) -> None:
        asset_type, asset_id = _parse_asset_ref(asset_ref)
        if asset_type == "factor_spec":
            return
        collection = ASSET_TYPE_TO_COLLECTION[asset_type]
        record = get_record(collection, asset_id)
        if record is None:
            return
        updated = dict(record)
        updated["tags"] = dict(tags)
        upsert_record(collection, asset_id, updated)

    def assign_tags(
        self,
        *,
        asset_ref: str,
        tags: Mapping[str, str],
        assigned_by: str,
        source: str = "manual",
        reason: str = "",
    ) -> dict[str, object]:
        _ = self.resolve_asset(asset_ref)
        cleaned = {
            str(key): str(value)
            for key, value in tags.items()
            if str(key).strip() and str(value).strip()
        }
        if not cleaned:
            raise ValidationError("At least one non-empty tag is required")
        assignments = self._upsert_tag_assignments(
            asset_ref=asset_ref,
            tags=cleaned,
            source=source,
            assigned_by=assigned_by,
            reason=reason,
        )
        effective = self.effective_tags(asset_ref)
        self._update_asset_tag_snapshot(asset_ref, effective)
        _ = event_store.append(
            event_type="factor_asset.tags_assigned",
            payload={
                "asset_ref": asset_ref,
                "tag_keys": sorted(cleaned.keys()),
                "source": source,
                "assignment_ids": [str(item["assignment_id"]) for item in assignments],
            },
        )
        return {
            "asset_ref": asset_ref,
            "tags": effective,
            "assignments": assignments,
        }

    def synchronize_asset(
        self,
        *,
        asset_ref: str,
        record: Mapping[str, object],
        manual_tags: Mapping[str, str] | None = None,
        assigned_by: str = "system",
    ) -> dict[str, str]:
        tags = self.ensure_inferred_tags(
            asset_ref, record=record, assigned_by=assigned_by
        )
        if manual_tags:
            _ = self.assign_tags(
                asset_ref=asset_ref,
                tags={str(key): str(value) for key, value in manual_tags.items()},
                assigned_by=assigned_by,
                source="manual",
                reason="manual factor asset tag assignment",
            )
            tags = self.effective_tags(asset_ref, strict=False)
        self._update_asset_tag_snapshot(asset_ref, tags)
        return tags


class FactorAssetLineageService:
    """Directed lineage edge operations for factor assets."""

    def __init__(self, taxonomy_service: FactorAssetTaxonomyService) -> None:
        self._taxonomy_service: FactorAssetTaxonomyService = taxonomy_service

    def _validate_ref(self, asset_ref: str, *, require_existing: bool) -> None:
        _ = _parse_asset_ref(asset_ref)
        if require_existing:
            _ = self._taxonomy_service.resolve_asset(asset_ref)

    def add_edge(
        self,
        *,
        source_ref: str,
        target_ref: str,
        relation_type: str,
        created_by: str,
        metadata: Mapping[str, object] | None = None,
        validate_assets: bool = True,
    ) -> dict[str, object]:
        source_ref = source_ref.strip()
        target_ref = target_ref.strip()
        relation_type = relation_type.strip() or "derived_from"
        if source_ref == target_ref:
            raise ValidationError("Lineage source_ref and target_ref must differ")
        self._validate_ref(source_ref, require_existing=validate_assets)
        self._validate_ref(target_ref, require_existing=validate_assets)
        record = FactorLineageEdgeRecord(
            edge_id=_edge_id(source_ref, target_ref, relation_type),
            source_ref=source_ref,
            target_ref=target_ref,
            relation_type=relation_type,
            created_by=created_by,
            created_at=utcnow(),
            metadata=dict(metadata or {}),
        )
        upsert_record("factor_lineage_edges", record.edge_id, record.to_dict())
        _ = event_store.append(
            event_type="factor_asset.lineage_edge_upserted",
            payload={
                "edge_id": record.edge_id,
                "source_ref": source_ref,
                "target_ref": target_ref,
                "relation_type": relation_type,
            },
        )
        return record.to_dict()

    @staticmethod
    def _edges() -> list[dict[str, object]]:
        return [
            dict(record)
            for record in runtime_state_store.load()["factor_lineage_edges"].values()
        ]

    def _reachable(
        self,
        *,
        asset_ref: str,
        incoming: bool,
    ) -> tuple[list[str], list[dict[str, object]]]:
        visited: set[str] = {asset_ref}
        refs: list[str] = []
        edges: list[dict[str, object]] = []
        frontier: deque[str] = deque([asset_ref])
        all_edges = self._edges()
        while frontier:
            current = frontier.popleft()
            for edge in all_edges:
                source = str(edge.get("source_ref", ""))
                target = str(edge.get("target_ref", ""))
                if incoming:
                    matches = target == current
                    next_ref = source
                else:
                    matches = source == current
                    next_ref = target
                if not matches or not next_ref or next_ref in visited:
                    continue
                visited.add(next_ref)
                refs.append(next_ref)
                edges.append(edge)
                frontier.append(next_ref)
        return refs, edges

    def lineage(
        self, *, asset_ref: str, direction: LineageDirection = "both"
    ) -> dict[str, object]:
        _ = self._taxonomy_service.resolve_asset(asset_ref)
        ancestor_refs: list[str] = []
        descendant_refs: list[str] = []
        selected_edges: list[dict[str, object]] = []
        if direction in {"ancestors", "both"}:
            ancestor_refs, ancestor_edges = self._reachable(
                asset_ref=asset_ref, incoming=True
            )
            selected_edges.extend(ancestor_edges)
        if direction in {"descendants", "both"}:
            descendant_refs, descendant_edges = self._reachable(
                asset_ref=asset_ref, incoming=False
            )
            selected_edges.extend(descendant_edges)
        deduped_edges = list(
            {str(edge.get("edge_id")): edge for edge in selected_edges}.values()
        )
        return {
            "asset_ref": asset_ref,
            "direction": direction,
            "ancestors": [self._asset_node(ref) for ref in ancestor_refs],
            "descendants": [self._asset_node(ref) for ref in descendant_refs],
            "edges": sorted(
                deduped_edges, key=lambda item: str(item.get("created_at", ""))
            ),
        }

    def _asset_node(self, asset_ref: str) -> dict[str, object]:
        try:
            return factor_card_service.asset_summary(asset_ref)
        except (NotFoundError, ValidationError):
            asset_type, asset_id = _parse_asset_ref(asset_ref)
            return {
                "asset_ref": asset_ref,
                "asset_type": asset_type,
                "asset_id": asset_id,
                "name": asset_id,
                "tags": {},
            }


class FactorCardService:
    """Searchable factor asset inventory and card generation."""

    def __init__(
        self,
        taxonomy_service: FactorAssetTaxonomyService,
        lineage_service: FactorAssetLineageService,
    ) -> None:
        self._taxonomy_service: FactorAssetTaxonomyService = taxonomy_service
        self._lineage_service: FactorAssetLineageService = lineage_service

    def _record_name(self, asset_type: str, record: Mapping[str, object]) -> str:
        if asset_type == "factor_spec":
            return str(record.get("name") or record.get("spec_version") or "")
        if asset_type == "candidate_factor":
            return str(
                record.get("candidate_name") or record.get("factor_spec_version") or ""
            )
        if asset_type == "effective_factor":
            return str(
                record.get("effective_name") or record.get("effective_factor_id") or ""
            )
        return str(
            record.get("admitted_name") or record.get("admitted_factor_id") or ""
        )

    def _status(self, asset_type: str, record: Mapping[str, object]) -> str:
        if asset_type == "candidate_factor":
            return str(record.get("pool_status", ""))
        if asset_type == "effective_factor":
            return str(record.get("activation_status", ""))
        if asset_type == "admitted_factor":
            return str(record.get("admission_status", ""))
        return "registered"

    def asset_summary(
        self,
        asset_ref: str,
        *,
        record: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        asset_type, asset_id = _parse_asset_ref(asset_ref)
        asset_record = (
            dict(record)
            if record is not None
            else self._taxonomy_service.resolve_asset(asset_ref)
        )
        tags = self._taxonomy_service.effective_tags(
            asset_ref, record=asset_record, strict=False
        )
        return {
            "asset_ref": asset_ref,
            "asset_type": asset_type,
            "asset_id": asset_id,
            "lifecycle_stage": ASSET_TYPE_TO_STAGE[asset_type],
            "name": self._record_name(asset_type, asset_record),
            "factor_spec_version": str(
                asset_record.get("factor_spec_version")
                or asset_record.get("spec_version")
                or ""
            ),
            "source_family": str(
                asset_record.get("source_family") or tags.get("source_family", "")
            ),
            "status": self._status(asset_type, asset_record),
            "tags": tags,
            "updated_at": str(
                asset_record.get("latest_seen_at")
                or asset_record.get("activated_at")
                or asset_record.get("admitted_at")
                or asset_record.get("created_at")
                or ""
            ),
        }

    def _asset_summaries(self) -> list[dict[str, object]]:
        summaries: list[dict[str, object]] = []
        for spec in spec_registry.list_factor_specs_sync():
            asset_ref = _asset_ref("factor_spec", spec.spec_version)
            summaries.append(self.asset_summary(asset_ref, record=spec.to_dict()))
        state = runtime_state_store.load()
        for asset_type, collection in ASSET_TYPE_TO_COLLECTION.items():
            id_field = ASSET_TYPE_TO_ID_FIELD[asset_type]
            for record in state[collection].values():
                asset_id = str(record.get(id_field, ""))
                if asset_id:
                    summaries.append(
                        self.asset_summary(
                            _asset_ref(asset_type, asset_id),
                            record=record,
                        )
                    )
        return summaries

    @staticmethod
    def _parse_tag_filters(raw_tags: Iterable[str]) -> dict[str, str]:
        filters: dict[str, str] = {}
        for raw in raw_tags:
            for item in str(raw).split(","):
                if not item.strip():
                    continue
                if "=" not in item:
                    raise ValidationError(f"Tag filter must use key=value: {item}")
                key, value = item.split("=", 1)
                filters[key.strip()] = value.strip()
        return filters

    def search_assets(
        self,
        *,
        tag_filters: Iterable[str] = (),
        source_family: str | None = None,
        lifecycle_stage: str | None = None,
        text: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, object]:
        parsed_tags = self._parse_tag_filters(tag_filters)
        normalized_text = (text or "").strip().lower()
        matched: list[dict[str, object]] = []
        for summary in self._asset_summaries():
            tags = _string_tags(summary.get("tags"))
            if source_family and str(summary.get("source_family")) != source_family:
                continue
            if (
                lifecycle_stage
                and str(summary.get("lifecycle_stage")) != lifecycle_stage
            ):
                continue
            if any(tags.get(key) != value for key, value in parsed_tags.items()):
                continue
            if normalized_text:
                corpus = _lower_corpus(
                    summary.get("asset_ref"),
                    summary.get("name"),
                    summary.get("factor_spec_version"),
                    summary.get("tags"),
                )
                if normalized_text not in corpus:
                    continue
            matched.append(summary)
        ordered = sorted(matched, key=lambda item: str(item.get("asset_ref", "")))
        return {
            "assets": ordered[offset : offset + limit],
            "total": len(ordered),
            "filters": {
                "tags": parsed_tags,
                "source_family": source_family,
                "lifecycle_stage": lifecycle_stage,
                "text": text,
                "limit": str(limit),
                "offset": str(offset),
            },
        }

    def _validation_summary(
        self, asset_ref: str, record: Mapping[str, object]
    ) -> dict[str, object]:
        asset_type, _ = _parse_asset_ref(asset_ref)
        state = runtime_state_store.load()
        claims: list[dict[str, object]] = []
        if asset_type == "candidate_factor":
            candidate_id = str(record.get("candidate_factor_id", ""))
            claims = [
                dict(item)
                for item in state["validation_claims"].values()
                if str(item.get("candidate_factor_id")) == candidate_id
            ]
        elif asset_type in {"effective_factor", "admitted_factor"}:
            claim_id = str(record.get("validation_claim_id", ""))
            claim = state["validation_claims"].get(claim_id)
            claims = [dict(claim)] if claim is not None else []
        elif asset_type == "factor_spec":
            spec_version = str(record.get("spec_version", ""))
            claims = [
                dict(item)
                for item in state["validation_claims"].values()
                if str(item.get("factor_spec_version")) == spec_version
            ]
        claims = sorted(
            claims, key=lambda item: str(item.get("created_at", "")), reverse=True
        )
        latest = claims[0] if claims else {}
        approved = [
            item for item in claims if str(item.get("claim_status")) == "approved"
        ]
        return {
            "claim_count": len(claims),
            "approved_claim_count": len(approved),
            "latest_validation_claim_id": str(latest.get("validation_claim_id", "")),
            "latest_dataset_version": str(latest.get("dataset_version", "")),
            "latest_verdict": str(latest.get("verdict", "")),
            "latest_claim_status": str(latest.get("claim_status", "")),
            "score_summary": _object_dict(latest.get("score_summary", {})),
        }

    def _governance_status(
        self, asset_ref: str, record: Mapping[str, object]
    ) -> dict[str, object]:
        asset_type, _ = _parse_asset_ref(asset_ref)
        return {
            "lifecycle_stage": ASSET_TYPE_TO_STAGE[asset_type],
            "status": self._status(asset_type, record),
            "approval_request_id": str(record.get("approval_request_id", "")),
            "approved_by": str(
                record.get("approved_by")
                or record.get("activated_by")
                or record.get("admitted_by")
                or ""
            ),
            "retired_at": str(record.get("retired_at", "")),
            "replacement_ref": str(
                record.get("replacement_effective_factor_id")
                or record.get("replacement_admitted_factor_id")
                or ""
            ),
        }

    def _evidence_refs(self, asset_ref: str, record: Mapping[str, object]) -> list[str]:
        refs = _string_list(record.get("evidence_artifact_ids", []))
        asset_type, _ = _parse_asset_ref(asset_ref)
        if asset_type == "candidate_factor":
            candidate_id = str(record.get("candidate_factor_id", ""))
            for claim in runtime_state_store.load()["validation_claims"].values():
                if str(claim.get("candidate_factor_id")) == candidate_id:
                    refs.extend(_string_list(claim.get("evidence_artifact_ids", [])))
        return list(dict.fromkeys(refs))

    def card(
        self, *, asset_ref: str, generated_by: str = "system"
    ) -> dict[str, object]:
        record = self._taxonomy_service.resolve_asset(asset_ref)
        tags = self._taxonomy_service.ensure_inferred_tags(asset_ref, record=record)
        assignment_summary = self._taxonomy_service.assignment_summary(asset_ref)
        lineage = self._lineage_service.lineage(asset_ref=asset_ref, direction="both")
        card = {
            "card_version": "factor_card@1.0",
            "asset_ref": asset_ref,
            "generated_at": utcnow(),
            "generated_by": generated_by,
            "identity": self.asset_summary(asset_ref, record=record),
            "tags": tags,
            "tag_assignments": assignment_summary["assignments"],
            "lineage": lineage,
            "validation_summary": self._validation_summary(asset_ref, record),
            "governance_status": self._governance_status(asset_ref, record),
            "evidence_refs": self._evidence_refs(asset_ref, record),
        }
        upsert_record("factor_cards", asset_ref, card)
        return card


class FactorAssetService:
    """Facade used by lifecycle services, API, CLI, and UI."""

    def __init__(self) -> None:
        self.taxonomy_service: FactorAssetTaxonomyService = FactorAssetTaxonomyService()
        self.lineage_service: FactorAssetLineageService = FactorAssetLineageService(
            self.taxonomy_service
        )
        self.card_service: FactorCardService = FactorCardService(
            self.taxonomy_service,
            self.lineage_service,
        )

    def taxonomy(self) -> dict[str, object]:
        return self.taxonomy_service.taxonomy()

    def assign_tags(
        self,
        *,
        asset_ref: str,
        tags: Mapping[str, str],
        assigned_by: str,
        source: str = "manual",
        reason: str = "",
    ) -> dict[str, object]:
        return self.taxonomy_service.assign_tags(
            asset_ref=asset_ref,
            tags=tags,
            assigned_by=assigned_by,
            source=source,
            reason=reason,
        )

    def add_lineage_edge(
        self,
        *,
        source_ref: str,
        target_ref: str,
        relation_type: str,
        created_by: str,
        metadata: Mapping[str, object] | None = None,
        validate_assets: bool = True,
    ) -> dict[str, object]:
        return self.lineage_service.add_edge(
            source_ref=source_ref,
            target_ref=target_ref,
            relation_type=relation_type,
            created_by=created_by,
            metadata=metadata,
            validate_assets=validate_assets,
        )

    def lineage(
        self, *, asset_ref: str, direction: LineageDirection = "both"
    ) -> dict[str, object]:
        return self.lineage_service.lineage(asset_ref=asset_ref, direction=direction)

    def card(
        self, *, asset_ref: str, generated_by: str = "system"
    ) -> dict[str, object]:
        return self.card_service.card(asset_ref=asset_ref, generated_by=generated_by)

    def search_assets(
        self,
        *,
        tag_filters: Iterable[str] = (),
        source_family: str | None = None,
        lifecycle_stage: str | None = None,
        text: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, object]:
        return self.card_service.search_assets(
            tag_filters=tag_filters,
            source_family=source_family,
            lifecycle_stage=lifecycle_stage,
            text=text,
            limit=limit,
            offset=offset,
        )

    def synchronize_candidate(
        self,
        *,
        candidate: Mapping[str, object],
        manual_tags: Mapping[str, str] | None = None,
        parent_factor_refs: Iterable[str] = (),
        assigned_by: str = "system",
    ) -> dict[str, object]:
        candidate_id = str(candidate.get("candidate_factor_id", ""))
        if not candidate_id:
            return dict(candidate)
        asset_ref = _asset_ref("candidate_factor", candidate_id)
        tags = self.taxonomy_service.synchronize_asset(
            asset_ref=asset_ref,
            record=candidate,
            manual_tags=manual_tags,
            assigned_by=assigned_by,
        )
        spec_version = str(candidate.get("factor_spec_version", "")).strip()
        if spec_version:
            _ = self.add_lineage_edge(
                source_ref=_asset_ref("factor_spec", spec_version),
                target_ref=asset_ref,
                relation_type="specifies",
                created_by=assigned_by,
                metadata={"lifecycle_edge": True},
                validate_assets=False,
            )
        for parent_ref in parent_factor_refs:
            normalized_parent = str(parent_ref).strip()
            if not normalized_parent:
                continue
            _ = self.add_lineage_edge(
                source_ref=normalized_parent,
                target_ref=asset_ref,
                relation_type="derived_from",
                created_by=assigned_by,
                metadata={"manual_parent": True},
                validate_assets=True,
            )
        updated = dict(candidate)
        updated["tags"] = tags
        upsert_record("candidate_pool_factors", candidate_id, updated)
        return updated

    def synchronize_effective(
        self,
        *,
        effective: Mapping[str, object],
        assigned_by: str = "system",
    ) -> dict[str, object]:
        effective_id = str(effective.get("effective_factor_id", ""))
        if not effective_id:
            return dict(effective)
        asset_ref = _asset_ref("effective_factor", effective_id)
        tags = self.taxonomy_service.synchronize_asset(
            asset_ref=asset_ref,
            record=effective,
            assigned_by=assigned_by,
        )
        candidate_id = str(effective.get("candidate_factor_id", "")).strip()
        if candidate_id:
            _ = self.add_lineage_edge(
                source_ref=_asset_ref("candidate_factor", candidate_id),
                target_ref=asset_ref,
                relation_type="validated_as",
                created_by=assigned_by,
                metadata={"lifecycle_edge": True},
                validate_assets=False,
            )
        updated = dict(effective)
        updated["tags"] = tags
        upsert_record("effective_factors", effective_id, updated)
        return updated

    def synchronize_admitted(
        self,
        *,
        admitted: Mapping[str, object],
        assigned_by: str = "system",
    ) -> dict[str, object]:
        admitted_id = str(admitted.get("admitted_factor_id", ""))
        if not admitted_id:
            return dict(admitted)
        asset_ref = _asset_ref("admitted_factor", admitted_id)
        tags = self.taxonomy_service.synchronize_asset(
            asset_ref=asset_ref,
            record=admitted,
            assigned_by=assigned_by,
        )
        effective_id = str(admitted.get("effective_factor_id", "")).strip()
        if effective_id:
            _ = self.add_lineage_edge(
                source_ref=_asset_ref("effective_factor", effective_id),
                target_ref=asset_ref,
                relation_type="admitted_as",
                created_by=assigned_by,
                metadata={"lifecycle_edge": True},
                validate_assets=False,
            )
        updated = dict(admitted)
        updated["tags"] = tags
        upsert_record("admitted_factors", admitted_id, updated)
        return updated


factor_asset_service = FactorAssetService()
factor_card_service = factor_asset_service.card_service
