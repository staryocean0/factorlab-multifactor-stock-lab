#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from factor_lab.governance.reaka_multifactor_infrastructure_v1 import (
    CURRENT_MANIFEST_PATH,
    ONTOLOGY_PATH,
    ROLLBACK_V2_PATH,
    SEMANTIC_INVARIANTS,
    SIX_SURFACE_PATH,
    STAGE3_CORRECTION_PATH,
    STAGE3_FORBIDDEN_KEYS,
    STATE_MACHINE_V2_PATH,
    file_digest,
    read_json,
    source_closure,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]


def _object(formation: str, owner: str, stage: str, may_decide: list[str], may_not_decide: list[str]) -> dict[str, object]:
    return {
        "formation": formation,
        "owner": owner,
        "stage": stage,
        "may_decide": may_decide,
        "may_not_decide": may_not_decide,
    }


def _normative_entry(role: str, relative: str, scope: str, *, required: bool = False) -> dict[str, object]:
    path = ROOT / relative
    entry: dict[str, object] = {
        "role": role,
        "path": relative,
        "scope": scope,
        "required_first_read": required,
        "file_digest": file_digest(path),
    }
    if path.suffix == ".json":
        entry["canonical_digest"] = read_json(path)["canonical_digest"]
    return entry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    targets = (
        ONTOLOGY_PATH,
        SIX_SURFACE_PATH,
        STATE_MACHINE_V2_PATH,
        ROLLBACK_V2_PATH,
        STAGE3_CORRECTION_PATH,
        CURRENT_MANIFEST_PATH,
    )
    if not args.overwrite and any(path.exists() for path in targets):
        raise FileExistsError("reaka_multifactor_infrastructure_contract_exists")
    closure = source_closure()
    ontology = write_json(
        ONTOLOGY_PATH,
        {
            "schema_id": "factorlab.reaka_multifactor_semantic_ontology@1.0",
            "status": "current_normative_semantic_root",
            "objects": {
                "product_target": _object("user_financial_freeze", "user", "stage0", ["financial_question"], ["model_parameters"]),
                "factor": _object("PIT_factor_research", "project_and_data", "stage1_stage2", ["input_candidate"], ["operator_label"]),
                "S_obs": _object(
                    "user_and_project_PIT_input",
                    "user_and_project",
                    "stage3_stage5",
                    ["observable_condition_identity"],
                    ["K_i", "N_effective"],
                ),
                "S_factor": _object(
                    "conditional_factor_evidence", "research_evidence", "stage4", ["conditional_mechanism"], ["latent_state_name"]
                ),
                "H_x_H_y": _object("learned_by_encoder", "model", "stage6", ["latent_input_representation"], ["operator_count"]),
                "Z_S_latent": _object("learned_by_encoder_and_gate", "model", "stage6", ["selector_representation"], ["named_macro_truth"]),
                "K_i": _object("learned_by_model", "model", "stage6_operator_capacity", ["latent_transition_matrix"], ["user_feature"]),
                "N_max": _object(
                    "preregistered_bounded_capacity",
                    "controller",
                    "stage6_operator_capacity",
                    ["candidate_boundary"],
                    ["effective_operator_count"],
                ),
                "N_effective": _object(
                    "post_training_sequential_admission",
                    "model_and_evidence",
                    "stage6_operator_capacity",
                    ["current_task_capacity"],
                    ["eternal_market_state_count"],
                ),
                "residual": _object(
                    "learned_after_operator_chain_stops",
                    "model_and_evidence",
                    "post_operator",
                    ["leftover_dynamics"],
                    ["repair_upstream_failure"],
                ),
                "score": _object("frozen_model_output", "model", "pre_SSA", ["ranking_candidate"], ["account_authority"]),
                "account": _object("score_portfolio_cost_execution", "account_audit", "A0_A7", ["financial_outcome"], ["model_retraining"]),
            },
            "semantic_invariants": SEMANTIC_INVARIANTS,
            "paper_equations": {
                "selector": "a=SelectorNet(Z,H_y)",
                "training_operator": "K_s=sum(alpha_i*K_i)",
                "inference_operator": "K_s=argmax_selector_operator",
                "koopman_step": "Z_hat_next=K_s*Z",
            },
            "fresh_oos": False,
            "production_authority": False,
            "source_closure": closure,
        },
    )
    six_surface = write_json(
        SIX_SURFACE_PATH,
        {
            "schema_id": "factorlab.reaka_multifactor_six_surface_infrastructure@1.0",
            "status": "current_normative_surface_contract",
            "surfaces": {
                "user_document": {
                    "responsibility": "entry_order_commands_stop_points",
                    "forbidden": ["new_math_definition", "scientific_result_authority"],
                },
                "whitepaper": {
                    "responsibility": "financial_math_reasoning_objects_counterexamples",
                    "forbidden": ["mutable_current_pointer"],
                },
                "machine_contract": {"responsibility": "identity_stage_scope_authority_digest", "forbidden": ["ambiguous_untyped_state"]},
                "source_code": {"responsibility": "domain_objects_invariants_fail_closed", "forbidden": ["unmanifested_default_authority"]},
                "tests": {"responsibility": "positive_negative_cross_surface_regressions", "forbidden": ["happy_path_only"]},
                "scripts": {"responsibility": "build_freeze_run_validate_close_publish", "forbidden": ["second_domain_semantics"]},
            },
            "unlisted_default": "historical_or_specialized_no_current_normative_authority",
            "semantic_invariants": SEMANTIC_INVARIANTS,
            "production_authority": False,
            "source_closure": closure,
        },
    )
    state_machine = write_json(
        STATE_MACHINE_V2_PATH,
        {
            "schema_id": "factorlab.state_factor_research_state_machine@2.0",
            "status": "current_stage0_6_semantic_separation",
            "supersedes_current_normative_authority_of": "docs/ops/state_factor_research_state_machine@1.0.json",
            "semantic_invariants": SEMANTIC_INVARIANTS,
            "stages": [
                {"stage": "stage0_product_coordinate_freeze", "object": "product_target", "operator_count_decision_authority": False},
                {"stage": "stage1_factor_effectiveness", "object": "factor", "operator_count_decision_authority": False},
                {"stage": "stage2_factor_three_pathway", "object": "factor", "operator_count_decision_authority": False},
                {
                    "stage": "stage3_observable_context_support",
                    "object": "S_obs",
                    "required_outputs": [
                        "scope",
                        "PIT",
                        "episodes",
                        "transitions",
                        "duration_prevalence",
                        "temporal_cross_sectional_support",
                        "observable_context_support_certificate",
                    ],
                    "forbidden_outputs": sorted(STAGE3_FORBIDDEN_KEYS),
                    "operator_count_decision_authority": False,
                    "example_valid_output": {
                        "observable_context_support_certificate": {
                            "status": "observable_context_ready_for_stage4",
                            "operator_decision_out_of_scope": True,
                        }
                    },
                },
                {
                    "stage": "stage4_observable_context_factor_pairing",
                    "object": "S_obs_x_factor",
                    "operator_count_decision_authority": False,
                },
                {
                    "stage": "stage5_model_input_assembly",
                    "object": "S_obs_to_H_x_gate_interaction",
                    "operator_count_decision_authority": False,
                },
                {
                    "stage": "stage6_model_training_and_operator_capacity",
                    "object": "Z_K_i_N_effective",
                    "operator_count_decision_authority": True,
                    "selection_rule": "K1_then_K2_then_K3_until_failure_or_N_max",
                },
            ],
            "stage3_terminal_states": [
                "observable_context_ready_for_stage4",
                "observable_context_requires_continuous_or_shrunk_pairing",
                "observable_context_diagnostic_only",
                "observable_context_data_blocked",
                "observable_context_financial_review_pending",
            ],
            "stage3_certificate_name": "observable_context_support_certificate",
            "state_learnability_certificate_name_for_current_work": False,
            "fresh_oos": False,
            "production_authority": False,
            "source_closure": closure,
        },
    )
    rollback = write_json(
        ROLLBACK_V2_PATH,
        {
            "schema_id": "factorlab.reaka_prediction_content_rollback@2.0",
            "status": "current_stage_rollback_semantics",
            "state_definition_change_earliest_reopen": "stage3_observable_context_support",
            "stage3_reopen_reason": "observable_input_identity_and_downstream_pairing_invalidated",
            "stage3_operator_count_decision_authority": False,
            "operator_count_selection_stage": "stage6_model_training_and_operator_capacity",
            "old_checkpoint_reuse_allowed_after_predictive_content_change": False,
            "semantic_invariants": SEMANTIC_INVARIANTS,
            "production_authority": False,
            "source_closure": closure,
        },
    )
    old_result = read_json(ROOT / "output/factor-rotation/reaka_v2_stage3_state_episode_atlas_v1_2011_2025/formal/result.json")
    old_validation = read_json(ROOT / "docs/ops/evidence/reaka_v2_stage3_state_episode_atlas_v1_20260904/validation_report.json")
    old_authority = read_json(ROOT / "docs/ops/reaka_strategy_authority_registry@110.0.json")
    old_succession = read_json(ROOT / "docs/ops/reaka_controller_succession_audit@271.0.json")
    correction = write_json(
        STAGE3_CORRECTION_PATH,
        {
            "schema_id": "factorlab.reaka_v2_stage3_observable_context_authority_correction@1.0",
            "status": "raw_observable_measurements_retained_operator_inference_revoked",
            "retained_evidence": {
                "result_digest": old_result["canonical_digest"],
                "validation_digest": old_validation["canonical_digest"],
                "allowed_files": ["state_months.csv", "state_episodes.csv", "state_support.csv", "transition_counts.csv"],
                "allowed_claim": "S_obs_PIT_episode_transition_duration_and_support_description_only",
            },
            "revoked_claims": [
                "slow_context_low_rank_modulator_as_operator_route",
                "discrete_operator_expert_not_allowed_from_S_obs_episodes",
                "unshrunk_K_matrix_not_allowed_from_S_obs_episodes",
            ],
            "revoked_current_authorities": {
                "authority_110_digest": old_authority["canonical_digest"],
                "succession_271_digest": old_succession["canonical_digest"],
            },
            "stage3_operator_count_decision_authority": False,
            "stage3_measurement_reexecution_required": False,
            "stage4_execution_allowed": False,
            "model_training_allowed": False,
            "production_authority": False,
            "semantic_invariants": SEMANTIC_INVARIANTS,
            "source_closure": closure,
        },
    )
    roots = [
        _normative_entry(
            "infrastructure_plan",
            "docs/user/reaka_multifactor_infrastructure_systematic_optimization_plan.md",
            "systematic_rebuild_plan_and_stop_rules",
        ),
        _normative_entry(
            "current_entry",
            "docs/user/reaka_multifactor_current_workflow.md",
            "reading_order_and_stop_points",
            required=True,
        ),
        _normative_entry(
            "semantic_ontology_explanation",
            "docs/ops/reaka_multifactor_semantic_ontology_whitepaper.md",
            "object_reasoning_and_forbidden_inference",
            required=True,
        ),
        _normative_entry(
            "semantic_ontology_contract",
            "docs/ops/reaka_multifactor_semantic_ontology@1.0.json",
            "object_ownership_and_legal_inference",
            required=True,
        ),
        _normative_entry(
            "six_surface_explanation",
            "docs/ops/reaka_multifactor_six_surface_infrastructure_whitepaper.md",
            "artifact_roles_tone_and_boundaries",
        ),
        _normative_entry(
            "six_surface_contract",
            "docs/ops/reaka_multifactor_six_surface_infrastructure@1.0.json",
            "artifact_responsibility",
            required=True,
        ),
        _normative_entry(
            "product_definition",
            "docs/ops/reaka_product_driven_multiscale_research_whitepaper.md",
            "product_frequency_target_cost",
        ),
        _normative_entry(
            "factor_research",
            "docs/ops/reaka_factor_discovery_three_pathway_whitepaper.md",
            "factor_identity_and_three_pathways",
        ),
        _normative_entry(
            "observable_context_explanation",
            "docs/ops/state_factor_research_state_machine_v2_whitepaper.md",
            "S_obs_stage_reasoning_no_operator_authority",
        ),
        _normative_entry(
            "observable_context_state_machine",
            "docs/ops/state_factor_research_state_machine@2.0.json",
            "S_obs_support_no_operator_authority",
            required=True,
        ),
        _normative_entry(
            "prediction_content_rollback_explanation",
            "docs/ops/reaka_prediction_content_rollback_v2_whitepaper.md",
            "rollback_reasoning_without_authority_transfer",
        ),
        _normative_entry(
            "prediction_content_rollback",
            "docs/ops/reaka_prediction_content_rollback@2.0.json",
            "earliest_reopen_without_authority_transfer",
        ),
        _normative_entry(
            "model_assembly",
            "docs/ops/reaka_multifactor_model_assembly_v2_whitepaper.md",
            "S_obs_to_Hx_gate_then_model_training",
        ),
        _normative_entry(
            "input_math",
            "docs/ops/reaka_input_mathematical_compatibility_whitepaper.md",
            "frequency_rank_capacity_residual_relationships",
        ),
        _normative_entry(
            "parameter_governance",
            "docs/ops/reaka_paper_parameter_governance_whitepaper.md",
            "parameter_sources_and_instantiation_only",
        ),
        _normative_entry(
            "operator_semantics_explanation",
            "docs/ops/reaka_operator_identifiability_whitepaper.md",
            "K_ownership_identifiability_and_failure_meaning",
        ),
        _normative_entry(
            "operator_semantics",
            "docs/ops/reaka_operator_identifiability@1.0.json",
            "K_ownership_and_identifiability",
            required=True,
        ),
        _normative_entry(
            "operator_residual_admission",
            "docs/ops/koopman_residual_admission@1.0.json",
            "K1_K2_K3_then_residual",
        ),
        _normative_entry(
            "strategy_progression_explanation",
            "docs/ops/strategy_progressive_development_whitepaper.md",
            "progression_retention_and_promotion_reasoning",
        ),
        _normative_entry(
            "strategy_progression",
            "docs/ops/strategy_progressive_development@1.0.json",
            "progression_promotion_and_authority",
        ),
        _normative_entry(
            "strategy_science_acceptance_explanation",
            "docs/ops/post_training_strategy_science_acceptance_whitepaper.md",
            "SSA_reasoning_before_account",
        ),
        _normative_entry(
            "strategy_science_acceptance",
            "docs/ops/post_training_strategy_science_acceptance@1.0.json",
            "SSA_before_account",
        ),
        _normative_entry(
            "account_audit",
            "docs/ops/post_training_account_audit@1.1.json",
            "A0_A7_after_SSA",
        ),
        _normative_entry(
            "current_handoff",
            "docs/user/reaka_strategy_v2_external_ai_handoff_v2.md",
            "context_recovery_with_semantic_checksum",
        ),
        _normative_entry(
            "stage3_authority_correction",
            "docs/ops/reaka_v2_stage3_observable_context_authority_correction@1.0.json",
            "retain_measurement_revoke_K_inference",
        ),
    ]
    write_json(
        CURRENT_MANIFEST_PATH,
        {
            "schema_id": "factorlab.reaka_multifactor_current_manifest@1.0",
            "status": "current_normative_closure_frozen",
            "strategy_scope": "REAKA_multifactor_stock_selection_and_shared_factor_research",
            "default_unlisted_classification": "historical_or_specialized_no_current_normative_authority",
            "first_read_sequence": [
                "docs/user/reaka_multifactor_current_workflow.md",
                "docs/ops/reaka_multifactor_semantic_ontology@1.0.json",
                "docs/ops/reaka_multifactor_current_manifest@1.0.json",
                "docs/ops/state_factor_research_state_machine@2.0.json",
                "docs/ops/reaka_operator_identifiability@1.0.json",
            ],
            "normative_roots": roots,
            "revoked_current_normative_paths": [
                "docs/ops/state_factor_research_state_machine@1.0.json",
                "docs/ops/state_factor_research_state_machine_whitepaper.md",
                "docs/user/reaka_strategy_v2_external_ai_handoff.md",
                "docs/ops/reaka_strategy_authority_registry@110.0.json",
                "docs/ops/reaka_controller_succession_audit@271.0.json",
                "docs/ops/reaka_v2_stage3_state_episode_atlas_final_result.md",
            ],
            "current_handoff": "docs/user/reaka_strategy_v2_external_ai_handoff_v2.md",
            "next_legal_action": "user_review_then_freeze_stage4_contract",
            "stage4_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
            "semantic_invariants": SEMANTIC_INVARIANTS,
            "ontology_digest": ontology["canonical_digest"],
            "six_surface_digest": six_surface["canonical_digest"],
            "state_machine_v2_digest": state_machine["canonical_digest"],
            "rollback_v2_digest": rollback["canonical_digest"],
            "stage3_correction_digest": correction["canonical_digest"],
            "source_closure": closure,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
