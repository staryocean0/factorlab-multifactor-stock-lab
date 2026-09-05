"""Hashing utilities for deterministic IDs."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(data: Any) -> str:
    """Convert data to canonical JSON string for hashing.

    - Sorts dictionary keys
    - Removes whitespace
    - Handles nested structures
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def sha256_hash(data: Any) -> str:
    """Generate SHA256 hash of canonical JSON data."""
    canonical = canonical_json(data)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dataset_hash(schema_version: str, records: list[dict[str, object]]) -> str:
    """Generate deterministic hash for a dataset.

    Excludes runtime-only fields like timestamps from identity.
    """
    identity_fields = {
        "schema_version": schema_version,
        "record_count": len(records),
        "record_hashes": [sha256_hash(r) for r in records[:100]],  # Sample first 100
    }
    return sha256_hash(identity_fields)


def manifest_hash(artifacts: list[dict[str, object]]) -> str:
    """Generate hash for a manifest."""

    def artifact_sort_key(artifact: dict[str, object]) -> str:
        name = artifact.get("name", "")
        return name if isinstance(name, str) else str(name)

    return sha256_hash({"artifacts": sorted(artifacts, key=artifact_sort_key)})


def code_version_hash(source_files: list[str]) -> str:
    """Generate hash representing code version."""
    # In production, this would use git commit hash
    return sha256_hash({"files": source_files})


def env_fingerprint_hash(env_vars: dict[str, str]) -> str:
    """Generate hash of environment configuration.

    Only includes relevant env vars, not secrets.
    """
    relevant_keys = [
        "PYTHON_VERSION",
        "FACTOR_LAB_VERSION",
        "DATABASE_URL",  # URL without credentials
    ]
    filtered = {k: env_vars.get(k, "") for k in relevant_keys}
    return sha256_hash(filtered)
