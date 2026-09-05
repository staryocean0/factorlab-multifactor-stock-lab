from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from factor_lab.governance.reaka_foundation_contract import (
    CURRENT_MANIFEST, SEMANTICS_PATH, canonical_digest, file_digest,
    require_research_action, validate_foundation,
)

ROOT = Path(__file__).resolve().parents[2]


def load(root: Path, path: str) -> dict:
    return json.loads((root / path).read_text(encoding="utf-8"))


def seal(root: Path, path: str, body: dict) -> None:
    body["canonical_digest"] = canonical_digest(body)
    (root / path).write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def reseal_manifest(root: Path) -> None:
    manifest = load(root, CURRENT_MANIFEST)
    for rows in manifest["five_in_one"].values():
        for row in rows:
            row["file_digest"] = file_digest(root / row["path"])
    seal(root, CURRENT_MANIFEST, manifest)


@pytest.fixture
def package(tmp_path: Path) -> Path:
    manifest = load(ROOT, CURRENT_MANIFEST)
    paths = {CURRENT_MANIFEST} | {
        row["path"] for rows in manifest["five_in_one"].values() for row in rows
    }
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path


def test_current_contract_passes_without_market_data_or_old_evidence(package: Path) -> None:
    assert not (package / "data").exists()
    assert not (package / "output").exists()
    report = validate_foundation(package)
    assert report["infrastructure_consistency"] == "passed", report["errors"]
    assert report["data_readiness"] == "not_evaluated"
    assert report["historical_evidence_readiness"] == "blocked"
    assert report["scientific_acceptance"] == "not_established"
    assert report["research_execution_allowed"] is False


@pytest.mark.parametrize("surface", ["documentation", "whitepaper", "code", "tests", "workflow"])
def test_a_change_on_any_surface_breaks_frozen_source_identity(package: Path, surface: str) -> None:
    row = load(package, CURRENT_MANIFEST)["five_in_one"][surface][0]
    path = package / row["path"]
    path.write_bytes(path.read_bytes() + b"\nchanged\n")
    report = validate_foundation(package)
    assert report["infrastructure_consistency"] == "failed"
    assert any("source drift:" in error for error in report["errors"])


@pytest.mark.parametrize("key", [
    "larger_gate_emphasizes_return_encoding", "residual_predictor_is_mandatory",
    "stage4_realized_contribution_is_forward_predictive_increment",
    "teacher_forced_denoising_is_history_only_forecast_evidence",
])
def test_resealing_does_not_make_wrong_semantics_valid(package: Path, key: str) -> None:
    semantics = load(package, SEMANTICS_PATH)
    semantics["invariants"][key] = not semantics["invariants"][key]
    seal(package, SEMANTICS_PATH, semantics)
    reseal_manifest(package)
    assert f"semantic invariant drift: {key}" in validate_foundation(package)["errors"]


def test_integer_boolean_substitution_is_not_an_authority_receipt(package: Path) -> None:
    manifest = load(package, CURRENT_MANIFEST)
    manifest["research_actions"]["train"] = 0
    seal(package, CURRENT_MANIFEST, manifest)
    assert "research execution unexpectedly open: train" in validate_foundation(package)["errors"]


@pytest.mark.parametrize("path", [CURRENT_MANIFEST, SEMANTICS_PATH])
def test_self_signed_open_training_is_rejected_before_any_research(package: Path, path: str) -> None:
    document = load(package, path)
    document["research_actions"]["train"] = True
    seal(package, path, document)
    reseal_manifest(package)
    with pytest.raises(PermissionError, match="foundation invalid"):
        require_research_action(package, "train")


def test_code_pass_does_not_allow_training_or_unknown_actions(package: Path) -> None:
    assert validate_foundation(package)["infrastructure_consistency"] == "passed"
    for action in ("train", "stage4_execute", "invented_action"):
        with pytest.raises(PermissionError, match="blocks research action"):
            require_research_action(package, action)


def test_legacy_status_cannot_be_restored_by_resealing(package: Path) -> None:
    manifest = load(package, CURRENT_MANIFEST)
    manifest["next_legal_action"] = "user_financial_review_of_stage4_evidence"
    seal(package, CURRENT_MANIFEST, manifest)
    assert "next action drift" in validate_foundation(package)["errors"]


def test_required_guard_cannot_be_removed_from_source_inventory(package: Path) -> None:
    manifest = load(package, CURRENT_MANIFEST)
    target = "scripts/factor_rotation/close_reaka_v2_stage4_observable_factor_pairing_v1.py"
    manifest["five_in_one"]["workflow"] = [
        row for row in manifest["five_in_one"]["workflow"] if row["path"] != target
    ]
    seal(package, CURRENT_MANIFEST, manifest)
    assert any("missing required surface paths: workflow" in e for e in validate_foundation(package)["errors"])


def test_entry_must_route_to_current_even_after_resealing(package: Path) -> None:
    (package / "README.md").write_text("Use current@1.2 and approve the old Stage4 evidence.\n")
    reseal_manifest(package)
    assert "entry not routed to current: README.md" in validate_foundation(package)["errors"]


def test_path_escape_is_rejected(package: Path) -> None:
    manifest = load(package, CURRENT_MANIFEST)
    manifest["five_in_one"]["code"].append({"path": "../outside.py", "file_digest": "sha256:" + "0" * 64})
    seal(package, CURRENT_MANIFEST, manifest)
    assert "unsafe source path: ../outside.py" in validate_foundation(package)["errors"]


def test_malformed_contract_has_machine_readable_failure_and_nonzero_exit(package: Path) -> None:
    (package / SEMANTICS_PATH).write_text("[")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_reaka_foundation.py"), "--root", str(package)],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["infrastructure_consistency"] == "failed"
    assert report["errors"]


def test_ci_keeps_strict_foundation_gate_independent_from_dataset_gate() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    foundation, dataset = workflow.split("  dataset-integrity:", 1)
    assert "python scripts/validate_reaka_foundation.py" in foundation
    assert "pytest -q tests/unit" in foundation
    assert "--report-only" not in foundation
    assert "continue-on-error" not in workflow
    assert "python scripts/validate_theme_package.py" not in foundation
    assert "python scripts/validate_theme_package.py" in dataset
    assert "if: github.event_name == 'workflow_dispatch'" in dataset
    assert "needs:" not in foundation
