#!/usr/bin/env python3
from __future__ import annotations

from factor_lab.factor_rotation.reaka_v2_stage3_observable_context_v2 import (
    OUTPUT_FILES,
    OUTPUT_ROOT,
    ROOT,
    load_contract,
)
from factor_lab.governance.reaka_multifactor_infrastructure_v1 import (
    SEMANTIC_INVARIANTS,
    canonical_valid,
    file_digest,
    read_json,
    validate_stage_payload,
    write_json,
)

EVIDENCE = ROOT / "docs/ops/evidence/reaka_v2_stage3_observable_context_v2_20260904"


def main() -> int:
    contract = load_contract()
    formal_root = OUTPUT_ROOT / "formal"
    isolated_root = OUTPUT_ROOT / "isolated"
    for name in (*OUTPUT_FILES, "result.json"):
        if file_digest(formal_root / name) != file_digest(isolated_root / name):
            raise ValueError(f"stage3_v2_tree_byte_mismatch:{name}")
    formal = read_json(formal_root / "result.json")
    isolated = read_json(isolated_root / "result.json")
    certificate = read_json(formal_root / "observable_context_support_certificate.json")
    receipt = read_json(formal_root / "measurement_receipt.json")
    for payload in (formal, isolated, certificate, receipt):
        if not canonical_valid(payload):
            raise ValueError("stage3_v2_output_digest_invalid")
    validate_stage_payload("stage3_observable_context_support", certificate)
    if certificate.get("status") != "observable_context_ready_for_stage4":
        raise ValueError("stage3_v2_terminal_status_invalid")
    if certificate.get("operator_decision_out_of_scope") is not True:
        raise ValueError("stage3_v2_operator_scope_not_closed")
    if certificate.get("semantic_invariants") != SEMANTIC_INVARIANTS:
        raise ValueError("stage3_v2_semantic_checksum_invalid")
    temporal = certificate["temporal_cross_sectional_support"]
    episodes = certificate["episodes"]
    transitions = certificate["transitions"]
    if not isinstance(temporal, dict) or temporal.get("temporal_decision_months") != 68:
        raise ValueError("stage3_v2_temporal_month_count_invalid")
    if temporal.get("cross_sectional_rows") != 361628:
        raise ValueError("stage3_v2_cross_sectional_support_invalid")
    if not isinstance(transitions, dict) or transitions != {
        "physical_month_transitions": 67,
        "state_switches": 26,
    }:
        raise ValueError("stage3_v2_transition_summary_invalid")
    if not isinstance(episodes, dict):
        raise ValueError("stage3_v2_episode_summary_invalid")
    by_state = episodes.get("by_state")
    if not isinstance(by_state, dict):
        raise ValueError("stage3_v2_episode_by_state_invalid")
    persistent = {state: int(values["persistent_episode_count"]) for state, values in by_state.items() if isinstance(values, dict)}
    if persistent != {"up": 1, "sideways": 9, "down": 1}:
        raise ValueError(f"stage3_v2_persistent_episode_count_invalid:{persistent}")
    if receipt.get("market_data_read") is not False or receipt.get("model_run") is not False:
        raise ValueError("stage3_v2_forbidden_reexecution")
    if formal.get("stage4_execution_allowed") is not False:
        raise ValueError("stage3_v2_stage4_opened")
    write_json(
        EVIDENCE / "validation_report.json",
        {
            "schema_id": "factorlab.reaka_v2_stage3_observable_context_validation@2.0",
            "status": "passed",
            "contract_digest": contract["canonical_digest"],
            "formal_result_digest": formal["canonical_digest"],
            "isolated_result_digest": isolated["canonical_digest"],
            "certificate_digest": certificate["canonical_digest"],
            "formal_isolated_byte_identical_files": [*OUTPUT_FILES, "result.json"],
            "stage3_terminal": "observable_context_ready_for_stage4",
            "operator_decision_out_of_scope": True,
            "stage4_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
