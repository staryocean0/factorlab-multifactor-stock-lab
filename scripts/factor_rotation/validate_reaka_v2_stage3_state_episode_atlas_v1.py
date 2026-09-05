#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

import pandas as pd

from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    canonical_valid,
    file_digest,
    read_json,
    write_json,
)
from factor_lab.factor_rotation.reaka_v2_stage3_state_episode_atlas_v1 import (
    SCIENCE_FILES,
    load_contract,
    scientific_body,
)
from factor_lab.portfolio.post_training_strategy_science_acceptance import (
    assert_no_scientific_wall_clock,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--isolated-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    contract = load_contract()
    formal = read_json(args.formal_root / "result.json")
    isolated = read_json(args.isolated_root / "result.json")
    for payload in (formal, isolated):
        if not canonical_valid(payload):
            raise ValueError("reaka_v2_stage3_result_digest_invalid")
        assert_no_scientific_wall_clock(payload)
    if scientific_body(formal) != scientific_body(isolated):
        raise ValueError("reaka_v2_stage3_result_mismatch")
    for name in (*SCIENCE_FILES, "result.json"):
        if file_digest(args.formal_root / name) != file_digest(args.isolated_root / name):
            raise ValueError(f"reaka_v2_stage3_byte_mismatch:{name}")

    months = pd.read_csv(args.formal_root / "state_months.csv")
    episodes = pd.read_csv(args.formal_root / "state_episodes.csv")
    support = pd.read_csv(args.formal_root / "state_support.csv")
    transitions = pd.read_csv(args.formal_root / "transition_counts.csv")
    certificate = read_json(args.formal_root / "state_learnability_certificate.json")
    comparison = read_json(args.formal_root / "comparison_summary.json")
    for payload in (certificate, comparison):
        if not canonical_valid(payload):
            raise ValueError("reaka_v2_stage3_science_digest_invalid")
        assert_no_scientific_wall_clock(payload)

    if int(months["decision_year"].max()) > 2025:
        raise ValueError("reaka_v2_stage3_post2025_decision_row")
    source = pd.PeriodIndex(months["source_period"], freq="M")
    decision = pd.PeriodIndex(months["decision_period"], freq="M")
    if not all(left + 1 == right for left, right in zip(source, decision, strict=True)):
        raise ValueError("reaka_v2_stage3_not_previous_calendar_month")
    development = months.loc[months["data_role"].eq("development_material_state_certificate")]
    if len(development) != 68:
        raise ValueError("reaka_v2_stage3_development_month_count")
    dev_transitions = transitions.loc[transitions["data_role"].eq("development_material_state_certificate")]
    if int(dev_transitions["transition_count"].sum()) != 67:
        raise ValueError("reaka_v2_stage3_transition_count")
    if (
        int(
            dev_transitions.loc[
                dev_transitions["from_state"] != dev_transitions["to_state"],
                "transition_count",
            ].sum()
        )
        != 26
    ):
        raise ValueError("reaka_v2_stage3_switch_count")
    dev_support = support.loc[support["data_role"].eq("development_material_state_certificate")]
    persistent = {str(row.trend): int(row.persistent_independent_episode_count) for row in dev_support.itertuples(index=False)}
    if persistent != {"up": 1, "sideways": 9, "down": 1}:
        raise ValueError(f"reaka_v2_stage3_persistent_episode_counts:{persistent}")
    if bool(episodes.loc[episodes["persistent_ge_2_months"], "duration_months"].lt(2).any()):
        raise ValueError("reaka_v2_stage3_persistent_episode_too_short")
    required = cast(dict[str, object], certificate["required_stage3_items"])
    if set(required) != set(cast(list[str], contract["stage3_required_items"])):
        raise ValueError("reaka_v2_stage3_required_item_set")
    if not all(value is True for value in required.values()):
        raise ValueError("reaka_v2_stage3_required_item_missing")
    if certificate.get("composite_learnability_route") != "slow_context_low_rank_modulator":
        raise ValueError("reaka_v2_stage3_route")
    for forbidden in (
        "discrete_operator_expert_allowed",
        "unshrunk_full_matrix_allowed",
        "standalone_rank_expert_allowed",
        "stage6_training_allowed",
    ):
        if certificate.get(forbidden) is not False:
            raise ValueError(f"reaka_v2_stage3_forbidden_authority:{forbidden}")
    if comparison.get("route_selected_from_development_only") is not True:
        raise ValueError("reaka_v2_stage3_repeat_period_influenced_route")
    if formal.get("model_training_executed") is not False or formal.get("account_executed") is not False:
        raise ValueError("reaka_v2_stage3_downstream_execution")

    args.evidence_root.mkdir(parents=True, exist_ok=True)
    write_json(
        args.evidence_root / "validation_report.json",
        {
            "schema_id": "factorlab.reaka_v2_stage3_state_episode_atlas_validation@1.0",
            "status": "passed",
            "contract_digest": contract["canonical_digest"],
            "formal_result_digest": formal["canonical_digest"],
            "isolated_result_digest": isolated["canonical_digest"],
            "certificate_digest": certificate["canonical_digest"],
            "formal_isolated_byte_identical_files": [*SCIENCE_FILES, "result.json"],
            "development_decision_months": 68,
            "development_physical_transitions": 67,
            "development_state_switches": 26,
            "persistent_episode_count": persistent,
            "composite_learnability_route": "slow_context_low_rank_modulator",
            "stage4_execution_allowed": False,
            "model_training_executed": False,
            "account_executed": False,
            "post_2025_decision_rows": 0,
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
