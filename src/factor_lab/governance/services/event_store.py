"""Event store for domain events."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from typing import cast

from factor_lab.core.events import EventEnvelope
from factor_lab.core.runtime_state import runtime_state_store


class EventStore:
    """Store for domain events with outbox pattern."""

    def __init__(self):
        self._events: dict[str, list[EventEnvelope]] = {}

    def _connect(self) -> sqlite3.Connection:
        _ = runtime_state_store.load()
        connection = sqlite3.connect(runtime_state_store.authority_path)
        connection.row_factory = sqlite3.Row
        self._initialize_outbox_schema(connection)
        return connection

    def _initialize_outbox_schema(self, connection: sqlite3.Connection) -> None:
        _ = connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_event_outbox (
                event_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                processed INTEGER NOT NULL DEFAULT 0,
                processed_at TEXT,
                last_error TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        _ = connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_runtime_event_outbox_pending
            ON runtime_event_outbox (processed, created_at)
            """
        )
        connection.commit()

    def _event_from_payload(self, payload_json: str) -> EventEnvelope:
        raw_event_object = cast(object, json.loads(payload_json))
        if not isinstance(raw_event_object, dict):
            raise ValueError("Outbox payload is invalid")
        raw_event = cast(dict[str, object], raw_event_object)
        timestamp = raw_event.get("timestamp")
        parsed_timestamp = datetime.now(UTC)
        if isinstance(timestamp, str):
            normalized_timestamp = timestamp.removesuffix("Z")
            parsed_timestamp = datetime.fromisoformat(normalized_timestamp)
            if parsed_timestamp.tzinfo is None:
                parsed_timestamp = parsed_timestamp.replace(tzinfo=UTC)
        raw_payload = raw_event.get("payload", {})
        if isinstance(raw_payload, dict):
            payload = cast(dict[str, object], raw_payload)
        else:
            payload = {}
        run_value = raw_event.get("run_id")
        job_value = raw_event.get("job_id")
        correlation_value = raw_event.get("correlation_id")
        causation_value = raw_event.get("causation_id")
        return EventEnvelope(
            event_id=str(raw_event.get("event_id", "")),
            event_type=str(raw_event.get("event_type", "")),
            payload=payload,
            run_id=str(run_value) if run_value else None,
            job_id=str(job_value) if job_value else None,
            correlation_id=str(correlation_value) if correlation_value else None,
            causation_id=str(causation_value) if causation_value else None,
            sequence_no=int(str(raw_event.get("sequence_no", 0) or 0)),
            timestamp=parsed_timestamp,
        )

    def _persist_outbox_event(self, event: EventEnvelope) -> None:
        event_payload = event.to_dict()
        timestamp_text = str(cast(object, event_payload["timestamp"]))
        with closing(self._connect()) as connection:
            _ = connection.execute(
                """
                INSERT INTO runtime_event_outbox (
                    event_id,
                    payload_json,
                    processed,
                    processed_at,
                    last_error,
                    retry_count,
                    created_at
                ) VALUES (?, ?, 0, NULL, NULL, 0, ?)
                ON CONFLICT(event_id)
                DO UPDATE SET
                    payload_json=excluded.payload_json,
                    processed=0,
                    processed_at=NULL,
                    last_error=NULL
                """,
                (
                    event.event_id,
                    json.dumps(event_payload, sort_keys=True),
                    timestamp_text,
                ),
            )
            connection.commit()

    def append(
        self,
        event_type: str,
        payload: dict[str, object],
        run_id: str | None = None,
        job_id: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> EventEnvelope:
        """Append an event to the store."""
        # Get sequence number for this run
        sequence_no = self._get_next_sequence(run_id)

        event = EventEnvelope(
            event_type=event_type,
            payload=payload,
            run_id=run_id,
            job_id=job_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            sequence_no=sequence_no,
            timestamp=datetime.now(UTC),
        )

        # Store in run-specific list
        if run_id:
            if run_id not in self._events:
                self._events[run_id] = []
            self._events[run_id].append(event)

        runtime_state_store.append_event(event.to_dict())
        self._persist_outbox_event(event)

        return event

    def _events_for_run_from_state(self, run_id: str) -> list[EventEnvelope]:
        state_events = runtime_state_store.load()["events"]
        envelopes: list[EventEnvelope] = []
        for raw_event in state_events:
            if raw_event.get("run_id") != run_id:
                continue
            timestamp = raw_event.get("timestamp")
            parsed_timestamp = datetime.now(UTC)
            if isinstance(timestamp, str):
                normalized_timestamp = timestamp.removesuffix("Z")
                parsed_timestamp = datetime.fromisoformat(normalized_timestamp)
                if parsed_timestamp.tzinfo is None:
                    parsed_timestamp = parsed_timestamp.replace(tzinfo=UTC)
            raw_payload = raw_event.get("payload", {})
            payload_source: dict[str, object]
            payload_source = (
                cast(dict[str, object], raw_payload)
                if isinstance(raw_payload, dict)
                else {}
            )
            payload = payload_source
            run_value = raw_event.get("run_id")
            job_value = raw_event.get("job_id")
            correlation_value = raw_event.get("correlation_id")
            causation_value = raw_event.get("causation_id")
            envelopes.append(
                EventEnvelope(
                    event_id=str(raw_event.get("event_id", "")),
                    event_type=str(raw_event.get("event_type", "")),
                    payload=payload,
                    run_id=str(run_value) if run_value else None,
                    job_id=str(job_value) if job_value else None,
                    correlation_id=(
                        str(correlation_value) if correlation_value else None
                    ),
                    causation_id=str(causation_value) if causation_value else None,
                    sequence_no=int(str(raw_event.get("sequence_no", 0) or 0)),
                    timestamp=parsed_timestamp,
                )
            )
        return sorted(envelopes, key=lambda event: event.sequence_no or 0)

    def _get_next_sequence(self, run_id: str | None) -> int:
        """Get next sequence number for a run."""
        if not run_id:
            return 0
        existing = self._events_for_run_from_state(run_id)
        if not existing:
            return 1
        return max(e.sequence_no or 0 for e in existing) + 1

    def get_events_for_run(self, run_id: str) -> list[EventEnvelope]:
        """Get all events for a run in sequence order."""
        return self._events_for_run_from_state(run_id)

    def get_timeline(self, run_id: str) -> list[dict[str, object]]:
        """Get timeline of events for a run."""
        events = self.get_events_for_run(run_id)
        return [e.to_dict() for e in events]

    def get_outbox_batch(self, limit: int = 100) -> list[EventEnvelope]:
        """Get pending outbox events."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM runtime_event_outbox
                WHERE processed = 0
                ORDER BY created_at, event_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        outbox_rows = cast(list[sqlite3.Row], rows)
        return [
            self._event_from_payload(str(cast(object, row["payload_json"])))
            for row in outbox_rows
        ]

    def mark_outbox_processed(self, event_ids: list[str]) -> None:
        """Mark outbox events as processed."""
        if not event_ids:
            return
        processed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        placeholders = ",".join("?" for _ in event_ids)
        with closing(self._connect()) as connection:
            _ = connection.execute(
                f"""
                UPDATE runtime_event_outbox
                SET processed = 1,
                    processed_at = ?,
                    last_error = NULL
                WHERE event_id IN ({placeholders})
                """,
                (processed_at, *event_ids),
            )
            connection.commit()

    def record_outbox_failure(self, event_id: str, error: str) -> None:
        with closing(self._connect()) as connection:
            _ = connection.execute(
                """
                UPDATE runtime_event_outbox
                SET processed = 0,
                    processed_at = NULL,
                    retry_count = retry_count + 1,
                    last_error = ?
                WHERE event_id = ?
                """,
                (error, event_id),
            )
            connection.commit()

    def pending_outbox_count(self) -> int:
        with closing(self._connect()) as connection:
            row_object = cast(
                sqlite3.Row | None,
                connection.execute(
                    """
                    SELECT COUNT(1) AS count
                    FROM runtime_event_outbox
                    WHERE processed = 0
                    """
                ).fetchone(),
            )
        if row_object is None:
            return 0
        return int(str(cast(object, row_object["count"])))

    def reset(self) -> None:
        self._events.clear()
        with closing(self._connect()) as connection:
            _ = connection.execute("DELETE FROM runtime_event_outbox")
            connection.commit()


# Global event store instance
event_store = EventStore()
