#!/usr/bin/env python3
"""Freeze the result-free P6.2 intraday OT1--OT3 contract."""

from __future__ import annotations

import json
from pathlib import Path

from factor_lab.factor_rotation.reaka_intraday_orthogonal_ot_v1 import (
    CLOCKS,
    ELIGIBLE_TOOL_IDS,
    LOOKBACK,
    MIN_OBSERVATIONS,
    SCHEMA_ID,
    file_digest,
    read_json,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
ISSUE_REF = "bd://fl-eginj.2"
P6_ACCEPTANCE = ROOT / "docs/ops/evidence/reaka_intraday_target_fill_v1_20260831" / "controller_acceptance.json"
CONTRACT = ROOT / "docs/ops/reaka_intraday_orthogonal_OT1_OT3@1.0.json"
SUCCESSION = ROOT / "docs/ops/reaka_controller_succession_audit@146.0.json"
INCIDENT = ROOT / "docs/ops/evidence/reaka_intraday_orthogonal_OT_v1_20260831" / "pre_result_contract_incident.json"
MANIFEST_INCIDENT = ROOT / "docs/ops/evidence/reaka_intraday_orthogonal_OT_v1_20260831" / "pre_OT2_manifest_identity_incident.json"
VALIDATION_INVENTORY_INCIDENT = (
    ROOT / "docs/ops/evidence/reaka_intraday_orthogonal_OT_v1_20260831" / "preclose_validation_inventory_incident.json"
)
P6_ROOT = ROOT / "output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020"
CORE = ROOT / "output/factor-rotation/reaka_condensation_B7_admission_v1_2009_2020" / "extended_weekly_membership.parquet"
CLOUDRIDGE = (
    ROOT / "output/factor-rotation/reaka_opportunity_ledger_v9_inputs_2008_2020" / "cloudridge_beta_weekly_2008_2020.constituents.csv"
)
REGISTRY = ROOT / "docs/ops/factor_condensation_index_registry@1.0.json"
SOURCE_PATHS = (
    "docs/ops/reaka_intraday_orthogonal_OT1_OT3_whitepaper.md",
    "docs/user/reaka_intraday_orthogonal_OT1_OT3_workflow.md",
    "src/factor_lab/factor_rotation/reaka_intraday_orthogonal_ot_v1.py",
    "scripts/factor_rotation/freeze_reaka_intraday_OT1_OT3_v1.py",
    "scripts/factor_rotation/run_reaka_intraday_OT1_v1.py",
    "scripts/factor_rotation/build_reaka_intraday_OT2_candidates_v1.py",
    "scripts/factor_rotation/run_reaka_intraday_OT2_annual_session_v1.py",
    "scripts/factor_rotation/finalize_reaka_intraday_OT2_OT3_v1.py",
    "scripts/factor_rotation/validate_reaka_intraday_OT1_OT3_v1.py",
    "scripts/factor_rotation/close_reaka_intraday_OT1_OT3_v1.py",
    "tests/unit/test_reaka_intraday_orthogonal_ot_v1.py",
    "src/factor_lab/factor_rotation/orthogonal_index_timing_transport_ot1_v1.py",
    "src/factor_lab/factor_rotation/orthogonal_factor_timing_state_v1.py",
    "src/factor_lab/factor_rotation/orthogonal_timing_stock_transport_v1.py",
)


def main() -> None:
    p6 = read_json(P6_ACCEPTANCE)
    source_closure = {relative: file_digest(ROOT / relative) for relative in SOURCE_PATHS}
    contract = write_json(
        CONTRACT,
        {
            "schema_id": SCHEMA_ID,
            "status": "frozen_controller_execution_authorized",
            "issue_ref": ISSUE_REF,
            "P6_1_acceptance_digest": p6["canonical_digest"],
            "pre_result_contract_incident_digest": read_json(INCIDENT)["canonical_digest"],
            "pre_OT2_manifest_identity_incident_digest": read_json(MANIFEST_INCIDENT)["canonical_digest"],
            "preclose_validation_inventory_incident_digest": read_json(VALIDATION_INVENTORY_INCIDENT)["canonical_digest"],
            "decision_clocks": list(CLOCKS),
            "fit_end": "strict_t_minus_1",
            "data_usage": {
                "2007_2008": "warmup_only",
                "2009_2020": "consumed_development_material",
                "post_2020_rows_allowed": 0,
                "fresh_oos": False,
            },
            "inputs": {
                "formal_P6_1_manifest": file_digest(P6_ROOT / "formal/manifest.json"),
                "isolated_P6_1_manifest": file_digest(P6_ROOT / "isolated/manifest.json"),
                "cloudridge_membership_digest": file_digest(CLOUDRIDGE),
                "accepted_core_membership_digest": file_digest(CORE),
                "accepted_registry_digest": file_digest(REGISTRY),
            },
            "OT1": {
                "order": [
                    "market",
                    "single_small_minus_large_size",
                    "accepted_dynamic_industries",
                    "stock_idiosyncratic",
                ],
                "history_input": "decision_clock_H20_history_return",
                "future_target": "same_clock_post_bar_fill_H20_return",
                "factor_projection_fit": "history_only_strict_t_minus_1",
                "stock_beta_fit": "120_daily_H20_rows_strict_t_minus_1",
                "lookback_rows": LOOKBACK,
                "minimum_observations": MIN_OBSERVATIONS,
                "stock_beta_cadence": "D5",
                "effective": "same_day_after_1430_or_1445_decision_bar",
                "crossfit_folds": 5,
                "fold_rule": "symbol_position_mod_5",
                "carrier_excludes_entire_stock_fold": True,
                "epsilon_history": "raw_history_minus_prior_fit_factor_mapping",
                "epsilon_future": "raw_future_target_minus_same_frozen_factor_mapping",
            },
            "OT2": {
                "candidate_tools": list(ELIGIBLE_TOOL_IDS),
                "transparent_control": "naked_residual_level_follow_control_v1",
                "state_input": "history_factor_basis_only",
                "evaluation_grid": "D5",
                "evaluation_target": "future_H20_factor_basis_same_clock",
                "annual_metric": "mean_H20_net_per_D5_decision_not_daily_sum",
                "cost_bps_per_D5_state_change": 7.0,
                "years": list(range(2009, 2021)),
                "annual_sessions_sequential_and_digest_chained": True,
                "selection": ("one_tool_or_transparent_fallback_per_family_per_clock"),
                "all_attempts_enter_multiplicity": True,
            },
            "OT3": {
                "output_columns": [
                    "market_timing_transport",
                    "size_timing_transport",
                    "industry_timing_transport",
                ],
                "pre_sum_allowed": False,
                "effective": "same_day_after_decision_bar",
            },
            "formal_isolated_byte_replay_required": True,
            "source_closure": source_closure,
            "OT1_execution_allowed": True,
            "OT2_execution_allowed_after_OT1_pass": True,
            "OT3_execution_allowed_after_OT2_pass": True,
            "model_training_allowed": False,
            "score_materialization_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    succession = write_json(
        SUCCESSION,
        {
            "schema_id": "factorlab.reaka_controller_succession_audit@146.0",
            "status": "P6_2_intraday_OT1_OT3_execution_open",
            "issue_ref": ISSUE_REF,
            "contract_digest": contract["canonical_digest"],
            "next_legal_action": "formal_isolated_OT1_then_12_OT2_years_then_OT3",
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    print(
        json.dumps(
            {
                "contract_digest": contract["canonical_digest"],
                "succession_digest": succession["canonical_digest"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
