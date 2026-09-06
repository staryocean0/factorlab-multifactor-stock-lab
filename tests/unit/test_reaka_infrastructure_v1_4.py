"""Current-tree navigation, semantics and honest scope counterexamples."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from factor_lab.governance.reaka_infrastructure_v1_4 import (
    POINTER, assess_dependencies, current_sources, heading_anchors, link_issues,
    markdown_links, navigation_inventory, read_json, safe_path, validate_infrastructure,
)

ROOT = Path(__file__).resolve().parents[2]


def save(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def package(tmp_path: Path) -> Path:
    # Copy only structural sources and link targets, never market panels.
    pointer = read_json(ROOT / POINTER)
    manifest = read_json(ROOT / pointer["manifest"])
    paths = current_sources(pointer["manifest"], manifest)
    for directory in ("docs", ".codex", ".github"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    for path in paths:
        source = ROOT / path
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    state = read_json(ROOT / manifest["state"])
    for section, field in (("r1", "receipt"), ("r2", "recovery_request"), ("historical_stage4", "receipt")):
        path = state[section][field]
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    # The route to the historical textual explanation is deliberately present.
    path = "cloud_results/first_round_rework_20260906/rework.md"
    (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / path, tmp_path / path)
    for path in ("NOTICE.md",):
        shutil.copyfile(ROOT / path, tmp_path / path)
    (tmp_path / "tests/unit").mkdir(parents=True, exist_ok=True)
    return tmp_path


def manifest_at(root: Path) -> tuple[Path, dict]:
    path = root / read_json(root / POINTER)["manifest"]
    return path, read_json(path)


def test_live_tree_has_consistent_routes_and_no_market_prerequisite(package: Path) -> None:
    assert not (package / "data").exists()
    report = validate_infrastructure(package)
    assert report["infrastructure_consistency"] == "passed", report["errors"]
    assert report["dataset_readiness"] == "not_evaluated"
    assert report["research_permission"] == "not_granted_by_infrastructure_validation"
    assert report["production_authority"] is False


def test_ordinary_document_edit_does_not_require_resealing(package: Path) -> None:
    with (package / "README.md").open("a", encoding="utf-8") as out:
        out.write("\n正常解释性修订，无需重封历史摘要。\n")
    assert not validate_infrastructure(package)["errors"]


@pytest.mark.parametrize("key", ["larger_gate_emphasizes_return_encoding", "financial_residual_equals_latent_residual", "residual_predictor_is_mandatory", "teacher_forced_denoising_is_history_only_forecast_evidence", "stage4_realized_contribution_is_forward_predictive_increment"])
def test_wrong_math_is_still_rejected(package: Path, key: str) -> None:
    _, manifest = manifest_at(package)
    path = package / manifest["semantics"]
    semantics = read_json(path)
    semantics["invariants"][key] = not semantics["invariants"][key]
    save(path, semantics)
    assert f"semantic invariant drift: {key}" in validate_infrastructure(package)["errors"]


def test_boolean_zero_does_not_grant_or_satisfy_authority(package: Path) -> None:
    path, manifest = manifest_at(package)
    manifest["production_authority"] = 0
    save(path, manifest)
    assert validate_infrastructure(package)["errors"]


def test_zero_cannot_replace_a_false_mathematical_statement(package: Path) -> None:
    _, manifest = manifest_at(package)
    path = package / manifest["semantics"]
    semantics = read_json(path)
    semantics["invariants"]["residual_predictor_is_mandatory"] = 0
    save(path, semantics)
    assert validate_infrastructure(package)["errors"]


def test_global_wait_state_cannot_return_as_manifest_permission(package: Path) -> None:
    path, manifest = manifest_at(package)
    manifest["next_legal_action"] = "wait_for_all_data"
    save(path, manifest)
    assert any("temporary global permission" in x for x in validate_infrastructure(package)["errors"])


def test_semantics_cannot_become_a_temporary_execution_menu(package: Path) -> None:
    _, manifest = manifest_at(package)
    path = package / manifest["semantics"]
    semantics = read_json(path)
    semantics["research_actions"] = {"train": False}
    save(path, semantics)
    assert any("temporary execution permissions" in x for x in validate_infrastructure(package)["errors"])


def test_updated_progress_needs_no_new_math_contract(package: Path) -> None:
    _, manifest = manifest_at(package)
    path = package / manifest["state"]
    state = read_json(path)
    state["current_task"] = "another_authorized_independent_source_audit"
    save(path, state)
    assert not validate_infrastructure(package)["errors"]


def test_missing_data_blocks_only_its_own_dependency_check(package: Path) -> None:
    blocked = assess_dependencies(package, ["data/not_delivered.npy"])
    assert blocked["availability"] == "blocked_for_this_task"
    assert assess_dependencies(package, ["README.md"])["availability"] == "available"
    assert assess_dependencies(package, [])["availability"] == "available"
    assert not blocked["pit_verified"]
    assert not validate_infrastructure(package)["errors"]


@pytest.mark.parametrize("path", ["../escape", "/tmp/escape", "a/../../escape", "C:\\escape", "", "a\\..\\escape"])
def test_unsafe_paths_rejected(package: Path, path: str) -> None:
    with pytest.raises(ValueError):
        safe_path(package, path)


def test_symlink_escape_rejected(package: Path, tmp_path_factory) -> None:
    other = tmp_path_factory.mktemp("outside") / "secret"
    other.write_text("outside")
    (package / "escape").symlink_to(other)
    with pytest.raises(ValueError):
        safe_path(package, "escape")


def test_duplicate_json_keys_and_nonfinite_are_rejected(tmp_path: Path) -> None:
    file = tmp_path / "bad.json"
    for text in ('{"x":1,"x":2}', '{"x":NaN}', '[]'):
        file.write_text(text)
        with pytest.raises(ValueError):
            read_json(file)


def test_duplicate_reading_route_is_rejected(package: Path) -> None:
    path, manifest = manifest_at(package)
    manifest["reading_routes"]["takeover"].append("AGENTS.md")
    save(path, manifest)
    assert any("duplicate paths" in x for x in validate_infrastructure(package)["errors"])


def test_broken_current_link_is_a_failure(package: Path) -> None:
    with (package / "README.md").open("a") as out:
        out.write("\n[bad](docs/not-there.md)\n")
    assert any("missing_target" in x for x in validate_infrastructure(package)["errors"])


def test_broken_historical_link_is_reported_without_blocking_current(package: Path) -> None:
    (package / "docs/history-only.md").write_text("[old](not-there.md)\n")
    report = validate_infrastructure(package, inventory=True)
    assert not report["errors"]
    assert any(x["source"] == "docs/history-only.md" for x in report["navigation_inventory"]["issues"])


def test_legacy_entry_cannot_replace_current_router(package: Path) -> None:
    (package / "ai-readme.md").write_text("Use old current@1.2 and repeat twelve annual stages.\n")
    assert any("entry does not route" in x for x in validate_infrastructure(package)["errors"])


def test_markdown_reference_heading_and_code_handling(tmp_path: Path) -> None:
    (tmp_path / "source.md").write_text("[a](target.md#hello)\n[b][ref]\n[ref]: target.md#missing\n```\n[x](not-a-link.md)\n```\n")
    (tmp_path / "target.md").write_text("# Hello\n# Hello\n")
    assert heading_anchors((tmp_path / "target.md").read_text()) == {"hello", "hello-1"}
    assert "not-a-link.md" not in markdown_links((tmp_path / "source.md").read_text())
    issues = link_issues(tmp_path, "source.md")
    assert len(issues) == 1 and issues[0]["reason"] == "missing_heading_anchor"


def test_missing_evidence_locator_is_not_silently_accepted(package: Path) -> None:
    _, manifest = manifest_at(package)
    path = package / manifest["state"]
    state = read_json(path)
    state["r1"]["receipt"] = "missing-receipt.json"
    save(path, state)
    assert any("missing evidence locator" in x for x in validate_infrastructure(package)["errors"])


def _runner():
    spec = importlib.util.spec_from_file_location("infra_test_runner", ROOT / "scripts/run_infrastructure_tests.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_tests_are_not_hidden_and_restored_dependencies_rejoin(tmp_path: Path) -> None:
    runner = _runner()
    legacy = next(iter(runner.KNOWN_LEGACY_DEPENDENCIES))
    (tmp_path / legacy).parent.mkdir(parents=True)
    (tmp_path / legacy).write_text("def test_old(): pass\n")
    fresh = "tests/unit/test_new_unknown.py"
    (tmp_path / fresh).write_text("import nonexistent_current_dependency\n")
    scope = runner.test_scope(tmp_path)
    assert fresh in scope["selected_unit_modules"]
    assert scope["deferred_historical_modules"][0]["test_module"] == legacy
    assert not scope["full_repository_validated"]
    for dep in runner.KNOWN_LEGACY_DEPENDENCIES[legacy]:
        (tmp_path / dep).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / dep).write_text("# dependency restored\n")
    scope = runner.test_scope(tmp_path)
    assert legacy in scope["selected_unit_modules"]
    assert not scope["deferred_historical_modules"]


def test_junit_skips_and_errors_remain_visible(tmp_path: Path) -> None:
    path = tmp_path / "tests.xml"
    path.write_text('<testsuites><testsuite><testcase><skipped/></testcase><testcase><error/></testcase></testsuite></testsuites>')
    result = _runner().junit_summary(path)
    assert result == {"tests": 2, "skipped": 1, "errors": 1, "failures": 0}


def test_actual_ci_routes_do_not_hide_current_failures() -> None:
    text = (ROOT / ".github/workflows/ci.yml").read_text()
    foundation, rest = text.split("  dataset-integrity:", 1)
    assert "python scripts/validate_reaka_foundation.py" in foundation
    assert "python scripts/run_infrastructure_tests.py" in foundation
    assert "continue-on-error" not in text
    assert "--report-only" not in foundation
    assert "sparse-checkout:" in foundation
    assert "python scripts/validate_theme_package.py" in rest
    assert "full-unit" in rest


def test_active_skill_no_longer_imposes_the_archived_protocol() -> None:
    text = (ROOT / ".codex/skills/strategy-slice-rebuild/SKILL.md").read_text()
    assert "CURRENT.json" in text
    assert "Use twelve sequential natural-year" not in text
    assert "Use for every strategy change" not in text
    interface = (ROOT / ".codex/skills/strategy-slice-rebuild/agents/openai.yaml").read_text()
    assert "CURRENT.json" in interface
    assert "run sequential annual blind tests" not in interface


def test_cli_bad_pointer_fails_machine_readably(tmp_path: Path) -> None:
    (tmp_path / "CURRENT.json").write_text("{")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/validate_reaka_foundation.py"), "--root", str(tmp_path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert json.loads(result.stdout)["infrastructure_consistency"] == "failed"
