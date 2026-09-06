#!/usr/bin/env python3
# pyright: reportAny=false, reportUnknownVariableType=false
"""Validate P6.4.1 and freeze corrected financial/mathematical gate semantics."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    canonical_valid,
    file_digest,
    read_json,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/ops/reaka_intraday_K1_clock_attribution@1.0.json"
P64_ROOT = ROOT / "output/factor-rotation/reaka_intraday_K1_formal_v1_2011_2018"
OUTPUT = ROOT / "output/factor-rotation/reaka_intraday_K1_clock_attribution_v1_2011_2017"
EVIDENCE = ROOT / "docs/ops/evidence/reaka_intraday_K1_clock_attribution_v1_20260831"
GATE = ROOT / "docs/ops/reaka_intraday_K1_gate_semantics@1.0.json"
REPORT = EVIDENCE / "validation_report.json"
ACCEPTANCE = EVIDENCE / "controller_acceptance.json"
REGISTRY = ROOT / "docs/ops/reaka_strategy_authority_registry@12.0.json"
PROGRESSIVE = ROOT / "docs/ops/reaka_current_strategy_progressive_index@12.0.json"
SUCCESSION = ROOT / "docs/ops/reaka_controller_succession_audit@155.0.json"


def inventory(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): file_digest(path) for path in sorted(root.rglob("*")) if path.is_file()}


def command_status(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def dominant_effect(row: Mapping[str, object]) -> dict[str, object]:
    shares = {
        "clock": float(cast(float, row["absolute_clock_share"])),
        "configuration": float(cast(float, row["absolute_config_share"])),
        "interaction": float(cast(float, row["absolute_interaction_share"])),
    }
    dominant = max(shares, key=shares.__getitem__)
    return {"dominant": dominant, "shares": shares}


def main() -> None:
    blockers: list[str] = []
    contract = read_json(CONTRACT)
    if not canonical_valid(contract):
        blockers.append("contract_digest_invalid")
    source_mismatches = [
        relative
        for relative, expected in cast(Mapping[str, str], contract["source_closure"]).items()
        if not (ROOT / relative).exists() or file_digest(ROOT / relative) != expected
    ]
    blockers.extend(f"source_closure_drift:{value}" for value in source_mismatches)
    control_mismatches: list[str] = []
    for identity, expected in cast(
        Mapping[str, Mapping[str, str]],
        contract["P6_4_control_inventories"],
    ).items():
        tree, suffix = identity.split("_", maxsplit=1)
        if inventory(P64_ROOT / tree / suffix) != dict(expected):
            control_mismatches.append(identity)
    blockers.extend(f"P6_4_control_drift:{value}" for value in control_mismatches)
    missing_cell_mismatches: dict[str, object] = {}
    for cell in ("1430_B", "1445_A"):
        formal = inventory(OUTPUT / "formal" / cell)
        isolated = inventory(OUTPUT / "isolated" / cell)
        mismatches = sorted(key for key in set(formal) | set(isolated) if formal.get(key) != isolated.get(key))
        missing_cell_mismatches[cell] = mismatches
        if mismatches:
            blockers.append(f"missing_cell_replay_mismatch:{cell}")
        for tree in ("formal", "isolated"):
            fit = read_json(OUTPUT / tree / cell / "fit.json")
            if fit.get("2018_rows_read") != 0 or fit.get("2019_2020_rows_read") != 0:
                blockers.append(f"missing_cell_outer_read:{tree}:{cell}")
    formal = read_json(OUTPUT / "formal" / "attribution.json")
    isolated = read_json(OUTPUT / "isolated" / "attribution.json")
    if formal.get("canonical_digest") != isolated.get("canonical_digest"):
        blockers.append("attribution_replay_mismatch")
    semantics = cast(Mapping[str, object], formal["forecast_semantics"])
    if semantics.get("passed") is not True:
        blockers.append("forecast_semantics_audit_failed")
    if formal.get("2018_rows_read") != 0 or formal.get("2019_2020_rows_read") != 0:
        blockers.append("attribution_outer_read")
    effects = cast(Mapping[str, Mapping[str, object]], formal["factorial_effects"])
    effect_attribution = {metric: dominant_effect(row) for metric, row in effects.items()}
    ruff = command_status(
        [
            "ruff",
            "check",
            "src/factor_lab/factor_rotation/reaka_intraday_k1_clock_attribution_v1.py",
            "scripts/factor_rotation/freeze_reaka_intraday_K1_clock_attribution_v1.py",
            "scripts/factor_rotation/run_reaka_intraday_K1_clock_missing_cell_v1.py",
            "scripts/factor_rotation/run_reaka_intraday_K1_clock_attribution_v1.py",
            "scripts/factor_rotation/validate_close_reaka_intraday_K1_clock_attribution_v1.py",
            "tests/unit/test_reaka_intraday_k1_clock_attribution_v1.py",
        ]
    )
    pytest = command_status(["pytest", "-q", "tests/unit/test_reaka_intraday_k1_clock_attribution_v1.py"])
    basedpyright = command_status(
        [
            "basedpyright",
            "src/factor_lab/factor_rotation/reaka_intraday_k1_clock_attribution_v1.py",
            "tests/unit/test_reaka_intraday_k1_clock_attribution_v1.py",
        ]
    )
    for name, check in (("ruff", ruff), ("pytest", pytest), ("basedpyright", basedpyright)):
        if check["returncode"] != 0:
            blockers.append(f"{name}_failed")
    gate = write_json(
        GATE,
        {
            "schema_id": "factorlab.reaka_intraday_K1_gate_semantics@1.0",
            "status": "corrected_financial_mathematical_alignment_frozen",
            "attribution_contract_digest": contract["canonical_digest"],
            "current_financial_object": "three_seed_daily_rankz_equal_weight_ensemble_one_step_H20_score",
            "current_operator_application_count": 1,
            "seed_level_hard_numerical_gates": [
                "finite_loss_gradient_parameter_and_score",
                "condition_number_times_float32_epsilon_at_most_1e_minus_3",
            ],
            "ensemble_level_hard_financial_robustness_gates": [
                "member_drop_score_spearman_at_least_0p95",
                "input_noise_score_spearman_at_least_0p95",
            ],
            "current_one_step_diagnostics_without_permanent_threshold": [
                "one_step_latent_relative_mse",
                "observed_one_step_gain_distribution",
                "advanced_to_next_rms_ratio",
            ],
            "spectral_radius": {
                "current_one_step_hard_gate": False,
                "current_role": "recursive_rollout_diagnostic",
                "hard_gate_reopens_if": "future_policy_applies_K_recursively_beyond_one_step",
            },
            "single_seed_perturbation_hard_veto": False,
            "single_seed_perturbation_role": "distribution_and_exception_diagnostic",
            "P6_4_1430_old_rejection": "superseded_semantics_misaligned_not_promoted_or_confirmed",
            "P6_4_1445_confirmation": "preserved",
            "2018_may_reopen_for_1430": False,
            "new_unseen_confirmation_required_for_1430": True,
            "P6_5_execution_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    report = write_json(
        REPORT,
        {
            "schema_id": "factorlab.reaka_intraday_K1_clock_attribution_validation@1.0",
            "status": "passed" if not blockers else "blocked",
            "contract_digest": contract["canonical_digest"],
            "attribution_digest": formal["canonical_digest"],
            "gate_semantics_digest": gate["canonical_digest"],
            "effect_attribution": effect_attribution,
            "source_closure_mismatches": source_mismatches,
            "control_mismatches": control_mismatches,
            "missing_cell_mismatches": missing_cell_mismatches,
            "checks": {"ruff": ruff, "pytest": pytest, "basedpyright": basedpyright},
            "blockers": blockers,
            "2018_rows_read": 0,
            "2019_2020_rows_read": 0,
            "account_run": False,
            "P6_5_execution_allowed": False,
            "production_authority": False,
        },
    )
    if blockers:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    acceptance = write_json(
        ACCEPTANCE,
        {
            "schema_id": "factorlab.reaka_intraday_K1_clock_attribution_controller_acceptance@1.0",
            "status": "P6_4_1_root_attribution_complete_gate_semantics_corrected_waiting_user",
            "issue_ref": "bd://fl-eginj.5",
            "validation_report_digest": report["canonical_digest"],
            "gate_semantics_digest": gate["canonical_digest"],
            "cells": formal["cells"],
            "factorial_effects": formal["factorial_effects"],
            "effect_attribution": effect_attribution,
            "P6_4_1430_status": "old_rejection_revoked_requires_new_unseen_confirmation_not_2018_reuse",
            "P6_4_1445_status": "confirmed_research_baseline_preserved",
            "next_legal_action": "user_review_root_attribution_and_clock_policy_before_any_P6_5",
            "P6_5_execution_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    registry = write_json(
        REGISTRY,
        {
            "schema_id": "factorlab.reaka_strategy_authority_registry@12.0",
            "stable_alias": "REAKA_CURRENT_STRATEGY_DEVELOPMENT_V1",
            "current_stage": acceptance["status"],
            "current_acceptance_digest": acceptance["canonical_digest"],
            "gate_semantics_digest": gate["canonical_digest"],
            "deployment_candidate": False,
            "production_pointer_changed": False,
            "production_authority": False,
        },
    )
    progressive = write_json(
        PROGRESSIVE,
        {
            "schema_id": "factorlab.reaka_current_strategy_progressive_index@12.0",
            "stable_alias": "REAKA_CURRENT_STRATEGY_DEVELOPMENT_V1",
            "completed_phase": "P6_4_1_clock_configuration_root_attribution",
            "current_acceptance_digest": acceptance["canonical_digest"],
            "next_legal_action": acceptance["next_legal_action"],
            "P6_5_execution_allowed": False,
            "production_authority": False,
        },
    )
    succession = write_json(
        SUCCESSION,
        {
            "schema_id": "factorlab.reaka_controller_succession_audit@155.0",
            "status": acceptance["status"],
            "issue_ref": "bd://fl-eginj.5",
            "controller_acceptance_digest": acceptance["canonical_digest"],
            "authority_registry_digest": registry["canonical_digest"],
            "progressive_index_digest": progressive["canonical_digest"],
            "next_legal_action": acceptance["next_legal_action"],
            "P6_5_execution_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    print(
        json.dumps(
            {
                "report_digest": report["canonical_digest"],
                "acceptance_digest": acceptance["canonical_digest"],
                "gate_semantics_digest": gate["canonical_digest"],
                "succession_digest": succession["canonical_digest"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
