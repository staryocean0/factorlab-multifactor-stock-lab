from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/reaka_r2_local_audit_v1_1.py"
SPEC = importlib.util.spec_from_file_location("reaka_r2_local_audit_v1_1", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _canonical(payload: dict) -> str:
    return MODULE.canonical_digest(payload)


def test_g1_raw_miss_does_not_accept_stale_embedded_canonical(tmp_path: Path) -> None:
    valid = {"selected_tool": "tool_A"}
    expected = _canonical(valid)
    tampered = {"selected_tool": "tool_B", "canonical_digest": expected}
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    observed = MODULE.digest_row(path, expected, "raw_sha256")
    assert observed["convention"] == "raw_sha256"
    assert observed["status"] == "byte_mismatch"
    assert _canonical(tampered) != expected


def test_g1_canonical_convention_recomputes_body_not_embedded_field(tmp_path: Path) -> None:
    valid = {"selected_tool": "tool_A"}
    expected = _canonical(valid)
    tampered = {"selected_tool": "tool_B", "canonical_digest": expected}
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    observed = MODULE.digest_row(path, expected, "canonical_digest")
    assert observed["convention"] == "canonical_digest"
    assert observed["status"] == "byte_mismatch"
    assert observed["recomputed_canonical_digest"] == _canonical(tampered)
    assert observed["embedded_canonical_digest"] == expected


def test_g2_ot1_parent_requires_finite_support_agreement() -> None:
    hist = MODULE.finite_err(np.array([0.5, np.nan]), np.array([0.5, 0.8]))
    fut = MODULE.finite_err(np.array([0.3]), np.array([0.3]))
    assert hist["violations"] == 0
    assert not MODULE.check_ok(hist)
    assert MODULE.check_ok(fut)
    report = {
        "checks": {
            "B": _ok_b(),
            "C_1430": _c(hist, fut),
            "C_1445": _c(fut, fut),
            "D_1430": _d(True, MODULE.finite_err(np.array([1.0]), np.array([1.0]))),
            "D_1445": _d(True, MODULE.finite_err(np.array([1.0]), np.array([1.0]))),
        }
    }
    judged = MODULE.rejudge_existing_report(report)
    assert judged["C"]["C_1430"]["passed"] is False
    assert judged["C"]["C_1445"]["passed"] is True


def test_g3_ot2_parent_consumes_stored_state_mismatch() -> None:
    mismatch = MODULE.finite_err(np.array([1.0]), np.array([2.0]))
    report = {
        "checks": {
            "B": _ok_b(),
            "C_1430": _c(
                MODULE.finite_err(np.array([1.0]), np.array([1.0])),
                MODULE.finite_err(np.array([1.0]), np.array([1.0])),
            ),
            "C_1445": _c(
                MODULE.finite_err(np.array([1.0]), np.array([1.0])),
                MODULE.finite_err(np.array([1.0]), np.array([1.0])),
            ),
            "D_1430": _d(True, mismatch),
            "D_1445": _d(True, MODULE.finite_err(np.array([1.0]), np.array([1.0]))),
        }
    }
    judged = MODULE.rejudge_existing_report(report)
    assert judged["D_full_reference_only"]["D_1430"]["passed"] is False
    assert judged["D_full_reference_only"]["D_1445"]["passed"] is True


def test_g4_empty_evaluation_fails_when_labelled_inference_exists() -> None:
    b = _ok_b()
    b["clocks"]["14:30"]["evaluation_rows"] = 0
    b["clocks"]["14:30"]["inference_rows"] = 2
    b["clocks"]["14:30"]["inference_without_future"] = 0
    b["clocks"]["14:30"]["evaluation_is_finite_future_subset"] = True
    report = {
        "checks": {
            "B": b,
            "C_1430": _c(
                MODULE.finite_err(np.array([1.0]), np.array([1.0])),
                MODULE.finite_err(np.array([1.0]), np.array([1.0])),
            ),
            "C_1445": _c(
                MODULE.finite_err(np.array([1.0]), np.array([1.0])),
                MODULE.finite_err(np.array([1.0]), np.array([1.0])),
            ),
            "D_1430": _d(True, MODULE.finite_err(np.array([1.0]), np.array([1.0]))),
            "D_1445": _d(True, MODULE.finite_err(np.array([1.0]), np.array([1.0]))),
        }
    }
    judged = MODULE.rejudge_existing_report(report)
    assert judged["B"]["clocks"]["14:30"]["evaluation_ok"] is False
    assert judged["B"]["passed"] is False


def test_g5_missing_datahub_sample_cannot_pass_parent() -> None:
    b = _ok_b()
    b["datahub_sample"] = {"status": "blocked_missing_dependency"}
    report = {
        "checks": {
            "B": b,
            "C_1430": _c(
                MODULE.finite_err(np.array([1.0]), np.array([1.0])),
                MODULE.finite_err(np.array([1.0]), np.array([1.0])),
            ),
            "C_1445": _c(
                MODULE.finite_err(np.array([1.0]), np.array([1.0])),
                MODULE.finite_err(np.array([1.0]), np.array([1.0])),
            ),
            "D_1430": _d(True, MODULE.finite_err(np.array([1.0]), np.array([1.0]))),
            "D_1445": _d(True, MODULE.finite_err(np.array([1.0]), np.array([1.0]))),
        }
    }
    judged = MODULE.rejudge_existing_report(report)
    assert judged["B"]["datahub_required_exact_passed"] is False
    assert judged["B"]["passed"] is False


def test_raw_match_still_passes_under_declared_raw(tmp_path: Path) -> None:
    path = tmp_path / "x.bin"
    path.write_bytes(b"abc")
    expected = "sha256:" + hashlib.sha256(b"abc").hexdigest()
    observed = MODULE.digest_row(path, expected, "raw_sha256")
    assert observed["status"] == "byte_match"
    assert observed["convention"] == "raw_sha256"


def _ok_b() -> dict:
    hist = {
        "compared": 2,
        "only_left_finite": 0,
        "only_right_finite": 0,
        "max_abs": 0.0,
        "p99_abs": 0.0,
        "violations": 0,
    }
    clock = {
        "history": hist,
        "future": hist,
        "history_passed": True,
        "future_passed": True,
        "clock_order_passed": True,
        "inference_rows": 2,
        "evaluation_rows": 2,
        "inference_without_future": 0,
        "evaluation_is_finite_future_subset": True,
    }
    return {
        "status": "passed",
        "axis": {"calendar_unique": True, "symbols_unique": True, "decision_unique_sorted": True},
        "datahub_sample": {"status": "passed"},
        "clocks": {"14:30": dict(clock), "14:45": dict(clock)},
    }


def _c(hist: dict, fut: dict) -> dict:
    return {
        "status": "passed",
        "history_on_stored_support": hist,
        "future_on_stored_support": fut,
        "uses_future_any": False,
        "fit_end_is_calendar_day_minus_1": True,
        "fold_is_symbol_position_mod_5": True,
        "ols_spot": {"status": "passed"},
    }


def _d(prefix_stable: bool, stored: dict) -> dict:
    return {
        "status": "passed",
        "transport_clock_match": True,
        "selection_clock": {"fresh_oos_claimed": False},
        "prefix": [{"family": "market", "prefix_stable": prefix_stable, "recomputed_vs_stored": stored}],
    }
