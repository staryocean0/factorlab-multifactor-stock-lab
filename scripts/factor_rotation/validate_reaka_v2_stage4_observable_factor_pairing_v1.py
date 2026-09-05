#!/usr/bin/env python3
from __future__ import annotations

import pandas as pd

from factor_lab.factor_rotation.reaka_v2_stage4_observable_factor_pairing_v1 import (
    EVIDENCE_ROOT,
    OUTPUT_FILES,
    OUTPUT_ROOT,
    load_contract,
)
from factor_lab.governance.reaka_multifactor_infrastructure_v1 import canonical_valid, file_digest, read_json, recursive_keys, write_json


def _markdown(summary: pd.DataFrame) -> str:
    dev = summary.loc[summary["data_role"].eq("development_material_pairing")]
    repeat = summary.loc[summary["data_role"].eq("consumed_repeat_comparison_no_retune")]
    lines = [
        "# REAKA V2 Stage4 用户金融审核请求",
        "",
        "机器只报告方向证据，不代签金融结论。请逐项判断保留、修改或拒绝。",
        "",
        "## 2011-2016开发材料",
        "",
        "| 假设 | 时钟 | 月内/外 | pooled lift | episode同向 | 年度同向 | 机器描述 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in dev.to_dict(orient="records"):
        months = f"{row['n_in_months']}/{row['n_out_months']}"
        episode_sign = f"{row['aligned_episode_count']}/{row['factor_active_episode_count']}"
        annual_sign = f"{row['aligned_year_count']}/{row['comparable_year_count']}"
        lines.append(
            f"| {row['hypothesis_id']} | {row['decision_clock']} | {months} | "
            f"{float(row['pooled_lift']):.6f} | {episode_sign} | {annual_sign} | "
            f"{row['machine_directional_evidence']} |"
        )
    lines.extend(
        [
            "",
            "## 2018-2025已消费对照",
            "",
            "| 假设 | 时钟 | pooled lift | episode同向 | 年度同向 | 机器描述 |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for row in repeat.to_dict(orient="records"):
        episode_sign = f"{row['aligned_episode_count']}/{row['factor_active_episode_count']}"
        annual_sign = f"{row['aligned_year_count']}/{row['comparable_year_count']}"
        lines.append(
            f"| {row['hypothesis_id']} | {row['decision_clock']} | "
            f"{float(row['pooled_lift']):.6f} | {episode_sign} | {annual_sign} | "
            f"{row['machine_directional_evidence']} |"
        )
    lines.extend(
        [
            "",
            "## 请用户审核",
            "",
            "1. 哪些机制符合您的金融理解并可进入Stage5输入装配？",
            "2. 哪些应拒绝或重述？",
            "3. 是否接受2018-2025只能作已消费对照、不能冒充fresh OOS？",
            "",
            "Stage5、训练、K容量和账户在回执前保持关闭。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    contract = load_contract()
    formal_root = OUTPUT_ROOT / "formal"
    isolated_root = OUTPUT_ROOT / "isolated"
    for name in (*OUTPUT_FILES, "result.json"):
        if file_digest(formal_root / name) != file_digest(isolated_root / name):
            raise ValueError(f"stage4_tree_byte_mismatch:{name}")
    formal = read_json(formal_root / "result.json")
    isolated = read_json(isolated_root / "result.json")
    request = read_json(formal_root / "advisor_interpretation_request.json")
    for payload in (formal, isolated, request):
        if not canonical_valid(payload):
            raise ValueError("stage4_output_digest_invalid")
    if formal.get("legacy_same_month_trend_used") is not False:
        raise ValueError("stage4_legacy_same_month_state_used")
    panel = pd.read_csv(formal_root / "pairing_panel.csv")
    source = pd.PeriodIndex(panel["source_period"], freq="M")
    decision = pd.PeriodIndex(panel["period"], freq="M")
    if not all(left + 1 == right for left, right in zip(source, decision, strict=True)):
        raise ValueError("stage4_state_not_previous_calendar_month")
    summary = pd.read_csv(formal_root / "hypothesis_summary.csv")
    if len(summary) != 30 or len(summary.loc[summary["data_role"].eq("development_material_pairing")]) != 10:
        raise ValueError("stage4_summary_inventory_invalid")
    if set(summary["factor"]) != {"index", "industry"} or "size" in set(summary["factor"]):
        raise ValueError("stage4_factor_scope_invalid")
    if set(summary["financial_verdict"]) != {"waiting_user_review"}:
        raise ValueError("stage4_financial_verdict_forged")
    if request.get("advisor_interpretation_receipt_present") is not False:
        raise ValueError("stage4_advisor_receipt_forged")
    forbidden = {"operator_count_N", "N_effective", "K2_allowed", "state_to_operator_mapping"}
    if recursive_keys(formal) & forbidden or recursive_keys(request) & forbidden:
        raise ValueError("stage4_operator_authority_present")
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    review_path = EVIDENCE_ROOT / "advisor_interpretation_request.md"
    review_path.write_text(_markdown(summary), encoding="utf-8")
    write_json(
        EVIDENCE_ROOT / "validation_report.json",
        {
            "schema_id": "factorlab.reaka_v2_stage4_observable_factor_pairing_validation@1.0",
            "status": "passed_machine_evidence_waiting_user_financial_review",
            "contract_digest": contract["canonical_digest"],
            "formal_result_digest": formal["canonical_digest"],
            "isolated_result_digest": isolated["canonical_digest"],
            "formal_isolated_byte_identical_files": [*OUTPUT_FILES, "result.json"],
            "review_request_digest": file_digest(review_path),
            "hypothesis_count": 5,
            "advisor_interpretation_receipt_present": False,
            "stage5_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
