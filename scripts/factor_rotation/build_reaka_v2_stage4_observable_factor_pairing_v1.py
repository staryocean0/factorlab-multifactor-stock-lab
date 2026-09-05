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

from factor_lab.factor_rotation.reaka_v2_stage4_observable_factor_pairing_v1 import (
    CONTRACT,
    FACTOR_ROOT,
    HYPOTHESES,
    OUTPUT_FILES,
    ROOT,
    STATE_ROOT,
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
    manifest = read_json(ROOT / "docs/ops/reaka_multifactor_current_manifest@1.1.json")
    authority = read_json(ROOT / "docs/ops/reaka_strategy_authority_registry@112.0.json")
    succession = read_json(ROOT / "docs/ops/reaka_controller_succession_audit@273.0.json")
    stage3_contract = read_json(ROOT / "docs/ops/reaka_v2_stage3_observable_context@2.0.json")
    stage3_validation = read_json(ROOT / "docs/ops/evidence/reaka_v2_stage3_observable_context_v2_20260904/validation_report.json")
    for name, payload in (
        ("manifest", manifest),
        ("authority", authority),
        ("succession", succession),
        ("stage3_contract", stage3_contract),
        ("stage3_validation", stage3_validation),
    ):
        if not canonical_valid(payload):
            raise PermissionError(f"stage4_upstream_digest_invalid:{name}")
    if authority.get("next_legal_action") != "user_review_then_freeze_stage4_contract":
        raise PermissionError("stage4_not_current_next_action")
    input_digests: dict[str, object] = {}
    for tree in ("formal", "isolated"):
        input_digests[tree] = {
            "state_months.csv": file_digest(STATE_ROOT / tree / "state_months.csv"),
            "monthly_selector_panel.csv": file_digest(FACTOR_ROOT / tree / "monthly_selector_panel.csv"),
        }
    if input_digests["formal"] != input_digests["isolated"]:
        raise PermissionError("stage4_input_tree_mismatch")
    write_json(
        CONTRACT,
        {
            "schema_id": "factorlab.reaka_v2_stage4_observable_factor_pairing@1.0",
            "status": "result_free_stage4_pairing_contract_frozen",
            "stage": "stage4_observable_context_factor_pairing",
            "objects": ["S_obs", "index_component_contribution", "industry_component_contribution"],
            "factor_result_identity": "V1_selected_holdings_linked_log_component_attribution_consumed_history_only",
            "legacy_same_month_trend_column_allowed": False,
            "state_join": "decision_month_uses_previous_calendar_month_S_obs",
            "hypotheses": [
                item.__dict__
                if hasattr(item, "__dict__")
                else {
                    "hypothesis_id": item.hypothesis_id,
                    "factor": item.factor,
                    "condition": item.condition,
                    "expected_direction": item.expected_direction,
                    "financial_mechanism": item.financial_mechanism,
                }
                for item in HYPOTHESES
            ],
            "excluded_factors": ["size", "other_residual"],
            "multiplicity_family_size": len(HYPOTHESES),
            "statistics": [
                "condition_inside_outside_monthly_lift",
                "factor_active_episode_count",
                "episode_dispersion",
                "annual_dispersion",
                "two_clock_report",
            ],
            "data_usage": {
                "2011_05_2016_12": "development_material_pairing",
                "2017": "development_listing_not_pass_evidence",
                "2018_2025": "consumed_repeat_comparison_no_retune",
                "2026": "unread",
            },
            "financial_hypothesis_receipt": {
                "status": "user_mechanism_declared_before_stage4_results",
                "advisor_interpretation_of_results": "pending",
                "AI_may_sign_financial_verdict": False,
            },
            "upstream": {
                "manifest_digest": manifest["canonical_digest"],
                "authority_digest": authority["canonical_digest"],
                "succession_digest": succession["canonical_digest"],
                "stage3_contract_digest": stage3_contract["canonical_digest"],
                "stage3_validation_digest": stage3_validation["canonical_digest"],
            },
            "input_digests": input_digests,
            "output_inventory": [*OUTPUT_FILES, "result.json"],
            "formal_isolated_byte_identity_required": True,
            "semantic_invariants": SEMANTIC_INVARIANTS,
            "authority": {
                "stage4_execution_allowed": True,
                "stage5_execution_allowed": False,
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
