# pyright: reportAny=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnusedCallResult=false
"""Human interpretation workflow for latent cluster candidates.

Phase 3 deliberately keeps interpretation auditable and deterministic.  The
service freezes the evidence used during naming, records the human decision, and
only creates or links latent factor definitions.  It does not materialize
negative exposures, CandidateFactors, ValidationClaims, or new factor versions.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Final, Literal, cast

from factor_lab.core.errors import NotFoundError, ValidationError
from factor_lab.core.hashing import sha256_hash
from factor_lab.core.runtime_records import (
    artifact_payload,
    get_record,
    materialize_artifact,
    upsert_record,
    utcnow,
)
from factor_lab.core.runtime_state import runtime_state_store
from factor_lab.governance.services.event_store import event_store
from factor_lab.latent.services.latent_factor_contract_service import (
    latent_factor_contract_service,
)

LatentInterpretationDecision = Literal[
    "discard",
    "keep_as_explanation",
    "interpret_new",
    "merge_existing",
    "inverse_existing",
]

LATENT_INTERPRETATION_SNAPSHOT_SCHEMA_VERSION: Final[str] = (
    "latent_interpretation_evidence_snapshot@1.0"
)
LATENT_INTERPRETATION_RECORD_SCHEMA_VERSION: Final[str] = (
    "latent_interpretation_record@1.0"
)

_ALLOWED_DECISIONS: Final[frozenset[str]] = frozenset(
    {
        "discard",
        "keep_as_explanation",
        "interpret_new",
        "merge_existing",
        "inverse_existing",
    }
)
_FACTOR_LINK_DECISIONS: Final[frozenset[str]] = frozenset(
    {"merge_existing", "inverse_existing"}
)
_RELATION_TYPE_BY_DECISION: Final[dict[str, str]] = {
    "merge_existing": "merged_evidence",
    "inverse_existing": "inverse_evidence",
}
_CLUSTER_STATUS_BY_DECISION: Final[dict[str, str]] = {
    "discard": "discarded",
    "keep_as_explanation": "kept_as_explanation",
    "interpret_new": "interpreted",
    "merge_existing": "interpreted",
    "inverse_existing": "interpreted",
}


def _uuid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _required_text(value: object, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValidationError(f"{field_name} is required")
    return text


def _optional_text(value: object) -> str:
    return str(value or "").strip()


def _record_dict(value: Mapping[str, object] | None) -> dict[str, object]:
    return dict(value) if value is not None else {}


def _artifact_id_from_ref(ref: object) -> str:
    text = str(ref or "").strip()
    if text.startswith("artifact:"):
        return text.split(":", maxsplit=1)[1]
    return text


def _artifact_record_with_payload(artifact_id: str) -> dict[str, object]:
    artifact = get_record("artifacts", artifact_id)
    if artifact is None:
        return {}
    return {
        "artifact": dict(artifact),
        "payload": artifact_payload(artifact),
    }


@dataclass(slots=True)
class LatentInterpretationRecord:
    interpretation_id: str
    schema_version: str
    cluster_id: str
    run_id: str
    decision: str
    decision_reason: str
    name: str
    thesis: str
    horizon: str
    latent_factor_type: str
    created_by: str
    created_at: str
    naming_time: str
    evidence_snapshot_artifact_id: str
    evidence_snapshot_ref: str
    advisory_summary: dict[str, object] = field(default_factory=dict)
    latent_factor_id: str = ""
    target_latent_factor_id: str = ""
    evidence_relation_id: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class LatentFactorEvidenceRelationRecord:
    relation_id: str
    latent_factor_id: str
    cluster_id: str
    interpretation_id: str
    relation_type: str
    evidence_snapshot_artifact_id: str
    decision_reason: str
    created_by: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class LatentInterpretationService:
    """Auditable latent cluster interpretation workflow."""

    def list_discovery_runs(
        self, *, status: str | None = None
    ) -> list[dict[str, object]]:
        runs = [
            dict(record)
            for record in runtime_state_store.load()["latent_discovery_runs"].values()
            if not status or str(record.get("status", "")) == status
        ]
        return sorted(runs, key=lambda item: str(item.get("created_at", "")))

    def get_discovery_run(self, run_id: str) -> dict[str, object]:
        run = get_record("latent_discovery_runs", run_id)
        if run is None:
            raise NotFoundError(f"latent discovery run not found: {run_id}")
        return dict(run)

    def list_clusters(
        self,
        *,
        run_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, object]]:
        clusters = [
            dict(record)
            for record in runtime_state_store.load()[
                "latent_cluster_candidates"
            ].values()
            if (not run_id or str(record.get("run_id", "")) == run_id)
            and (not status or str(record.get("status", "")) == status)
        ]
        return sorted(
            clusters,
            key=lambda item: (
                str(item.get("run_id", "")),
                int(str(item.get("cluster_rank", "0") or "0")),
                str(item.get("cluster_id", "")),
            ),
        )

    def get_cluster(self, cluster_id: str) -> dict[str, object]:
        cluster = get_record("latent_cluster_candidates", cluster_id)
        if cluster is None:
            raise NotFoundError(f"latent cluster candidate not found: {cluster_id}")
        return dict(cluster)

    def cluster_detail(self, cluster_id: str) -> dict[str, object]:
        cluster = self.get_cluster(cluster_id)
        run_id = str(cluster.get("run_id", ""))
        return {
            "cluster": cluster,
            "run": self.get_discovery_run(run_id),
            "membership_frames": self._membership_frame_details(cluster_id),
            "similarity_matrices": self._similarity_matrix_details(run_id),
            "representative_series": self._representative_series_detail(cluster),
            "review_artifacts": self._review_artifact_details(run_id),
            "interpretation_records": self.list_interpretation_records(
                cluster_id=cluster_id
            ),
            "advisory": self.advisory_for_cluster(cluster),
        }

    def list_interpretation_records(
        self,
        *,
        cluster_id: str | None = None,
        latent_factor_id: str | None = None,
    ) -> list[dict[str, object]]:
        records = []
        for record in runtime_state_store.load()[
            "latent_interpretation_records"
        ].values():
            if cluster_id and str(record.get("cluster_id", "")) != cluster_id:
                continue
            if latent_factor_id and str(record.get("latent_factor_id", "")) != (
                latent_factor_id
            ):
                continue
            records.append(dict(record))
        return sorted(records, key=lambda item: str(item.get("created_at", "")))

    def advisory_for_cluster(
        self, cluster: Mapping[str, object] | str
    ) -> dict[str, object]:
        cluster_record = (
            self.get_cluster(cluster) if isinstance(cluster, str) else dict(cluster)
        )
        core_assets = [
            str(item)
            for item in cast(list[object], cluster_record.get("core_assets", []))
        ]
        inverse_assets = [
            str(item)
            for item in cast(list[object], cluster_record.get("inverse_assets", []))
        ]
        overlap = (
            dict(cast(Mapping[str, object], cluster_record.get("explicit_overlap", {})))
            if isinstance(cluster_record.get("explicit_overlap"), Mapping)
            else {}
        )
        top_industry = _optional_text(overlap.get("industry_top"))
        rank = str(cluster_record.get("cluster_rank", ""))
        cohesion = cluster_record.get("cohesion_score", 0.0)
        separation = cluster_record.get("separation_score", 0.0)
        stability = cluster_record.get("stability_score", 0.0)
        core_preview = ", ".join(core_assets[:4])
        inverse_preview = ", ".join(inverse_assets[:4])

        summary_parts = [
            f"Cluster rank {rank} contains {len(core_assets)} core assets",
            f"cohesion={cohesion}",
            f"separation={separation}",
            f"stability={stability}",
        ]
        if top_industry:
            summary_parts.append(f"top explicit overlap={top_industry}")
        if inverse_assets:
            summary_parts.append(f"inverse assets detected={len(inverse_assets)}")

        name_suggestions: list[str] = []
        if top_industry:
            name_suggestions.append(f"{top_industry} latent co-movement")
        if core_assets:
            name_suggestions.append(f"{core_assets[0]} peer latent cluster")
        if top_industry and inverse_assets:
            name_suggestions.append(f"{top_industry} inverse basket timing")
        if not name_suggestions:
            name_suggestions.append(f"latent cluster {rank}")

        return {
            "method": "deterministic_rule_summary@1.0",
            "summary": "; ".join(summary_parts),
            "name_suggestions": name_suggestions[:3],
            "thesis_prompt": (
                "Explain the economic or market-structure reason connecting "
                + f"core assets ({core_preview})"
                + (f" and inverse assets ({inverse_preview})" if inverse_assets else "")
                + "."
            ),
            "requires_human_review": True,
        }

    def interpret_cluster(
        self,
        *,
        cluster_id: str,
        decision: LatentInterpretationDecision | str,
        decision_reason: str,
        name: str,
        thesis: str,
        horizon: str,
        latent_factor_type: str,
        created_by: str,
        target_latent_factor_id: str | None = None,
        naming_time: str | None = None,
    ) -> dict[str, object]:
        decision_text = _required_text(decision, field_name="decision")
        if decision_text not in _ALLOWED_DECISIONS:
            raise ValidationError(
                f"Unsupported latent interpretation decision: {decision_text}"
            )
        required_reason = _required_text(
            decision_reason,
            field_name="decision_reason",
        )
        required_name = _required_text(name, field_name="name")
        required_thesis = _required_text(thesis, field_name="thesis")
        required_horizon = _required_text(horizon, field_name="horizon")
        required_type = _required_text(
            latent_factor_type,
            field_name="latent_factor_type",
        )
        actor = _required_text(created_by, field_name="created_by")
        naming_at = _required_text(naming_time or utcnow(), field_name="naming_time")

        cluster = self.get_cluster(cluster_id)
        run_id = str(cluster.get("run_id", ""))
        target_id = _optional_text(target_latent_factor_id)
        latent_factor_id = ""
        relation_id = ""

        snapshot = self._materialize_evidence_snapshot(
            cluster=cluster,
            naming_time=naming_at,
            created_by=actor,
        )
        snapshot_artifact_id = str(snapshot["artifact_id"])

        if decision_text == "interpret_new":
            definition = latent_factor_contract_service.create_factor_definition(
                source_cluster_ids=[cluster_id],
                name=required_name,
                thesis=required_thesis,
                horizon=required_horizon,
                latent_factor_type=required_type,
                created_by=actor,
                naming_time=naming_at,
                description=required_reason,
                status="research",
            )
            latent_factor_id = str(definition["latent_factor_id"])
        elif decision_text in _FACTOR_LINK_DECISIONS:
            target_id = _required_text(
                target_id,
                field_name="target_latent_factor_id",
            )
            if get_record("latent_factor_definitions", target_id) is None:
                raise ValidationError(
                    f"latent factor definition not found: {target_id}"
                )
            latent_factor_id = target_id

        interpretation_id = self._interpretation_id(
            cluster_id=cluster_id,
            decision=decision_text,
            name=required_name,
            naming_time=naming_at,
        )
        record = LatentInterpretationRecord(
            interpretation_id=interpretation_id,
            schema_version=LATENT_INTERPRETATION_RECORD_SCHEMA_VERSION,
            cluster_id=cluster_id,
            run_id=run_id,
            decision=decision_text,
            decision_reason=required_reason,
            name=required_name,
            thesis=required_thesis,
            horizon=required_horizon,
            latent_factor_type=required_type,
            target_latent_factor_id=target_id,
            latent_factor_id=latent_factor_id,
            created_by=actor,
            created_at=utcnow(),
            naming_time=naming_at,
            evidence_snapshot_artifact_id=snapshot_artifact_id,
            evidence_snapshot_ref=f"artifact:{snapshot_artifact_id}",
            advisory_summary=self.advisory_for_cluster(cluster),
        ).to_dict()

        if decision_text in _RELATION_TYPE_BY_DECISION:
            relation = self._append_factor_evidence_relation(
                latent_factor_id=latent_factor_id,
                cluster_id=cluster_id,
                interpretation_id=interpretation_id,
                relation_type=_RELATION_TYPE_BY_DECISION[decision_text],
                evidence_snapshot_artifact_id=snapshot_artifact_id,
                decision_reason=required_reason,
                created_by=actor,
            )
            relation_id = str(relation["relation_id"])
            record["evidence_relation_id"] = relation_id

        upsert_record("latent_interpretation_records", interpretation_id, record)
        updated_cluster = self._transition_cluster(
            cluster,
            decision=decision_text,
            interpretation_id=interpretation_id,
            latent_factor_id=latent_factor_id,
        )
        _ = event_store.append(
            event_type="latent_cluster_candidate.interpreted",
            payload={
                "cluster_id": cluster_id,
                "decision": decision_text,
                "interpretation_id": interpretation_id,
                "latent_factor_id": latent_factor_id,
                "evidence_relation_id": relation_id,
            },
            run_id=run_id,
        )
        return {
            "interpretation_record": record,
            "cluster": updated_cluster,
            "latent_factor": _record_dict(
                get_record("latent_factor_definitions", latent_factor_id)
                if latent_factor_id
                else None
            ),
            "evidence_relation": _record_dict(
                get_record("latent_factor_evidence_relations", relation_id)
                if relation_id
                else None
            ),
            "evidence_snapshot": snapshot,
        }

    def _interpretation_id(
        self,
        *,
        cluster_id: str,
        decision: str,
        name: str,
        naming_time: str,
    ) -> str:
        digest = sha256_hash(
            {
                "cluster_id": cluster_id,
                "decision": decision,
                "name": name,
                "naming_time": naming_time,
            }
        )[:20]
        return f"lir_{digest}"

    def _membership_frame_details(self, cluster_id: str) -> list[dict[str, object]]:
        details: list[dict[str, object]] = []
        for record in runtime_state_store.load()[
            "latent_cluster_membership_frames"
        ].values():
            if str(record.get("cluster_id", "")) != cluster_id:
                continue
            record_dict = dict(record)
            details.append(
                {
                    "record": record_dict,
                    "payload": (
                        latent_factor_contract_service.artifact_payload_for_record(
                            record_dict
                        )
                    ),
                }
            )
        return sorted(
            details,
            key=lambda item: str(
                cast(dict[str, object], item["record"]).get("created_at", "")
            ),
        )

    def _similarity_matrix_details(self, run_id: str) -> list[dict[str, object]]:
        details: list[dict[str, object]] = []
        for record in runtime_state_store.load()["latent_similarity_matrices"].values():
            if str(record.get("run_id", "")) != run_id:
                continue
            record_dict = dict(record)
            details.append(
                {
                    "record": record_dict,
                    "payload": (
                        latent_factor_contract_service.artifact_payload_for_record(
                            record_dict
                        )
                    ),
                }
            )
        return sorted(
            details,
            key=lambda item: str(
                cast(dict[str, object], item["record"]).get("created_at", "")
            ),
        )

    def _representative_series_detail(
        self,
        cluster: Mapping[str, object],
    ) -> dict[str, object]:
        artifact_id = _artifact_id_from_ref(cluster.get("representative_series_ref"))
        if not artifact_id:
            return {}
        return _artifact_record_with_payload(artifact_id)

    def _review_artifact_details(self, run_id: str) -> list[dict[str, object]]:
        details: list[dict[str, object]] = []
        for artifact in runtime_state_store.list_artifacts_for_run(run_id):
            if str(artifact.get("artifact_type", "")) != "latent_cluster_review_report":
                continue
            details.append(
                {
                    "artifact": dict(artifact),
                    "payload": artifact_payload(artifact),
                }
            )
        return details

    def _materialize_evidence_snapshot(
        self,
        *,
        cluster: Mapping[str, object],
        naming_time: str,
        created_by: str,
    ) -> dict[str, object]:
        cluster_id = str(cluster.get("cluster_id", ""))
        run_id = str(cluster.get("run_id", ""))
        payload = {
            "schema_version": LATENT_INTERPRETATION_SNAPSHOT_SCHEMA_VERSION,
            "cluster_id": cluster_id,
            "run_id": run_id,
            "frozen_at": utcnow(),
            "naming_time": naming_time,
            "created_by": created_by,
            "run": self.get_discovery_run(run_id),
            "cluster": dict(cluster),
            "membership_frames": self._membership_frame_details(cluster_id),
            "similarity_matrices": self._similarity_matrix_details(run_id),
            "representative_series": self._representative_series_detail(cluster),
            "review_artifacts": self._review_artifact_details(run_id),
            "advisory": self.advisory_for_cluster(cluster),
        }
        artifact = materialize_artifact(
            run_id,
            "latent_interpretation_evidence_snapshot",
            payload,
        )
        return {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "storage_uri": artifact.storage_uri,
            "payload": payload,
        }

    def _append_factor_evidence_relation(
        self,
        *,
        latent_factor_id: str,
        cluster_id: str,
        interpretation_id: str,
        relation_type: str,
        evidence_snapshot_artifact_id: str,
        decision_reason: str,
        created_by: str,
    ) -> dict[str, object]:
        record = LatentFactorEvidenceRelationRecord(
            relation_id=_uuid("lfer"),
            latent_factor_id=latent_factor_id,
            cluster_id=cluster_id,
            interpretation_id=interpretation_id,
            relation_type=relation_type,
            evidence_snapshot_artifact_id=evidence_snapshot_artifact_id,
            decision_reason=decision_reason,
            created_by=created_by,
            created_at=utcnow(),
        ).to_dict()
        upsert_record(
            "latent_factor_evidence_relations",
            str(record["relation_id"]),
            record,
        )
        return record

    def _transition_cluster(
        self,
        cluster: Mapping[str, object],
        *,
        decision: str,
        interpretation_id: str,
        latent_factor_id: str,
    ) -> dict[str, object]:
        updated = dict(cluster)
        updated["status"] = _CLUSTER_STATUS_BY_DECISION[decision]
        updated["latest_interpretation_id"] = interpretation_id
        updated["interpreted_at"] = utcnow()
        if latent_factor_id:
            updated["latent_factor_id"] = latent_factor_id
        upsert_record(
            "latent_cluster_candidates",
            str(updated["cluster_id"]),
            updated,
        )
        return updated


latent_interpretation_service = LatentInterpretationService()
