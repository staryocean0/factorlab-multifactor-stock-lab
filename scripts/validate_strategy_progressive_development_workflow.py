#!/usr/bin/env python3
# pyright: reportAny=false
# pyright: reportArgumentType=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnusedCallResult=false
"""Validate progressive strategy-development and post-training audit artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
for location in (ROOT, ROOT / "src"):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from factor_lab.factor_rotation.reaka_post_training_account_adapter import (  # noqa: E402
    validate_reaka_p7_adapter,
)
from factor_lab.governance.canonicalization import canonical_digest  # noqa: E402
from factor_lab.governance.sealed_source import resolve_sealed_source_digest  # noqa: E402
from factor_lab.governance.strategy_progressive_development import (  # noqa: E402
    SOURCE_REFS,
    validate_post_training_contract,
    validate_progression_contract,
)

DEFAULT_OUTPUT = ROOT / "output/governance/strategy-progressive-development/current"
EXPECTED_ARTIFACTS = {
    "progression_contract.json",
    "post_training_account_audit_contract.json",
    "hard_soft_boundary.json",
    "infrastructure_backtrace.json",
    "reaka_p7_compatibility.json",
    "reaka_p7_progression_migration.json",
    "report_zh.md",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def validate_bundle(output_dir: Path) -> dict[str, object]:
    manifest = _load_json(output_dir / "manifest.json")
    body = dict(manifest)
    stored = body.pop("canonical_digest", None)
    if stored != canonical_digest(body):
        raise ValueError("strategy progression manifest digest mismatch")
    if (
        manifest.get("schema_id") != "factorlab.strategy_progressive_development_manifest@1.0"
        or manifest.get("fresh_oos") is not False
        or manifest.get("production_authority") is not False
    ):
        raise ValueError("strategy progression manifest authority drifted")
    artifacts = cast(list[dict[str, object]], manifest.get("artifacts", []))
    if {str(row.get("path")) for row in artifacts} != EXPECTED_ARTIFACTS:
        raise ValueError("strategy progression artifact inventory is incomplete")
    for row in artifacts:
        path = output_dir / str(row["path"])
        if not path.is_file() or _sha256(path) != row.get("sha256"):
            raise ValueError(f"strategy progression artifact digest mismatch: {path.name}")
        if path.stat().st_size != int(cast(int, row["bytes"])):
            raise ValueError(f"strategy progression artifact size mismatch: {path.name}")
    source_digests = cast(dict[str, str], manifest.get("source_digests", {}))
    if set(source_digests) != set(SOURCE_REFS):
        raise ValueError("strategy progression source inventory is incomplete")
    for relative, digest in source_digests.items():
        resolution = resolve_sealed_source_digest(ROOT, relative, digest)
        if not resolution.recoverable:
            raise ValueError(f"strategy progression source is unrecoverable: {relative}")

    progression = _load_json(output_dir / "progression_contract.json")
    post_training = _load_json(output_dir / "post_training_account_audit_contract.json")
    validate_progression_contract(progression)
    validate_post_training_contract(post_training)
    if manifest.get("progression_contract_digest") != progression.get("canonical_digest"):
        raise ValueError("manifest progression contract binding drifted")
    if manifest.get("post_training_contract_digest") != post_training.get("canonical_digest"):
        raise ValueError("manifest post-training contract binding drifted")
    compatibility = _load_json(output_dir / "reaka_p7_compatibility.json")
    migration = _load_json(output_dir / "reaka_p7_progression_migration.json")
    adapter_blockers = validate_reaka_p7_adapter(compatibility, migration)
    if adapter_blockers:
        raise ValueError("REAKA progression adapter invalid:" + ",".join(adapter_blockers))
    backtrace = _load_json(output_dir / "infrastructure_backtrace.json")
    if (
        backtrace.get("earliest_top_level_governance_drift")
        != "reaka_controller_succession_audit@189.0"
        or backtrace.get("earliest_unplanned_execution_stop")
        != "reaka_controller_succession_audit@195.0"
        or backtrace.get("historical_contracts_mutated") is not False
    ):
        raise ValueError("infrastructure backtrace drifted")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = validate_bundle(cast(Path, args.output_dir).resolve())
    print(
        json.dumps(
            {
                "status": "passed",
                "progression_contract_digest": manifest["progression_contract_digest"],
                "post_training_contract_digest": manifest["post_training_contract_digest"],
                "retention_strength_gate": False,
                "post_training_stage_count": 8,
                "fresh_oos": False,
                "production_authority": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
