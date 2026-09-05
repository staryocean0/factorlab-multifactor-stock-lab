# pyright: reportAny=false
# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportOperatorIssue=false
# pyright: reportReturnType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Project-level post-training strategy science acceptance.

This stage sits after a frozen model/score snapshot and before A0--A7.  It
asks whether the frozen score has any in-sample diagnostic signal on a
single frozen selector, and attributes that signal to factor representation,
K/state dynamics, and residual.  Complete account snapshots, Cartesian
families, costs, and RealizedPnlLedger remain A0--A7 products.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from factor_lab.portfolio.account_research_bundle import (
    SELECTION_OPPORTUNITY_COLUMNS,
    validate_selection_opportunity_ledger,
)

SCHEMA_ID: Final = "factorlab.post_training_strategy_science_acceptance@1.0"
SCORE_PATH_SCHEMA_ID: Final = "factorlab.score_path_diagnostic_ledger@1.0"
ATTRIBUTION_SCHEMA_ID: Final = "factorlab.score_component_attribution_ledger@1.0"
DIAGNOSTIC_POLICY_ID: Final = "N30_equal_eligible_unconstrained"
DIAGNOSTIC_PATH_ID: Final = "score_path_diagnostic_N30_equal"
DIAGNOSTIC_TOP_N: Final = 30
FIT_YEAR_START: Final = 2011
FIT_YEAR_END: Final = 2016
REVIEW_YEAR_FORBIDDEN: Final = 2017
SUBPERIODS: Final[tuple[tuple[str, str, str], ...]] = (
    ("2011_2013", "2011-01-01", "2013-12-31"),
    ("2014_2016", "2014-01-01", "2016-12-31"),
)
FORBIDDEN_SCIENTIFIC_WALL_CLOCK_KEYS: Final[tuple[str, ...]] = (
    "wall_time",
    "wall_time_seconds",
    "elapsed_seconds",
    "duration_seconds",
    "started_at",
    "finished_at",
    "host_timestamp",
    "runtime_ms",
    "runtime_seconds",
)
SCORE_PATH_COLUMNS: Final[tuple[str, ...]] = (
    "date",
    "variant_id",
    "policy_id",
    "path_id",
    "asset_id",
    "score",
    "selected",
    "weight",
    "forward_return",
    "simple_contribution",
    "linked_log_contribution",
)
ATTRIBUTION_COLUMNS: Final[tuple[str, ...]] = (
    "decision_id",
    "decision_time",
    "variant_id",
    "asset_id",
    "score_factor",
    "score_k_state",
    "score_full",
    "forward_return",
)
OUTCOMES: Final[tuple[str, ...]] = (
    "diagnostic_signal_present_account_contract_may_open",
    "no_signal",
    "infrastructure_gap",
)


class StrategyScienceAcceptanceError(ValueError):
    """Fail-closed SSA validation error."""


def _require_columns(frame: pd.DataFrame, expected: tuple[str, ...], code: str) -> None:
    missing = [name for name in expected if name not in frame.columns]
    if missing:
        raise StrategyScienceAcceptanceError(f"{code}:{','.join(missing)}")


def assert_no_scientific_wall_clock(payload: object, *, path: str = "$") -> None:
    """Reject host wall-clock keys in scientific JSON."""

    if isinstance(payload, Mapping):
        for key, value in payload.items():
            name = str(key)
            if name in FORBIDDEN_SCIENTIFIC_WALL_CLOCK_KEYS:
                raise StrategyScienceAcceptanceError(f"scientific_wall_clock_forbidden:{path}.{name}")
            assert_no_scientific_wall_clock(value, path=f"{path}.{name}")
        return
    if isinstance(payload, list):
        for index, value in enumerate(payload):
            assert_no_scientific_wall_clock(value, path=f"{path}[{index}]")


def assert_year_bounds(
    stamps: pd.Series,
    *,
    min_year: int = FIT_YEAR_START,
    max_year: int = FIT_YEAR_END,
    column: str,
) -> None:
    years = pd.to_datetime(stamps, errors="raise").dt.year
    if years.isna().any():
        raise StrategyScienceAcceptanceError(f"ssa_timestamp_invalid:{column}")
    if (years == REVIEW_YEAR_FORBIDDEN).any():
        raise StrategyScienceAcceptanceError(f"ssa_2017_read_forbidden:{column}")
    if int(years.min()) < min_year or int(years.max()) > max_year:
        raise StrategyScienceAcceptanceError(f"ssa_year_bound_violated:{column}")


def _linked_log_contributions(
    simple: NDArray[np.float64],
    daily_return: float,
) -> NDArray[np.float64]:
    if not math.isfinite(daily_return):
        raise StrategyScienceAcceptanceError("ssa_score_path_daily_return_not_finite")
    if abs(daily_return) <= 1.0e-15:
        return np.zeros_like(simple)
    scale = math.log1p(daily_return) / daily_return
    return simple * scale


def build_selection_opportunity_ledger(
    *,
    decision_ids: Sequence[str],
    decision_times: Sequence[pd.Timestamp],
    variant_id: str,
    policy_id: str,
    asset_ids: Sequence[str],
    scores: NDArray[np.float64],
    forward_returns: NDArray[np.float64],
    score_available_at: Sequence[pd.Timestamp],
    label_start_times: Sequence[pd.Timestamp],
    label_end_times: Sequence[pd.Timestamp],
    top_n: int = DIAGNOSTIC_TOP_N,
) -> pd.DataFrame:
    """Build a single-policy opportunity ledger over an already-eligible universe."""

    if top_n != DIAGNOSTIC_TOP_N:
        raise StrategyScienceAcceptanceError("ssa_diagnostic_top_n_not_frozen")
    if policy_id != DIAGNOSTIC_POLICY_ID:
        raise StrategyScienceAcceptanceError("ssa_diagnostic_policy_not_frozen")
    size = len(decision_ids)
    if not (
        size
        == len(decision_times)
        == len(asset_ids)
        == len(scores)
        == len(forward_returns)
        == len(score_available_at)
        == len(label_start_times)
        == len(label_end_times)
    ):
        raise StrategyScienceAcceptanceError("ssa_opportunity_length_mismatch")
    work = pd.DataFrame(
        {
            "decision_id": np.asarray(decision_ids, dtype=str),
            "decision_time": pd.to_datetime(decision_times, errors="raise"),
            "variant_id": variant_id,
            "policy_id": policy_id,
            "asset_id": np.asarray(asset_ids, dtype=str),
            "score": np.asarray(scores, dtype=np.float64),
            "score_available_at": pd.to_datetime(score_available_at, errors="raise"),
            "eligible": True,
            "label_start_time": pd.to_datetime(label_start_times, errors="raise"),
            "label_end_time": pd.to_datetime(label_end_times, errors="raise"),
            "realized_forward_return": np.asarray(forward_returns, dtype=np.float64),
        }
    )
    assert_year_bounds(work["decision_time"], column="decision_time")
    rows: list[dict[str, object]] = []
    for decision_id, group in work.groupby("decision_id", sort=True):
        local = group.reset_index(drop=True)
        if len(local) < top_n:
            continue
        score_order = np.lexsort(
            (local["asset_id"].to_numpy(str), -local["score"].to_numpy(np.float64))
        )
        opportunity_order = np.lexsort(
            (
                local["asset_id"].to_numpy(str),
                -local["realized_forward_return"].to_numpy(np.float64),
            )
        )
        selected = set(int(value) for value in score_order[:top_n])
        opportunity_rank = {
            int(position): rank + 1 for rank, position in enumerate(opportunity_order)
        }
        oracle = set(int(value) for value in opportunity_order[:top_n])
        for local_position, record in local.iterrows():
            index = int(local_position)
            is_selected = index in selected
            bucket = "oracle_topn" if index in oracle else "outside_oracle_topn"
            selection_rank = (
                int(np.flatnonzero(score_order == index)[0]) + 1 if is_selected else math.nan
            )
            rows.append(
                {
                    "decision_id": str(decision_id),
                    "decision_time": record["decision_time"],
                    "variant_id": variant_id,
                    "policy_id": policy_id,
                    "asset_id": str(record["asset_id"]),
                    "score": float(record["score"]),
                    "score_available_at": record["score_available_at"],
                    "eligible": True,
                    "selected": is_selected,
                    "selection_rank": selection_rank,
                    "label_start_time": record["label_start_time"],
                    "label_end_time": record["label_end_time"],
                    "realized_forward_return": float(record["realized_forward_return"]),
                    "opportunity_rank": int(opportunity_rank[index]),
                    "opportunity_bucket": bucket,
                }
            )
    if not rows:
        raise StrategyScienceAcceptanceError("ssa_opportunity_no_complete_cross_section")
    frame = pd.DataFrame(rows, columns=list(SELECTION_OPPORTUNITY_COLUMNS))
    _ = validate_selection_opportunity_ledger(frame)
    return frame.sort_values(
        ["decision_time", "variant_id", "selection_rank", "asset_id"],
        kind="mergesort",
    ).reset_index(drop=True)


def opportunity_decision_summary(ledger: pd.DataFrame) -> pd.DataFrame:
    """Per-decision opportunity capture against the eligible-set midpoint."""

    _ = validate_selection_opportunity_ledger(ledger)
    rows: list[dict[str, object]] = []
    for (decision_id, variant_id, policy_id), group in ledger.groupby(
        ["decision_id", "variant_id", "policy_id"],
        sort=True,
    ):
        eligible = group[group["eligible"].astype(bool)]
        selected = group[group["selected"].astype(bool)]
        eligible_count = int(len(eligible))
        if eligible_count < DIAGNOSTIC_TOP_N or len(selected) != DIAGNOSTIC_TOP_N:
            raise StrategyScienceAcceptanceError("ssa_opportunity_decision_incomplete")
        midpoint = (eligible_count + 1) / 2.0
        median_rank = float(selected["opportunity_rank"].median())
        overlap = float(
            selected["opportunity_bucket"].astype(str).eq("oracle_topn").mean()
        )
        rows.append(
            {
                "decision_id": str(decision_id),
                "decision_time": pd.Timestamp(selected["decision_time"].iloc[0]),
                "variant_id": str(variant_id),
                "policy_id": str(policy_id),
                "eligible_count": eligible_count,
                "selected_count": DIAGNOSTIC_TOP_N,
                "eligible_midpoint": midpoint,
                "selected_median_opportunity_rank": median_rank,
                "better_than_random": bool(median_rank < midpoint),
                "selected_oracle_overlap_share": overlap,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["decision_time", "variant_id"],
        kind="mergesort",
    ).reset_index(drop=True)


def build_score_path_ledger(opportunity: pd.DataFrame) -> pd.DataFrame:
    """Equal-weight selected path without costs, fills, or corporate actions."""

    _ = validate_selection_opportunity_ledger(opportunity)
    selected = opportunity[opportunity["selected"].astype(bool)].copy()
    if selected.empty:
        raise StrategyScienceAcceptanceError("ssa_score_path_empty")
    weight = 1.0 / float(DIAGNOSTIC_TOP_N)
    selected["weight"] = weight
    selected["simple_contribution"] = weight * selected["realized_forward_return"].to_numpy(
        np.float64
    )
    rows: list[dict[str, object]] = []
    for (decision_time, variant_id, policy_id), group in selected.groupby(
        ["decision_time", "variant_id", "policy_id"],
        sort=True,
    ):
        if len(group) != DIAGNOSTIC_TOP_N:
            raise StrategyScienceAcceptanceError("ssa_score_path_selected_count_invalid")
        simple = group["simple_contribution"].to_numpy(np.float64)
        daily_return = float(simple.sum())
        linked = _linked_log_contributions(simple, daily_return)
        for local_index, record in enumerate(group.itertuples(index=False)):
            rows.append(
                {
                    "date": pd.Timestamp(decision_time),
                    "variant_id": str(variant_id),
                    "policy_id": str(policy_id),
                    "path_id": DIAGNOSTIC_PATH_ID,
                    "asset_id": str(record.asset_id),
                    "score": float(record.score),
                    "selected": True,
                    "weight": weight,
                    "forward_return": float(record.realized_forward_return),
                    "simple_contribution": float(simple[local_index]),
                    "linked_log_contribution": float(linked[local_index]),
                }
            )
    frame = pd.DataFrame(rows, columns=list(SCORE_PATH_COLUMNS))
    _ = validate_score_path_ledger(frame)
    return frame.sort_values(
        ["date", "variant_id", "asset_id"],
        kind="mergesort",
    ).reset_index(drop=True)


def validate_score_path_ledger(frame: pd.DataFrame) -> dict[str, object]:
    """Validate the diagnostic score-path conservation identity."""

    _require_columns(frame, SCORE_PATH_COLUMNS, "ssa_score_path_columns_missing")
    if tuple(frame.columns[: len(SCORE_PATH_COLUMNS)]) != SCORE_PATH_COLUMNS:
        # allow extra adapter columns after the core identity
        pass
    key = ["date", "variant_id", "policy_id", "path_id", "asset_id"]
    if frame.duplicated(key).any():
        raise StrategyScienceAcceptanceError("ssa_score_path_key_duplicate")
    if frame["path_id"].astype(str).ne(DIAGNOSTIC_PATH_ID).any():
        raise StrategyScienceAcceptanceError("ssa_score_path_id_not_frozen")
    if frame["policy_id"].astype(str).ne(DIAGNOSTIC_POLICY_ID).any():
        raise StrategyScienceAcceptanceError("ssa_score_path_policy_not_frozen")
    assert_year_bounds(frame["date"], column="date")
    selected = frame["selected"].astype(bool).to_numpy()
    if not selected.all():
        raise StrategyScienceAcceptanceError("ssa_score_path_unselected_row")
    weight = pd.to_numeric(frame["weight"], errors="raise").to_numpy(np.float64)
    forward = pd.to_numeric(frame["forward_return"], errors="raise").to_numpy(np.float64)
    simple = pd.to_numeric(frame["simple_contribution"], errors="raise").to_numpy(np.float64)
    linked = pd.to_numeric(frame["linked_log_contribution"], errors="raise").to_numpy(np.float64)
    if not np.allclose(weight, 1.0 / DIAGNOSTIC_TOP_N, rtol=0.0, atol=1.0e-15):
        raise StrategyScienceAcceptanceError("ssa_score_path_weight_not_frozen")
    if not np.allclose(simple, weight * forward, rtol=1.0e-12, atol=1.0e-12):
        raise StrategyScienceAcceptanceError("ssa_score_path_simple_identity_failed")
    for (_, _, _), group in frame.groupby(["date", "variant_id", "policy_id"], sort=False):
        if len(group) != DIAGNOSTIC_TOP_N:
            raise StrategyScienceAcceptanceError("ssa_score_path_group_size_invalid")
        daily = float(group["simple_contribution"].sum())
        linked_sum = float(group["linked_log_contribution"].sum())
        expected_log = math.log1p(daily) if abs(daily) > 1.0e-15 else 0.0
        if not math.isfinite(daily) or abs(linked_sum - expected_log) > 1.0e-12:
            raise StrategyScienceAcceptanceError("ssa_score_path_conservation_failed")
        _ = linked
    return {
        "schema_id": SCORE_PATH_SCHEMA_ID,
        "row_count": len(frame),
        "decision_count": int(frame.groupby(["date", "variant_id"]).ngroups),
        "complete_realized_pnl": False,
        "account_snapshot": False,
        "cost_applied": False,
    }


def build_attribution_ledger(
    *,
    decision_ids: Sequence[str],
    decision_times: Sequence[pd.Timestamp],
    variant_id: str,
    asset_ids: Sequence[str],
    score_factor: NDArray[np.float64],
    score_k_state: NDArray[np.float64],
    score_full: NDArray[np.float64],
    forward_returns: NDArray[np.float64],
) -> pd.DataFrame:
    """Persist nested score components on the same eligible coordinates."""

    size = len(decision_ids)
    if not (
        size
        == len(decision_times)
        == len(asset_ids)
        == len(score_factor)
        == len(score_k_state)
        == len(score_full)
        == len(forward_returns)
    ):
        raise StrategyScienceAcceptanceError("ssa_attribution_length_mismatch")
    frame = pd.DataFrame(
        {
            "decision_id": np.asarray(decision_ids, dtype=str),
            "decision_time": pd.to_datetime(decision_times, errors="raise"),
            "variant_id": variant_id,
            "asset_id": np.asarray(asset_ids, dtype=str),
            "score_factor": np.asarray(score_factor, dtype=np.float64),
            "score_k_state": np.asarray(score_k_state, dtype=np.float64),
            "score_full": np.asarray(score_full, dtype=np.float64),
            "forward_return": np.asarray(forward_returns, dtype=np.float64),
        }
    )
    _ = validate_attribution_ledger(frame)
    return frame.sort_values(
        ["decision_time", "variant_id", "asset_id"],
        kind="mergesort",
    ).reset_index(drop=True)


def validate_attribution_ledger(frame: pd.DataFrame) -> dict[str, object]:
    _require_columns(frame, ATTRIBUTION_COLUMNS, "ssa_attribution_columns_missing")
    key = ["decision_id", "variant_id", "asset_id"]
    if frame.duplicated(key).any():
        raise StrategyScienceAcceptanceError("ssa_attribution_key_duplicate")
    assert_year_bounds(frame["decision_time"], column="decision_time")
    values = frame[["score_factor", "score_k_state", "score_full", "forward_return"]]
    numeric = values.apply(lambda column: pd.to_numeric(column, errors="coerce"))
    if not np.isfinite(numeric.to_numpy(np.float64)).all():
        raise StrategyScienceAcceptanceError("ssa_attribution_nonfinite")
    return {
        "schema_id": ATTRIBUTION_SCHEMA_ID,
        "row_count": len(frame),
        "decision_count": int(frame["decision_id"].nunique()),
        "k2_is_candidate": False,
    }


def daily_rankic(
    scores: NDArray[np.float64],
    targets: NDArray[np.float64],
    decision_ids: NDArray[np.str_],
) -> dict[str, float | int]:
    """Mean daily Spearman on complete cross-sections of at least TopN names."""

    from scipy.stats import spearmanr

    rankics: list[float] = []
    for decision_id in np.unique(decision_ids):
        local = decision_ids == decision_id
        if int(local.sum()) < DIAGNOSTIC_TOP_N:
            continue
        correlation = float(spearmanr(scores[local], targets[local]).statistic)
        if math.isfinite(correlation):
            rankics.append(correlation)
    if not rankics:
        raise StrategyScienceAcceptanceError("ssa_rankic_no_complete_cross_section")
    values = np.asarray(rankics, dtype=np.float64)
    return {
        "decision_count": int(len(values)),
        "mean_daily_rankic": float(values.mean()),
        "daily_rankic_standard_error": float(values.std(ddof=1) / math.sqrt(len(values)))
        if len(values) > 1
        else math.nan,
    }


def mask_subperiod(
    stamps: pd.Series,
    *,
    start: str,
    end: str,
) -> NDArray[np.bool_]:
    dates = pd.to_datetime(stamps, errors="raise")
    return (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))


@dataclass(frozen=True, slots=True)
class SSAClockEvidence:
    variant_id: str
    mean_daily_rankic: float
    subperiod_rankic: dict[str, float]
    selected_median_opportunity_rank: float
    eligible_midpoint: float
    decision_count: int
    factor_rankic: float
    k_state_rankic: float
    residual_increment_rankic: float


def adjudicate_strategy_science_acceptance(
    *,
    clocks: Sequence[SSAClockEvidence],
    rows_2017_read: int,
    rows_2018_plus_read: int,
    k2_selected: bool,
    account_family_searched: bool,
    both_trees_match: bool,
    scientific_payload: Mapping[str, object],
) -> dict[str, object]:
    """Outcome-neutral SSA gate. Passing only opens a later A0--A7 contract."""

    assert_no_scientific_wall_clock(scientific_payload)
    infrastructure_reasons: list[str] = []
    if rows_2017_read != 0:
        infrastructure_reasons.append("2017_rows_read")
    if rows_2018_plus_read != 0:
        infrastructure_reasons.append("2018_plus_rows_read")
    if k2_selected:
        infrastructure_reasons.append("k2_selected_as_candidate")
    if account_family_searched:
        infrastructure_reasons.append("account_family_searched")
    if not both_trees_match:
        infrastructure_reasons.append("formal_isolated_mismatch")
    if not clocks:
        infrastructure_reasons.append("no_clock_evidence")
    if infrastructure_reasons:
        return {
            "schema_id": SCHEMA_ID,
            "status": "infrastructure_gap",
            "account_contract_may_open": False,
            "reasons": infrastructure_reasons,
            "fresh_oos": False,
            "production_authority": False,
        }

    signal_reasons: list[str] = []
    for clock in clocks:
        if clock.decision_count <= 0:
            signal_reasons.append(f"{clock.variant_id}:empty")
            continue
        if not (clock.mean_daily_rankic > 0.0):
            signal_reasons.append(f"{clock.variant_id}:rankic_not_positive")
        for label, value in clock.subperiod_rankic.items():
            if not (value > 0.0):
                signal_reasons.append(f"{clock.variant_id}:{label}_rankic_not_positive")
        if not (clock.selected_median_opportunity_rank < clock.eligible_midpoint):
            signal_reasons.append(f"{clock.variant_id}:opportunity_not_better_than_random")
    status = (
        "no_signal"
        if signal_reasons
        else "diagnostic_signal_present_account_contract_may_open"
    )
    return {
        "schema_id": SCHEMA_ID,
        "status": status,
        "account_contract_may_open": status
        == "diagnostic_signal_present_account_contract_may_open",
        "reasons": signal_reasons,
        "clocks": [
            {
                "variant_id": clock.variant_id,
                "mean_daily_rankic": clock.mean_daily_rankic,
                "subperiod_rankic": dict(clock.subperiod_rankic),
                "selected_median_opportunity_rank": clock.selected_median_opportunity_rank,
                "eligible_midpoint": clock.eligible_midpoint,
                "decision_count": clock.decision_count,
                "factor_rankic": clock.factor_rankic,
                "k_state_rankic": clock.k_state_rankic,
                "residual_increment_rankic": clock.residual_increment_rankic,
            }
            for clock in clocks
        ],
        "fresh_oos": False,
        "production_authority": False,
        "complete_realized_pnl": False,
        "a0_a7_executed": False,
    }


__all__ = [
    "ATTRIBUTION_COLUMNS",
    "DIAGNOSTIC_PATH_ID",
    "DIAGNOSTIC_POLICY_ID",
    "DIAGNOSTIC_TOP_N",
    "FORBIDDEN_SCIENTIFIC_WALL_CLOCK_KEYS",
    "SCHEMA_ID",
    "SCORE_PATH_COLUMNS",
    "SSAClockEvidence",
    "StrategyScienceAcceptanceError",
    "SUBPERIODS",
    "adjudicate_strategy_science_acceptance",
    "assert_no_scientific_wall_clock",
    "assert_year_bounds",
    "build_attribution_ledger",
    "build_score_path_ledger",
    "build_selection_opportunity_ledger",
    "daily_rankic",
    "mask_subperiod",
    "opportunity_decision_summary",
    "validate_attribution_ledger",
    "validate_score_path_ledger",
]
