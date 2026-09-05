#!/usr/bin/env python3
"""Validate the project-level strategy-slice rebuild artifact bundle."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
for location in (ROOT, ROOT / "src"):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from factor_lab.governance.canonicalization import canonical_digest  # noqa: E402
from factor_lab.market_state.timing_annual_session_rebuild import (  # noqa: E402
    CODE_VERSION,
    SCHEMA_ID,
    SOURCE_REFS,
    validate_strategy_slice_rebuild_contract,
)

DEFAULT_OUTPUT = ROOT / "output/market-state-foundation/strategy-slice-rebuild/current"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _source_digest_recoverable(root: Path, relative: str, expected: str) -> bool:
    """Accept current bytes or the exact historical blob sealed originally."""

    current = root / relative
    if current.is_file() and _sha256(current) == expected:
        return True
    history = subprocess.run(
        ["git", "log", "--all", "--format=%H", "--", relative],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if history.returncode != 0:
        return False
    for commit in history.stdout.splitlines():
        blob = subprocess.run(
            ["git", "show", f"{commit}:{relative}"],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if blob.returncode == 0 and hashlib.sha256(blob.stdout).hexdigest() == expected:
            return True
    return False


def validate_bundle(output_dir: Path) -> dict[str, object]:
    manifest = _load_json(output_dir / "manifest.json")
    if (
        manifest.get("schema_id") != f"{SCHEMA_ID}_manifest@1.0"
        or manifest.get("code_version") != CODE_VERSION
        or manifest.get("production_authority") is not False
    ):
        raise ValueError("strategy-slice manifest identity drifted")
    expected_names = {
        "contract.json",
        "annual_session_atlas.csv",
        "session_protocol.json",
        "constraint_governance.json",
        "report_zh.md",
    }
    artifacts = cast(list[dict[str, object]], manifest.get("artifacts", []))
    if {str(item.get("path")) for item in artifacts} != expected_names:
        raise ValueError("strategy-slice artifact inventory is incomplete")
    for item in artifacts:
        path = output_dir / str(item["path"])
        if not path.is_file() or _sha256(path) != item.get("sha256"):
            raise ValueError(f"strategy-slice artifact hash mismatch: {path.name}")
        if path.stat().st_size != int(cast(int, item["bytes"])):
            raise ValueError(f"strategy-slice artifact size drifted: {path.name}")
    source_digests = cast(dict[str, str], manifest.get("source_digests", {}))
    if set(source_digests) != set(SOURCE_REFS):
        raise ValueError("strategy-slice source inventory is incomplete")
    for relative, digest in source_digests.items():
        if not _source_digest_recoverable(ROOT, relative, digest):
            raise ValueError(f"strategy-slice sealed source bytes unrecoverable: {relative}")
    contract = _load_json(output_dir / "contract.json")
    validate_strategy_slice_rebuild_contract(contract)
    if manifest.get("contract_digest") != canonical_digest(contract):
        raise ValueError("strategy-slice contract binding drifted")
    with (output_dir / "annual_session_atlas.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        slices = list(csv.DictReader(handle))
    if (
        len(slices) != 12
        or slices[0]["start"] != "2009-01-01"
        or slices[-1]["end_exclusive"] != "2021-01-01"
    ):
        raise ValueError("annual-session atlas drifted")
    if any(
        left["end_exclusive"] != right["start"]
        for left, right in zip(slices, slices[1:], strict=False)
    ):
        raise ValueError("annual-session atlas contains gaps or overlap")
    if (output_dir / "overlap_audit.json").exists() or (
        output_dir / "overlap_pairs.csv"
    ).exists():
        raise ValueError("retired rolling-window artifacts remain in the current bundle")
    session_protocol = _load_json(output_dir / "session_protocol.json")
    constraints = _load_json(output_dir / "constraint_governance.json")
    if session_protocol != contract["session_protocol"] or constraints != contract["constraint_governance"]:
        raise ValueError("split annual-session governance drifted from the contract")
    return contract


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    contract = validate_bundle(cast(Path, args.output_dir).resolve())
    print(
        json.dumps(
            {
                "status": "passed",
                "schema_id": contract["schema_id"],
                "annual_session_count": 12,
                "rolling_windows_allowed": False,
                "batch_scientific_judgment_allowed": False,
                "consumed_lockbox_reuse_allowed": False,
                "production_authority": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
