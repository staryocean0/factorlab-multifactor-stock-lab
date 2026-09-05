# pyright: reportAny=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false, reportUnannotatedClassAttribute=false, reportUnnecessaryCast=false
"""Runtime state persistence shared by API services and scripts."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sqlite3
import uuid
from collections.abc import Callable, Mapping
from contextlib import closing
from copy import deepcopy
from pathlib import Path
from typing import TypeAlias, TypedDict, cast

from factor_lab.core.settings import (
    get_artifacts_dir,
    get_runtime_database_path,
    get_runtime_snapshot_path,
    get_staging_dir,
)
from factor_lab.core.storage import (
    is_http_storage_uri,
    resolve_local_storage_path,
    to_portable_storage_uri,
)

Record: TypeAlias = dict[str, object]


class RuntimeState(TypedDict):
    runs: dict[str, Record]
    jobs: dict[str, Record]
    artifacts: dict[str, Record]
    risk_overrides: dict[str, Record]
    principals: dict[str, Record]
    tokens: dict[str, Record]
    secret_refs: dict[str, Record]
    data_sources: dict[str, Record]
    data_source_refreshes: dict[str, Record]
    candidate_factors: dict[str, Record]
    candidate_review_records: dict[str, Record]
    candidate_sets: dict[str, Record]
    candidate_pool_factors: dict[str, Record]
    candidate_batches: dict[str, Record]
    candidate_batch_members: dict[str, Record]
    validation_claims: dict[str, Record]
    effective_factors: dict[str, Record]
    admitted_factors: dict[str, Record]
    strategy_specs: dict[str, Record]
    factor_tag_definitions: dict[str, Record]
    factor_tag_assignments: dict[str, Record]
    factor_lineage_edges: dict[str, Record]
    factor_cards: dict[str, Record]
    factor_health_reports: dict[str, Record]
    factor_alert_notifications: dict[str, Record]
    factor_redundancy_reports: dict[str, Record]
    admitted_factor_lifecycle_events: dict[str, Record]
    factor_materializations: dict[str, Record]
    factor_lifecycle_events: dict[str, Record]
    latent_discovery_runs: dict[str, Record]
    latent_feature_sets: dict[str, Record]
    latent_cluster_candidates: dict[str, Record]
    latent_cluster_membership_frames: dict[str, Record]
    latent_similarity_matrices: dict[str, Record]
    latent_interpretation_records: dict[str, Record]
    latent_factor_evidence_relations: dict[str, Record]
    latent_factor_definitions: dict[str, Record]
    latent_factor_versions: dict[str, Record]
    latent_factor_exposure_frames: dict[str, Record]
    latent_factor_cards: dict[str, Record]
    latent_cluster_stability_reports: dict[str, Record]
    latent_factor_drift_decay_reports: dict[str, Record]
    latent_factor_sets: dict[str, Record]
    latent_governance_handoffs: dict[str, Record]
    factor_temporal_profiles: dict[str, Record]
    factor_ontology_profiles: dict[str, Record]
    market_factor_research_evidence: dict[str, Record]
    factor_observation_frames: dict[str, Record]
    asset_factor_exposure_frames: dict[str, Record]
    factor_state_evidence: dict[str, Record]
    industry_memberships: dict[str, Record]
    cohort_index_definitions: dict[str, Record]
    cohort_index_return_frames: dict[str, Record]
    factor_rotation_reports: dict[str, Record]
    conditional_factor_evaluation_reports: dict[str, Record]
    stock_correlation_distribution_reports: dict[str, Record]
    correlation_core_index_definitions: dict[str, Record]
    correlation_core_index_rebalances: dict[str, Record]
    correlation_core_index_constituent_frames: dict[str, Record]
    correlation_core_index_level_frames: dict[str, Record]
    cloudridge_beta_index_definitions: dict[str, Record]
    cloudridge_beta_index_strength_scans: dict[str, Record]
    cloudridge_beta_index_rebalances: dict[str, Record]
    cloudridge_beta_index_constituent_frames: dict[str, Record]
    cloudridge_beta_index_level_frames: dict[str, Record]
    correlation_threshold_pool_index_definitions: dict[str, Record]
    correlation_threshold_pool_index_threshold_scans: dict[str, Record]
    correlation_threshold_pool_index_rebalances: dict[str, Record]
    correlation_threshold_pool_index_constituent_frames: dict[str, Record]
    correlation_threshold_pool_index_level_frames: dict[str, Record]
    review_sessions: dict[str, Record]
    candidate_card_snapshots: dict[str, Record]
    feedback_records: dict[str, Record]
    rerun_requests: dict[str, Record]
    approval_requests: dict[str, Record]
    approval_decisions: dict[str, Record]
    review_assignments: dict[str, Record]
    events: list[Record]


def _initial_state() -> RuntimeState:
    return {
        "runs": {},
        "jobs": {},
        "artifacts": {},
        "risk_overrides": {},
        "principals": {},
        "tokens": {},
        "secret_refs": {},
        "data_sources": {},
        "data_source_refreshes": {},
        "candidate_factors": {},
        "candidate_review_records": {},
        "candidate_sets": {},
        "candidate_pool_factors": {},
        "candidate_batches": {},
        "candidate_batch_members": {},
        "validation_claims": {},
        "effective_factors": {},
        "admitted_factors": {},
        "strategy_specs": {},
        "factor_tag_definitions": {},
        "factor_tag_assignments": {},
        "factor_lineage_edges": {},
        "factor_cards": {},
        "factor_health_reports": {},
        "factor_alert_notifications": {},
        "factor_redundancy_reports": {},
        "admitted_factor_lifecycle_events": {},
        "factor_materializations": {},
        "factor_lifecycle_events": {},
        "latent_discovery_runs": {},
        "latent_feature_sets": {},
        "latent_cluster_candidates": {},
        "latent_cluster_membership_frames": {},
        "latent_similarity_matrices": {},
        "latent_interpretation_records": {},
        "latent_factor_evidence_relations": {},
        "latent_factor_definitions": {},
        "latent_factor_versions": {},
        "latent_factor_exposure_frames": {},
        "latent_factor_cards": {},
        "latent_cluster_stability_reports": {},
        "latent_factor_drift_decay_reports": {},
        "latent_factor_sets": {},
        "latent_governance_handoffs": {},
        "factor_temporal_profiles": {},
        "factor_ontology_profiles": {},
        "market_factor_research_evidence": {},
        "factor_observation_frames": {},
        "asset_factor_exposure_frames": {},
        "factor_state_evidence": {},
        "industry_memberships": {},
        "cohort_index_definitions": {},
        "cohort_index_return_frames": {},
        "factor_rotation_reports": {},
        "conditional_factor_evaluation_reports": {},
        "stock_correlation_distribution_reports": {},
        "correlation_core_index_definitions": {},
        "correlation_core_index_rebalances": {},
        "correlation_core_index_constituent_frames": {},
        "correlation_core_index_level_frames": {},
        "cloudridge_beta_index_definitions": {},
        "cloudridge_beta_index_strength_scans": {},
        "cloudridge_beta_index_rebalances": {},
        "cloudridge_beta_index_constituent_frames": {},
        "cloudridge_beta_index_level_frames": {},
        "correlation_threshold_pool_index_definitions": {},
        "correlation_threshold_pool_index_threshold_scans": {},
        "correlation_threshold_pool_index_rebalances": {},
        "correlation_threshold_pool_index_constituent_frames": {},
        "correlation_threshold_pool_index_level_frames": {},
        "review_sessions": {},
        "candidate_card_snapshots": {},
        "feedback_records": {},
        "rerun_requests": {},
        "approval_requests": {},
        "approval_decisions": {},
        "review_assignments": {},
        "events": [],
    }


def _empty_state_with_defaults(raw: Mapping[str, object] | None = None) -> RuntimeState:
    state = deepcopy(_initial_state())
    if raw is None:
        return state

    for key in state:
        value = raw.get(key)
        if key == "events":
            if isinstance(value, list):
                state[key] = [
                    cast(dict[str, object], item)
                    for item in cast(list[object], value)
                    if isinstance(item, dict)
                ]
            continue
        if isinstance(value, dict):
            state[key] = {
                str(record_id): cast(dict[str, object], record)
                for record_id, record in value.items()
                if isinstance(record, dict)
            }
    return state


class RuntimeStateStore:
    def __init__(
        self,
        authority_path_factory: Callable[[], Path],
        snapshot_path_factory: Callable[[], Path],
    ):
        self._authority_path_factory = authority_path_factory
        self._snapshot_path_factory = snapshot_path_factory

    @property
    def _authority_path(self) -> Path:
        authority_path = self._authority_path_factory()
        authority_path.parent.mkdir(parents=True, exist_ok=True)
        return authority_path

    @property
    def _snapshot_path(self) -> Path:
        snapshot_path = self._snapshot_path_factory()
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        return snapshot_path

    @property
    def authority_path(self) -> Path:
        return self._authority_path

    @property
    def state_path(self) -> Path:
        """Compatibility snapshot path used by legacy scripts and tests."""
        return self._snapshot_path

    @property
    def backend_name(self) -> str:
        return "sqlite"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._authority_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_state_entries (
                entry_no INTEGER PRIMARY KEY AUTOINCREMENT,
                collection TEXT NOT NULL,
                record_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE(collection, record_id)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_runtime_state_entries_collection
            ON runtime_state_entries (collection, entry_no)
            """
        )
        connection.commit()

    def _database_is_empty(self, connection: sqlite3.Connection) -> bool:
        row = connection.execute(
            "SELECT COUNT(1) AS count FROM runtime_state_entries"
        ).fetchone()
        if row is None:
            return True
        return int(row["count"]) == 0

    def _load_from_connection(self, connection: sqlite3.Connection) -> RuntimeState:
        state = deepcopy(_initial_state())
        rows = connection.execute(
            """
            SELECT collection, record_id, payload_json
            FROM runtime_state_entries
            ORDER BY entry_no
            """
        ).fetchall()
        for row in rows:
            payload = json.loads(str(row["payload_json"]))
            if not isinstance(payload, dict):
                continue
            collection = str(row["collection"])
            if collection == "events":
                state["events"].append(cast(dict[str, object], payload))
                continue
            if collection == "auth_tokens":
                collection = "tokens"
            if collection not in state:
                continue
            state[collection][str(row["record_id"])] = cast(dict[str, object], payload)
        return state

    def _write_state_to_connection(
        self, connection: sqlite3.Connection, state: Mapping[str, object]
    ) -> None:
        normalized_state = _empty_state_with_defaults(cast(Mapping[str, object], state))
        for collection, records in normalized_state.items():
            if collection == "events":
                event_records = cast(list[dict[str, object]], records)
                for index, record in enumerate(event_records):
                    record_id = str(record.get("event_id") or f"event-{index}")
                    connection.execute(
                        """
                        INSERT INTO runtime_state_entries (
                            collection,
                            record_id,
                            payload_json
                        ) VALUES (?, ?, ?)
                        """,
                        (collection, record_id, json.dumps(record, sort_keys=True)),
                    )
                continue

            collection_records = cast(dict[str, dict[str, object]], records)
            for record_id, record in collection_records.items():
                connection.execute(
                    """
                    INSERT INTO runtime_state_entries (
                        collection,
                        record_id,
                        payload_json
                    ) VALUES (?, ?, ?)
                    """,
                    (collection, record_id, json.dumps(record, sort_keys=True)),
                )

    def _write_snapshot(self, state: RuntimeState) -> None:
        _ = self._snapshot_path.write_text(
            json.dumps(state, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _relocate_storage_uris(
        self,
        state: RuntimeState,
        source_data_home: Path,
        target_data_home: Path,
    ) -> RuntimeState:
        if source_data_home == target_data_home:
            return state

        source_artifacts = source_data_home / "artifacts"
        target_artifacts = target_data_home / "artifacts"

        for artifact in state["artifacts"].values():
            storage_uri = artifact.get("storage_uri")
            if not isinstance(storage_uri, str):
                continue
            if is_http_storage_uri(storage_uri):
                continue
            resolved_path = resolve_local_storage_path(
                storage_uri,
                base_dir=source_data_home,
            )
            try:
                relative_path = resolved_path.relative_to(source_artifacts)
            except ValueError:
                continue
            artifact["storage_uri"] = to_portable_storage_uri(
                target_artifacts / relative_path
            )

        for event in state["events"]:
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            storage_uri = payload.get("storage_uri")
            if not isinstance(storage_uri, str):
                continue
            if is_http_storage_uri(storage_uri):
                continue
            resolved_path = resolve_local_storage_path(
                storage_uri,
                base_dir=source_data_home,
            )
            try:
                relative_path = resolved_path.relative_to(source_artifacts)
            except ValueError:
                continue
            payload["storage_uri"] = to_portable_storage_uri(
                target_artifacts / relative_path
            )

        return state

    def _load_snapshot(self) -> RuntimeState | None:
        if not self._snapshot_path.exists():
            return None
        raw = json.loads(self._snapshot_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        return _empty_state_with_defaults(cast(dict[str, object], raw))

    def _ensure_initialized(self) -> None:
        authority_exists = self._authority_path.exists()
        snapshot_state = self._load_snapshot() if not authority_exists else None
        with closing(self._connect()) as connection:
            self._initialize_schema(connection)
            if snapshot_state is not None and self._database_is_empty(connection):
                self._write_state_to_connection(connection, snapshot_state)
                connection.commit()

            if self._database_is_empty(connection):
                self._write_snapshot(_initial_state())
            elif not self._snapshot_path.exists():
                self._write_snapshot(self._load_from_connection(connection))

    def load(self) -> RuntimeState:
        self._ensure_initialized()
        with closing(self._connect()) as connection:
            return self._load_from_connection(connection)

    def save(self, state: RuntimeState) -> None:
        self._ensure_initialized()
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM runtime_state_entries")
            self._write_state_to_connection(connection, state)
            connection.commit()
        self._write_snapshot(_empty_state_with_defaults(state))

    def reset(self) -> None:
        artifacts_dir = get_artifacts_dir()
        staging_dir = get_staging_dir()
        if artifacts_dir.exists():
            shutil.rmtree(artifacts_dir)
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        staging_dir.mkdir(parents=True, exist_ok=True)
        if self._snapshot_path.exists():
            self._snapshot_path.unlink()
        with closing(self._connect()) as connection:
            self._initialize_schema(connection)
            _ = connection.execute("DELETE FROM runtime_state_entries")
            connection.commit()
        self._write_snapshot(_initial_state())

    def upsert(
        self, collection: str, record_id: str, record: Mapping[str, object]
    ) -> None:
        self._ensure_initialized()
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO runtime_state_entries (collection, record_id, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(collection, record_id)
                DO UPDATE SET payload_json=excluded.payload_json
                """,
                (collection, record_id, json.dumps(dict(record), sort_keys=True)),
            )
            connection.commit()
            snapshot = self._load_from_connection(connection)
        self._write_snapshot(snapshot)

    def append_event(self, record: Mapping[str, object]) -> None:
        self._ensure_initialized()
        event_record = dict(record)
        record_id = str(event_record.get("event_id") or uuid.uuid4())
        event_record["event_id"] = record_id
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO runtime_state_entries (collection, record_id, payload_json)
                VALUES (?, ?, ?)
                """,
                ("events", record_id, json.dumps(event_record, sort_keys=True)),
            )
            connection.commit()
            snapshot = self._load_from_connection(connection)
        self._write_snapshot(snapshot)

    def list_artifacts_for_run(self, run_id: str) -> list[Record]:
        artifacts: list[Record] = []
        self._ensure_initialized()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM runtime_state_entries
                WHERE collection = 'artifacts'
                ORDER BY entry_no
                """
            ).fetchall()
        for row in rows:
            payload = json.loads(str(row["payload_json"]))
            if isinstance(payload, dict) and payload.get("run_id") == run_id:
                artifacts.append(cast(dict[str, object], payload))
        return artifacts

    def backup_to(self, destination: Path) -> Path:
        self._ensure_initialized()
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._authority_path, destination / self._authority_path.name)
        shutil.copy2(self._snapshot_path, destination / self._snapshot_path.name)
        artifacts_dir = get_artifacts_dir()
        if artifacts_dir.exists():
            shutil.copytree(artifacts_dir, destination / "artifacts")
        manifest = {
            "report_type": "runtime_state_backup",
            "backend": self.backend_name,
            "created_at": dt.datetime.now(dt.UTC).isoformat(),
            "data_home": str(self._authority_path.parent),
            "authority_file": self._authority_path.name,
            "snapshot_file": self._snapshot_path.name,
        }
        _ = (destination / "backup_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return destination

    def restore_from(self, source: Path) -> Path:
        if not source.exists():
            raise FileNotFoundError(source)
        if not source.is_dir():
            raise ValueError("Runtime state restore source must be a backup directory")

        manifest_path = source / "backup_manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Backup manifest is invalid")

        authority_file = str(manifest.get("authority_file", self._authority_path.name))
        snapshot_file = str(manifest.get("snapshot_file", self._snapshot_path.name))
        source_home_raw = manifest.get("data_home", self._authority_path.parent)
        source_data_home = Path(str(source_home_raw))

        authority_source = source / authority_file
        snapshot_source = source / snapshot_file
        if not authority_source.exists():
            raise FileNotFoundError(authority_source)

        self._authority_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(authority_source, self._authority_path)
        if snapshot_source.exists():
            shutil.copy2(snapshot_source, self._snapshot_path)

        artifacts_source = source / "artifacts"
        artifacts_target = get_artifacts_dir()
        if artifacts_target.exists():
            shutil.rmtree(artifacts_target)
        if artifacts_source.exists():
            shutil.copytree(artifacts_source, artifacts_target)
        else:
            artifacts_target.mkdir(parents=True, exist_ok=True)

        with closing(self._connect()) as connection:
            self._initialize_schema(connection)
            restored_state = self._load_from_connection(connection)
        relocated_state = self._relocate_storage_uris(
            restored_state,
            source_data_home,
            self._authority_path.parent,
        )
        self.save(relocated_state)
        return self._authority_path


runtime_state_store = RuntimeStateStore(
    get_runtime_database_path,
    get_runtime_snapshot_path,
)
