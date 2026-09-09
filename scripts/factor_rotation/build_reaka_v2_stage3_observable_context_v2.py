#!/usr/bin/env python3
from __future__ import annotations

# ruff: noqa: E402
# Retired materializers cannot recreate historical current/evidence authority.
# Keep this check before legacy imports, including optional project dependencies.
import sys as _foundation_sys
from pathlib import Path as _FoundationPath

_FOUNDATION_ROOT = _FoundationPath(__file__).resolve().parents[2]
if str(_FOUNDATION_ROOT / "src") not in _foundation_sys.path:
    _foundation_sys.path.insert(0, str(_FOUNDATION_ROOT / "src"))
from factor_lab.governance.reaka_foundation_contract import (  # noqa: E402
    reject_legacy_entrypoint as _reject_legacy_entrypoint,
)

if __name__ == "__main__":
    _reject_legacy_entrypoint(__file__)

import argparse

from factor_lab.factor_rotation.reaka_v2_stage3_observable_context_v2 import (
    ALLOWED_INPUT_FILES,
    CONTRACT,
    CORRECTION,
    OLD_ROOT,
    OUTPUT_FILES,
    ROOT,
    source_closure,
)
from factor_lab.governance.reaka_multifactor_infrastructure_v1 import (
    SEMANTIC_INVARIANTS,
    canonical_valid,
    file_digest,
    read_json,
    write_json,
)


def main() -> int:
    _reject_legacy_entrypoint(__file__)
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if CONTRACT.exists() and not args.overwrite:
        raise FileExistsError(f"contract_exists:{CONTRACT}")
    correction = read_json(CORRECTION)
    state_machine = read_json(ROOT / "docs/ops/state_factor_research_state_machine@2.0.json")
    manifest = read_json(ROOT / "docs/ops/reaka_multifactor_current_manifest@1.0.json")
    authority = read_json(ROOT / "docs/ops/reaka_strategy_authority_registry@111.0.json")
    succession = read_json(ROOT / "docs/ops/reaka_controller_succession_audit@272.0.json")
    for name, payload in (
        ("correction", correction),
        ("state_machine", state_machine),
        ("manifest", manifest),
        ("authority", authority),
        ("succession", succession),
    ):
        if not canonical_valid(payload):
            raise PermissionError(f"stage3_v2_upstream_digest_invalid:{name}")
    retained = correction["retained_evidence"]
    if not isinstance(retained, dict) or tuple(retained["allowed_files"]) != ALLOWED_INPUT_FILES:
        raise PermissionError("stage3_v2_allowed_measurement_files_invalid")
    input_digests: dict[str, object] = {}
    for tree in ("formal", "isolated"):
        input_digests[tree] = {name: file_digest(OLD_ROOT / tree / name) for name in ALLOWED_INPUT_FILES}
    if input_digests["formal"] != input_digests["isolated"]:
        raise PermissionError("stage3_v2_retained_measurements_tree_mismatch")
    write_json(
        CONTRACT,
        {
            "schema_id": "factorlab.reaka_v2_stage3_observable_context@2.0",
            "status": "result_free_stage3_observable_context_contract_frozen",
            "stage": "stage3_observable_context_support",
            "object": "S_obs",
            "input_mode": "reuse_validated_raw_measurements_without_market_reexecution",
            "allowed_input_files": list(ALLOWED_INPUT_FILES),
            "retained_input_digests": input_digests,
            "upstream": {
                "correction_digest": correction["canonical_digest"],
                "state_machine_digest": state_machine["canonical_digest"],
                "manifest_digest": manifest["canonical_digest"],
                "authority_digest": authority["canonical_digest"],
                "succession_digest": succession["canonical_digest"],
            },
            "required_outputs": [
                "scope",
                "PIT",
                "episodes",
                "transitions",
                "duration_prevalence",
                "temporal_cross_sectional_support",
                "observable_context_support_certificate",
            ],
            "output_inventory": [*OUTPUT_FILES, "result.json"],
            "formal_isolated_byte_identity_required": True,
            "semantic_invariants": SEMANTIC_INVARIANTS,
            "authority": {
                "stage3_execution_allowed": True,
                "stage4_execution_allowed": False,
                "model_training_allowed": False,
                "account_execution_allowed": False,
                "production_authority": False,
            },
            "fresh_oos": False,
            "production_authority": False,
            "source_closure": source_closure(),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
