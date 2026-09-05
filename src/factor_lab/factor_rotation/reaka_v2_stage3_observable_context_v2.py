# pyright: reportAny=false
"""REAKA V2 Stage3 successor: S_obs support only, no operator authority."""

from __future__ import annotations

from pathlib import Path
from typing import Final, cast

import pandas as pd

from factor_lab.governance.reaka_multifactor_infrastructure_v1 import (
    SEMANTIC_INVARIANTS,
    canonical_valid,
    file_digest,
    read_json,
    validate_stage_payload,
    write_json,
)

ROOT: Final = Path(__file__).resolve().parents[3]
CONTRACT: Final = ROOT / "docs/ops/reaka_v2_stage3_observable_context@2.0.json"
OLD_ROOT: Final = ROOT / "output/factor-rotation/reaka_v2_stage3_state_episode_atlas_v1_2011_2025"
OUTPUT_ROOT: Final = ROOT / "output/factor-rotation/reaka_v2_stage3_observable_context_v2_2011_2025"
CORRECTION: Final = ROOT / "docs/ops/reaka_v2_stage3_observable_context_authority_correction@1.0.json"
ALLOWED_INPUT_FILES: Final = (
    "state_months.csv",
    "state_episodes.csv",
    "state_support.csv",
    "transition_counts.csv",
)
OUTPUT_FILES: Final = (
    "measurement_receipt.json",
    "observable_context_support_certificate.json",
)
SOURCE_FILES: Final = (
    "docs/ops/reaka_multifactor_semantic_ontology@1.0.json",
    "docs/ops/reaka_multifactor_current_manifest@1.0.json",
    "docs/ops/state_factor_research_state_machine@2.0.json",
    "docs/ops/reaka_prediction_content_rollback@2.0.json",
    "docs/ops/reaka_v2_stage3_observable_context_authority_correction@1.0.json",
    "docs/ops/reaka_v2_stage3_observable_context_whitepaper.md",
    "docs/user/reaka_v2_stage3_observable_context_workflow.md",
    "docs/user/reaka_multifactor_current_workflow_v1_1.md",
    "src/factor_lab/factor_rotation/reaka_v2_stage3_observable_context_v2.py",
    "scripts/factor_rotation/build_reaka_v2_stage3_observable_context_v2.py",
    "scripts/factor_rotation/run_reaka_v2_stage3_observable_context_v2.py",
    "scripts/factor_rotation/validate_reaka_v2_stage3_observable_context_v2.py",
    "scripts/factor_rotation/close_reaka_v2_stage3_observable_context_v2.py",
    "tests/unit/test_reaka_v2_stage3_observable_context_v2.py",
)


def source_closure() -> dict[str, str]:
    return {relative: file_digest(ROOT / relative) for relative in SOURCE_FILES}


def load_contract() -> dict[str, object]:
    payload = read_json(CONTRACT)
    if not canonical_valid(payload):
        raise PermissionError("reaka_v2_stage3_v2_contract_digest_invalid")
    if payload.get("source_closure") != source_closure():
        raise PermissionError("reaka_v2_stage3_v2_source_closure_drift")
    if payload.get("stage") != "stage3_observable_context_support":
        raise PermissionError("reaka_v2_stage3_v2_stage_invalid")
    authority = cast(dict[str, object], payload["authority"])
    for field in (
        "stage4_execution_allowed",
        "model_training_allowed",
        "account_execution_allowed",
        "production_authority",
    ):
        if authority.get(field) is not False:
            raise PermissionError(f"reaka_v2_stage3_v2_authority_open:{field}")
    return payload


def _development(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.loc[frame["data_role"].eq("development_material_state_certificate")]


def build_certificate(
    months: pd.DataFrame,
    episodes: pd.DataFrame,
    support: pd.DataFrame,
    transitions: pd.DataFrame,
) -> dict[str, object]:
    dev_months = _development(months)
    dev_episodes = _development(episodes)
    dev_support = _development(support)
    dev_transitions = _development(transitions)
    state_rows: dict[str, object] = {}
    records = cast(list[dict[str, object]], dev_support.to_dict(orient="records"))
    for row in records:
        trend = str(row["trend"])
        state_rows[trend] = {
            "temporal_month_count": int(cast(int, row["temporal_month_count"])),
            "prevalence": float(cast(float, row["prevalence"])),
            "raw_episode_count": int(cast(int, row["raw_independent_episode_count"])),
            "persistent_episode_count": int(cast(int, row["persistent_independent_episode_count"])),
            "median_raw_duration_months": float(cast(float, row["median_raw_duration_months"])),
            "maximum_duration_months": int(cast(int, row["maximum_duration_months"])),
        }
    physical_transitions = int(dev_transitions["transition_count"].sum())
    switches = int(
        dev_transitions.loc[
            dev_transitions["from_state"] != dev_transitions["to_state"],
            "transition_count",
        ].sum()
    )
    payload: dict[str, object] = {
        "schema_id": "factorlab.observable_context_support_certificate@2.0",
        "status": "observable_context_ready_for_stage4",
        "stage": "stage3_observable_context_support",
        "object": "S_obs",
        "scope": "global_market",
        "state_identity": {
            "carrier": "CN_A_CLOUDRIDGE_BETA_EQW",
            "grain": "monthly",
            "source": "previous_calendar_month",
            "trend_states": ["up", "sideways", "down"],
            "deadband": "one_prior_daily_sigma_times_sqrt_source_month_trading_days",
            "volatility_role": "diagnostic_label_only_not_episode_split",
        },
        "PIT": {
            "source_month_must_precede_decision_month": True,
            "future_decision_year_read": False,
        },
        "episodes": {
            "development_episode_rows": int(len(dev_episodes)),
            "by_state": state_rows,
            "minimum_persistent_duration_months": 2,
        },
        "transitions": {
            "physical_month_transitions": physical_transitions,
            "state_switches": switches,
        },
        "duration_prevalence": state_rows,
        "temporal_cross_sectional_support": {
            "temporal_decision_months": int(len(dev_months)),
            "cross_sectional_rows": int(dev_months["cross_sectional_row_count"].sum()),
            "cross_sectional_rows_do_not_multiply_global_episodes": True,
        },
        "support_caveat": ("thin persistent up/down segments require Stage4 uncertainty, dispersion and preregistered shrinkage treatment"),
        "operator_decision_out_of_scope": True,
        "stage4_requires_new_result_free_contract": True,
        "stage4_execution_allowed": False,
        "model_training_allowed": False,
        "account_execution_allowed": False,
        "semantic_invariants": SEMANTIC_INVARIANTS,
        "fresh_oos": False,
        "production_authority": False,
    }
    validate_stage_payload("stage3_observable_context_support", payload)
    return payload


def execute_tree(*, tree: str) -> dict[str, object]:
    if tree not in {"formal", "isolated"}:
        raise ValueError("reaka_v2_stage3_v2_tree_invalid")
    contract = load_contract()
    output = OUTPUT_ROOT / tree
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"reaka_v2_stage3_v2_output_exists:{output}")
    inputs = OLD_ROOT / tree
    months = pd.read_csv(inputs / "state_months.csv")
    episodes = pd.read_csv(inputs / "state_episodes.csv")
    support = pd.read_csv(inputs / "state_support.csv")
    transitions = pd.read_csv(inputs / "transition_counts.csv")
    certificate = build_certificate(months, episodes, support, transitions)
    receipt = write_json(
        output / "measurement_receipt.json",
        {
            "schema_id": "factorlab.reaka_v2_stage3_measurement_reuse_receipt@2.0",
            "status": "retained_measurements_reused_without_market_or_model_reexecution",
            "input_digests": {name: file_digest(inputs / name) for name in ALLOWED_INPUT_FILES},
            "input_files_read": list(ALLOWED_INPUT_FILES),
            "market_data_read": False,
            "factor_return_read": False,
            "model_run": False,
            "account_run": False,
            "semantic_invariants": SEMANTIC_INVARIANTS,
            "production_authority": False,
        },
    )
    cert = write_json(output / "observable_context_support_certificate.json", certificate)
    result = write_json(
        output / "result.json",
        {
            "schema_id": "factorlab.reaka_v2_stage3_observable_context_result@2.0",
            "status": "stage3_observable_context_complete_waiting_user_stage4_checkpoint",
            "contract_digest": contract["canonical_digest"],
            "measurement_receipt_digest": receipt["canonical_digest"],
            "certificate_digest": cert["canonical_digest"],
            "output_file_digests": {name: file_digest(output / name) for name in OUTPUT_FILES},
            "stage4_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    return result
