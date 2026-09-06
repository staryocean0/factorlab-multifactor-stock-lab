#!/usr/bin/env python3
# pyright: reportAny=false, reportUnknownVariableType=false
"""Validate and close the fit-prefix per-seed K1 successor."""

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
CONTRACT = ROOT / "docs/ops/reaka_intraday_K1_fit_prefix_successor@1.0.json"
OUTPUT = ROOT / "output/factor-rotation/reaka_intraday_K1_fit_prefix_successor_v1_2011_2017"
EVIDENCE = ROOT / "docs/ops/evidence/reaka_intraday_K1_fit_prefix_successor_v1_20260831"
REPORT = EVIDENCE / "validation_report.json"
ACCEPTANCE = EVIDENCE / "controller_acceptance.json"
REGISTRY = ROOT / "docs/ops/reaka_strategy_authority_registry@16.0.json"
PROGRESSIVE = ROOT / "docs/ops/reaka_current_strategy_progressive_index@16.0.json"
SUCCESSION = ROOT / "docs/ops/reaka_controller_succession_audit@164.0.json"


def inventory(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): file_digest(path) for path in sorted(root.rglob("*")) if path.is_file()}


def command_status(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, cwd=ROOT, check=False, text=True, capture_output=True)
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def main() -> None:
    blockers: list[str] = []
    contract = read_json(CONTRACT)
    if not canonical_valid(contract):
        blockers.append("contract_digest_invalid")
    source_mismatches = [
        path
        for path, digest in cast(Mapping[str, str], contract["source_closure"]).items()
        if not (ROOT / path).exists() or file_digest(ROOT / path) != digest
    ]
    blockers.extend(f"source_drift:{value}" for value in source_mismatches)
    clock_reports: dict[str, dict[str, object]] = {}
    passed: list[str] = []
    for suffix in ("1430", "1445"):
        left = inventory(OUTPUT / "formal" / suffix)
        right = inventory(OUTPUT / "isolated" / suffix)
        mismatch = sorted(key for key in set(left) | set(right) if left.get(key) != right.get(key))
        if mismatch:
            blockers.append(f"tree_replay_mismatch:{suffix}")
        fit = read_json(OUTPUT / "formal" / suffix / "formal.json")
        for seed in cast(list[Mapping[str, object]], fit["seed_results"]):
            if seed.get("2017_used_for_checkpoint_selection") is not False:
                blockers.append(f"checkpoint_target_leak:{suffix}:seed{seed['seed']}")
        if fit.get("2018_rows_read") != 0 or fit.get("2019_2020_rows_read") != 0:
            blockers.append(f"outer_read:{suffix}")
        if fit.get("status") == "passed_retrospective_K1_candidate":
            passed.append(suffix)
        clock_reports[suffix] = {
            "status": fit["status"],
            "digest": fit["canonical_digest"],
            "config": fit["config"],
            "seed_results": fit["seed_results"],
            "diagnostic": fit["diagnostic"],
            "mismatches": mismatch,
        }
    ruff = command_status(
        [
            "ruff",
            "check",
            "src/factor_lab/factor_rotation/reaka_intraday_k1_fit_prefix_successor_v1.py",
            "scripts/factor_rotation/freeze_reaka_intraday_K1_fit_prefix_successor_v1.py",
            "scripts/factor_rotation/run_reaka_intraday_K1_fit_prefix_successor_v1.py",
            "scripts/factor_rotation/validate_close_reaka_intraday_K1_fit_prefix_successor_v1.py",
            "tests/unit/test_reaka_intraday_k1_fit_prefix_successor_v1.py",
        ]
    )
    pytest = command_status(["pytest", "-q", "tests/unit/test_reaka_intraday_k1_fit_prefix_successor_v1.py"])
    basedpyright = command_status(
        [
            "basedpyright",
            "src/factor_lab/factor_rotation/reaka_intraday_k1_fit_prefix_successor_v1.py",
            "tests/unit/test_reaka_intraday_k1_fit_prefix_successor_v1.py",
        ]
    )
    for name, check in (("ruff", ruff), ("pytest", pytest), ("basedpyright", basedpyright)):
        if check["returncode"] != 0:
            blockers.append(f"{name}_failed")
    scientific_status = (
        "frozen_retrospective_common_K1_candidate_waiting_genuinely_unseen_confirmation"
        if len(passed) == 2
        else "fit_prefix_successor_failed"
    )
    report = write_json(
        REPORT,
        {
            "schema_id": "factorlab.reaka_intraday_K1_fit_prefix_successor_validation@1.0",
            "status": "passed" if not blockers else "blocked",
            "scientific_status": scientific_status,
            "contract_digest": contract["canonical_digest"],
            "clock_reports": clock_reports,
            "source_mismatches": source_mismatches,
            "checks": {"ruff": ruff, "pytest": pytest, "basedpyright": basedpyright},
            "blockers": blockers,
            "2018_rows_read": 0,
            "2019_2020_rows_read": 0,
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
            "schema_id": "factorlab.reaka_intraday_K1_fit_prefix_successor_controller_acceptance@1.0",
            "status": scientific_status,
            "issue_ref": "bd://fl-eginj.7",
            "validation_report_digest": report["canonical_digest"],
            "clock_reports": clock_reports,
            "next_legal_action": "wait_for_genuinely_unseen_confirmation_before_P6_5"
            if len(passed) == 2
            else "stop_or_freeze_new_math_family",
            "P6_5_execution_allowed": False,
            "production_authority": False,
        },
    )
    registry = write_json(
        REGISTRY,
        {
            "schema_id": "factorlab.reaka_strategy_authority_registry@16.0",
            "stable_alias": "REAKA_CURRENT_STRATEGY_DEVELOPMENT_V1",
            "current_stage": acceptance["status"],
            "current_acceptance_digest": acceptance["canonical_digest"],
            "production_authority": False,
        },
    )
    progressive = write_json(
        PROGRESSIVE,
        {
            "schema_id": "factorlab.reaka_current_strategy_progressive_index@16.0",
            "stable_alias": "REAKA_CURRENT_STRATEGY_DEVELOPMENT_V1",
            "completed_phase": "P6_4_4_fit_prefix_per_seed_K1_successor",
            "current_acceptance_digest": acceptance["canonical_digest"],
            "P6_5_execution_allowed": False,
            "production_authority": False,
        },
    )
    succession = write_json(
        SUCCESSION,
        {
            "schema_id": "factorlab.reaka_controller_succession_audit@164.0",
            "status": acceptance["status"],
            "controller_acceptance_digest": acceptance["canonical_digest"],
            "authority_registry_digest": registry["canonical_digest"],
            "progressive_index_digest": progressive["canonical_digest"],
            "next_legal_action": acceptance["next_legal_action"],
            "P6_5_execution_allowed": False,
            "production_authority": False,
        },
    )
    print(
        json.dumps(
            {
                "report": report["canonical_digest"],
                "acceptance": acceptance["canonical_digest"],
                "succession": succession["canonical_digest"],
                "status": scientific_status,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
