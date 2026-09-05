"""Candidate-factor profiling and usage classification workflow."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

import pandas as pd

from factor_lab.factor_rotation.dates import normalize_date_series
from factor_lab.factor_rotation.effectiveness_profile import (
    build_factor_effectiveness_profile,
    build_factor_profile_cards,
)
from factor_lab.factor_rotation.factor_state import (
    ACTIVE_STATES,
    CORE_STABLE,
    HAZARD,
    INSUFFICIENT_HISTORY,
)

CANDIDATE_USAGE_SCHEMA_VERSION: Final[str] = "factor_rotation_candidate_usage.v1"

CORE_STATIC: Final[str] = "core_static"
DYNAMIC_CORE: Final[str] = "dynamic_core"
SATELLITE_ONLY: Final[str] = "satellite_only"
REGIME_CONDITIONAL: Final[str] = "regime_conditional"
RISK_FILTER_ONLY: Final[str] = "risk_filter_only"
REVERSE_SIGNAL_CANDIDATE: Final[str] = "reverse_signal_candidate"
WATCHLIST: Final[str] = "watchlist"
DISABLED: Final[str] = "disabled"

ALLOCATABLE_USAGE_CLASSES: Final[set[str]] = {
    CORE_STATIC,
    DYNAMIC_CORE,
    SATELLITE_ONLY,
    REGIME_CONDITIONAL,
}
SUPPRESSED_USAGE_CLASSES: Final[set[str]] = {
    RISK_FILTER_ONLY,
    REVERSE_SIGNAL_CANDIDATE,
    WATCHLIST,
    DISABLED,
}


def build_factor_portfolio_from_candidate_date_records(
    date_records: pd.DataFrame,
) -> pd.DataFrame:
    """Convert candidate validation date records into profile-compatible rows."""

    required = {"date", "factor_id", "top_excess"}
    missing = required - set(date_records.columns)
    if missing:
        raise ValueError(f"candidate date records missing columns: {sorted(missing)}")
    frame = date_records.copy()
    frame["date"] = normalize_date_series(frame["date"])
    frame["factor_id"] = frame["factor_id"].astype(str)
    frame["top_excess"] = pd.to_numeric(frame["top_excess"], errors="coerce")
    frame = frame.dropna(subset=["date", "factor_id", "top_excess"])
    return (
        frame.rename(columns={"top_excess": "excess_return"})[
            ["date", "factor_id", "excess_return"]
        ]
        .assign(bucket="top")
        .sort_values(["factor_id", "date"])
        .reset_index(drop=True)
    )


def build_candidate_profile_artifacts(
    promotion_records: Iterable[dict[str, object]],
    date_records: pd.DataFrame,
    *,
    lookback_windows: tuple[int, ...] = (30, 60, 126, 252, 504, 756),
    factor_metadata: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Build profile, cards, and usage report for all evaluable candidates."""

    promotion_records = [dict(record) for record in promotion_records]
    portfolio = build_factor_portfolio_from_candidate_date_records(date_records)
    profile = build_factor_effectiveness_profile(
        portfolio,
        lookback_windows=lookback_windows,
    )
    cards = build_factor_profile_cards(profile, factor_metadata=factor_metadata)
    usage_report = build_factor_candidate_usage_report(
        promotion_records,
        profile,
        cards,
    )
    enriched = enrich_promotion_records_with_usage(promotion_records, usage_report)
    return {
        "factor_portfolio_panel": portfolio,
        "factor_effectiveness_profile": profile,
        "factor_profile_cards": cards,
        "factor_candidate_usage_report": usage_report,
        "enriched_promotion_records": enriched,
    }


def build_factor_candidate_usage_report(
    promotion_records: Iterable[dict[str, object]],
    profile: pd.DataFrame,
    cards: dict[str, object] | None = None,
) -> dict[str, object]:
    """Classify how each candidate factor may be used downstream."""

    records = []
    profile = profile.copy()
    if not profile.empty:
        profile["factor_id"] = profile["factor_id"].astype(str)
    card_map = {
        str(card.get("factor_id")): card
        for card in (cards or {}).get("cards", [])
        if isinstance(card, dict) and card.get("factor_id") is not None
    }
    for record in promotion_records:
        factor_id = str(record.get("factor_id", ""))
        factor_profile = (
            profile[profile["factor_id"] == factor_id] if not profile.empty else profile
        )
        summary = summarize_factor_profile(factor_profile)
        usage, reasons = classify_candidate_usage(record, summary)
        records.append(
            {
                "factor_id": factor_id,
                "promotion_status": str(record.get("status", "")),
                "usage_classification": usage,
                "usage_reasons": reasons,
                "profile_summary": summary,
                "scalar_evidence": {
                    "mean_excess_return": _float_or_none(
                        record.get("mean_excess_return")
                    ),
                    "mean_rank_ic": _float_or_none(record.get("mean_rank_ic")),
                    "oos_pass_rate": _float_or_none(record.get("oos_pass_rate")),
                    "observation_count": int(record.get("observation_count", 0) or 0),
                },
                "profile_card": card_map.get(factor_id, {}),
                "schema_version": CANDIDATE_USAGE_SCHEMA_VERSION,
            }
        )
    usage_counts = pd.Series(
        [record["usage_classification"] for record in records], dtype="object"
    ).value_counts()
    return {
        "report_type": "factor_rotation_candidate_usage_report_v1",
        "schema_version": CANDIDATE_USAGE_SCHEMA_VERSION,
        "record_count": len(records),
        "usage_counts": {
            str(key): int(value) for key, value in usage_counts.to_dict().items()
        },
        "records": records,
        "pit_policy": "candidate_usage_from_train_only_profile_and_scalar_validation",
    }


def enrich_promotion_records_with_usage(
    promotion_records: Iterable[dict[str, object]],
    usage_report: dict[str, object],
) -> list[dict[str, object]]:
    usage_by_factor = {
        str(record.get("factor_id")): record
        for record in usage_report.get("records", [])
        if isinstance(record, dict)
    }
    enriched: list[dict[str, object]] = []
    for record in promotion_records:
        output = dict(record)
        usage = usage_by_factor.get(str(output.get("factor_id")), {})
        output["usage_classification"] = usage.get("usage_classification", WATCHLIST)
        output["usage_reasons"] = usage.get("usage_reasons", [])
        output["profile_summary"] = usage.get("profile_summary", {})
        output["candidate_usage_schema_version"] = CANDIDATE_USAGE_SCHEMA_VERSION
        enriched.append(output)
    return enriched


def summarize_factor_profile(profile: pd.DataFrame) -> dict[str, object]:
    if profile.empty:
        return {
            "profile_row_count": 0,
            "latest_date": "",
            "active_state_share": 0.0,
            "hazard_state_share": 0.0,
            "core_state_share": 0.0,
            "positive_profile_share": 0.0,
            "best_lookback_days": None,
            "best_recent_score": None,
            "latest_states": [],
        }
    frame = profile.copy()
    frame["date"] = normalize_date_series(frame["date"])
    frame["state_label"] = frame["state_label"].astype(str)
    latest_date = frame["date"].max()
    latest = frame[frame["date"] == latest_date].copy()
    latest["top_bucket_excess_sharpe"] = pd.to_numeric(
        latest["top_bucket_excess_sharpe"],
        errors="coerce",
    )
    ranked_latest = latest.sort_values("top_bucket_excess_sharpe", ascending=False)
    best = ranked_latest.iloc[0] if not ranked_latest.empty else None
    state_counts = frame["state_label"].value_counts(normalize=True)
    positive_share = float((frame["top_bucket_excess_mean"] > 0.0).mean())
    return {
        "profile_row_count": int(len(frame)),
        "latest_date": str(latest_date),
        "active_state_share": float(
            sum(state_counts.get(state, 0.0) for state in ACTIVE_STATES)
        ),
        "hazard_state_share": float(state_counts.get(HAZARD, 0.0)),
        "core_state_share": float(state_counts.get(CORE_STABLE, 0.0)),
        "positive_profile_share": positive_share,
        "insufficient_history_share": float(state_counts.get(INSUFFICIENT_HISTORY, 0.0)),
        "best_lookback_days": (
            int(best["lookback_days"]) if best is not None and pd.notna(best["lookback_days"]) else None
        ),
        "best_recent_score": (
            float(best["top_bucket_excess_sharpe"])
            if best is not None and pd.notna(best["top_bucket_excess_sharpe"])
            else None
        ),
        "latest_states": [
            {
                "lookback_days": int(row["lookback_days"]),
                "state_label": str(row["state_label"]),
                "top_bucket_excess_sharpe": _float_or_none(
                    row["top_bucket_excess_sharpe"]
                ),
            }
            for _, row in latest.iterrows()
        ],
    }


def classify_candidate_usage(
    promotion_record: dict[str, object],
    profile_summary: dict[str, object],
) -> tuple[str, list[str]]:
    """Classify intended usage from scalar evidence and profile shape."""

    status = str(promotion_record.get("status", ""))
    mean_excess = _float_or_none(promotion_record.get("mean_excess_return")) or 0.0
    mean_ic = _float_or_none(promotion_record.get("mean_rank_ic")) or 0.0
    oos = _float_or_none(promotion_record.get("oos_pass_rate")) or 0.0
    obs = int(promotion_record.get("observation_count", 0) or 0)
    active_share = float(profile_summary.get("active_state_share", 0.0) or 0.0)
    hazard_share = float(profile_summary.get("hazard_state_share", 0.0) or 0.0)
    core_share = float(profile_summary.get("core_state_share", 0.0) or 0.0)
    positive_share = float(profile_summary.get("positive_profile_share", 0.0) or 0.0)

    reasons: list[str] = []
    if obs < 20 or int(profile_summary.get("profile_row_count", 0) or 0) == 0:
        return WATCHLIST, ["insufficient_profile_or_scalar_observations"]
    if hazard_share >= 0.35:
        return DISABLED, ["high_hazard_profile_share"]
    if mean_excess < 0.0 and mean_ic < 0.0 and positive_share < 0.35:
        return REVERSE_SIGNAL_CANDIDATE, ["negative_scalar_evidence_and_profile"]
    if mean_excess <= 0.0 and mean_ic > 0.0 and active_share >= 0.35:
        return RISK_FILTER_ONLY, ["rank_ic_positive_but_top_bucket_not_positive"]

    if status == "validated_factor" and core_share >= 0.35 and oos >= 0.60:
        reasons.extend(["validated_scalar_evidence", "material_core_state_share"])
        return CORE_STATIC, reasons
    if status == "validated_factor" and active_share >= 0.45 and oos >= 0.50:
        reasons.extend(["validated_scalar_evidence", "active_profile_states"])
        return DYNAMIC_CORE, reasons
    if active_share >= 0.30 and positive_share >= 0.45:
        return SATELLITE_ONLY, ["positive_but_not_stable_enough_for_core"]
    if active_share > 0.0:
        return REGIME_CONDITIONAL, ["limited_active_profile_windows"]
    return WATCHLIST, ["mixed_or_weak_profile_evidence"]


def usage_records_by_factor(usage_report: dict[str, object] | None) -> dict[str, dict[str, object]]:
    if not usage_report:
        return {}
    return {
        str(record.get("factor_id")): record
        for record in usage_report.get("records", [])
        if isinstance(record, dict) and record.get("factor_id") is not None
    }


def _float_or_none(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) else None
