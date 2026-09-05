# pyright: reportAny=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Read-only aggregation service for the productized Latent Factor Lab.

The service intentionally composes existing latent discovery, interpretation,
exposure, and handoff records without invoking mutating helpers such as
``build_factor_card``.  Write paths remain owned by the existing discovery /
interpret / materialize / register / handoff endpoints.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Final, cast

from factor_lab.core.errors import NotFoundError
from factor_lab.core.runtime_records import artifact_payload, get_record
from factor_lab.core.runtime_state import runtime_state_store
from factor_lab.factor_engine.repositories.spec_registry import spec_registry

_LATENT_STEP_ORDER: Final[tuple[str, ...]] = (
    "discover",
    "review_clusters",
    "interpret",
    "exposure",
    "validate",
)


def _record(value: Mapping[str, object] | None) -> dict[str, object]:
    return dict(value) if value is not None else {}


def _object_dict(value: object) -> dict[str, object]:
    return dict(cast(Mapping[str, object], value)) if isinstance(value, Mapping) else {}


def _object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [
        dict(cast(Mapping[str, object], item))
        for item in value
        if isinstance(item, Mapping)
    ]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [str(item) for item in value]


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _int(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _record_payload(record: Mapping[str, object] | None) -> dict[str, object]:
    if record is None:
        return {}
    artifact_id = str(record.get("artifact_id", ""))
    if not artifact_id:
        return {}
    artifact = get_record("artifacts", artifact_id)
    if artifact is None:
        return {}
    return artifact_payload(artifact)


def _date_key(row: Mapping[str, object]) -> str:
    return str(row.get("date") or row.get("timestamp") or "").split("T", maxsplit=1)[0]


def _row_symbol(row: Mapping[str, object]) -> str:
    return str(row.get("symbol") or row.get("asset_id") or "")


def _matches_optional_window(
    row: Mapping[str, object],
    *,
    symbol: str | None,
    start_date: str | None,
    end_date: str | None,
) -> bool:
    if symbol and _row_symbol(row) != symbol:
        return False
    date_key = _date_key(row)
    if start_date and date_key < start_date:
        return False
    if end_date and date_key > end_date:
        return False
    return True


def _workflow_item(
    status: str,
    *,
    label: str,
    detail: str,
    ref: str = "",
) -> dict[str, object]:
    return {"status": status, "label": label, "detail": detail, "ref": ref}


class LatentLabStateService:
    """Read-only Latent Factor Lab aggregation and preview service."""

    def state(
        self,
        *,
        run_id: str | None = None,
        cluster_id: str | None = None,
        latent_factor_id: str | None = None,
        exposure_frame_id: str | None = None,
        handoff_id: str | None = None,
        cluster_limit: int = 50,
        graph_edge_limit: int = 300,
        exposure_limit: int = 500,
        include_raw: bool = False,
    ) -> dict[str, object]:
        state = runtime_state_store.load()
        resolved = self._resolve_selection(
            run_id=run_id,
            cluster_id=cluster_id,
            latent_factor_id=latent_factor_id,
            exposure_frame_id=exposure_frame_id,
            handoff_id=handoff_id,
        )
        run = resolved["run"]
        cluster = resolved["cluster"]
        latent_factor = resolved["latent_factor"]
        exposure_frame = resolved["exposure_frame"]
        handoff = resolved["handoff"]
        factor_card = self._latest_factor_card(
            str(latent_factor.get("latent_factor_id", ""))
        )
        clusters = self._clusters_for_run_or_recent(
            run_id=str(run.get("run_id", "")), limit=cluster_limit
        )
        factor_refs = self._factor_refs(
            latent_factor_id=str(latent_factor.get("latent_factor_id", "")),
            exposure_frame=exposure_frame,
        )
        workflow = self._workflow_status(
            run=run,
            cluster=cluster,
            latent_factor=latent_factor,
            exposure_frame=exposure_frame,
            handoff=handoff,
            clusters=clusters,
        )
        visualization: dict[str, object] = {
            "cluster_graph": self.cluster_graph_payload(
                cluster_id=str(cluster.get("cluster_id", "")),
                edge_limit=graph_edge_limit,
            ),
            "lifecycle_timeline": self.lifecycle_timeline(
                exposure_frame=exposure_frame,
                factor_refs=factor_refs,
                handoff=handoff,
            ),
        }
        if exposure_frame:
            visualization["exposure_preview"] = self.exposure_preview(
                str(exposure_frame["exposure_frame_id"]),
                limit=exposure_limit,
                symbol=None,
                start_date=None,
                end_date=None,
            )
        payload: dict[str, object] = {
            "selection": {
                "run_id": str(run.get("run_id", "")),
                "cluster_id": str(cluster.get("cluster_id", "")),
                "latent_factor_id": str(latent_factor.get("latent_factor_id", "")),
                "exposure_frame_id": str(exposure_frame.get("exposure_frame_id", "")),
                "handoff_id": str(handoff.get("handoff_id", "")),
                "candidate_factor_id": str(factor_refs.get("candidate_factor_id", "")),
                "validation_claim_id": str(factor_refs.get("validation_claim_id", "")),
            },
            "current": {
                "run": run,
                "cluster": cluster,
                "latent_factor": latent_factor,
                "factor_card": factor_card,
                "exposure_frame": exposure_frame,
                "handoff": handoff,
                "candidate": factor_refs.get("candidate", {}),
                "validation_claim": factor_refs.get("validation_claim", {}),
                "factor_spec": factor_refs.get("factor_spec", {}),
            },
            "workflow_status": workflow,
            "summary_cards": self._summary_cards(
                runtime_state=state,
                run=run,
                clusters=clusters,
                factor_refs=factor_refs,
                handoff=handoff,
            ),
            "recommended_next_action": self._recommended_next_action(workflow),
            "recent_runs": self._recent_runs(limit=10),
            "clusters": clusters,
            "factor_refs": factor_refs,
            "visualization": visualization,
            "limits": {
                "cluster_limit": cluster_limit,
                "graph_edge_limit": graph_edge_limit,
                "exposure_limit": exposure_limit,
            },
        }
        if include_raw:
            payload["raw"] = {
                "latent_discovery_runs": deepcopy(state["latent_discovery_runs"]),
                "latent_cluster_candidates": deepcopy(
                    state["latent_cluster_candidates"]
                ),
                "latent_factor_definitions": deepcopy(
                    state["latent_factor_definitions"]
                ),
                "latent_factor_exposure_frames": deepcopy(
                    state["latent_factor_exposure_frames"]
                ),
                "latent_governance_handoffs": deepcopy(
                    state["latent_governance_handoffs"]
                ),
            }
        return payload

    def exposure_preview(
        self,
        exposure_frame_id: str,
        *,
        limit: int = 500,
        symbol: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, object]:
        frame = get_record("latent_factor_exposure_frames", exposure_frame_id)
        if frame is None:
            raise NotFoundError(f"latent exposure frame not found: {exposure_frame_id}")
        rows = _object_list(_record_payload(frame).get("rows", []))
        filtered_rows = [
            row
            for row in rows
            if _matches_optional_window(
                row, symbol=symbol, start_date=start_date, end_date=end_date
            )
        ]
        ordered_rows = sorted(
            filtered_rows,
            key=lambda item: (_date_key(item), _row_symbol(item)),
        )
        bounded_limit = max(1, min(int(limit), 5_000))
        sample_rows = ordered_rows[:bounded_limit]
        latest_key = max((_date_key(row) for row in filtered_rows), default="")
        latest_rows = [row for row in filtered_rows if _date_key(row) == latest_key]
        latest_snapshot = sorted(
            latest_rows,
            key=lambda item: abs(_number(item.get("exposure"))),
            reverse=True,
        )[:bounded_limit]
        ranked = sorted(
            filtered_rows,
            key=lambda item: _number(item.get("exposure")),
            reverse=True,
        )
        heatmap_rows = [
            {
                "date": _date_key(row),
                "symbol": _row_symbol(row),
                "exposure": _number(row.get("exposure")),
                "membership_role": str(row.get("membership_role", "")),
            }
            for row in sample_rows
        ]
        return {
            "exposure_frame": dict(frame),
            "filters": {
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "limit": bounded_limit,
            },
            "row_count": len(filtered_rows),
            "sample_rows": sample_rows,
            "latest_snapshot": latest_snapshot,
            "top_positive": ranked[: min(10, len(ranked))],
            "top_negative": list(reversed(ranked[-min(10, len(ranked)) :]))
            if ranked
            else [],
            "histogram_bins": self._histogram_bins(filtered_rows),
            "heatmap": {
                "rows": heatmap_rows,
                "x": "date",
                "y": "symbol",
                "color": "exposure",
                "truncated": len(filtered_rows) > len(sample_rows),
            },
        }

    def cluster_graph_payload(
        self,
        *,
        cluster_id: str,
        edge_limit: int,
    ) -> dict[str, object]:
        if not cluster_id:
            return {
                "type": "cytoscape",
                "elements": [],
                "nodes": [],
                "edges": [],
                "edge_count": 0,
                "edge_limit": edge_limit,
                "truncated": False,
                "styles": self._cytoscape_styles(),
            }
        cluster = get_record("latent_cluster_candidates", cluster_id)
        if cluster is None:
            raise NotFoundError(f"latent cluster candidate not found: {cluster_id}")
        run_id = str(cluster.get("run_id", ""))
        core_assets = _string_list(cluster.get("core_assets"))
        inverse_assets = _string_list(cluster.get("inverse_assets"))
        graph_assets = list(dict.fromkeys([*core_assets, *inverse_assets]))
        nodes: list[dict[str, object]] = []
        edges: list[dict[str, object]] = []
        for asset_id in graph_assets:
            role = "core_asset" if asset_id in core_assets else "inverse_asset"
            nodes.append(
                {
                    "data": {
                        "id": f"asset:{asset_id}",
                        "label": asset_id,
                        "node_type": role,
                        "asset_id": asset_id,
                    },
                    "classes": role,
                }
            )
        explicit_overlap = _object_dict(cluster.get("explicit_overlap"))
        overlap_nodes, overlap_edges = self._explicit_overlap_elements(
            explicit_overlap=explicit_overlap,
            graph_assets=graph_assets,
        )
        nodes.extend(overlap_nodes)
        edges.extend(overlap_edges)
        similarity_edges = self._similarity_graph_edges(
            run_id=run_id,
            graph_assets=graph_assets,
        )
        all_edges = [*edges, *similarity_edges]
        bounded_limit = max(0, int(edge_limit))
        truncated_edges = all_edges[:bounded_limit] if bounded_limit else []
        elements = [*nodes, *truncated_edges]
        return {
            "type": "cytoscape",
            "elements": elements,
            "nodes": nodes,
            "edges": truncated_edges,
            "edge_count": len(all_edges),
            "edge_limit": bounded_limit,
            "truncated": len(all_edges) > len(truncated_edges),
            "styles": self._cytoscape_styles(),
            "layout": {"name": "cose", "animate": False},
        }

    def lifecycle_timeline(
        self,
        *,
        exposure_frame: Mapping[str, object],
        factor_refs: Mapping[str, object],
        handoff: Mapping[str, object],
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        if exposure_frame:
            rows.append(
                {
                    "stage": "latent_factor_exposure_frame",
                    "status": "complete",
                    "ref": str(exposure_frame.get("exposure_frame_id", "")),
                    "created_at": str(exposure_frame.get("created_at", "")),
                }
            )
        factor_spec = _object_dict(factor_refs.get("factor_spec"))
        if factor_spec:
            rows.append(
                {
                    "stage": "FactorSpec",
                    "status": "complete",
                    "ref": str(factor_spec.get("spec_version", "")),
                    "created_at": str(factor_spec.get("created_at", "")),
                }
            )
        candidate = _object_dict(factor_refs.get("candidate"))
        if candidate:
            rows.append(
                {
                    "stage": "Candidate",
                    "status": str(candidate.get("pool_status", "proposed")),
                    "ref": str(candidate.get("candidate_factor_id", "")),
                    "created_at": str(candidate.get("created_at", "")),
                }
            )
        claim = _object_dict(factor_refs.get("validation_claim"))
        if claim:
            rows.append(
                {
                    "stage": "ValidationClaim",
                    "status": str(claim.get("claim_status", "")),
                    "ref": str(claim.get("validation_claim_id", "")),
                    "created_at": str(claim.get("created_at", "")),
                }
            )
        if handoff:
            status = str(handoff.get("status", ""))
            rows.append(
                {
                    "stage": "handoff",
                    "status": status,
                    "ref": str(handoff.get("handoff_id", "")),
                    "failed_stage": str(handoff.get("failed_stage", "")),
                    "created_at": str(handoff.get("created_at", "")),
                }
            )
        return rows

    def _resolve_selection(
        self,
        *,
        run_id: str | None,
        cluster_id: str | None,
        latent_factor_id: str | None,
        exposure_frame_id: str | None,
        handoff_id: str | None,
    ) -> dict[str, dict[str, object]]:
        state = runtime_state_store.load()
        handoff = _record(state["latent_governance_handoffs"].get(handoff_id or ""))
        resolved_exposure_frame_id = exposure_frame_id or str(
            handoff.get("exposure_frame_id", "")
        )
        exposure_frame = _record(
            state["latent_factor_exposure_frames"].get(resolved_exposure_frame_id)
        )
        resolved_latent_factor_id = (
            latent_factor_id
            or str(handoff.get("latent_factor_id", ""))
            or str(exposure_frame.get("latent_factor_id", ""))
        )
        if not resolved_latent_factor_id and exposure_frame:
            version = state["latent_factor_versions"].get(
                str(exposure_frame.get("latent_factor_version", ""))
            )
            if version is not None:
                resolved_latent_factor_id = str(version.get("latent_factor_id", ""))
        latent_factor = _record(
            state["latent_factor_definitions"].get(resolved_latent_factor_id)
        )
        resolved_cluster_id = cluster_id
        if not resolved_cluster_id:
            source_cluster_ids = _string_list(latent_factor.get("source_cluster_ids"))
            resolved_cluster_id = source_cluster_ids[0] if source_cluster_ids else ""
        cluster = _record(
            state["latent_cluster_candidates"].get(resolved_cluster_id or "")
        )
        resolved_run_id = run_id or str(cluster.get("run_id", ""))
        if not resolved_run_id and exposure_frame:
            resolved_run_id = str(exposure_frame.get("run_id", ""))
        run = _record(state["latent_discovery_runs"].get(resolved_run_id or ""))
        if not handoff and exposure_frame:
            handoffs = [
                dict(record)
                for record in state["latent_governance_handoffs"].values()
                if str(record.get("exposure_frame_id", ""))
                == str(exposure_frame.get("exposure_frame_id", ""))
            ]
            handoff = (
                sorted(handoffs, key=lambda item: str(item.get("updated_at", "")))[-1]
                if handoffs
                else {}
            )
        if not latent_factor and cluster:
            interpretations = self._interpretations(
                cluster_id=str(cluster["cluster_id"])
            )
            for record in reversed(interpretations):
                candidate_id = str(record.get("latent_factor_id", ""))
                if candidate_id:
                    latent_factor = _record(
                        state["latent_factor_definitions"].get(candidate_id)
                    )
                    break
        return {
            "run": run,
            "cluster": cluster,
            "latent_factor": latent_factor,
            "exposure_frame": exposure_frame,
            "handoff": handoff,
        }

    def _recent_runs(self, *, limit: int) -> list[dict[str, object]]:
        runs = [
            dict(record)
            for record in runtime_state_store.load()["latent_discovery_runs"].values()
        ]
        return sorted(
            runs, key=lambda item: str(item.get("created_at", "")), reverse=True
        )[:limit]

    def _clusters_for_run_or_recent(
        self, *, run_id: str, limit: int
    ) -> list[dict[str, object]]:
        clusters = [
            dict(record)
            for record in runtime_state_store.load()[
                "latent_cluster_candidates"
            ].values()
            if not run_id or str(record.get("run_id", "")) == run_id
        ]
        ordered = sorted(
            clusters,
            key=lambda item: (
                str(item.get("run_id", "")),
                _int(item.get("cluster_rank")),
                str(item.get("cluster_id", "")),
            ),
        )
        return ordered[: max(0, int(limit))]

    def _latest_factor_card(self, latent_factor_id: str) -> dict[str, object]:
        if not latent_factor_id:
            return {}
        cards = [
            dict(record)
            for record in runtime_state_store.load()["latent_factor_cards"].values()
            if str(record.get("latent_factor_id", "")) == latent_factor_id
        ]
        return (
            sorted(cards, key=lambda item: str(item.get("generated_at", "")))[-1]
            if cards
            else {}
        )

    def _interpretations(self, *, cluster_id: str) -> list[dict[str, object]]:
        records = [
            dict(record)
            for record in runtime_state_store.load()[
                "latent_interpretation_records"
            ].values()
            if str(record.get("cluster_id", "")) == cluster_id
        ]
        return sorted(records, key=lambda item: str(item.get("created_at", "")))

    def _factor_refs(
        self,
        *,
        latent_factor_id: str,
        exposure_frame: Mapping[str, object],
    ) -> dict[str, object]:
        state = runtime_state_store.load()
        exposure_frames = [
            dict(record)
            for record in state["latent_factor_exposure_frames"].values()
            if (
                latent_factor_id
                and str(record.get("latent_factor_id", "")) == latent_factor_id
            )
            or (
                exposure_frame
                and str(record.get("exposure_frame_id", ""))
                == str(exposure_frame.get("exposure_frame_id", ""))
            )
        ]
        spec_versions = {
            str(frame.get("factor_spec_version", ""))
            for frame in exposure_frames
            if str(frame.get("factor_spec_version", ""))
        }
        selected_spec_version = str(exposure_frame.get("factor_spec_version", ""))
        factor_specs: list[dict[str, object]] = []
        for spec_version in sorted(spec_versions):
            spec = spec_registry.get_factor_spec_sync(spec_version)
            if spec is not None:
                factor_specs.append(spec.to_dict())
        candidates = [
            dict(record)
            for record in state["candidate_pool_factors"].values()
            if str(record.get("factor_spec_version", "")) in spec_versions
        ]
        candidate_ids = {
            str(candidate.get("candidate_factor_id", "")) for candidate in candidates
        }
        claims = [
            dict(record)
            for record in state["validation_claims"].values()
            if str(record.get("candidate_factor_id", "")) in candidate_ids
        ]
        latest_candidate = (
            sorted(candidates, key=lambda item: str(item.get("created_at", "")))[-1]
            if candidates
            else {}
        )
        latest_claim = (
            sorted(claims, key=lambda item: str(item.get("created_at", "")))[-1]
            if claims
            else {}
        )
        selected_spec = next(
            (
                item
                for item in factor_specs
                if str(item.get("spec_version", "")) == selected_spec_version
            ),
            factor_specs[-1] if factor_specs else {},
        )
        return {
            "exposure_frames": sorted(
                exposure_frames, key=lambda item: str(item.get("created_at", ""))
            ),
            "factor_specs": factor_specs,
            "candidates": candidates,
            "validation_claims": claims,
            "factor_spec": selected_spec,
            "candidate": latest_candidate,
            "validation_claim": latest_claim,
            "candidate_factor_id": str(latest_candidate.get("candidate_factor_id", "")),
            "validation_claim_id": str(latest_claim.get("validation_claim_id", "")),
        }

    def _workflow_status(
        self,
        *,
        run: Mapping[str, object],
        cluster: Mapping[str, object],
        latent_factor: Mapping[str, object],
        exposure_frame: Mapping[str, object],
        handoff: Mapping[str, object],
        clusters: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        discover_status = str(run.get("status", ""))
        if not run:
            discover = _workflow_item(
                "ready", label="Discover", detail="Submit a latent discovery run"
            )
        elif discover_status == "failed":
            discover = _workflow_item(
                "failed",
                label="Discover",
                detail="Discovery failed",
                ref=str(run.get("run_id", "")),
            )
        elif discover_status == "completed":
            discover = _workflow_item(
                "complete",
                label="Discover",
                detail="Discovery completed",
                ref=str(run.get("run_id", "")),
            )
        else:
            discover = _workflow_item(
                "ready",
                label="Discover",
                detail=f"Discovery status={discover_status}",
                ref=str(run.get("run_id", "")),
            )

        if discover["status"] != "complete":
            review = _workflow_item(
                "blocked",
                label="Review Clusters",
                detail="Waiting for completed discovery run",
            )
        elif cluster:
            review = _workflow_item(
                "complete",
                label="Review Clusters",
                detail="Cluster selected",
                ref=str(cluster.get("cluster_id", "")),
            )
        elif clusters:
            review = _workflow_item(
                "ready",
                label="Review Clusters",
                detail="Select a cluster for interpretation",
            )
        else:
            review = _workflow_item(
                "blocked", label="Review Clusters", detail="No clusters available"
            )

        cluster_status = str(cluster.get("status", ""))
        if not cluster:
            interpret = _workflow_item(
                "blocked", label="Interpret", detail="Select a cluster first"
            )
        elif latent_factor:
            interpret = _workflow_item(
                "complete",
                label="Interpret",
                detail="Latent factor linked",
                ref=str(latent_factor.get("latent_factor_id", "")),
            )
        elif cluster_status in {"discarded", "kept_as_explanation"}:
            interpret = _workflow_item(
                "complete",
                label="Interpret",
                detail=f"Cluster marked {cluster_status}",
                ref=str(cluster.get("cluster_id", "")),
            )
        else:
            interpret = _workflow_item(
                "ready",
                label="Interpret",
                detail="Name or classify the selected cluster",
                ref=str(cluster.get("cluster_id", "")),
            )

        if not latent_factor:
            exposure = _workflow_item(
                "blocked", label="Exposure", detail="Interpret a latent factor first"
            )
        elif exposure_frame:
            exposure = _workflow_item(
                "complete",
                label="Exposure",
                detail="Exposure frame materialized",
                ref=str(exposure_frame.get("exposure_frame_id", "")),
            )
        else:
            exposure = _workflow_item(
                "ready",
                label="Exposure",
                detail="Materialize exposure frame",
                ref=str(latent_factor.get("latent_factor_id", "")),
            )

        if not exposure_frame:
            validate = _workflow_item(
                "blocked",
                label="Validate",
                detail="Materialize an exposure frame first",
            )
        elif handoff and str(handoff.get("status", "")) == "failed":
            validate = _workflow_item(
                "failed",
                label="Validate",
                detail=f"Handoff failed at {handoff.get('failed_stage', '')}",
                ref=str(handoff.get("handoff_id", "")),
            )
        elif handoff and str(handoff.get("status", "")) == "blocked_temporal_routing":
            temporal_class = str(
                _object_dict(handoff.get("gate_details")).get("temporal_class", "")
            )
            detail = "Temporal routing blocked direct regression"
            if temporal_class:
                detail = f"{detail} for {temporal_class}"
            validate = _workflow_item(
                "blocked",
                label="Validate",
                detail=detail,
                ref=str(handoff.get("handoff_id", "")),
            )
        elif handoff and str(handoff.get("status", "")) == "pending_review":
            validate = _workflow_item(
                "complete",
                label="Validate",
                detail="Candidate and ValidationClaim pending review",
                ref=str(handoff.get("handoff_id", "")),
            )
        else:
            validate = _workflow_item(
                "ready",
                label="Validate",
                detail="Handoff exposure frame to Candidate + ValidationClaim",
                ref=str(exposure_frame.get("exposure_frame_id", "")),
            )
        return {
            "steps": {
                "discover": discover,
                "review_clusters": review,
                "interpret": interpret,
                "exposure": exposure,
                "validate": validate,
            },
            "order": list(_LATENT_STEP_ORDER),
        }

    def _recommended_next_action(
        self, workflow: Mapping[str, object]
    ) -> dict[str, object]:
        steps = _object_dict(workflow.get("steps"))
        actions = {
            "discover": "Submit or load a latent discovery run.",
            "review_clusters": "Select a cluster and inspect the graph/evidence.",
            "interpret": "Record the human interpretation or discard decision.",
            "exposure": "Materialize a latent exposure frame and inspect preview.",
            "validate": (
                "Handoff to Candidate + ValidationClaim, then review in governance."
            ),
        }
        for step in _LATENT_STEP_ORDER:
            item = _object_dict(steps.get(step))
            if item.get("status") in {"failed", "ready"} or (
                step == "validate"
                and item.get("status") == "blocked"
                and item.get("ref")
            ):
                message = actions[step]
                if step == "validate" and item.get("status") == "blocked":
                    message = (
                        "Direct regression is blocked; use factor-dynamics cohort, "
                        "rotation, or conditional surfaces instead."
                    )
                return {
                    "step": step,
                    "status": str(item.get("status", "")),
                    "message": message,
                    "detail": str(item.get("detail", "")),
                }
        return {
            "step": "complete",
            "status": "complete",
            "message": "Latent Factor Lab workflow is ready for governance review.",
            "detail": "No pending Lab-side action detected.",
        }

    def _summary_cards(
        self,
        *,
        runtime_state: Mapping[str, object],
        run: Mapping[str, object],
        clusters: Sequence[Mapping[str, object]],
        factor_refs: Mapping[str, object],
        handoff: Mapping[str, object],
    ) -> list[dict[str, object]]:
        state = runtime_state
        return [
            {
                "label": "Run",
                "value": str(run.get("status", "not_selected"))
                if run
                else "not_selected",
                "caption": str(run.get("run_id", "")) if run else "No run selected",
            },
            {
                "label": "Clusters",
                "value": len(clusters),
                "caption": "Loaded cluster rows for selected run",
            },
            {
                "label": "Exposure frames",
                "value": len(
                    cast(Mapping[str, object], state["latent_factor_exposure_frames"])
                ),
                "caption": "Total persisted latent exposure frames",
            },
            {
                "label": "Handoff",
                "value": str(handoff.get("status", "not_started"))
                if handoff
                else "not_started",
                "caption": str(handoff.get("handoff_id", ""))
                if handoff
                else "No handoff selected",
            },
            {
                "label": "Candidate / Claim",
                "value": str(factor_refs.get("candidate_factor_id", ""))
                or "not_created",
                "caption": str(factor_refs.get("validation_claim_id", ""))
                or "No validation claim",
            },
        ]

    def _explicit_overlap_elements(
        self,
        *,
        explicit_overlap: Mapping[str, object],
        graph_assets: Sequence[str],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        top_industry = str(explicit_overlap.get("industry_top", "")).strip()
        if not top_industry:
            return [], []
        node_id = f"overlap:industry:{top_industry}"
        nodes: list[dict[str, object]] = [
            {
                "data": {
                    "id": node_id,
                    "label": f"industry: {top_industry}",
                    "node_type": "explicit_overlap",
                    "overlap_type": "industry_top",
                    "count": _int(explicit_overlap.get("industry_top_count")),
                },
                "classes": "explicit_overlap",
            }
        ]
        edges: list[dict[str, object]] = [
            {
                "data": {
                    "id": f"edge:overlap:{asset_id}:{top_industry}",
                    "source": f"asset:{asset_id}",
                    "target": node_id,
                    "label": "explicit overlap",
                    "edge_type": "explicit_overlap",
                    "weight": 1.0,
                },
                "classes": "explicit_overlap",
            }
            for asset_id in graph_assets
        ]
        return nodes, edges

    def _similarity_graph_edges(
        self,
        *,
        run_id: str,
        graph_assets: Sequence[str],
    ) -> list[dict[str, object]]:
        if not run_id or not graph_assets:
            return []
        asset_set = set(graph_assets)
        matrices = [
            dict(record)
            for record in runtime_state_store.load()[
                "latent_similarity_matrices"
            ].values()
            if str(record.get("run_id", "")) == run_id
        ]
        if not matrices:
            return []
        matrix = sorted(matrices, key=lambda item: str(item.get("created_at", "")))[-1]
        payload_edges = _object_list(_record_payload(matrix).get("edges", []))
        edges: list[dict[str, object]] = []
        for index, edge in enumerate(payload_edges):
            left = str(edge.get("asset_i", ""))
            right = str(edge.get("asset_j", ""))
            if left not in asset_set or right not in asset_set:
                continue
            similarity = _number(edge.get("similarity"))
            edge_type = (
                "positive_similarity" if similarity >= 0 else "negative_similarity"
            )
            edges.append(
                {
                    "data": {
                        "id": f"edge:similarity:{index}:{left}:{right}",
                        "source": f"asset:{left}",
                        "target": f"asset:{right}",
                        "label": f"{similarity:.3f}",
                        "edge_type": edge_type,
                        "similarity": similarity,
                        "component": str(edge.get("component", "total")),
                        "weight": abs(similarity),
                    },
                    "classes": edge_type,
                }
            )
        return sorted(
            edges,
            key=lambda item: abs(
                _number(_object_dict(item.get("data")).get("similarity"))
            ),
            reverse=True,
        )

    def _histogram_bins(
        self, rows: Sequence[Mapping[str, object]], *, bin_count: int = 10
    ) -> list[dict[str, object]]:
        values = [_number(row.get("exposure")) for row in rows]
        if not values:
            return []
        minimum = min(values)
        maximum = max(values)
        if minimum == maximum:
            return [
                {
                    "bin_start": minimum,
                    "bin_end": maximum,
                    "count": len(values),
                }
            ]
        width = (maximum - minimum) / bin_count
        bins: list[dict[str, object]] = [
            {
                "bin_start": minimum + index * width,
                "bin_end": minimum + (index + 1) * width,
                "count": 0,
            }
            for index in range(bin_count)
        ]
        for value in values:
            index = min(int((value - minimum) / width), bin_count - 1)
            bins[index]["count"] = _int(bins[index]["count"]) + 1
        return bins

    def _cytoscape_styles(self) -> list[dict[str, object]]:
        return [
            {
                "selector": "node",
                "style": {
                    "label": "data(label)",
                    "font-size": 12,
                    "text-valign": "center",
                    "text-halign": "center",
                    "background-color": "#94a3b8",
                },
            },
            {"selector": ".core_asset", "style": {"background-color": "#2563eb"}},
            {"selector": ".inverse_asset", "style": {"background-color": "#f97316"}},
            {
                "selector": ".explicit_overlap",
                "style": {"background-color": "#a855f7", "line-color": "#a855f7"},
            },
            {
                "selector": ".positive_similarity",
                "style": {"line-color": "#16a34a", "width": 2},
            },
            {
                "selector": ".negative_similarity",
                "style": {"line-color": "#dc2626", "width": 2, "line-style": "dashed"},
            },
        ]


latent_lab_state_service = LatentLabStateService()
