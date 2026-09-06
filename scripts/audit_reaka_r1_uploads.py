#!/usr/bin/env python3
"""Audit pinned uploads. Exit 0 reviewed, 1 invalid, 2 source evidence blocked."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from factor_lab.governance.reaka_foundation_contract import validate_foundation
from factor_lab.governance.reaka_r1_upload_audit import ArtifactReader, audit_uploads


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input-root", type=Path, required=True)
    p.add_argument("--input-commit", required=True)
    p.add_argument("--tree", type=Path, required=True)
    p.add_argument("--restored-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    foundation = validate_foundation(ROOT)
    if foundation["infrastructure_consistency"] != "passed":
        raise ValueError(f"foundation invalid: {foundation['errors']}")
    actual = subprocess.check_output(["git", "-C", str(args.input_root), "rev-parse", "HEAD"], text=True).strip()
    if actual != args.input_commit:
        raise ValueError("input checkout differs from pinned commit")
    previous = json.loads((ROOT / "cloud_results/first_round_rework_20260905/rework_result.json").read_text())
    tree = json.loads(args.tree.read_text())
    actual_tree = subprocess.check_output(["git", "-C", str(args.input_root), "rev-parse", "HEAD^{tree}"], text=True).strip()
    if actual_tree != tree["sha"]:
        raise ValueError("remote tree snapshot differs from pinned checkout")
    reader = ArtifactReader(args.input_root, args.restored_root)
    report = audit_uploads(reader, previous, tree)
    report["input_commit"] = actual
    report["input_tree"] = tree["sha"]
    report["foundation"] = foundation
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: report[k] for k in ("delivered_byte_acceptance", "next_step", "next_step_status", "errors")}, ensure_ascii=False))
    return 1 if report["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
