from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts/reaka_r3_x_fine_compare.py"
MODULE_ROOT = ROOT / "src/factor_lab/factor_rotation"


def git_blob(path: Path) -> str:
    proc = subprocess.run(["git", "hash-object", str(path)], cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def constant(text: str, name: str) -> str:
    match = re.search(rf'^{name}\s*=\s*"([0-9a-f]{{40}})"$', text, flags=re.MULTILINE)
    assert match, name
    return match.group(1)


def test_cli_frozen_blobs_match_current_fine_sources():
    text = CLI.read_text(encoding="utf-8")
    assert constant(text, "EXPECTED_FINE_RUNNER_GIT_BLOB") == git_blob(MODULE_ROOT / "reaka_r3_x_fine_runner.py")
    assert constant(text, "EXPECTED_FINE_PREFLIGHT_GIT_BLOB") == git_blob(MODULE_ROOT / "reaka_r3_x_fine_preflight.py")


def test_cli_preflight_precedes_any_fine_run():
    text = CLI.read_text(encoding="utf-8")
    source_guard = text.index("source_entrypoints = validate_theme_entrypoints()")
    preflight = text.index("pre = preflight.run(")
    fine = text.index("result = fine.run(")
    assert source_guard < preflight < fine
    assert "--preflight-only" in text
    assert '"new_fits": 0' in text
    assert '"new_inference": 0' in text


def test_fresh_reload_also_checks_frozen_sources_first():
    text = CLI.read_text(encoding="utf-8")
    branch = text.index("if args.reload_fine_worker:")
    guard = text.index("validate_theme_entrypoints()", branch)
    reload_call = text.index("fine.reload_arm_worker(", branch)
    assert branch < guard < reload_call


def test_cli_passes_repository_root_to_preflight_and_runner():
    text = CLI.read_text(encoding="utf-8")
    assert "timeiso_root, xcoarse_root, ROOT," in text
    assert 'ROOT / "src/factor_lab/factor_rotation",\n            FACTORLAB_ROOT' not in text
