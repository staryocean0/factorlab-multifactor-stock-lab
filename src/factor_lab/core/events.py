"""Event envelope and types."""

import uuid
from datetime import UTC, datetime
from typing import Any


class EventEnvelope:
    """Standard event envelope for all domain events."""

    def __init__(
        self,
        event_type: str,
        payload: dict[str, Any],
        event_id: str | None = None,
        run_id: str | None = None,
        job_id: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        sequence_no: int | None = None,
        timestamp: datetime | None = None,
    ):
        self.event_id = event_id or str(uuid.uuid4())
        self.event_type = event_type
        self.payload = payload
        self.run_id = run_id
        self.job_id = job_id
        self.correlation_id = correlation_id
        self.causation_id = causation_id
        self.sequence_no = sequence_no
        self.timestamp = timestamp or datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        timestamp = self.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        timestamp_text = timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "run_id": self.run_id,
            "job_id": self.job_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "sequence_no": self.sequence_no,
            "timestamp": timestamp_text,
        }


class DomainEvent:
    """Base class for domain events."""

    def __init__(self, event_type: str, **kwargs):
        self.envelope = EventEnvelope(event_type=event_type, payload=kwargs)

    def to_dict(self) -> dict[str, Any]:
        return self.envelope.to_dict()
