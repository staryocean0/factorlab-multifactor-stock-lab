"""State machine services for Run, Job, and Artifact lifecycles."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


class ArtifactPublishState(StrEnum):
    STAGING = "staging"
    VALIDATED = "validated"
    PUBLISHED = "published"
    FAILED = "failed"


# State transition definitions
RUN_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.PENDING: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.RUNNING: {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED},
    RunStatus.COMPLETED: set(),  # Terminal state
    RunStatus.FAILED: set(),  # Terminal state
    RunStatus.CANCELLED: set(),  # Terminal state
}

JOB_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.RUNNING: {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLING},
    JobStatus.CANCELLING: {JobStatus.CANCELLED, JobStatus.SUCCEEDED, JobStatus.FAILED},
    JobStatus.SUCCEEDED: set(),  # Terminal state
    JobStatus.FAILED: set(),  # Terminal state
    JobStatus.CANCELLED: set(),  # Terminal state
}

ARTIFACT_TRANSITIONS: dict[ArtifactPublishState, set[ArtifactPublishState]] = {
    ArtifactPublishState.STAGING: {
        ArtifactPublishState.VALIDATED,
        ArtifactPublishState.FAILED,
    },
    ArtifactPublishState.VALIDATED: {
        ArtifactPublishState.PUBLISHED,
        ArtifactPublishState.FAILED,
    },
    ArtifactPublishState.PUBLISHED: set(),  # Terminal state - immutable
    ArtifactPublishState.FAILED: set(),  # Terminal state
}


@dataclass
class StateMachineContext:
    """Context for state machine transitions."""

    run_id: str
    principal_id: str
    correlation_id: str | None = None


class RunStateMachine:
    """State machine for Run lifecycle."""

    # Required artifacts for each run type to reach completed state
    REQUIRED_ARTIFACTS: dict[str, set[str]] = {
        "dataset_publish": {
            "dataset_manifest",
            "data_quality_report",
        },
        "factor_evaluation": {
            "factor_frame",
            "eval_metrics_table",
            "eval_report",
            "run_record_snapshot",
        },
        "factor_mining": {
            "mining_search_plan",
            "generated_factor_manifest",
            "mining_leaderboard",
            "search_path_report",
            "redundancy_report",
            "run_record_snapshot",
        },
        "portfolio_construction": {
            "signal_frame",
            "weights_frame",
            "constraint_diagnostic",
            "run_record_snapshot",
        },
        "backtest": {
            "assumption_snapshot",
            "backtest_result",
            "backtest_report",
            "trades_summary",
            "run_record_snapshot",
        },
        "ml_training": {
            "prediction_frame",
            "training_metrics",
            "model_card",
            "baseline_comparison_report",
            "run_record_snapshot",
        },
    }

    @classmethod
    def can_transition(cls, current: RunStatus, target: RunStatus) -> bool:
        """Check if state transition is valid."""
        return target in RUN_TRANSITIONS.get(current, set())

    @classmethod
    def transition(
        cls, current: RunStatus, target: RunStatus, context: StateMachineContext
    ) -> RunStatus:
        """Perform state transition."""
        if not cls.can_transition(current, target):
            raise ValueError(f"Invalid transition from {current} to {target}")
        return target

    @classmethod
    def is_terminal(cls, status: RunStatus) -> bool:
        """Check if state is terminal."""
        return status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}

    @classmethod
    def can_complete(cls, run_type: str, published_artifacts: set[str]) -> bool:
        """Check if run can be completed based on required artifacts."""
        required = cls.REQUIRED_ARTIFACTS.get(run_type, set())
        return required.issubset(published_artifacts)

    @classmethod
    def get_missing_artifacts(
        cls, run_type: str, published_artifacts: set[str]
    ) -> set[str]:
        """Get list of missing required artifacts."""
        required = cls.REQUIRED_ARTIFACTS.get(run_type, set())
        return required - published_artifacts


class JobStateMachine:
    """State machine for Job lifecycle."""

    @classmethod
    def can_transition(cls, current: JobStatus, target: JobStatus) -> bool:
        """Check if state transition is valid."""
        return target in JOB_TRANSITIONS.get(current, set())

    @classmethod
    def transition(
        cls, current: JobStatus, target: JobStatus, context: StateMachineContext
    ) -> JobStatus:
        """Perform state transition."""
        if not cls.can_transition(current, target):
            raise ValueError(f"Invalid transition from {current} to {target}")
        return target

    @classmethod
    def is_terminal(cls, status: JobStatus) -> bool:
        """Check if state is terminal."""
        return status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}


class ArtifactStateMachine:
    """State machine for Artifact publish lifecycle."""

    @classmethod
    def can_transition(
        cls, current: ArtifactPublishState, target: ArtifactPublishState
    ) -> bool:
        """Check if state transition is valid."""
        return target in ARTIFACT_TRANSITIONS.get(current, set())

    @classmethod
    def transition(
        cls,
        current: ArtifactPublishState,
        target: ArtifactPublishState,
        context: StateMachineContext,
    ) -> ArtifactPublishState:
        """Perform state transition."""
        if not cls.can_transition(current, target):
            raise ValueError(f"Invalid transition from {current} to {target}")

        # Special handling: PUBLISHED is immutable - no going back
        if (
            current == ArtifactPublishState.PUBLISHED
            and target != ArtifactPublishState.PUBLISHED
        ):
            raise ValueError(
                "Cannot transition away from PUBLISHED state - artifacts are immutable"
            )

        return target

    @classmethod
    def is_terminal(cls, state: ArtifactPublishState) -> bool:
        """Check if state is terminal."""
        return state in {ArtifactPublishState.PUBLISHED, ArtifactPublishState.FAILED}

    @classmethod
    def is_published(cls, state: ArtifactPublishState) -> bool:
        """Check if artifact is published."""
        return state == ArtifactPublishState.PUBLISHED
