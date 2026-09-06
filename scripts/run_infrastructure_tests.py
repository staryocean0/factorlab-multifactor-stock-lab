#!/usr/bin/env python3
"""Run current unit coverage with explicit, dependency-scoped legacy gaps.

New tests are included by default. Only exact historical modules named below
can be deferred, and only while their named source dependencies are absent.
No pytest skip or ignore option is passed. Full-unit validation remains a
separate command; selected coverage success never certifies the whole repo.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PREFIX = "src/factor_lab/factor_rotation/"
FILTER_SOURCE = "src/factor_lab/filtering/cloudridge_3_0_hybrid_filter_bank.py"
KNOWN_LEGACY_DEPENDENCIES = {
    "tests/unit/test_reaka_current_k1_account_ledgers_v1.py": [
        PREFIX + "reaka_intraday_target_fill_v1.py",
        PREFIX + "reaka_intraday_orthogonal_ot_v1.py",
        PREFIX + "reaka_intraday_k1_clock_attribution_v1.py",
        FILTER_SOURCE,
    ],
    "tests/unit/test_reaka_intraday_k1_fit_prefix_successor_v1.py": [
        PREFIX + "reaka_intraday_k1_clock_attribution_v1.py",
    ],
    "tests/unit/test_reaka_intraday_orthogonal_ot_v1.py": [FILTER_SOURCE],
}
# The filter dependency is from the actual merge-collection failure, not a guess:
# Actions 34012432073, job 101430431354, snapshot b21bb752146d898f1d0d7c3a8728402912ba811f.
# Both imports pass through orthogonal_factor_timing_state_v1.py:17.


def test_scope(root: Path) -> dict[str, Any]:
    files = sorted(path.relative_to(root).as_posix() for path in (root / "tests/unit").rglob("test_*.py"))
    selected: list[str] = []
    deferred: list[dict[str, Any]] = []
    for file in files:
        missing = [dep for dep in KNOWN_LEGACY_DEPENDENCIES.get(file, []) if not (root / dep).is_file()]
        if missing:
            deferred.append({"test_module": file, "missing_source_dependencies": missing,
                             "status": "not_executed_not_passed",
                             "provenance": "docs/ops/infrastructure_audit_20260906.md"})
        else:
            selected.append(file)
    return {"discovered_unit_modules": files, "selected_unit_modules": selected,
            "deferred_historical_modules": deferred,
            "all_unit_modules_selected": not deferred,
            "full_repository_validated": False,
            "historical_fixture_commit": "3a75376e1f7f871bb72e48f886c275919b3c9671"}


def junit_summary(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    return {"tests": len(cases),
            "failures": sum(len(case.findall("failure")) for case in cases),
            "errors": sum(len(case.findall("error")) for case in cases),
            "skipped": sum(len(case.findall("skipped")) for case in cases)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=Path("foundation-validation"))
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = test_scope(root)
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    report["checkout_commit"] = git.stdout.strip() if git.returncode == 0 else None
    report["python"] = sys.version
    report["platform"] = platform.platform()
    report["dependencies"] = {}
    for name in ("pytest", "numpy", "pandas", "pyarrow", "torch"):
        try:
            report["dependencies"][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            report["dependencies"][name] = "not_installed"
    xml = out / "tests.xml"
    command = [sys.executable, "-m", "pytest", "-q", *report["selected_unit_modules"], f"--junitxml={xml}"]
    report["command"] = command
    report["status"] = "running"
    path = out / "test_scope.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not report["selected_unit_modules"]:
        report["status"] = "failed_empty_scope"
        code = 1
    else:
        code = subprocess.run(command, cwd=root).returncode
        try:
            summary = junit_summary(xml)
            report["junit"] = summary
            if not summary["tests"] or summary["failures"] or summary["errors"] or summary["skipped"]:
                code = code or 1
        except (OSError, ET.ParseError) as exc:
            report["junit_error"] = str(exc)
            code = code or 1
        report["status"] = "passed_selected_scope" if code == 0 else "failed"
    report["exit_code"] = code
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report.get(key) for key in ("status", "junit", "deferred_historical_modules", "full_repository_validated")}, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
