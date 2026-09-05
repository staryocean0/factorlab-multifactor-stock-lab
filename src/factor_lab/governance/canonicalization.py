"""Shared canonical JSON and SHA-256 primitives for governance contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping


def canonical_json(payload: Mapping[str, object]) -> str:
    """Return the frozen ``factorlab_canonical_json@1`` representation."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def canonical_digest(payload: Mapping[str, object]) -> str:
    """Return a lowercase full-64 SHA-256 digest of canonical JSON."""

    encoded = canonical_json(payload).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


__all__ = ["canonical_digest", "canonical_json"]
