"""Fixed public broker adapter for LIQ-01-SUPPORT-01.

This module reuses the reviewed LIQ research transport/isolation/writeback code,
but replaces its allowlist with one diagnostic-only profile. Private source
remains in the private repository at an immutable commit; no private bytes are
stored in this public repository.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location("_factorlab_research_broker", HERE / "research_broker.py")
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

_policy_spec = importlib.util.spec_from_file_location(
    "_factorlab_support_profile_contract", HERE / "support_profile_contract.py"
)
policy = importlib.util.module_from_spec(_policy_spec)
_policy_spec.loader.exec_module(policy)

PROFILE_NAME = policy.PROFILE_NAME
SOURCE_PATHS = tuple(sorted(policy.SOURCE_PATHS))
MANIFEST_PATH = policy.MANIFEST_PATH
INPUT_FILES = tuple(sorted(policy.INPUT_FILES))
COMMAND = list(policy.COMMAND)
VERIFY_COMMAND = list(policy.VERIFY_COMMAND)
VERIFICATION_TIMEOUT_SECONDS = 300
VALIDATE_HOST_TIMEOUT_SECONDS = 330

# Keep transport, isolation, private result publication, release identity and
# resource ceilings from the already reviewed research broker. Only the fixed
# source/command allowlist and validator timeout differ for this diagnostic.
base.PROFILE_NAME = PROFILE_NAME
base.SOURCE_PATHS = SOURCE_PATHS
base.MANIFEST_PATH = MANIFEST_PATH
base.INPUT_FILES = INPUT_FILES
base.COMMAND = COMMAND
base.VERIFY_COMMAND = VERIFY_COMMAND
base.VERIFICATION_TIMEOUT_SECONDS = VERIFICATION_TIMEOUT_SECONDS
base.VALIDATE_HOST_TIMEOUT_SECONDS = VALIDATE_HOST_TIMEOUT_SECONDS

_original_validate_profile = base.validate_profile


def validate_profile(value):
    """Apply both transport constraints and the diagnostic-specific contract."""
    _original_validate_profile(value)
    policy.validate_profile(value)
    return value


base.validate_profile = validate_profile


def run():
    base.run()


if __name__ == "__main__":
    run()
