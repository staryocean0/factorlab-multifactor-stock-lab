from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from factor_lab.governance.canonicalization import canonical_digest
from factor_lab.governance.reaka_foundation_audit import (
    CLOSED_FLAGS,
    CURRENT_ENTRY,
    CURRENT_MANIFEST,
    FACTOR_ROOT,
    SEMANTICS,
    STAGE4_FILES,
    STAGE4_ROOT,
    STATE_ROOT,
    audit_foundation,
    file_digest,
)

CONTRACT = "docs/ops/stage4.json"
VALIDATION = "docs/ops/validation.json"
HANDOFF = "docs/user/handoff.md"
REVIEW = "docs/user/review.md"


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seal(root: Path, relative: str, payload: dict) -> dict:
    body = {key: value for key, value in payload.items() if key != "canonical_digest"}
    body["canonical_digest"] = canonical_digest(body)
    _write(root, relative, json.dumps(body, indent=2) + "\n")
    return body


def _load(root: Path, relative: str) -> dict:
    return json.loads((root / relative).read_text())


def _reseal_manifest(root: Path) -> None:
    manifest = _load(root, CURRENT_MANIFEST)
    for row in manifest["normative_roots"]:
        row["file_digest"] = file_digest(root / row["path"])
        if row["path"].endswith(".json"):
            row["canonical_digest"] = _load(root, row["path"])["canonical_digest"]
    _seal(root, CURRENT_MANIFEST, manifest)


@pytest.fixture
def package(tmp_path: Path) -> Path:
    closed = dict.fromkeys(CLOSED_FLAGS, False)
    _write(tmp_path, CURRENT_ENTRY, CURRENT_MANIFEST + "\n")
    checksum = "\n".join(f"{key} = {str(value).lower()}" for key, value in SEMANTICS.items())
    _write(tmp_path, HANDOFF, f"{CURRENT_MANIFEST}\n{CURRENT_ENTRY}\n{checksum}\n")
    _write(tmp_path, REVIEW, "Unsigned financial review request.\n")
    inputs: dict = {}
    for tree in ("formal", "isolated"):
        inputs[tree] = {}
        for name, base in (("state_months.csv", STATE_ROOT), ("monthly_selector_panel.csv", FACTOR_ROOT)):
            relative = f"{base}/{tree}/{name}"
            _write(tmp_path, relative, "period,value\n2015-01,1\n")
            inputs[tree][name] = file_digest(tmp_path / relative)
    contract = _seal(tmp_path, CONTRACT, {
        "authority": closed, "fresh_oos": False, "semantic_invariants": SEMANTICS,
        "input_digests": inputs, "output_inventory": sorted(STAGE4_FILES | {"result.json"}),
    })
    results = {}
    for tree in ("formal", "isolated"):
        base = f"{STAGE4_ROOT}/{tree}"
        for name in sorted(STAGE4_FILES - {"advisor_interpretation_request.json"}):
            _write(tmp_path, f"{base}/{name}", "financial_verdict\nwaiting_user_review\n")
        _write(tmp_path, f"{base}/pairing_panel.csv",
               "period,source_period,data_role,decision_clock\n2015-01,2014-12,development_material_pairing,14:30\n")
        request = _seal(tmp_path, f"{base}/advisor_interpretation_request.json", {
            "semantic_invariants": SEMANTICS, "stage5_execution_allowed": False,
            "production_authority": False, "advisor_interpretation_receipt_present": False,
        })
        results[tree] = _seal(tmp_path, f"{base}/result.json", {
            **closed, "contract_digest": contract["canonical_digest"],
            "advisor_interpretation_receipt_present": False,
            "advisor_request_digest": request["canonical_digest"],
            "output_digests": {name: file_digest(tmp_path / base / name) for name in sorted(STAGE4_FILES)},
        })
    _seal(tmp_path, VALIDATION, {
        **closed, "contract_digest": contract["canonical_digest"],
        "formal_result_digest": results["formal"]["canonical_digest"],
        "isolated_result_digest": results["isolated"]["canonical_digest"],
        "review_request_digest": file_digest(tmp_path / REVIEW),
        "advisor_interpretation_receipt_present": False,
    })
    manifest = {
        **closed, "semantic_invariants": SEMANTICS,
        "next_legal_action": "user_financial_review_of_stage4_evidence",
        "default_unlisted_classification": "historical_or_specialized_no_current_normative_authority",
        "normative_roots": [
            {"role": role, "path": relative}
            for role, relative in (
                ("current_entry", CURRENT_ENTRY), ("current_handoff", HANDOFF),
                ("current_stage4_contract", CONTRACT), ("current_stage4_validation", VALIDATION),
                ("current_stage4_review_request", REVIEW),
            )
        ],
        "revoked_current_normative_paths": [],
    }
    _seal(tmp_path, CURRENT_MANIFEST, manifest)
    _reseal_manifest(tmp_path)
    return tmp_path


def _codes(report: dict) -> set[str]:
    return {row["code"] for row in report["findings"]}


def test_complete_available_closure_passes_without_mutating_files(package: Path) -> None:
    before = {str(path): path.read_bytes() for path in package.rglob("*") if path.is_file()}
    report = audit_foundation(package)
    assert report["status"] == "passed", report
    assert report["audit_execution_completed"] is True
    assert report["scientific_result_validated"] is False
    assert report["financial_receipt_signed"] is False
    assert before == {str(path): path.read_bytes() for path in package.rglob("*") if path.is_file()}


def test_missing_isolated_evidence_is_incomplete_not_replayed(package: Path) -> None:
    shutil.rmtree(package / STAGE4_ROOT / "isolated")
    report = audit_foundation(package)
    assert report["status"] == "incomplete"
    assert report["hard_error_count"] == 0
    assert report["foundation_readiness"] == "blocked"


def test_both_output_trees_changed_identically_still_fail_frozen_hashes(package: Path) -> None:
    for tree in ("formal", "isolated"):
        _write(package, f"{STAGE4_ROOT}/{tree}/annual_dispersion.csv", "lift\n999\n")
    report = audit_foundation(package)
    assert report["status"] == "failed"
    assert "frozen_digest_mismatch" in _codes(report)
    assert "formal_isolated_mismatch" not in _codes(report)


def test_changed_input_is_rejected_even_when_output_receipts_are_unchanged(package: Path) -> None:
    _write(package, f"{STATE_ROOT}/formal/state_months.csv", "period,value\n2015-01,2\n")
    report = audit_foundation(package)
    assert report["status"] == "failed"
    assert "frozen_digest_mismatch" in _codes(report)


def test_self_consistent_result_for_another_contract_is_rejected(package: Path) -> None:
    relative = f"{STAGE4_ROOT}/formal/result.json"
    result = _load(package, relative)
    result["contract_digest"] = "sha256:" + "0" * 64
    _seal(package, relative, result)
    assert "result_contract_mismatch" in _codes(audit_foundation(package))


def test_self_consistent_financial_signature_is_rejected(package: Path) -> None:
    relative = f"{STAGE4_ROOT}/formal/result.json"
    result = _load(package, relative)
    result["advisor_interpretation_receipt_present"] = True
    _seal(package, relative, result)
    assert "financial_receipt_forged" in _codes(audit_foundation(package))


def test_semantic_authority_change_fails_even_with_recomputed_canonical_digest(package: Path) -> None:
    manifest = _load(package, CURRENT_MANIFEST)
    manifest["semantic_invariants"]["user_supplies_operator_count"] = True
    _seal(package, CURRENT_MANIFEST, manifest)
    assert "semantic_invariants_mismatch" in _codes(audit_foundation(package))


def test_missing_historical_source_is_gap_and_not_a_current_hash_repair(package: Path) -> None:
    manifest = _load(package, CURRENT_MANIFEST)
    manifest["base_source_closure"] = {"old/not-shipped.py": "sha256:" + "0" * 64}
    _seal(package, CURRENT_MANIFEST, manifest)
    report = audit_foundation(package)
    assert report["status"] == "incomplete"
    assert report["hard_error_count"] == 0


def test_current_document_byte_drift_is_hard_error(package: Path) -> None:
    _write(package, CURRENT_ENTRY, CURRENT_MANIFEST + "\nSilently changed current workflow.\n")
    assert "frozen_digest_mismatch" in _codes(audit_foundation(package))


def test_frozen_stale_handoff_is_visible_without_rewriting_it(package: Path) -> None:
    text = (package / HANDOFF).read_text().replace("@1.2", "@1.0").replace("_v1_2", "")
    _write(package, HANDOFF, text)
    _reseal_manifest(package)
    report = audit_foundation(package)
    assert report["status"] == "incomplete"
    assert "frozen_handoff_version_conflict" in _codes(report)


def test_boolean_authority_cannot_be_integer_zero(package: Path) -> None:
    manifest = _load(package, CURRENT_MANIFEST)
    manifest["model_training_allowed"] = 0
    _seal(package, CURRENT_MANIFEST, manifest)
    assert "downstream_authority_not_closed" in _codes(audit_foundation(package))


def test_manifest_path_escape_is_rejected(package: Path) -> None:
    manifest = _load(package, CURRENT_MANIFEST)
    manifest["normative_roots"][0]["path"] = "../outside.md"
    _seal(package, CURRENT_MANIFEST, manifest)
    report = audit_foundation(package)
    assert "path_outside_package" in _codes(report)
    assert "current_entry_version_mismatch" in _codes(report)


def test_duplicate_month_cannot_pass_as_independent_monthly_support(package: Path) -> None:
    path = package / STAGE4_ROOT / "formal/pairing_panel.csv"
    text = path.read_text()
    path.write_text(text + text.splitlines(keepends=True)[1])
    report = audit_foundation(package)
    assert "duplicate_condition_month" in _codes(report)
    assert report["foundation_ready"] is False


def test_same_month_state_is_rejected(package: Path) -> None:
    path = package / STAGE4_ROOT / "formal/pairing_panel.csv"
    path.write_text(path.read_text().replace("2014-12", "2015-01"))
    assert "state_is_not_prior_month" in _codes(audit_foundation(package))
