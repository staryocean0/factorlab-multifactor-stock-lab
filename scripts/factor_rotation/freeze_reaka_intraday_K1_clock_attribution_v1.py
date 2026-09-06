#!/usr/bin/env python3
"""Freeze P6.4.1 matched clock/config attribution."""

from __future__ import annotations

import json
from pathlib import Path

from factor_lab.factor_rotation.reaka_intraday_k1_clock_attribution_v1 import (
    CELL_SPECS,
    SCHEMA_ID,
)
from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    file_digest,
    read_json,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
ISSUE_REF = "bd://fl-eginj.5"
P64_ACCEPTANCE = ROOT / "docs/ops/evidence/reaka_intraday_K1_formal_training_v1_20260831/controller_acceptance.json"
P64_ROOT = ROOT / "output/factor-rotation/reaka_intraday_K1_formal_v1_2011_2018"
EVIDENCE = ROOT / "docs/ops/evidence/reaka_intraday_K1_clock_attribution_v1_20260831"
GOVERNANCE = EVIDENCE / "parameter_governance"
CONTRACT = ROOT / "docs/ops/reaka_intraday_K1_clock_attribution@1.0.json"
SUCCESSION = ROOT / "docs/ops/reaka_controller_succession_audit@154.0.json"
SOURCE_PATHS = (
    "docs/ops/reaka_intraday_K1_clock_attribution_whitepaper.md",
    "docs/user/reaka_intraday_K1_clock_attribution_workflow.md",
    "src/factor_lab/factor_rotation/reaka_intraday_k1_clock_attribution_v1.py",
    "scripts/factor_rotation/freeze_reaka_intraday_K1_clock_attribution_v1.py",
    "scripts/factor_rotation/run_reaka_intraday_K1_clock_missing_cell_v1.py",
    "scripts/factor_rotation/run_reaka_intraday_K1_clock_attribution_v1.py",
    "scripts/factor_rotation/validate_close_reaka_intraday_K1_clock_attribution_v1.py",
    "tests/unit/test_reaka_intraday_k1_clock_attribution_v1.py",
    "src/factor_lab/factor_rotation/reaka_paper_v1.py",
)


def inventory(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): file_digest(path) for path in sorted(root.rglob("*")) if path.is_file()}


def main() -> None:
    acceptance = read_json(P64_ACCEPTANCE)
    workflow = write_json(
        GOVERNANCE / "workflow_gate.json",
        {
            "schema_id": "factorlab.reaka_intraday_K1_clock_attribution_workflow_gate@1.0",
            "status": "passed_for_fixed_paired_diagnostic",
            "P6_4_acceptance_digest": acceptance["canonical_digest"],
            "parameter_governance_whitepaper_digest": file_digest(ROOT / "docs/ops/reaka_paper_parameter_governance_whitepaper.md"),
            "succession_whitepaper_digest": file_digest(ROOT / "docs/ops/reaka_controller_succession_audit_whitepaper.md"),
            "new_parameter_search_allowed": False,
            "2018_read_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    financial = write_json(
        GOVERNANCE / "financial_alignment_gate.json",
        {
            "schema_id": "factorlab.reaka_intraday_K1_clock_attribution_financial_gate@1.0",
            "status": "passed_for_user_authorized_root_cause_diagnostic",
            "financial_question": "does_the_15_minute_clock_or_the_selected_model_configuration_drive_the_P6_4_flip",
            "financial_object": "three_seed_daily_rankz_equal_weight_ensemble_one_step_H20_score",
            "single_seed_is_financial_object": False,
            "recursive_K_rollout_is_current_financial_object": False,
            "P6_5_preapproved": False,
            "production_authority": False,
        },
    )
    root_scope = write_json(
        GOVERNANCE / "root_scope_gate.json",
        {
            "schema_id": "factorlab.reaka_intraday_K1_clock_attribution_root_scope@1.0",
            "status": "passed",
            "fixed_configurations": ["A_d8_h8_lr0p1_c4", "B_d16_h16_lr0p03_c3"],
            "active_axes": ["decision_clock", "fixed_configuration", "clock_x_configuration_interaction"],
            "inactive_axes": ["new_capacity", "new_learning_rate", "new_cycle", "K_greater_than_one", "residual"],
            "user_math_inputs_required": [],
            "production_authority": False,
        },
    )
    controls = {f"{tree}_{suffix}": inventory(P64_ROOT / tree / suffix) for tree in ("formal", "isolated") for suffix in ("1430", "1445")}
    contract = write_json(
        CONTRACT,
        {
            "schema_id": SCHEMA_ID,
            "status": "frozen_missing_cell_execution_authorized",
            "issue_ref": ISSUE_REF,
            "P6_4_acceptance_digest": acceptance["canonical_digest"],
            "parameter_governance": {
                "workflow_gate_digest": workflow["canonical_digest"],
                "financial_alignment_gate_digest": financial["canonical_digest"],
                "root_scope_gate_digest": root_scope["canonical_digest"],
            },
            "cells": [dict(row) for row in CELL_SPECS],
            "P6_4_control_inventories": controls,
            "fit_years": [2011, 2012, 2013, 2014, 2015, 2016],
            "diagnostic_year": 2017,
            "closed_years": [2018, 2019, 2020],
            "fresh_oos": False,
            "metrics": [
                "spectral_radius",
                "condition_number",
                "one_step_latent_relative_mse",
                "one_step_observed_gain_q50_q95_q99",
                "recursive_K1_K2_K4_observed_gain_q50_q95_q99",
                "ensemble_review_RankIC_and_spread",
                "ensemble_member_drop_score_spearman",
                "ensemble_input_noise_score_spearman",
                "clock_config_interaction_continuous_effects",
            ],
            "admission_or_candidate_selection_allowed": False,
            "formal_isolated_byte_replay_required": True,
            "source_closure": {relative: file_digest(ROOT / relative) for relative in SOURCE_PATHS},
            "missing_cell_training_allowed": True,
            "P6_5_execution_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    succession = write_json(
        SUCCESSION,
        {
            "schema_id": "factorlab.reaka_controller_succession_audit@154.0",
            "status": "P6_4_1_fixed_two_by_two_clock_attribution_open",
            "issue_ref": ISSUE_REF,
            "contract_digest": contract["canonical_digest"],
            "next_legal_action": "train_only_1430_B_and_1445_A_formal_isolated_then_run_paired_diagnostic",
            "missing_cell_training_allowed": True,
            "P6_5_execution_allowed": False,
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
