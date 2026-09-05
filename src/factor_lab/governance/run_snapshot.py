"""Run snapshot for reproducibility."""

import json
from typing import Any


class RunSnapshot:
    """Snapshot of run configuration for reproducibility."""

    def __init__(
        self,
        run_id: str,
        dataset_version: str,
        factor_spec_version: str,
        preprocess_spec_version: str,
        label_spec_version: str,
        protocol_version: str,
        code_version: str,
        env_fingerprint: str,
        seed: int,
        source_family: str = "",
    ):
        self.run_id = run_id
        self.dataset_version = dataset_version
        self.factor_spec_version = factor_spec_version
        self.preprocess_spec_version = preprocess_spec_version
        self.label_spec_version = label_spec_version
        self.protocol_version = protocol_version
        self.code_version = code_version
        self.env_fingerprint = env_fingerprint
        self.seed = seed
        self.source_family = source_family

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "run_id": self.run_id,
            "dataset_version": self.dataset_version,
            "factor_spec_version": self.factor_spec_version,
            "preprocess_spec_version": self.preprocess_spec_version,
            "label_spec_version": self.label_spec_version,
            "protocol_version": self.protocol_version,
            "code_version": self.code_version,
            "env_fingerprint": self.env_fingerprint,
            "seed": self.seed,
            "source_family": self.source_family,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunSnapshot":
        """Create from dictionary."""
        return cls(
            run_id=data["run_id"],
            dataset_version=data["dataset_version"],
            factor_spec_version=data["factor_spec_version"],
            preprocess_spec_version=data.get("preprocess_spec_version", ""),
            label_spec_version=data["label_spec_version"],
            protocol_version=data["protocol_version"],
            code_version=data["code_version"],
            env_fingerprint=data["env_fingerprint"],
            seed=data["seed"],
            source_family=str(data.get("source_family", "")),
        )
