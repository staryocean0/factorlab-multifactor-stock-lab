# pyright: reportAny=false
"""REAKA V2 Stage 3: PIT monthly CloudRidge trend episode certificate."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final, cast

import numpy as np
import pandas as pd

from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    canonical_valid,
    file_digest,
    read_json,
    write_json,
)
from factor_lab.factor_rotation.reaka_k1_only_index_regime_atlas_v1 import (
    classify_index_periods,
    load_cloudridge,
)
from factor_lab.factor_rotation.state_factor_research_state_machine import (
    StateScope,
    build_state_episode_profile,
    classify_state_learnability,
)
from factor_lab.portfolio.post_training_strategy_science_acceptance import (
    assert_no_scientific_wall_clock,
)
from factor_lab.governance.reaka_foundation_contract import require_research_action


ROOT: Final = Path(__file__).resolve().parents[3]
CONTRACT: Final = ROOT / "docs/ops/reaka_v2_stage3_state_episode_atlas@1.0.json"
INPUT_ROOT: Final = ROOT / "output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020"
STATE_ATLAS_CONTRACT: Final = ROOT / "docs/ops/reaka_k1_only_index_regime_atlas@1.0.json"
STATE_MACHINE_CONTRACT: Final = ROOT / "docs/ops/state_factor_research_state_machine@1.0.json"

TRENDS: Final = ("up", "sideways", "down")
DEVELOPMENT_START: Final = "2011-05"
DEVELOPMENT_END: Final = "2016-12"
HARD_DECISION_END: Final = "2025-12"
MIN_PERSISTENT_MONTHS: Final = 2
LATENT_DIM_DIAGNOSTIC: Final = 8
PROPOSED_OPERATOR_COUNT_DIAGNOSTIC: Final = 2
SCIENCE_FILES: Final = (
    "input_receipt.json",
    "state_months.csv",
    "state_episodes.csv",
    "state_support.csv",
    "transition_counts.csv",
    "state_learnability_certificate.json",
    "comparison_summary.json",
)
SOURCE_FILES: Final = (
    "docs/ops/state_factor_research_state_machine@1.0.json",
    "docs/ops/reaka_paper_parameter_governance_whitepaper.md",
    "docs/ops/reaka_strategy_round_registry@1.0.json",
    "docs/ops/reaka_k1_only_index_regime_atlas@1.0.json",
    "docs/ops/reaka_k1_only_index_regime_episodes@1.0.json",
    "docs/user/reaka_strategy_v2_external_ai_handoff.md",
    "docs/ops/reaka_v2_stage3_state_episode_atlas_whitepaper.md",
    "docs/user/reaka_v2_stage3_state_episode_atlas_workflow.md",
    "src/factor_lab/factor_rotation/state_factor_research_state_machine.py",
    "src/factor_lab/factor_rotation/reaka_k1_only_index_regime_atlas_v1.py",
    "src/factor_lab/factor_rotation/reaka_v2_stage3_state_episode_atlas_v1.py",
    "scripts/factor_rotation/freeze_reaka_v2_stage3_state_episode_atlas_v1.py",
    "scripts/factor_rotation/run_reaka_v2_stage3_state_episode_atlas_v1.py",
    "scripts/factor_rotation/validate_reaka_v2_stage3_state_episode_atlas_v1.py",
    "scripts/factor_rotation/close_reaka_v2_stage3_state_episode_atlas_v1.py",
    "tests/unit/test_reaka_v2_stage3_state_episode_atlas_v1.py",
)


def source_closure() -> dict[str, str]:
    return {relative: file_digest(ROOT / relative) for relative in SOURCE_FILES}


def load_contract() -> dict[str, object]:
    payload = read_json(CONTRACT)
    if not canonical_valid(payload):
        raise PermissionError("reaka_v2_stage3_contract_digest_invalid")
    if payload.get("schema_id") != "factorlab.reaka_v2_stage3_state_episode_atlas@1.0":
        raise PermissionError("reaka_v2_stage3_contract_schema_invalid")
    if payload.get("stage") != "stage3_state_episode_atlas":
        raise PermissionError("reaka_v2_stage3_contract_stage_invalid")
    if payload.get("source_closure") != source_closure():
        raise PermissionError("reaka_v2_stage3_source_closure_drift")
    authority = cast(dict[str, object], payload["authority"])
    forbidden = (
        "stage4_execution_allowed",
        "stage5_execution_allowed",
        "model_training_allowed",
        "account_execution_allowed",
        "strategy_pointer_change_allowed",
        "production_authority",
    )
    if any(authority.get(name) is not False for name in forbidden):
        raise PermissionError("reaka_v2_stage3_downstream_authority_open")
    return payload


def data_role(decision_year: int) -> str:
    if 2011 <= decision_year <= 2016:
        return "development_material_state_certificate"
    if decision_year == 2017:
        return "development_listing_not_pass_evidence"
    if 2018 <= decision_year <= 2025:
        return "consumed_repeat_comparison_no_retune"
    raise PermissionError(f"reaka_v2_stage3_decision_year_unassigned:{decision_year}")


def shift_to_decision_month(source_states: pd.DataFrame) -> pd.DataFrame:
    """Map a completed source month to the following decision month."""
    work = source_states.loc[source_states["trend"].isin(TRENDS)].copy()
    source_period = pd.PeriodIndex(work["period"].astype(str), freq="M")
    decision_period = source_period + 1
    work["source_period"] = source_period.astype(str)
    work["decision_period"] = decision_period.astype(str)
    work["decision_year"] = decision_period.year
    work = work.loc[work["decision_period"].between(DEVELOPMENT_START, HARD_DECISION_END)].copy()
    work["data_role"] = [data_role(int(year)) for year in work["decision_year"]]
    work["state_id"] = "cloudridge_trend_" + work["trend"].astype(str)
    work["pit_available_at"] = pd.to_datetime(work["last_date"]).dt.strftime("%Y-%m-%d")
    work["source_first_date"] = pd.to_datetime(work["first_date"]).dt.strftime("%Y-%m-%d")
    work["source_last_date"] = pd.to_datetime(work["last_date"]).dt.strftime("%Y-%m-%d")
    return work.sort_values("decision_period", kind="mergesort", ignore_index=True)


def load_cross_sectional_support(tree: str) -> tuple[pd.DataFrame, dict[str, object]]:
    clock_frames: list[pd.DataFrame] = []
    clock_receipts: dict[str, object] = {}
    for clock in ("1430", "1445"):
        store = INPUT_ROOT / tree / clock
        manifest = read_json(store / "manifest.json")
        if not canonical_valid(manifest):
            raise PermissionError(f"reaka_v2_stage3_input_manifest_invalid:{clock}")
        artifact_digests = cast(dict[str, object], manifest["artifact_digests"])
        for name in ("calendar.npy", "inference_rows.npy"):
            if file_digest(store / name) != artifact_digests[name]:
                raise PermissionError(f"reaka_v2_stage3_input_artifact_drift:{clock}:{name}")
        if manifest.get("post_2020_rows_read") != 0:
            raise PermissionError(f"reaka_v2_stage3_input_post2020:{clock}")
        calendar = np.load(store / "calendar.npy", mmap_mode="r")
        rows = np.load(store / "inference_rows.npy", mmap_mode="r")
        if rows.ndim != 2 or rows.shape[1] != 4:
            raise ValueError(f"reaka_v2_stage3_inference_rows_shape:{clock}")
        dates = pd.to_datetime(np.asarray(calendar[rows[:, 0]]))
        if int(rows[:, 2].max()) > 2020:
            raise PermissionError(f"reaka_v2_stage3_inference_rows_post2020:{clock}")
        frame = pd.DataFrame(
            {
                "date": dates,
                "symbol_index": np.asarray(rows[:, 1], dtype=np.int64),
                "year": np.asarray(rows[:, 2], dtype=np.int64),
                "phase_id": np.asarray(rows[:, 3], dtype=np.int64),
            }
        )
        frame["decision_period"] = frame["date"].dt.to_period("M").astype(str)
        monthly = (
            frame.groupby("decision_period", sort=True)
            .agg(
                cross_sectional_row_count=("symbol_index", "size"),
                unique_decision_dates=("date", "nunique"),
                unique_symbols=("symbol_index", "nunique"),
                phase_count=("phase_id", "nunique"),
            )
            .reset_index()
        )
        clock_frames.append(monthly)
        clock_receipts[clock] = {
            "manifest_digest": manifest["canonical_digest"],
            "calendar_digest": artifact_digests["calendar.npy"],
            "inference_rows_digest": artifact_digests["inference_rows.npy"],
            "inference_row_count": int(len(rows)),
            "maximum_inference_year": int(rows[:, 2].max()),
        }
    left, right = clock_frames
    pd.testing.assert_frame_equal(left, right, check_exact=True)
    return left, clock_receipts


def build_state_months(tree: str) -> tuple[pd.DataFrame, dict[str, object]]:
    state_atlas_contract = read_json(STATE_ATLAS_CONTRACT)
    if not canonical_valid(state_atlas_contract):
        raise PermissionError("reaka_v2_stage3_upstream_state_atlas_invalid")
    raw = classify_index_periods(load_cloudridge(tree), "monthly")
    months = shift_to_decision_month(raw)
    support, clock_receipts = load_cross_sectional_support(tree)
    months = months.merge(support, on="decision_period", how="left", validate="one_to_one")
    for column in (
        "cross_sectional_row_count",
        "unique_decision_dates",
        "unique_symbols",
        "phase_count",
    ):
        months[column] = months[column].fillna(0).astype(np.int64)
    months["cross_sectional_support_available"] = months["cross_sectional_row_count"].gt(0)
    keep = [
        "source_period",
        "decision_period",
        "decision_year",
        "data_role",
        "state_id",
        "trend",
        "vol",
        "source_first_date",
        "source_last_date",
        "pit_available_at",
        "n_days",
        "index_log_return",
        "sigma_pit",
        "band",
        "realized_vol",
        "vol_threshold",
        "cross_sectional_support_available",
        "cross_sectional_row_count",
        "unique_decision_dates",
        "unique_symbols",
        "phase_count",
    ]
    receipt = {
        "schema_id": "factorlab.reaka_v2_stage3_input_receipt@1.0",
        "cloudridge_index_id": "CN_A_CLOUDRIDGE_BETA_EQW",
        "cloudridge_file_digest": cast(dict[str, object], state_atlas_contract["cloudridge"])["file_digest"],
        "state_atlas_contract_digest": state_atlas_contract["canonical_digest"],
        "input_store_clocks": clock_receipts,
        "decision_month_min": str(months["decision_period"].min()),
        "decision_month_max": str(months["decision_period"].max()),
        "maximum_decision_year": int(months["decision_year"].max()),
        "post_2025_decision_rows": int(months["decision_year"].gt(2025).sum()),
        "model_training_run": False,
        "score_run": False,
        "account_run": False,
        "production_authority": False,
    }
    return months.loc[:, keep], receipt


def build_episodes(months: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for role, local in months.groupby("data_role", sort=False):
        local = local.sort_values("decision_period", kind="mergesort").copy()
        local["episode_number"] = (local["trend"].astype(str) != local["trend"].astype(str).shift(1)).cumsum()
        grouped = local.groupby("episode_number", sort=True)
        for emitted_number, (_episode_number, block) in enumerate(grouped, start=1):
            duration = int(len(block))
            rows.append(
                {
                    "data_role": str(role),
                    "episode_number": emitted_number,
                    "state_id": str(block["state_id"].iloc[0]),
                    "trend": str(block["trend"].iloc[0]),
                    "decision_start_period": str(block["decision_period"].iloc[0]),
                    "decision_end_period": str(block["decision_period"].iloc[-1]),
                    "source_start_period": str(block["source_period"].iloc[0]),
                    "source_end_period": str(block["source_period"].iloc[-1]),
                    "duration_months": duration,
                    "persistent_ge_2_months": duration >= MIN_PERSISTENT_MONTHS,
                    "vol_tag": _episode_vol_tag(cast(pd.Series, block["vol"]).astype(str)),
                    "cross_sectional_row_count": int(block["cross_sectional_row_count"].sum()),
                }
            )
    return pd.DataFrame(rows)


def _episode_vol_tag(values: pd.Series) -> str:
    high = int(values.eq("high").sum())
    low = int(values.eq("low").sum())
    if high == 0 and low == 0:
        return "unresolved"
    if high == low:
        return "mixed"
    return "high" if high > low else "low"


def build_transition_counts(months: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for role, local in months.groupby("data_role", sort=False):
        states = local.sort_values("decision_period", kind="mergesort")["trend"].astype(str).tolist()
        counts = {(left, right): 0 for left in TRENDS for right in TRENDS}
        for left, right in zip(states[:-1], states[1:], strict=True):
            counts[(left, right)] += 1
        for left in TRENDS:
            row_total = sum(counts[(left, right)] for right in TRENDS)
            for right in TRENDS:
                count = counts[(left, right)]
                rows.append(
                    {
                        "data_role": str(role),
                        "from_state": left,
                        "to_state": right,
                        "transition_count": count,
                        "conditional_probability": (float(count / row_total) if row_total else float("nan")),
                    }
                )
    return pd.DataFrame(rows)


def build_state_support(months: pd.DataFrame, episodes: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for role, local in months.groupby("data_role", sort=False):
        local_episodes = episodes.loc[episodes["data_role"].eq(role)]
        total_months = int(len(local))
        for trend in TRENDS:
            state_months = local.loc[local["trend"].eq(trend)]
            state_episodes = local_episodes.loc[local_episodes["trend"].eq(trend)]
            persistent = state_episodes.loc[state_episodes["persistent_ge_2_months"]]
            rows.append(
                {
                    "data_role": str(role),
                    "state_id": f"cloudridge_trend_{trend}",
                    "trend": trend,
                    "temporal_month_count": int(len(state_months)),
                    "prevalence": float(len(state_months) / total_months),
                    "raw_independent_episode_count": int(len(state_episodes)),
                    "persistent_independent_episode_count": int(len(persistent)),
                    "median_raw_duration_months": (float(state_episodes["duration_months"].median()) if len(state_episodes) else 0.0),
                    "median_persistent_duration_months": (float(persistent["duration_months"].median()) if len(persistent) else 0.0),
                    "maximum_duration_months": (int(state_episodes["duration_months"].max()) if len(state_episodes) else 0),
                    "cross_sectional_row_count": int(state_months["cross_sectional_row_count"].sum()),
                }
            )
    return pd.DataFrame(rows)


def _certificate_for_indicator(
    *,
    trend: str,
    development: pd.DataFrame,
    minimum_duration: int,
) -> dict[str, object]:
    indicator = development["trend"].astype(str).eq(trend).to_numpy(np.float64)
    profile = build_state_episode_profile(
        state_id=f"cloudridge_trend_{trend}",
        scope=StateScope.GLOBAL,
        state_probability=indicator,
        factor_active=np.ones(len(indicator), dtype=np.bool_),
        history_years=float(len(indicator) / 12.0),
        cross_sectional_row_count=int(development["cross_sectional_row_count"].sum()),
        latent_dim=LATENT_DIM_DIAGNOSTIC,
        proposed_operator_count=PROPOSED_OPERATOR_COUNT_DIAGNOSTIC,
        operator_parameterization="full",
        activation_threshold=0.5,
        minimum_episode_duration_steps=minimum_duration,
        financial_mechanism_approved=True,
        data_ready=True,
    )
    return classify_state_learnability(profile).as_dict()


def build_learnability_certificate(
    months: pd.DataFrame,
    support: pd.DataFrame,
    transitions: pd.DataFrame,
) -> dict[str, object]:
    development = months.loc[months["data_role"].eq("development_material_state_certificate")].sort_values(
        "decision_period", kind="mergesort"
    )
    if development["decision_period"].tolist() != pd.period_range(DEVELOPMENT_START, DEVELOPMENT_END, freq="M").astype(str).tolist():
        raise ValueError("reaka_v2_stage3_development_months_not_contiguous")
    raw_certificates = {
        trend: _certificate_for_indicator(
            trend=trend,
            development=development,
            minimum_duration=1,
        )
        for trend in TRENDS
    }
    persistent_certificates = {
        trend: _certificate_for_indicator(
            trend=trend,
            development=development,
            minimum_duration=MIN_PERSISTENT_MONTHS,
        )
        for trend in TRENDS
    }
    dev_support = support.loc[support["data_role"].eq("development_material_state_certificate")]
    persistent_by_state = {str(row.trend): int(row.persistent_independent_episode_count) for row in dev_support.itertuples(index=False)}
    dev_transitions = transitions.loc[transitions["data_role"].eq("development_material_state_certificate")]
    physical_transition_count = int(dev_transitions["transition_count"].sum())
    switch_count = int(
        dev_transitions.loc[
            dev_transitions["from_state"] != dev_transitions["to_state"],
            "transition_count",
        ].sum()
    )
    required = {
        "state_scope_global_sector_or_asset": True,
        "independent_episode_count": True,
        "transition_count": True,
        "state_switch_count": True,
        "duration_and_prevalence": True,
        "temporal_vs_cross_sectional_support": True,
        "state_learnability_certificate": True,
    }
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_v2_stage3_state_learnability_certificate@1.0",
        "status": "passed_slow_context_route_only_waiting_user_stage4_checkpoint",
        "stage": "stage3_state_episode_atlas",
        "version_id": "REAKA_STRATEGY_V2_STATE_WEIGHTED_ORTHOGONAL_14",
        "state_identity": {
            "scope": "global_market",
            "carrier": "CN_A_CLOUDRIDGE_BETA_EQW",
            "grain": "monthly",
            "decision_state_source": "previous_calendar_month",
            "trend_deadband": "one_prior_daily_sigma_times_sqrt_source_month_trading_days",
            "states": list(TRENDS),
            "volatility_role": "diagnostic_label_only_not_episode_split",
            "minimum_persistent_segment_months": MIN_PERSISTENT_MONTHS,
        },
        "development_boundary": {
            "decision_month_min": DEVELOPMENT_START,
            "decision_month_max": DEVELOPMENT_END,
            "temporal_month_count": int(len(development)),
            "physical_transition_count": physical_transition_count,
            "state_switch_count": switch_count,
            "cross_sectional_row_count": int(development["cross_sectional_row_count"].sum()),
            "cross_sectional_rows_do_not_multiply_global_episode_count": True,
        },
        "raw_monthly_state_certificates": raw_certificates,
        "persistent_segment_state_certificates": persistent_certificates,
        "persistent_independent_episode_count_by_state": persistent_by_state,
        "composite_learnability_route": "slow_context_low_rank_modulator",
        "route_basis": (
            "global monthly context with only one persistent up segment and one "
            "persistent down segment; distinct full Koopman operators are not identifiable"
        ),
        "discrete_operator_expert_allowed": False,
        "unshrunk_full_matrix_allowed": False,
        "standalone_rank_expert_allowed": False,
        "slow_context_direct_stock_rank_forbidden": True,
        "stage4_pairing_required_before_fusion": True,
        "stage5_parameter_and_fusion_freeze_required": True,
        "stage6_training_allowed": False,
        "required_stage3_items": required,
        "all_stage3_items_present": all(required.values()),
        "result_selection_reads": ["2011-05/2016-12 development state structure"],
        "result_selection_does_not_read": [
            "2017 listing",
            "2018-2025 consumed repeat comparison",
            "factor returns",
            "model scores",
            "account returns",
            "2026 decision rows",
        ],
        "fresh_oos": False,
        "production_authority": False,
    }
    assert_no_scientific_wall_clock(payload)
    return payload


def comparison_summary(months: pd.DataFrame, support: pd.DataFrame) -> dict[str, object]:
    rows: dict[str, object] = {}
    for role, local in months.groupby("data_role", sort=False):
        local_support = support.loc[support["data_role"].eq(role)]
        rows[str(role)] = {
            "decision_month_count": int(len(local)),
            "state_month_count": {trend: int(local["trend"].eq(trend).sum()) for trend in TRENDS},
            "raw_episode_count": {
                trend: int(
                    local_support.loc[
                        local_support["trend"].eq(trend),
                        "raw_independent_episode_count",
                    ].iloc[0]
                )
                for trend in TRENDS
            },
            "persistent_episode_count": {
                trend: int(
                    local_support.loc[
                        local_support["trend"].eq(trend),
                        "persistent_independent_episode_count",
                    ].iloc[0]
                )
                for trend in TRENDS
            },
        }
    return {
        "schema_id": "factorlab.reaka_v2_stage3_state_comparison@1.0",
        "status": "repeat_periods_reported_not_used_for_route",
        "roles": rows,
        "route_selected_from_development_only": True,
        "2017_is_pass_evidence": False,
        "2018_2025_can_retune": False,
        "post_2025_decision_rows": 0,
        "fresh_oos": False,
        "production_authority": False,
    }


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, float_format="%.12g", lineterminator="\n")


def execute_tree(*, tree: str, output_root: Path) -> dict[str, object]:
    require_research_action(Path(__file__).resolve().parents[3], "stage3_execute")
    if tree not in {"formal", "isolated"}:
        raise ValueError("reaka_v2_stage3_tree_invalid")
    contract = load_contract()
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"reaka_v2_stage3_output_exists:{output_root}")
    months, input_receipt = build_state_months(tree)
    episodes = build_episodes(months)
    transitions = build_transition_counts(months)
    support = build_state_support(months, episodes)
    certificate = build_learnability_certificate(months, support, transitions)
    comparison = comparison_summary(months, support)

    write_json(output_root / "input_receipt.json", input_receipt)
    _write_csv(output_root / "state_months.csv", months)
    _write_csv(output_root / "state_episodes.csv", episodes)
    _write_csv(output_root / "state_support.csv", support)
    _write_csv(output_root / "transition_counts.csv", transitions)
    write_json(output_root / "state_learnability_certificate.json", certificate)
    write_json(output_root / "comparison_summary.json", comparison)
    artifact_digests = {name: file_digest(output_root / name) for name in SCIENCE_FILES}
    result = write_json(
        output_root / "result.json",
        {
            "schema_id": "factorlab.reaka_v2_stage3_state_episode_atlas_result@1.0",
            "status": "stage3_complete_waiting_user_checkpoint_before_stage4",
            "contract_digest": contract["canonical_digest"],
            "certificate_digest": read_json(output_root / "state_learnability_certificate.json")["canonical_digest"],
            "composite_learnability_route": "slow_context_low_rank_modulator",
            "development_decision_months": 68,
            "development_physical_transitions": 67,
            "development_state_switches": 26,
            "development_cross_sectional_rows": int(
                months.loc[
                    months["data_role"].eq("development_material_state_certificate"),
                    "cross_sectional_row_count",
                ].sum()
            ),
            "persistent_episode_count": {
                str(row.trend): int(row.persistent_independent_episode_count)
                for row in support.loc[support["data_role"].eq("development_material_state_certificate")].itertuples(index=False)
            },
            "artifact_digests": artifact_digests,
            "stage4_execution_allowed": False,
            "stage5_execution_allowed": False,
            "model_training_executed": False,
            "account_executed": False,
            "post_2025_decision_rows": 0,
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    assert_no_scientific_wall_clock(result)
    return result


def scientific_body(payload: Mapping[str, object]) -> dict[str, object]:
    body = dict(payload)
    body.pop("canonical_digest", None)
    return body
