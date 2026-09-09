#!/usr/bin/env python3
"""Reproduce guard weaknesses in the 8ffdd90 R2 auditor using small fixtures.

Review evidence only, not production validation or a data/PIT certificate.
The digest helper below and predicate expressions are transcribed from the
GitHub-fetched source (blob a003fe75fbb127761b63b963c320deecd88de539).
We execute these isolated excerpts, not the complete pyarrow-dependent auditor.
A reproduced counterexample means a weakness was found, NOT that the auditor
or a real strategy passed. No market data, network, Actions or trading calls.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any
import numpy as np

ATOL = 1.0e-6
RTOL = 1.0e-5

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()

# Exact function excerpt, including the unsafe fallback being reviewed.
def digest_row(path: Path, expected: str | None, convention: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "path": str(path),
        "expected": expected,
        "convention": convention,
    }
    if not path.exists():
        row["status"] = "missing"
        return row
    row["size_bytes"] = path.stat().st_size
    row["raw_sha256"] = sha256_file(path)
    if expected is None:
        row["status"] = "present_unbound"
    elif convention == "raw_sha256":
        if row["raw_sha256"] == expected:
            row["status"] = "byte_match"
        elif path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            canonical = payload.get("canonical_digest")
            row["embedded_canonical_digest"] = canonical
            if canonical == expected:
                row["status"] = "byte_match"
                row["convention"] = "canonical_digest"
            else:
                row["status"] = "byte_mismatch"
        else:
            row["status"] = "byte_mismatch"
    else:
        row["raw_matches_recorded"] = row["raw_sha256"] == expected
        row["status"] = "present_unbound"
    return row

# Exact two numeric helper excerpts.
def finite_err(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    mask = np.isfinite(left) & np.isfinite(right)
    only_left = int((np.isfinite(left) & ~np.isfinite(right)).sum())
    only_right = int((~np.isfinite(left) & np.isfinite(right)).sum())
    if not mask.any():
        return {
            "compared": 0,
            "only_left_finite": only_left,
            "only_right_finite": only_right,
            "max_abs": None,
            "p99_abs": None,
            "violations": 0,
        }
    delta = np.abs(left[mask].astype(np.float64) - right[mask].astype(np.float64))
    scale = np.abs(right[mask].astype(np.float64))
    violations = int((delta > (ATOL + RTOL * scale)).sum())
    return {
        "compared": int(mask.sum()),
        "only_left_finite": only_left,
        "only_right_finite": only_right,
        "max_abs": float(delta.max()),
        "p99_abs": float(np.quantile(delta, 0.99)),
        "violations": violations,
    }

def check_ok(err: dict[str, Any]) -> bool:
    return (
        err["compared"] > 0
        and err["only_left_finite"] == 0
        and err["only_right_finite"] == 0
        and err["violations"] == 0
    )

def canonical(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "canonical_digest"}
    # The repository's canonicalization.py uses this representation.
    return "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

def run_probes() -> dict[str, Any]:
    findings = []
    with tempfile.TemporaryDirectory(prefix="r2-cloud-review-") as folder:
        path = Path(folder) / "selection.json"
        valid = {"selected_tool": "tool_A"}
        expected = canonical(valid)
        tampered = {"selected_tool": "tool_B", "canonical_digest": expected}
        path.write_text(json.dumps(tampered), encoding="utf-8")
        observed = digest_row(path, expected, "raw_sha256")
        reproduced = observed["status"] == "byte_match" and canonical(tampered) != expected
        assert reproduced
        findings.append({"id": "G1", "source_function": "digest_row", "counterexample_reproduced": reproduced,
                         "observed": observed["status"], "body_digest_matches_expected": False,
                         "issue": "stale embedded digest accepted; raw failure silently changes convention"})

    # audit_ot1's exact final predicate with all unrelated preconditions true.
    hist_stored = finite_err(np.array([0.5, np.nan]), np.array([0.5, 0.8]))
    fut_stored = finite_err(np.array([0.3]), np.array([0.3]))
    residual_cal_ok = residual_sym_ok = fold_ok = fit_check = True
    uses_future = False
    ols = {"status": "passed"}
    passed = (
        residual_cal_ok
        and residual_sym_ok
        and fold_ok
        and (not uses_future)
        and fit_check
        and hist_stored["violations"] == 0
        and fut_stored["violations"] == 0
        and hist_stored["compared"] > 0
        and fut_stored["compared"] > 0
        and ols["status"] == "passed"
    )
    assert passed and not check_ok(hist_stored)
    findings.append({"id": "G2", "source_function": "audit_ot1", "counterexample_reproduced": True,
                     "observed_passed": passed, "comparison": hist_stored,
                     "issue": "partial missing reconstruction on stored finite support ignored by final gate"})

    # audit_ot2's exact final predicate; stored-state discrepancy is omitted.
    mismatch = finite_err(np.array([1.0]), np.array([2.0]))
    prefix_rows = [{"prefix_stable": True, "recomputed_vs_stored": mismatch}]
    transport_clock = True
    tools = {"fresh_oos": False}
    passed = all(item["prefix_stable"] for item in prefix_rows) and transport_clock and tools.get("fresh_oos") is False
    assert passed and not check_ok(mismatch)
    findings.append({"id": "G3", "source_function": "audit_ot2", "counterexample_reproduced": True,
                     "observed_passed": passed, "stored_comparison": mismatch,
                     "issue": "stored-state mismatch calculated but excluded from final gate"})

    # audit_p61's exact evaluation-subset expression.
    infer = np.array([[0, 0], [1, 0]])
    infer_future = np.array([True, True])
    ev = np.array([], dtype=np.int64)
    eval_ok = bool(
        len(ev) == 0
        or (int(ev.max()) < len(infer) and bool(np.array_equal(np.sort(ev), np.flatnonzero(infer_future))))
    )
    assert eval_ok and not np.array_equal(ev, np.flatnonzero(infer_future))
    findings.append({"id": "G4", "source_function": "audit_p61", "counterexample_reproduced": True,
                     "observed_evaluation_subset_passed": eval_ok,
                     "issue": "empty evaluation accepted despite two finite future-labelled inference rows"})

    # The sampled DataHub status check in audit_p61's top-level conjunction.
    sample = {"status": "blocked_missing_dependency"}
    observed_gate = sample["status"] != "failed"
    assert observed_gate and sample["status"] != "passed"
    findings.append({"id": "G5", "source_function": "audit_p61", "counterexample_reproduced": True,
                     "parent_gate_accepts_missing_sample": observed_gate,
                     "issue": "parent passed can include blocked raw-source sampling; split arithmetic and source status"})
    return {"schema_id": "factorlab.r2_cloud_review_probes@1.0",
            "reviewed_commit": "8ffdd90b5a664337058fad4a301f85ddfa6aa599",
            "reviewed_source_blob": "a003fe75fbb127761b63b963c320deecd88de539",
            "execution": "current_cloud_session_isolated_source_excerpts_and_synthetic_fixtures",
            "python": sys.version, "numpy": np.__version__,
            "counterexamples_reproduced": len(findings), "findings": findings,
            "full_original_module_executed": False, "real_P6_data_read": False,
            "actual_submission_gate_failures_proven": False,
            "interpretation": "guard bugs reproduced, not evidence that actual arrays are corrupt. Submitted C/D numeric fields report zero support differences and zero store mismatches; preserve those scoped observations.",
            "full_pit_certified": False, "actions_executed": False}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_probes()
    text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(text)
    print(text)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
