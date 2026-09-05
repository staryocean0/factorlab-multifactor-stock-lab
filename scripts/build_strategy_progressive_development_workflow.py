#!/usr/bin/env python3
# pyright: reportAny=false
# pyright: reportArgumentType=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnusedCallResult=false
"""Materialize progressive strategy-development and post-training audit infrastructure."""

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
    build_reaka_p7_compatibility_map,
    build_reaka_p7_progression_migration_ledger,
)
from factor_lab.governance.canonicalization import canonical_digest  # noqa: E402
from factor_lab.governance.strategy_progressive_development import (  # noqa: E402
    SOURCE_REFS,
    load_frozen_contracts,
)

DEFAULT_OUTPUT = ROOT / "output/governance/strategy-progressive-development/current"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    output_dir = cast(Path, args.output_dir).resolve()
    if output_dir.exists() and not args.overwrite:
        raise FileExistsError(f"output already exists: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    progression, post_training = load_frozen_contracts(ROOT)
    compatibility = build_reaka_p7_compatibility_map()
    migration = build_reaka_p7_progression_migration_ledger()
    boundary = {
        "schema_id": "factorlab.strategy_progressive_hard_soft_boundary@1.0",
        "hard_validity_gate": progression["hard_validity_gate"],
        "progression_retention": progression["progression_retention"],
        "candidate_promotion": progression["candidate_promotion"],
        "fresh_validation": progression["fresh_validation"],
        "production_authorization": progression["production_authorization"],
    }
    boundary["canonical_digest"] = canonical_digest(boundary)
    audit_findings = {
        "schema_id": "factorlab.strategy_infrastructure_backtrace@1.0",
        "earliest_top_level_governance_drift": "reaka_controller_succession_audit@189.0",
        "earliest_unplanned_execution_stop": "reaka_controller_succession_audit@195.0",
        "root_causes": [
            "post-training account completion was strategy-specific rather than project-level",
            "fixed model scores did not guarantee complete PIT market/account support",
            "progression retention and candidate promotion shared one eligibility boolean",
            "top-level discovery remained at succession @188 while P7 advanced to @219",
        ],
        "historical_contracts_mutated": False,
        "post_2020_data_read": False,
    }
    audit_findings["canonical_digest"] = canonical_digest(audit_findings)
    report = "\n".join(
        (
            "# 策略渐进开发基础设施 V1",
            "",
            "- 金融、数学、时序、完整账户、确定性和权限是不可补偿硬门。",
            "- 同口径真实改善只需超过数值重放容差即可保留，不设经济强度门。",
            "- 稳定性、分布、成本和风险门只控制候选晋升，不删除 progression material。",
            "- 每轮模型/分数冻结后必须执行 A0—A7 训练后账户审计。",
            "- A4 盲测旧政策与 A5 打开完整候选族必须是两个物理命令。",
            "- REAKA P7 历史无晋升结论不变，但五类弱进步被索引为下一轮材料。",
            "- 所有回溯状态 fresh_oos=false、production_authority=false。",
            "",
        )
    )
    artifacts: dict[str, object] = {
        "progression_contract.json": progression,
        "post_training_account_audit_contract.json": post_training,
        "hard_soft_boundary.json": boundary,
        "infrastructure_backtrace.json": audit_findings,
        "reaka_p7_compatibility.json": compatibility,
        "reaka_p7_progression_migration.json": migration,
    }
    for name, payload in artifacts.items():
        _write_json(output_dir / name, payload)
    (output_dir / "report_zh.md").write_text(report, encoding="utf-8")

    artifact_names = (*artifacts, "report_zh.md")
    manifest: dict[str, object] = {
        "schema_id": "factorlab.strategy_progressive_development_manifest@1.0",
        "progression_contract_digest": progression["canonical_digest"],
        "post_training_contract_digest": post_training["canonical_digest"],
        "artifacts": [
            {
                "path": name,
                "sha256": _sha256(output_dir / name),
                "bytes": (output_dir / name).stat().st_size,
            }
            for name in artifact_names
        ],
        "source_digests": {relative: _sha256(ROOT / relative) for relative in SOURCE_REFS},
        "fresh_oos": False,
        "production_authority": False,
    }
    manifest["canonical_digest"] = canonical_digest(manifest)
    _write_json(output_dir / "manifest.json", manifest)
    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
