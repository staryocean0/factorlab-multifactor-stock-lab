"""Reproduce this frozen first-round rework checkpoint, not live data readiness.

Reads metadata only. Exit 2 means original inputs/contract are missing in the
saved GitHub tree; exit 0 means presence only, never reconstruction acceptance.
Refresh the GitHub snapshot separately after the user's completion notice.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from factor_lab.governance.reaka_foundation_contract import (  # noqa: E402
    canonical_digest, validate_foundation,
)

LEDGER_ROOT = "output/factor-rotation/reaka_current_k1_account_ledgers_v1_2011_2026/formal"
CURRENT = "docs/ops/evidence/reaka_current_k1_account_ledgers_v1_20260902/current.json"


def read(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def main() -> int:
    foundation = validate_foundation(ROOT)
    if foundation["infrastructure_consistency"] != "passed":
        print(json.dumps(foundation, ensure_ascii=False, indent=2))
        return 1
    snapshot = json.loads((HERE / "github_tree_snapshot.json").read_text())
    if snapshot["truncated"] or snapshot["repository"] != "staryocean0/factorlab-multifactor-stock-lab":
        raise ValueError("A complete snapshot of the correct repository is required")
    paths = {entry["path"] for entry in snapshot["entries"] if entry["type"] == "blob"}
    current = read(CURRENT)
    receipt = read(f"{LEDGER_ROOT}/execution_receipt.json")
    result = read(f"{LEDGER_ROOT}/result.json")
    for payload in (current, receipt, result):
        if canonical_digest(payload) != payload["canonical_digest"]:
            raise ValueError("Historical metadata canonical identity drifted")
    if current["result_digest"] != result["canonical_digest"] or receipt["result_digest"] != result["canonical_digest"]:
        raise ValueError("Historical result identity binding differs")
    inputs = [{"path": p, "expected_file_digest": digest, "present_in_snapshot": p in paths}
              for p, digest in sorted(receipt["input_digests"].items())]
    missing_inputs = [row for row in inputs if not row["present_in_snapshot"]]
    missing_sources = [{"path": p, "expected_file_digest": digest}
                       for p, digest in sorted(receipt["source_closure"].items()) if p not in paths]
    contract_present = current["contract_path"] in paths
    missing_daily = [f"data/development/cn_a_qfq_daily/year={year}/{month:02d}.parquet"
                     for year in (2023, 2024) for month in range(1, 13)
                     if f"data/development/cn_a_qfq_daily/year={year}/{month:02d}.parquet" not in paths]
    status = "blocked_at_original_input_and_model_lineage" if missing_inputs or not contract_present else "presence_only_requires_byte_verification"
    source_paths = [CURRENT, f"{LEDGER_ROOT}/execution_receipt.json", f"{LEDGER_ROOT}/result.json",
                    "src/factor_lab/factor_rotation/reaka_intraday_k1_preflight_v1.py",
                    "docs/ops/reaka_foundation_semantics@1.1.json",
                    "docs/ops/reaka_multifactor_current_manifest@1.3.json"]
    payload = {
        "schema_id": "factorlab.reaka_first_round_necessary_rework@1.0",
        "status": status,
        "authorization": "user_requested_necessary_first_round_rework_and_stop_at_data_blocker",
        "replay_scope": "frozen_remote_metadata_and_existing_current_foundation",
        "repository_snapshot_commit": snapshot["commit"],
        "repository_snapshot_tree": snapshot["tree"],
        "foundation_code_head": "3c8c3658a842b327a76523039f30b64240793ba3",
        "foundation_consistency": foundation,
        "incumbent": {
            "strategy_id": result["strategy_id"], "model_identity": result["model_identity"],
            "account_policy_id": result["account_policy_id"], "decision_clocks": result["decision_clocks"],
            "identity_evidence": "mutually_bound_historical_metadata_not_loaded_checkpoint",
            "latent_residual_mode": "r0_no_latent_residual_correction_network",
            "financial_residual_input": "shipped_K1_assembler_reads_epsilon_history_and_targets_epsilon_future",
            "actual_checkpoint_input_binding_verified": False,
        },
        "completed_documentary_rework": [
            "preserve_financial_product_and_three_factor_candidate_identities_without_claiming_revalidated_effectiveness",
            "separate_financial_epsilon_prediction_from_latent_residual_correction_r0",
            "do_not_force_incumbent_retraining_because_unrelated_MLP_or_DDPM_evidence_failed",
            "do_not_substitute_old_d8_K2_material_for_current_d8_h8_K1_r0",
            "realized_attribution_or_positive_selected_return_does_not_establish_incremental_prediction",
            "round2_CloudRidge_context_pairing_is_not_a_mandatory_first_round_retraining_step",
        ],
        "step_ledger": [
            {"step": "R0_financial_and_incumbent_semantics", "status": "documentary_rework_completed"},
            {"step": "R1_original_inputs_contract_and_checkpoint_binding", "status": status,
             "resume_here": True, "earlier_years_only_does_not_resolve_missing_intraday_inputs": True},
            {"step": "R2_PIT_horizon_factor_effectiveness_reverification", "status": "not_executed_dependency_R1",
             "rerun_rule": "only_inputs_or_evidence_affected_by_verified_identity_timing_or_estimand_defect"},
            {"step": "R3_capacity_and_residual_admission", "status": "not_executed_dependency_R1_R2",
             "rerun_rule": "readjudicate_affected_evidence_first_retrain_only_if_necessary_no_guaranteed_K2_or_residual"},
            {"step": "R4_scores_accounts_and_attribution", "status": "not_executed_dependency_upstream",
             "rerun_rule": "reuse_same_identity_scores_and_snapshots_if_verified_new_aggregation_only_when_sufficient"},
        ],
        "required_initial_input_inventory": inputs,
        "missing_initial_input_count": len(missing_inputs),
        "required_ledger_contract": {"path": current["contract_path"], "expected_canonical_digest": current["contract_digest"],
                                     "present_in_snapshot": contract_present},
        "missing_recorded_source_closure": missing_sources,
        "checkpoint_recovery": "No checkpoint path is established by the shipped current receipt; recover original input/fit manifests and their linked checkpoint, frozen configuration and training receipts. A model name or score digest alone is insufficient.",
        "pending_daily_upload_files": missing_daily,
        "daily_presence_is_not_content_or_PIT_verification": True,
        "daily_completion_alone_resolves_current_blocker": False,
        "recovery_inventory_is_initial_not_guaranteed_complete": True,
        "restoration_rule": "verify_expected_bytes_or_register_a_new_causal_rebuild_preserve_original_receipts_do_not_proxy_intraday_with_daily_close",
        "source_file_digests": {p: "sha256:" + hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_paths},
        "snapshot_file_digest": "sha256:" + hashlib.sha256((HERE / "github_tree_snapshot.json").read_bytes()).hexdigest(),
        "replay_script_digest": "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "market_rows_read": 0, "model_fits": 0, "capacity_candidates_tested": 0, "accounts_replayed": 0,
        "old_results_rewritten": False, "new_economic_results": False,
        "data_boundary": "2007_2008_warmup_2009_2025_declared_roles_no_2026_rows",
        "fresh_oos": False, "scientific_acceptance": "not_established", "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 2 if missing_inputs or not contract_present else 0


if __name__ == "__main__":
    raise SystemExit(main())
