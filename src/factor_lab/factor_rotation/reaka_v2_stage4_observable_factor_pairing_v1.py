# pyright: reportAny=false
"""Pair prior-month S_obs with realised selected-holdings attribution.

These descriptive comparisons are not forward factor IC or predictive admission.
The sealed @1.0 contract is historical: repaired live sources must not be rebound
into its source closure to obtain new execution authority.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Final, cast

import numpy as np
import pandas as pd

from factor_lab.governance.reaka_multifactor_infrastructure_v1 import (
    SEMANTIC_INVARIANTS,
    canonical_valid,
    file_digest,
    read_json,
    write_json,
)

ROOT: Final = Path(__file__).resolve().parents[3]
CONTRACT: Final = ROOT / "docs/ops/reaka_v2_stage4_observable_factor_pairing@1.0.json"
STATE_ROOT: Final = ROOT / "output/factor-rotation/reaka_v2_stage3_state_episode_atlas_v1_2011_2025"
FACTOR_ROOT: Final = ROOT / "output/factor-rotation/reaka_k1_only_factor_kline_selector_v1_2011_2025"
OUTPUT_ROOT: Final = ROOT / "output/factor-rotation/reaka_v2_stage4_observable_factor_pairing_v1_2011_2025"
EVIDENCE_ROOT: Final = ROOT / "docs/ops/evidence/reaka_v2_stage4_observable_factor_pairing_v1_20260905"
OUTPUT_FILES: Final = (
    "pairing_panel.csv",
    "annual_dispersion.csv",
    "episode_dispersion.csv",
    "hypothesis_summary.csv",
    "advisor_interpretation_request.json",
)
SOURCE_FILES: Final = (
    "docs/ops/reaka_multifactor_current_manifest@1.1.json",
    "docs/ops/state_factor_research_state_machine@2.0.json",
    "docs/ops/reaka_v2_stage3_observable_context@2.0.json",
    "docs/ops/reaka_v2_stage4_observable_factor_pairing_whitepaper.md",
    "docs/user/reaka_v2_stage4_observable_factor_pairing_workflow.md",
    "docs/user/reaka_multifactor_current_workflow_v1_2.md",
    "src/factor_lab/factor_rotation/reaka_v2_stage4_observable_factor_pairing_v1.py",
    "scripts/factor_rotation/build_reaka_v2_stage4_observable_factor_pairing_v1.py",
    "scripts/factor_rotation/run_reaka_v2_stage4_observable_factor_pairing_v1.py",
    "scripts/factor_rotation/validate_reaka_v2_stage4_observable_factor_pairing_v1.py",
    "scripts/factor_rotation/close_reaka_v2_stage4_observable_factor_pairing_v1.py",
    "tests/unit/test_reaka_v2_stage4_observable_factor_pairing_v1.py",
)


@dataclass(frozen=True, slots=True)
class Hypothesis:
    hypothesis_id: str
    factor: str
    condition: str
    expected_direction: str
    financial_mechanism: str


HYPOTHESES: Final = (
    Hypothesis("H_INDEX_UP", "index", "up", "enhance", "uptrend strengthens market skeleton"),
    Hypothesis("H_INDEX_DOWN", "index", "down", "weaken", "downtrend weakens market skeleton"),
    Hypothesis("H_INDUSTRY_UP", "industry", "up", "enhance", "uptrend supports industry participation"),
    Hypothesis("H_INDUSTRY_SIDEWAYS", "industry", "sideways", "enhance", "sideways regime supports industry opportunity"),
    Hypothesis("H_INDUSTRY_DOWN", "industry", "down", "weaken", "downtrend weakens industry contribution"),
)


def source_closure() -> dict[str, str]:
    return {relative: file_digest(ROOT / relative) for relative in SOURCE_FILES}


def load_contract() -> dict[str, object]:
    payload = read_json(CONTRACT)
    if not canonical_valid(payload) or payload.get("source_closure") != source_closure():
        raise PermissionError("reaka_v2_stage4_contract_or_source_invalid")
    authority = cast(dict[str, object], payload["authority"])
    if authority.get("stage4_execution_allowed") is not True:
        raise PermissionError("reaka_v2_stage4_execution_not_authorized")
    for field in ("stage5_execution_allowed", "model_training_allowed", "account_execution_allowed", "production_authority"):
        if authority.get(field) is not False:
            raise PermissionError(f"reaka_v2_stage4_downstream_open:{field}")
    return payload


def data_role(old_role: str) -> str:
    mapping = {
        "development_selection": "development_material_pairing",
        "development_listing": "development_listing_not_pass_evidence",
        "consumed_blackbox_diagnostic": "consumed_repeat_comparison_no_retune",
    }
    if old_role not in mapping:
        raise ValueError(f"reaka_v2_stage4_unknown_role:{old_role}")
    return mapping[old_role]


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    if frame.columns.has_duplicates or not set(columns).issubset(frame.columns):
        raise ValueError(f"reaka_v2_stage4_{label}_columns_invalid")
    if frame.empty or frame.loc[:, list(columns)].isna().any().any():
        raise ValueError(f"reaka_v2_stage4_{label}_missing_values")


def _months(values: pd.Series, label: str) -> pd.PeriodIndex:
    if not values.map(lambda value: isinstance(value, str)).all() or not values.str.fullmatch(r"\d{4}-\d{2}").all():
        raise ValueError(f"reaka_v2_stage4_{label}_month_invalid")
    try:
        return pd.PeriodIndex(values, freq="M")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"reaka_v2_stage4_{label}_month_invalid") from exc


def _local_timestamps(values: pd.Series) -> pd.DatetimeIndex:
    stamps = []
    for value in values:
        stamp = pd.Timestamp(value)
        stamps.append(stamp.tz_localize("Asia/Shanghai") if stamp.tzinfo is None else stamp.tz_convert("Asia/Shanghai"))
    return pd.DatetimeIndex(stamps)


def _validate_factor_rows(frame: pd.DataFrame) -> pd.PeriodIndex:
    _require_columns(frame, ("period", "decision_clock", "year", "index", "industry", "data_role"), "factor")
    periods = _months(frame["period"], "factor")
    if frame.duplicated(["period", "decision_clock"]).any():
        raise ValueError("reaka_v2_stage4_duplicate_monthly_key")
    if not frame["decision_clock"].isin(("14:30", "14:45")).all():
        raise ValueError("reaka_v2_stage4_clock_invalid")
    if not frame.groupby("period")["decision_clock"].nunique().eq(2).all():
        raise ValueError("reaka_v2_stage4_clock_support_mismatch")
    try:
        values = frame.loc[:, ["year", "index", "industry"]].apply(pd.to_numeric, errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError("reaka_v2_stage4_factor_values_invalid") from exc
    if not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError("reaka_v2_stage4_factor_values_nonfinite")
    if not np.array_equal(values["year"].to_numpy(), periods.year):
        raise ValueError("reaka_v2_stage4_year_mismatch")
    if (periods < pd.Period("2011-05", freq="M")).any() or (periods > pd.Period("2025-12", freq="M")).any():
        raise ValueError("reaka_v2_stage4_period_outside_frozen_boundary")
    expected = np.where(
        periods.year < 2017,
        "development_material_pairing",
        np.where(periods.year == 2017, "development_listing_not_pass_evidence", "consumed_repeat_comparison_no_retune"),
    )
    if not np.array_equal(frame["data_role"].to_numpy(), expected):
        raise ValueError("reaka_v2_stage4_calendar_role_mismatch")
    return periods


def _validate_pairing_panel(panel: pd.DataFrame) -> None:
    periods = _validate_factor_rows(panel)
    _require_columns(panel, ("source_period", "S_obs", "episode_id"), "pairing")
    source = _months(panel["source_period"], "source")
    if not (source + 1 == periods).all():
        raise ValueError("reaka_v2_stage4_not_previous_calendar_month")
    if not panel["S_obs"].isin(("up", "down", "sideways")).all():
        raise ValueError("reaka_v2_stage4_state_invalid")
    for field in ("source_period", "S_obs", "episode_id"):
        if not panel.groupby("period")[field].nunique().eq(1).all():
            raise ValueError("reaka_v2_stage4_cross_clock_state_mismatch")


def build_pairing_panel(states: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        states, ("decision_period", "source_period", "trend", "data_role", "pit_available_at", "source_last_date"), "state"
    )
    decision = _months(states["decision_period"], "state_decision")
    source = _months(states["source_period"], "state_source")
    if states.duplicated("decision_period").any():
        raise ValueError("reaka_v2_stage4_duplicate_state_month")
    if not (source + 1 == decision).all():
        raise ValueError("reaka_v2_stage4_not_previous_calendar_month")
    if not states["trend"].isin(("up", "down", "sideways")).all():
        raise ValueError("reaka_v2_stage4_state_invalid")
    try:
        available = _local_timestamps(states["pit_available_at"])
        last_date = _local_timestamps(states["source_last_date"])
    except (TypeError, ValueError) as exc:
        raise ValueError("reaka_v2_stage4_state_timestamp_invalid") from exc
    source_start = source.to_timestamp().tz_localize("Asia/Shanghai")
    decision_start = decision.to_timestamp().tz_localize("Asia/Shanghai")
    if (
        available.isna().any()
        or last_date.isna().any()
        or not ((last_date >= source_start) & (last_date < decision_start) & (last_date <= available)).all()
        or not (available < decision_start).all()
    ):
        raise ValueError("reaka_v2_stage4_state_not_pit")
    state = states.loc[:, ["decision_period", "source_period", "trend", "data_role"]].rename(
        columns={"trend": "S_obs", "data_role": "stage3_data_role"}
    )
    _require_columns(factors, ("period", "decision_clock", "year", "index", "industry", "data_role"), "factor")
    factor = factors.loc[:, ["period", "decision_clock", "year", "index", "industry", "data_role"]].copy()
    factor["data_role"] = [data_role(str(value)) for value in factor["data_role"]]
    _validate_factor_rows(factor)
    for column in ("year", "index", "industry"):
        factor[column] = pd.to_numeric(factor[column], errors="raise")
    joined = factor.merge(state, left_on="period", right_on="decision_period", how="inner", validate="many_to_one")
    if len(joined) != len(factor):
        raise ValueError("reaka_v2_stage4_state_join_gap")
    if not bool(
        (
            joined["data_role"]
            == joined["stage3_data_role"].replace({"development_material_state_certificate": "development_material_pairing"})
        ).all()
    ):
        raise ValueError("reaka_v2_stage4_role_mismatch")
    # Monthly state projection after both unique input keys have been checked;
    # this never drops or combines duplicate attribution observations.
    unique = joined.loc[joined["decision_clock"].eq("14:30"), ["data_role", "period", "S_obs"]].sort_values(
        ["data_role", "period"]
    )
    month_number = pd.Series(pd.PeriodIndex(unique["period"], freq="M").asi8, index=unique.index)
    starts = unique["data_role"].ne(unique["data_role"].shift()) | unique["S_obs"].ne(unique["S_obs"].shift())
    starts |= month_number.diff().ne(1)
    unique["episode_number"] = starts.groupby(unique["data_role"]).cumsum()
    joined = joined.merge(unique, on=["data_role", "period", "S_obs"], how="left", validate="many_to_one")
    joined["episode_id"] = joined["data_role"].astype(str) + ":" + joined["episode_number"].astype(int).astype(str)
    panel = joined.loc[
        :, ["period", "source_period", "year", "data_role", "decision_clock", "S_obs", "episode_id", "index", "industry"]
    ].sort_values(["period", "decision_clock"])
    _validate_pairing_panel(panel)
    return panel


def _aligned(value: float, expected: str) -> bool:
    return value > 0.0 if expected == "enhance" else value < 0.0


def _opposed(value: float, expected: str) -> bool:
    return value < 0.0 if expected == "enhance" else value > 0.0


def evaluate(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    _validate_pairing_panel(panel)
    annual_rows: list[dict[str, object]] = []
    episode_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    for role in panel["data_role"].drop_duplicates():
        role_panel = panel.loc[panel["data_role"].eq(role)]
        for hypothesis in HYPOTHESES:
            for clock in ("14:30", "14:45"):
                local = role_panel.loc[role_panel["decision_clock"].eq(clock)].copy()
                inside = local["S_obs"].eq(hypothesis.condition)
                outside_mean = float(local.loc[~inside, hypothesis.factor].mean())
                episode_effects: list[float] = []
                for episode_id, block in local.loc[inside].groupby("episode_id", sort=True):
                    effect = float(block[hypothesis.factor].mean() - outside_mean)
                    episode_effects.append(effect)
                    episode_rows.append(
                        {
                            "data_role": role,
                            "hypothesis_id": hypothesis.hypothesis_id,
                            "factor": hypothesis.factor,
                            "condition": hypothesis.condition,
                            "expected_direction": hypothesis.expected_direction,
                            "decision_clock": clock,
                            "episode_id": episode_id,
                            "start_period": str(block["period"].min()),
                            "end_period": str(block["period"].max()),
                            "duration_months": int(block["period"].nunique()),
                            "factor_active": bool(np.isfinite(block[hypothesis.factor]).any()),
                            "episode_mean": float(block[hypothesis.factor].mean()),
                            "outside_mean": outside_mean,
                            "effect_vs_outside": effect,
                            "aligned_with_expected_direction": _aligned(effect, hypothesis.expected_direction),
                        }
                    )
                annual_effects: list[float] = []
                for year, year_block in local.groupby("year", sort=True):
                    year_inside = year_block["S_obs"].eq(hypothesis.condition)
                    if not bool(year_inside.any()) or not bool((~year_inside).any()):
                        continue
                    mean_in = float(year_block.loc[year_inside, hypothesis.factor].mean())
                    mean_out = float(year_block.loc[~year_inside, hypothesis.factor].mean())
                    lift = mean_in - mean_out
                    annual_effects.append(lift)
                    annual_rows.append(
                        {
                            "data_role": role,
                            "hypothesis_id": hypothesis.hypothesis_id,
                            "decision_clock": clock,
                            "year": int(year),
                            "mean_in": mean_in,
                            "mean_out": mean_out,
                            "lift": lift,
                            "aligned_with_expected_direction": _aligned(lift, hypothesis.expected_direction),
                        }
                    )
                n_in = int(inside.sum())
                n_out = int((~inside).sum())
                pooled_lift = float(local.loc[inside, hypothesis.factor].mean() - outside_mean) if n_in and n_out else float("nan")
                episode_aligned = sum(_aligned(value, hypothesis.expected_direction) for value in episode_effects)
                annual_aligned = sum(_aligned(value, hypothesis.expected_direction) for value in annual_effects)
                if not episode_effects or not annual_effects:
                    machine_direction = "insufficient"
                elif pooled_lift == 0.0 and all(value == 0.0 for value in episode_effects + annual_effects):
                    machine_direction = "no_direction"
                elif (
                    _aligned(pooled_lift, hypothesis.expected_direction)
                    and episode_aligned * 2 >= len(episode_effects)
                    and annual_aligned * 2 >= len(annual_effects)
                ):
                    machine_direction = "aligned"
                elif (
                    _opposed(pooled_lift, hypothesis.expected_direction)
                    and sum(_opposed(value, hypothesis.expected_direction) for value in episode_effects) * 2 > len(episode_effects)
                    and sum(_opposed(value, hypothesis.expected_direction) for value in annual_effects) * 2 > len(annual_effects)
                ):
                    machine_direction = "opposed"
                else:
                    machine_direction = "mixed"
                summary_rows.append(
                    {
                        "data_role": role,
                        "hypothesis_id": hypothesis.hypothesis_id,
                        "factor": hypothesis.factor,
                        "condition": hypothesis.condition,
                        "expected_direction": hypothesis.expected_direction,
                        "financial_mechanism": hypothesis.financial_mechanism,
                        "decision_clock": clock,
                        "n_in_months": n_in,
                        "n_out_months": n_out,
                        "factor_active_episode_count": len(episode_effects),
                        "aligned_episode_count": episode_aligned,
                        "comparable_year_count": len(annual_effects),
                        "aligned_year_count": annual_aligned,
                        "pooled_lift": pooled_lift,
                        "median_episode_lift": float(np.median(episode_effects)) if episode_effects else float("nan"),
                        "median_annual_lift": float(np.median(annual_effects)) if annual_effects else float("nan"),
                        "machine_directional_evidence": machine_direction,
                        "financial_verdict": "waiting_user_review",
                    }
                )
    return pd.DataFrame(annual_rows), pd.DataFrame(episode_rows), pd.DataFrame(summary_rows)


def execute_tree(*, tree: str) -> dict[str, object]:
    from factor_lab.governance.reaka_foundation_contract import require_research_action

    require_research_action(ROOT, "stage4_execute")
    if tree not in {"formal", "isolated"}:
        raise ValueError("reaka_v2_stage4_tree_invalid")
    contract = load_contract()
    output = OUTPUT_ROOT / tree
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"reaka_v2_stage4_output_exists:{output}")
    states, factors = _load_bound_inputs(contract, tree=tree)
    panel = build_pairing_panel(states, factors)
    annual, episodes, summary = evaluate(panel)
    output.mkdir(parents=True, exist_ok=False)
    for name, frame in (
        ("pairing_panel.csv", panel),
        ("annual_dispersion.csv", annual),
        ("episode_dispersion.csv", episodes),
        ("hypothesis_summary.csv", summary),
    ):
        frame.to_csv(output / name, index=False, float_format="%.12g", lineterminator="\n")
    development = summary.loc[summary["data_role"].eq("development_material_pairing")]
    request = write_json(
        output / "advisor_interpretation_request.json",
        {
            "schema_id": "factorlab.reaka_v2_stage4_advisor_interpretation_request@1.0",
            "status": "waiting_user_financial_review",
            "hypothesis_ids": [item.hypothesis_id for item in HYPOTHESES],
            "development_machine_summary": development.to_dict(orient="records"),
            "questions": [
                "Does each directional pattern match the intended financial mechanism?",
                "Should any mechanism be retained, revised, or rejected before Stage5?",
            ],
            "advisor_interpretation_receipt_present": False,
            "stage5_execution_allowed": False,
            "semantic_invariants": SEMANTIC_INVARIANTS,
            "production_authority": False,
        },
    )
    result = write_json(
        output / "result.json",
        {
            "schema_id": "factorlab.reaka_v2_stage4_observable_factor_pairing_result@1.0",
            "status": "stage4_machine_evidence_complete_waiting_user_financial_review",
            "contract_digest": contract["canonical_digest"],
            "advisor_request_digest": request["canonical_digest"],
            "output_digests": {name: file_digest(output / name) for name in OUTPUT_FILES},
            "legacy_same_month_trend_used": False,
            "hypothesis_count": len(HYPOTHESES),
            "advisor_interpretation_receipt_present": False,
            "stage5_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    return result


def _load_bound_inputs(contract: dict[str, object], *, tree: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hash exactly the bytes parsed, before any output directory is created."""
    if tree not in {"formal", "isolated"}:
        raise ValueError("reaka_v2_stage4_tree_invalid")
    digests = contract.get("input_digests")
    expected = digests.get(tree) if isinstance(digests, dict) else None
    if not isinstance(expected, dict) or set(expected) != {"state_months.csv", "monthly_selector_panel.csv"}:
        raise PermissionError("reaka_v2_stage4_input_digest_inventory_invalid")
    frames: list[pd.DataFrame] = []
    for root, name in ((STATE_ROOT, "state_months.csv"), (FACTOR_ROOT, "monthly_selector_panel.csv")):
        try:
            raw = (root / tree / name).read_bytes()
        except OSError as exc:
            raise PermissionError(f"reaka_v2_stage4_input_unavailable:{name}") from exc
        actual = "sha256:" + hashlib.sha256(raw).hexdigest()
        if expected[name] != actual:
            raise PermissionError(f"reaka_v2_stage4_input_digest_mismatch:{name}")
        frames.append(pd.read_csv(BytesIO(raw)))
    return frames[0], frames[1]
