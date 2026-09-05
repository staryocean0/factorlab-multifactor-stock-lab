# pyright: reportAny=false
"""Helpers for run, job, artifact, and record persistence."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import cast

from factor_lab.core.runtime_state import Record, runtime_state_store
from factor_lab.core.settings import get_artifacts_dir
from factor_lab.core.storage import (
    read_json_storage_uri,
    to_portable_storage_uri,
)
from factor_lab.governance.services.event_store import event_store
from factor_lab.governance.services.state_machine import JobStatus, RunStatus


@dataclass(slots=True)
class ArtifactRecord:
    artifact_id: str
    run_id: str
    artifact_type: str
    artifact_name: str
    publish_state: str
    storage_uri: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class JobRecord:
    job_id: str
    run_id: str
    status: str
    status_uri: str
    job_type: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def get_collection(collection: str) -> dict[str, Record]:
    return cast(dict[str, Record], runtime_state_store.load()[collection])


def get_record(collection: str, record_id: str) -> Record | None:
    return get_collection(collection).get(record_id)


def upsert_record(
    collection: str,
    record_id: str,
    record: Mapping[str, object],
) -> None:
    runtime_state_store.upsert(collection, record_id, record)


def list_run_artifacts(run_id: str) -> list[dict[str, str]]:
    return [
        {key: str(value) for key, value in artifact.items()}
        for artifact in runtime_state_store.list_artifacts_for_run(run_id)
    ]


def get_artifact(artifact_id: str) -> Record | None:
    return get_record("artifacts", artifact_id)


def artifact_payload(artifact: Mapping[str, object]) -> dict[str, object]:
    storage_uri = artifact.get("storage_uri")
    if not isinstance(storage_uri, str):
        return {}
    try:
        raw = read_json_storage_uri(storage_uri, allow_http=False)
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return cast(dict[str, object], raw)


def materialize_artifact(
    run_id: str,
    artifact_type: str,
    payload: Mapping[str, object],
) -> ArtifactRecord:
    artifact_id = str(uuid.uuid4())
    artifact_dir = get_artifacts_dir() / run_id / artifact_type / artifact_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    content_path = artifact_dir / "content.json"
    _ = content_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    artifact = ArtifactRecord(
        artifact_id=artifact_id,
        run_id=run_id,
        artifact_type=artifact_type,
        artifact_name=f"{artifact_type}.json",
        publish_state="published",
        storage_uri=to_portable_storage_uri(content_path),
    )
    upsert_record("artifacts", artifact_id, artifact.to_dict())
    _ = event_store.append(
        event_type="artifact.published",
        payload={
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "storage_uri": artifact.storage_uri,
        },
        run_id=run_id,
    )
    return artifact


def create_run_record(
    *,
    run_type: str,
    principal_id: str,
    details: Mapping[str, object],
    status: RunStatus = RunStatus.PENDING,
) -> dict[str, object]:
    return {
        "run_id": str(uuid.uuid4()),
        "run_type": run_type,
        "status": status,
        "principal_id": principal_id,
        "created_at": utcnow(),
        **dict(details),
    }


def create_job_record(
    *,
    run_id: str,
    job_type: str,
    status: JobStatus = JobStatus.QUEUED,
) -> JobRecord:
    job_id = str(uuid.uuid4())
    return JobRecord(
        job_id=job_id,
        run_id=run_id,
        status=status,
        status_uri=f"/api/v1/jobs/{job_id}",
        job_type=job_type,
        created_at=utcnow(),
    )


def persist_run_and_job(run: Mapping[str, object], job: JobRecord) -> None:
    upsert_record("runs", str(run["run_id"]), run)
    upsert_record("jobs", job.job_id, job.to_dict())


def update_run_status(run_id: str, status: RunStatus) -> None:
    run = get_record("runs", run_id)
    if run is None:
        return
    updated = dict(run)
    updated["status"] = status
    upsert_record("runs", run_id, updated)


def update_job_status(job_id: str, status: JobStatus) -> None:
    job = get_record("jobs", job_id)
    if job is None:
        return
    updated = dict(job)
    updated["status"] = status
    upsert_record("jobs", job_id, updated)


def find_run_snapshot(run_id: str) -> dict[str, object]:
    for artifact in runtime_state_store.list_artifacts_for_run(run_id):
        if artifact.get("artifact_type") == "run_record_snapshot":
            return artifact_payload(artifact)
    return {}


def find_first_artifact_id(run_id: str, artifact_type: str) -> str | None:
    for artifact in runtime_state_store.list_artifacts_for_run(run_id):
        if str(artifact.get("artifact_type")) == artifact_type:
            return str(artifact.get("artifact_id"))
    return None
