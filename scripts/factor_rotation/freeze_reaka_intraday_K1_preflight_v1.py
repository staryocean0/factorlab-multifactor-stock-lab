#!/usr/bin/env python3
"""Freeze the result-free P6.3 intraday K1/r0 preflight contract."""

from __future__ import annotations

import json
from pathlib import Path

from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    CAPACITY_ROOTS,
    CLOCKS,
    FEATURE_DIM,
    HORIZON_DAYS,
    LR_GRID,
    SCHEMA_ID,
    SEQUENCE_POINTS,
    file_digest,
    read_json,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
ISSUE_REF = "bd://fl-eginj.3"
P62_ACCEPTANCE = ROOT / "docs/ops/evidence/reaka_intraday_orthogonal_OT_v1_20260831/controller_acceptance.json"
P5_ACCEPTANCE = ROOT / "docs/ops/evidence/reaka_framework_content_adapter_infrastructure_v1_20260831/controller_acceptance.json"
PARAMETER_CATALOG = ROOT / "docs/ops/reaka_paper_parameter_catalog@2.0.json"
P62_OUTPUT = ROOT / "output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020"
P61_OUTPUT = ROOT / "output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020"
CONTRACT = ROOT / "docs/ops/reaka_intraday_K1_preflight@1.0.json"
SUCCESSION = ROOT / "docs/ops/reaka_controller_succession_audit@148.0.json"
GOVERNANCE = ROOT / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831/parameter_governance"
INCIDENT = ROOT / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831/pre_contract_manifest_path_incident.json"
BACKEND_ENVIRONMENT_INCIDENT = (
    ROOT / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831/preclose_wrong_python_backend_incident.json"
)
ROCM_TRAINING_MODE_INCIDENT = (
    ROOT / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831/preclose_rocm_rnn_training_mode_incident.json"
)
COMPATIBILITY_SCHEMA_INCIDENT = (
    ROOT / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831/preclose_compatibility_schema_omission_incident.json"
)
STATIC_TYPE_GATE_INCIDENT = ROOT / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831/postclose_static_type_gate_incident.json"
BACKEND_TIMING_STABILITY_INCIDENT = (
    ROOT / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831/preclose_backend_timing_instability_incident.json"
)
SOURCE_PATHS = (
    "docs/ops/reaka_intraday_K1_preflight_whitepaper.md",
    "docs/user/reaka_intraday_K1_preflight_workflow.md",
    "src/factor_lab/factor_rotation/reaka_intraday_k1_preflight_v1.py",
    "scripts/factor_rotation/freeze_reaka_intraday_K1_preflight_v1.py",
    "scripts/factor_rotation/materialize_reaka_intraday_K1_input_v1.py",
    "scripts/factor_rotation/run_reaka_intraday_K1_preflight_v1.py",
    "scripts/factor_rotation/validate_reaka_intraday_K1_preflight_v1.py",
    "scripts/factor_rotation/close_reaka_intraday_K1_preflight_v1.py",
    "tests/unit/test_reaka_intraday_k1_preflight_v1.py",
)


def main() -> None:
    acceptance = read_json(P62_ACCEPTANCE)
    p5 = read_json(P5_ACCEPTANCE)
    catalog = read_json(PARAMETER_CATALOG)
    incident = write_json(
        INCIDENT,
        {
            "schema_id": "factorlab.reaka_intraday_K1_pre_contract_incident@1.0",
            "status": "archived_repaired_before_contract_freeze",
            "trigger": "P6_2_clock_root_has_no_top_level_manifest",
            "repair": "bind_each_actual_OT1_OT2_OT3_manifest_per_tree_and_clock",
            "parameter_governance_drafts_written_before_failure": True,
            "contract_written": False,
            "input_store_written": False,
            "scientific_result_written": False,
            "formal_training_run": False,
            "production_authority": False,
        },
    )
    workflow = write_json(
        GOVERNANCE / "workflow_gate.json",
        {
            "schema_id": "factorlab.reaka_intraday_K1_parameter_workflow_gate@1.0",
            "status": "passed_for_result_free_P6_3_preflight",
            "P6_2_acceptance_digest": acceptance["canonical_digest"],
            "P5_framework_acceptance_digest": p5["canonical_digest"],
            "parameter_catalog_digest": catalog["canonical_digest"],
            "parameter_governance_whitepaper_digest": file_digest(ROOT / "docs/ops/reaka_paper_parameter_governance_whitepaper.md"),
            "succession_whitepaper_digest": file_digest(ROOT / "docs/ops/reaka_controller_succession_audit_whitepaper.md"),
            "historical_parameter_override_allowed": False,
            "formal_training_allowed": False,
            "production_authority": False,
        },
    )
    financial = write_json(
        GOVERNANCE / "financial_alignment_gate.json",
        {
            "schema_id": "factorlab.reaka_intraday_K1_financial_alignment_gate@1.0",
            "status": "passed_for_mathematical_preflight_only",
            "user_instruction": "Codex_owns_mathematical_choices_user_retains_financial_decisions",
            "financial_task_identity_changed": False,
            "decision_and_rebalance_clocks": list(CLOCKS),
            "next_open_execution_allowed": False,
            "strategy_economics_preapproved": False,
            "formal_training_allowed": False,
            "production_authority": False,
        },
    )
    root_scope = write_json(
        GOVERNANCE / "root_scope_gate.json",
        {
            "schema_id": "factorlab.reaka_intraday_K1_parameter_root_scope@1.0",
            "status": "passed",
            "active": ["network.hidden_dimension", "optimizer.learning_rate"],
            "fixed": ["operator_count_K1", "residual_identity_r0_exact_zero"],
            "conditional": [],
            "inactive": [
                "selector.gumbel_temperature",
                "residual.denoiser_architecture",
                "residual.time_embedding_dimension",
            ],
            "latent_and_hidden_are_measured_capacity_coordinates": True,
            "historical_root_scope_override_allowed": False,
            "formal_training_allowed": False,
            "production_authority": False,
        },
    )
    inputs: dict[str, object] = {
        "P6_2_acceptance_digest": acceptance["canonical_digest"],
        "P6_1_manifests": {tree: file_digest(P61_OUTPUT / tree / "manifest.json") for tree in ("formal", "isolated")},
        "P6_2_manifests": {
            f"{tree}_{clock}_{stage}": file_digest(P62_OUTPUT / tree / clock / stage / "manifest.json")
            for tree in ("formal", "isolated")
            for clock in ("1430", "1445")
            for stage in ("ot1", "ot2", "ot3")
        },
    }
    contract = write_json(
        CONTRACT,
        {
            "schema_id": SCHEMA_ID,
            "status": "frozen_controller_preflight_execution_authorized",
            "issue_ref": ISSUE_REF,
            "inputs": inputs,
            "pre_contract_manifest_path_incident_digest": incident["canonical_digest"],
            "backend_environment_incident_digest": read_json(BACKEND_ENVIRONMENT_INCIDENT)["canonical_digest"],
            "ROCm_training_mode_incident_digest": read_json(ROCM_TRAINING_MODE_INCIDENT)["canonical_digest"],
            "compatibility_schema_incident_digest": read_json(COMPATIBILITY_SCHEMA_INCIDENT)["canonical_digest"],
            "static_type_gate_incident_digest": read_json(STATIC_TYPE_GATE_INCIDENT)["canonical_digest"],
            "backend_timing_stability_incident_digest": read_json(BACKEND_TIMING_STABILITY_INCIDENT)["canonical_digest"],
            "parameter_governance": {
                "workflow_gate_digest": workflow["canonical_digest"],
                "financial_alignment_gate_digest": financial["canonical_digest"],
                "root_scope_gate_digest": root_scope["canonical_digest"],
            },
            "decision_clocks": list(CLOCKS),
            "frequency_signature": "D5-H20-R5",
            "history_horizon_days": HORIZON_DAYS,
            "future_target_horizon_days": HORIZON_DAYS,
            "sequence_points": SEQUENCE_POINTS,
            "window_days": HORIZON_DAYS * SEQUENCE_POINTS,
            "operator_count": 1,
            "residual_identity": "r0_exact_zero",
            "feature_dim": FEATURE_DIM,
            "feature_blocks": {
                "selected_state": 14,
                "state_mask": 14,
                "stock_factor_exposure": 14,
                "exposure_reliability": 14,
                "exposure_mask": 14,
                "exposure_age_fraction": 1,
            },
            "forbidden_feature_blocks": ["price_volume", "LAT", "oracle", "future_target"],
            "inference_universe": "history_epsilon_complete_and_current_exposure_support_only",
            "target_may_filter_inference": False,
            "D5_phase_anchor": "2008-12-01",
            "fit_prefix_end_year": 2016,
            "capacity_roots": [{"latent_dimension": d, "hidden_dimension": h} for d, h in CAPACITY_ROOTS],
            "capacity_pruning_rule": "latent_dimension_le_measured_r_eff_with_d8_floor",
            "learning_rate_grid": list(LR_GRID),
            "learning_rate_rule": "largest_healthy_before_first_unhealthy_right_censor_blocks",
            "learning_rate_steps": 4,
            "backend_rule": "ROCm_only_if_numerical_parity_and_median_speedup_at_least_1p10_else_CPU",
            "backend_timing_blocks": 5,
            "backend_repetitions_per_block": 4,
            "minimum_rocm_speedup": 1.10,
            "backend_score_parity_max_abs": 0.0001,
            "backend_score_parity_min_spearman": 0.999999,
            "parameter_surface_count": 22,
            "user_math_inputs_required": [],
            "data_usage": {
                "2007_2008": "warmup_only",
                "2009_2020": "consumed_development_material",
                "post_2020_rows_allowed": 0,
                "fresh_oos": False,
            },
            "formal_isolated_byte_replay_required": True,
            "source_closure": {relative: file_digest(ROOT / relative) for relative in SOURCE_PATHS},
            "input_materialization_allowed": True,
            "compatibility_preflight_allowed": True,
            "LR_gradient_preflight_allowed": True,
            "CPU_ROCm_preflight_allowed": True,
            "formal_training_allowed": False,
            "score_materialization_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    succession = write_json(
        SUCCESSION,
        {
            "schema_id": "factorlab.reaka_controller_succession_audit@148.0",
            "status": "P6_3_intraday_K1_input_and_preflight_execution_open",
            "issue_ref": ISSUE_REF,
            "contract_digest": contract["canonical_digest"],
            "next_legal_action": "materialize_formal_isolated_inputs_then_run_result_free_preflight",
            "formal_training_allowed": False,
            "score_materialization_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    print(json.dumps({"contract_digest": contract["canonical_digest"], "succession_digest": succession["canonical_digest"]}, indent=2))


if __name__ == "__main__":
    main()
