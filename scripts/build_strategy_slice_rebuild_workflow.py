#!/usr/bin/env python3
"""Materialize the project-level annual-session whole-policy rebuild contract."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import asdict
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
    build_strategy_slice_rebuild_contract,
    canonical_pre2021_annual_sessions,
    validate_strategy_slice_rebuild_contract,
)

DEFAULT_OUTPUT = ROOT / "output/market-state-foundation/strategy-slice-rebuild/current"


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
    for obsolete_name in ("overlap_audit.json", "overlap_pairs.csv"):
        obsolete = output_dir / obsolete_name
        if obsolete.exists():
            obsolete.unlink()

    contract = build_strategy_slice_rebuild_contract()
    validate_strategy_slice_rebuild_contract(contract)
    slices = canonical_pre2021_annual_sessions()
    _write_json(output_dir / "contract.json", contract)
    with (output_dir / "annual_session_atlas.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(slices[0])))
        writer.writeheader()
        writer.writerows(asdict(item) for item in slices)
    _write_json(output_dir / "session_protocol.json", contract["session_protocol"])
    _write_json(output_dir / "constraint_governance.json", contract["constraint_governance"])
    report = "\n".join(
        (
            "# 策略自然年研究会话—整案重建基础设施",
            "",
            "- 默认图谱：2009—2020十二个互不重叠自然年，不使用半年错位滚动窗。",
            "- 每年必须独立完成旧快照盲测、图形事件归因、整案重建、策略快照与链式回执；上一年未封口不得开始下一年。",
            "- 脚本只允许准备证据，禁止批量生成解释、根因、硬约束或年度裁决。",
            "- 并行实验只共享共同起点和原始数据；策略、参数、候选、台账、结果与结论互相禁读。",
            "- 原始症状与未解决根因不得成为硬约束；同一根因最多晋级一条硬义务。",
            "- 硬义务数量不得超过完整候选族可表达自由度，否则报告候选族不足。",
            "- 只剩基准或账户等价方案时必须报告无增量后继，禁止包装成新版本。",
            "- 每次会话都从共同起点与本支线累计材料整案重建；禁止给上一胜者打补丁。",
            "- 2020会话后的最终快照尚无新鲜挑战，只能标记为等待未来验证的研究候选。",
            "- 2021—2026已消费，当前隔离分支不得复用其细节或聚合结果选策略。",
            "- 本基础设施不授予参数、路由、架构锁定或生产权。",
            "",
        )
    )
    (output_dir / "report_zh.md").write_text(report, encoding="utf-8")

    artifact_names = (
        "contract.json",
        "annual_session_atlas.csv",
        "session_protocol.json",
        "constraint_governance.json",
        "report_zh.md",
    )
    manifest: dict[str, object] = {
        "schema_id": f"{SCHEMA_ID}_manifest@1.0",
        "code_version": CODE_VERSION,
        "contract_digest": canonical_digest(contract),
        "artifacts": [
            {
                "path": name,
                "sha256": _sha256(output_dir / name),
                "bytes": (output_dir / name).stat().st_size,
            }
            for name in artifact_names
        ],
        "source_digests": {relative: _sha256(ROOT / relative) for relative in SOURCE_REFS},
        "production_authority": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
