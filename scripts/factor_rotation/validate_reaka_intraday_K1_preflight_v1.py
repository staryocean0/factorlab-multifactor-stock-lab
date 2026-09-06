#!/usr/bin/env python3
"""Fail-closed validation for the P6.3 K1/r0 input and preflight."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import numpy as np
from numpy.typing import NDArray

from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    CLOCK_SUFFIX,
    CLOCKS,
    COMPATIBILITY_REQUIRED_FIELDS,
    FEATURE_DIM,
    STORE_FILES,
    VALIDATION_SCHEMA_ID,
    canonical_valid,
    file_digest,
    read_json,
    validate_contract,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/ops/reaka_intraday_K1_preflight@1.0.json"
STORE = ROOT / "output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020"
EVIDENCE = ROOT / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831"
REPORT = EVIDENCE / "validation_report.json"
GOVERNANCE = EVIDENCE / "parameter_governance"


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


def main() -> None:
    contract = read_json(CONTRACT)
    blockers = validate_contract(contract)
    source_mismatches = [
        relative
        for relative, expected in cast(dict[str, str], contract["source_closure"]).items()
        if not (ROOT / relative).exists() or file_digest(ROOT / relative) != expected
    ]
    blockers.extend(f"source_closure_drift:{value}" for value in source_mismatches)
    governance_names = (
        "workflow_gate.json",
        "financial_alignment_gate.json",
        "root_scope_gate.json",
    )
    governance: dict[str, dict[str, object]] = {}
    for name in governance_names:
        path = GOVERNANCE / name
        if not path.exists():
            blockers.append(f"parameter_governance_receipt_missing:{name}")
            continue
        payload = read_json(path)
        governance[name] = payload
        if not canonical_valid(payload) or not str(payload.get("status", "")).startswith("passed"):
            blockers.append(f"parameter_governance_gate_invalid:{name}")
        if payload.get("formal_training_allowed") is not False:
            blockers.append(f"parameter_governance_training_leak:{name}")
    expected_governance = cast(dict[str, str], contract["parameter_governance"])
    for key, name in (
        ("workflow_gate_digest", "workflow_gate.json"),
        ("financial_alignment_gate_digest", "financial_alignment_gate.json"),
        ("root_scope_gate_digest", "root_scope_gate.json"),
    ):
        if name in governance and governance[name].get("canonical_digest") != expected_governance.get(key):
            blockers.append(f"contract_parameter_governance_binding_invalid:{key}")
    clock_reports: dict[str, object] = {}
    for clock in CLOCKS:
        suffix = CLOCK_SUFFIX[clock]
        formal = STORE / "formal" / suffix
        isolated = STORE / "isolated" / suffix
        missing = [
            f"{tree}:{name}"
            for tree, root in (("formal", formal), ("isolated", isolated))
            for name in STORE_FILES
            if not (root / name).exists()
        ]
        blockers.extend(f"missing_store_file:{suffix}:{value}" for value in missing)
        if missing:
            continue
        mismatches = [name for name in STORE_FILES if file_digest(formal / name) != file_digest(isolated / name)]
        blockers.extend(f"store_replay_mismatch:{suffix}:{name}" for name in mismatches)
        manifest = read_json(formal / "manifest.json")
        if not canonical_valid(manifest):
            blockers.append(f"store_manifest_digest_invalid:{suffix}")
        for key, expected in (
            ("contract_digest", contract["canonical_digest"]),
            ("decision_clock", clock),
            ("feature_dim", FEATURE_DIM),
            ("target_used_to_filter_inference", False),
            ("entry_used_to_filter_inference", False),
            ("post_2020_rows_read", 0),
            ("model_training_run", False),
            ("score_run", False),
            ("account_run", False),
        ):
            if manifest.get(key) != expected:
                blockers.append(f"store_manifest_field_invalid:{suffix}:{key}")
        if manifest.get("phase_ids") != [0, 1, 2, 3]:
            blockers.append(f"store_phase_ids_invalid:{suffix}")
        if int(cast(int, manifest.get("inference_without_label_count", 0))) <= 0:
            blockers.append(f"inference_target_independence_not_demonstrated:{suffix}")
        rows = cast(NDArray[np.int64], np.load(formal / "inference_rows.npy", mmap_mode="r"))
        labelled = cast(NDArray[np.int64], np.load(formal / "labelled_row_indices.npy", mmap_mode="r"))
        if len(rows) != int(cast(int, manifest["inference_row_count"])):
            blockers.append(f"inference_row_count_mismatch:{suffix}")
        if len(labelled) != int(cast(int, manifest["labelled_row_count"])):
            blockers.append(f"labelled_row_count_mismatch:{suffix}")
        preflight = EVIDENCE / "preflight" / suffix
        names = (
            "normalizer.json",
            "compatibility_certificate.json",
            "lr_gradient_receipt.json",
            "backend_receipt.json",
            "run_instantiation.json",
        )
        if any(not (preflight / name).exists() for name in names):
            blockers.append(f"preflight_receipt_missing:{suffix}")
            continue
        receipts = {name: read_json(preflight / name) for name in names}
        for name, payload in receipts.items():
            if not canonical_valid(payload):
                blockers.append(f"preflight_digest_invalid:{suffix}:{name}")
        compatibility = receipts["compatibility_certificate.json"]
        lr = receipts["lr_gradient_receipt.json"]
        backend = receipts["backend_receipt.json"]
        instantiation = receipts["run_instantiation.json"]
        if compatibility.get("status") != "compatible_with_claim_limitations":
            blockers.append(f"compatibility_not_passed:{suffix}")
        for field in COMPATIBILITY_REQUIRED_FIELDS:
            if field not in compatibility:
                blockers.append(f"compatibility_required_field_missing:{suffix}:{field}")
        if compatibility.get("decision_clock") != clock:
            blockers.append(f"compatibility_clock_invalid:{suffix}")
        if lr.get("status") != "passed" or lr.get("right_censored_identities") != []:
            blockers.append(f"LR_boundary_not_closed:{suffix}")
        if lr.get("target_read") is not False:
            blockers.append(f"LR_target_read:{suffix}")
        if backend.get("status") != "passed" or backend.get("selected_backend") not in ("cpu", "rocm"):
            blockers.append(f"backend_not_admitted:{suffix}")
        if backend.get("timing_blocks") != 5 or backend.get("repetitions_per_block") != 4:
            blockers.append(f"backend_timing_design_invalid:{suffix}")
        if backend.get("minimum_rocm_speedup") != 1.10:
            blockers.append(f"backend_speed_margin_invalid:{suffix}")
        if backend.get("target_read") is not False:
            blockers.append(f"backend_target_read:{suffix}")
        if instantiation.get("parameter_count") != 22 or len(cast(dict[str, object], instantiation.get("parameter_values", {}))) != 22:
            blockers.append(f"parameter_count_invalid:{suffix}")
        if instantiation.get("user_math_inputs_required") != []:
            blockers.append(f"user_math_input_unresolved:{suffix}")
        if instantiation.get("formal_training_allowed") is not False:
            blockers.append(f"formal_training_authority_leak:{suffix}")
        for key in expected_governance:
            if instantiation.get(key) != expected_governance[key]:
                blockers.append(f"run_instantiation_governance_binding_invalid:{suffix}:{key}")
        clock_reports[suffix] = {
            "inference_rows": manifest["inference_row_count"],
            "labelled_rows": manifest["labelled_row_count"],
            "inference_without_label": manifest["inference_without_label_count"],
            "r_eff": compatibility["r_eff"],
            "tau_s_days": compatibility["tau_s_days"],
            "n_eff_time": compatibility["n_eff_time"],
            "n_eff_design": compatibility["n_eff_design_time_x_sqrt_cross_section"],
            "n_eff_upper": compatibility["n_eff_cross_section_upper_bound"],
            "capacity_roots": compatibility["capacity_root_candidates"],
            "capacity_support": compatibility["capacity_support"],
            "learning_rates": lr["selected_learning_rates"],
            "selected_backend": backend["selected_backend"],
            "cpu_seconds": backend["cpu_seconds"],
            "rocm_seconds": backend["rocm_seconds"],
            "rocm_parity_passed": backend["parity_passed"],
            "formal_isolated_mismatches": mismatches,
        }
    ruff = command_status(
        [
            "ruff",
            "check",
            "src/factor_lab/factor_rotation/reaka_intraday_k1_preflight_v1.py",
            "scripts/factor_rotation/freeze_reaka_intraday_K1_preflight_v1.py",
            "scripts/factor_rotation/materialize_reaka_intraday_K1_input_v1.py",
            "scripts/factor_rotation/run_reaka_intraday_K1_preflight_v1.py",
            "scripts/factor_rotation/validate_reaka_intraday_K1_preflight_v1.py",
            "scripts/factor_rotation/close_reaka_intraday_K1_preflight_v1.py",
            "tests/unit/test_reaka_intraday_k1_preflight_v1.py",
        ]
    )
    pytest = command_status(["pytest", "-q", "tests/unit/test_reaka_intraday_k1_preflight_v1.py"])
    if ruff["returncode"] != 0:
        blockers.append("ruff_failed")
    if pytest["returncode"] != 0:
        blockers.append("pytest_failed")
    report = write_json(
        REPORT,
        {
            "schema_id": VALIDATION_SCHEMA_ID,
            "status": "passed" if not blockers else "blocked",
            "contract_digest": contract["canonical_digest"],
            "clock_reports": clock_reports,
            "source_closure_mismatches": source_mismatches,
            "parameter_governance_digests": expected_governance,
            "checks": {"ruff": ruff, "pytest": pytest},
            "blockers": blockers,
            "formal_training_run": False,
            "score_materialization_run": False,
            "account_run": False,
            "production_authority": False,
        },
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if blockers:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
