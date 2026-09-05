# pyright: reportAny=false, reportArgumentType=false
# pyright: reportAttributeAccessIssue=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnusedCallResult=false
"""Govern the non-financial shadow battle without weakening formal Round 3."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, cast

from factor_lab.factor_rotation.macro_regime_dual_strategy_round2 import (
    CHALLENGER_STRATEGY_ID,
    INCUMBENT_STRATEGY_ID,
)
from factor_lab.factor_rotation.macro_regime_dual_strategy_round3_execution import (
    COMPLETE_VALIDATION_YEARS,
    ROUND3_EXECUTION_TRIAL_ID,
    round3_execution_false_authority,
    validate_round3_execution_preflight,
)
from factor_lab.governance.canonicalization import canonical_digest

SHADOW_PREFLIGHT_SCHEMA_ID: Final = "macro_regime_dual_strategy_round3_nonfinancial_shadow_preflight@1.0"
SHADOW_CONTRACT_SCHEMA_ID: Final = "macro_regime_dual_strategy_round3_nonfinancial_shadow_contract@1.0"
SHADOW_RESULT_SCHEMA_ID: Final = "macro_regime_dual_strategy_round3_nonfinancial_shadow_result@1.0"
SHADOW_TRIAL_ID: Final = "macro_regime_v1_vs_reaka_v1_round3a_nonfinancial_shadow_2021_2025"
STRICT_FINANCIAL_BLOCKER: Final = "strict_financial_fixed_certified_artifact_missing"
_INPUT_COUNTS: Final[dict[str, int]] = {
    "stock_nonfinancial": 165,
    "timing_formula": 7,
    "macro_context": 6,
    "stock_level_input_count": 172,
    "unique_input_identity_count": 178,
}
_OMISSION: Final[dict[str, object]] = {
    "input_family": "strict_annual_first_release_financial",
    "factor_count": 21,
    "reason": STRICT_FINANCIAL_BLOCKER,
    "fallback_or_imputation_allowed": False,
    "formal_round3_equivalence_claimed": False,
}


def _seal(payload: dict[str, object]) -> dict[str, object]:
    payload.pop("canonical_digest", None)
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def _validate_digest(payload: Mapping[str, object]) -> None:
    expected = canonical_digest({key: value for key, value in payload.items() if key != "canonical_digest"})
    if payload.get("canonical_digest") != expected:
        raise ValueError("round3_shadow_canonical_digest_mismatch")


def build_round3_nonfinancial_shadow_contract() -> dict[str, object]:
    """Freeze the only permitted finance-absent continuation before outcomes."""

    payload: dict[str, object] = {
        "schema_id": SHADOW_CONTRACT_SCHEMA_ID,
        "trial_id": SHADOW_TRIAL_ID,
        "parent_formal_trial_id": ROUND3_EXECUTION_TRIAL_ID,
        "purpose": "provisional_replacement_evidence_not_formal_round3",
        "input_counts": dict(_INPUT_COUNTS),
        "declared_input_omission": dict(_OMISSION),
        "complete_validation_years": list(COMPLETE_VALIDATION_YEARS),
        "fold_policy": "train_through_y_minus_1_then_score_calendar_year_y",
        "target": "next_session_open_to_twentieth_market_session_close",
        "same_exam_for_both_strategies": True,
        "one_way_cost_bps": 15.0,
        "paired_primary_rule": ("moving_block_bootstrap_ci_excludes_zero_and_rank_ic_delta_same_direction"),
        "provisional_no_harm_thresholds": {
            "maximum_drawdown_relative_deterioration": 0.03,
            "turnover_relative_multiple": 1.25,
            "positive_outer_fold_rate": 0.60,
            "minimum_challenger_seed_count": 3,
        },
        "capacity_gate": {
            "evaluated": False,
            "reason": "adv_capacity_surface_not_part_of_fixed_ready_inputs",
        },
        "formal_replacement_allowed": False,
        "production_authority": False,
        "authority": round3_execution_false_authority(),
    }
    return _seal(payload)


def build_round3_nonfinancial_shadow_preflight(
    *,
    formal_preflight: Mapping[str, object],
    shadow_contract: Mapping[str, object],
) -> dict[str, object]:
    """Open only the declared ablation when strict finance is the sole blocker."""

    validate_round3_execution_preflight(formal_preflight)
    validate_round3_nonfinancial_shadow_contract(shadow_contract)
    blockers = formal_preflight.get("blockers")
    if formal_preflight.get("status") != "blocked" or blockers != [STRICT_FINANCIAL_BLOCKER]:
        raise ValueError("round3_shadow_requires_exact_single_formal_blocker")
    financial_binding = formal_preflight.get("financial_binding")
    macro_binding = formal_preflight.get("macro_binding")
    if (
        not isinstance(financial_binding, Mapping)
        or financial_binding.get("blockers") != [STRICT_FINANCIAL_BLOCKER]
        or not isinstance(macro_binding, Mapping)
        or macro_binding.get("status") != "ready"
    ):
        raise ValueError("round3_shadow_parent_binding_state_invalid")
    payload: dict[str, object] = {
        "schema_id": SHADOW_PREFLIGHT_SCHEMA_ID,
        "trial_id": SHADOW_TRIAL_ID,
        "status": "ready",
        "parent_formal_preflight_digest": str(formal_preflight.get("canonical_digest", "")),
        "shadow_contract_digest": str(shadow_contract.get("canonical_digest", "")),
        "input_counts": dict(_INPUT_COUNTS),
        "declared_input_omission": dict(_OMISSION),
        "macro_binding": dict(macro_binding),
        "market_cap_receipt_digest": str(formal_preflight.get("market_cap_receipt_digest", "")),
        "candidate_admission_digest": str(formal_preflight.get("candidate_admission_digest", "")),
        "remaining_blockers": [],
        "market_outcome_rows_read": 0,
        "battle_started": False,
        "formal_round3_status": "blocked",
        "formal_replacement_allowed": False,
        "authority": round3_execution_false_authority(),
    }
    _seal(payload)
    validate_round3_nonfinancial_shadow_preflight(payload)
    return payload


def validate_round3_nonfinancial_shadow_contract(
    payload: Mapping[str, object],
) -> None:
    if payload.get("schema_id") != SHADOW_CONTRACT_SCHEMA_ID:
        raise ValueError("round3_shadow_contract_schema_mismatch")
    if payload.get("trial_id") != SHADOW_TRIAL_ID:
        raise ValueError("round3_shadow_contract_trial_mismatch")
    if payload.get("input_counts") != _INPUT_COUNTS:
        raise ValueError("round3_shadow_contract_input_counts_changed")
    if payload.get("declared_input_omission") != _OMISSION:
        raise ValueError("round3_shadow_contract_omission_changed")
    if payload.get("formal_replacement_allowed") is not False:
        raise ValueError("round3_shadow_contract_cannot_authorize_replacement")
    _validate_false_authority(payload.get("authority"))
    _validate_digest(payload)


def validate_round3_nonfinancial_shadow_preflight(
    payload: Mapping[str, object],
) -> None:
    if payload.get("schema_id") != SHADOW_PREFLIGHT_SCHEMA_ID:
        raise ValueError("round3_shadow_preflight_schema_mismatch")
    if payload.get("trial_id") != SHADOW_TRIAL_ID:
        raise ValueError("round3_shadow_preflight_trial_mismatch")
    if payload.get("status") != "ready" or payload.get("remaining_blockers") != []:
        raise ValueError("round3_shadow_preflight_not_ready")
    if payload.get("input_counts") != _INPUT_COUNTS:
        raise ValueError("round3_shadow_preflight_input_counts_changed")
    if payload.get("declared_input_omission") != _OMISSION:
        raise ValueError("round3_shadow_preflight_omission_changed")
    if (
        payload.get("market_outcome_rows_read") != 0
        or payload.get("battle_started") is not False
        or payload.get("formal_round3_status") != "blocked"
        or payload.get("formal_replacement_allowed") is not False
    ):
        raise ValueError("round3_shadow_preflight_authority_boundary_invalid")
    _validate_false_authority(payload.get("authority"))
    _validate_digest(payload)


def _strategy_metrics(result: Mapping[str, object], strategy_id: str) -> Mapping[str, object]:
    rows = result.get("strategy_metrics")
    if not isinstance(rows, list):
        raise ValueError("round3_shadow_strategy_metrics_missing")
    match = next(
        (row for row in rows if isinstance(row, Mapping) and row.get("strategy_id") == strategy_id),
        None,
    )
    if not isinstance(match, Mapping):
        raise ValueError(f"round3_shadow_strategy_metrics_missing:{strategy_id}")
    return match


def _challenger_positive_fold_rate(result: Mapping[str, object]) -> float:
    folds = result.get("fold_results")
    if not isinstance(folds, list) or len(folds) != len(COMPLETE_VALIDATION_YEARS):
        raise ValueError("round3_shadow_five_folds_required")
    positive = 0
    for fold in folds:
        if not isinstance(fold, Mapping):
            raise ValueError("round3_shadow_fold_invalid")
        metrics = fold.get("challenger_annual_metrics")
        if not isinstance(metrics, Mapping):
            raise ValueError("round3_shadow_challenger_fold_metrics_missing")
        positive += int(
            float(
                cast(
                    float,
                    metrics.get("cost_adjusted_annualized_spread_return", 0.0),
                )
            )
            > 0.0
        )
    return positive / len(folds)


def build_round3_nonfinancial_shadow_assessment(
    result: Mapping[str, object],
) -> dict[str, object]:
    """Apply the pre-registered provisional replacement rules."""

    incumbent = _strategy_metrics(result, INCUMBENT_STRATEGY_ID)
    challenger = _strategy_metrics(result, CHALLENGER_STRATEGY_ID)
    incumbent_drawdown = abs(min(float(cast(float, incumbent["spread_max_drawdown"])), 0.0))
    challenger_drawdown = abs(min(float(cast(float, challenger["spread_max_drawdown"])), 0.0))
    drawdown_deterioration = challenger_drawdown - incumbent_drawdown
    incumbent_turnover = float(cast(float, incumbent["average_annualized_spread_turnover"]))
    challenger_turnover = float(cast(float, challenger["average_annualized_spread_turnover"]))
    turnover_ratio = challenger_turnover / incumbent_turnover if incumbent_turnover > 0.0 else None
    positive_fold_rate = _challenger_positive_fold_rate(result)
    folds = cast(list[Mapping[str, object]], result["fold_results"])
    seed_count = min(len(cast(Sequence[object], fold.get("challenger_seed_fit_receipts", []))) for fold in folds)
    paired = result.get("paired_comparison")
    if not isinstance(paired, Mapping):
        raise ValueError("round3_shadow_paired_comparison_missing")
    bootstrap = paired.get("moving_block_bootstrap")
    paired_ci_passed = bool(isinstance(bootstrap, Mapping) and bootstrap.get("ci_excludes_zero") is True)
    rank_ic_delta = float(cast(float, paired["challenger_minus_incumbent_mean_rank_ic"]))
    no_harm = {
        "maximum_drawdown": {
            "threshold": 0.03,
            "observed_relative_deterioration": drawdown_deterioration,
            "passed": drawdown_deterioration <= 0.03,
        },
        "turnover": {
            "threshold_relative_multiple": 1.25,
            "observed_relative_multiple": turnover_ratio,
            "passed": turnover_ratio is not None and turnover_ratio <= 1.25,
        },
        "positive_outer_fold_rate": {
            "threshold": 0.60,
            "observed": positive_fold_rate,
            "passed": positive_fold_rate >= 0.60,
        },
        "challenger_seed_count": {
            "threshold": 3,
            "observed": seed_count,
            "passed": seed_count >= 3,
        },
        "capacity": {
            "evaluated": False,
            "passed": False,
            "reason": "adv_capacity_surface_not_part_of_fixed_ready_inputs",
        },
    }
    evaluable_no_harm_passed = all(
        cast(Mapping[str, object], no_harm[key]).get("passed") is True
        for key in (
            "maximum_drawdown",
            "turnover",
            "positive_outer_fold_rate",
            "challenger_seed_count",
        )
    )
    mechanical_winner = result.get("winner_strategy_id")
    challenger_leads = mechanical_winner == CHALLENGER_STRATEGY_ID and paired_ci_passed and rank_ic_delta > 0.0 and evaluable_no_harm_passed
    if challenger_leads:
        verdict = "challenger_provisional_research_lead"
        recommendation = "advance_challenger_to_strict_financial_confirmation"
        scientific_verdict = "supported"
    elif mechanical_winner == INCUMBENT_STRATEGY_ID:
        verdict = "incumbent_research_lead"
        recommendation = "retain_incumbent_on_available_nonfinancial_evidence"
        scientific_verdict = "rejected"
    else:
        verdict = "inconclusive"
        recommendation = "continue_parallel_no_replacement"
        scientific_verdict = "inconclusive"
    assessment: dict[str, object] = {
        "shadow_verdict": verdict,
        "scientific_verdict": scientific_verdict,
        "provisional_replacement_recommendation": recommendation,
        "mechanical_winner_strategy_id": mechanical_winner,
        "paired_primary_gate_passed": paired_ci_passed,
        "rank_ic_direction_gate_passed": rank_ic_delta > 0.0,
        "evaluable_no_harm_passed": evaluable_no_harm_passed,
        "no_harm_gates": no_harm,
        "eligible_for_strict_financial_confirmation": challenger_leads,
        "eligible_for_promotion_review": False,
        "formal_replacement_allowed": False,
        "incumbent_pointer_changed": False,
        "formal_round3_status": "blocked",
    }
    assessment["canonical_digest"] = canonical_digest(assessment)
    return assessment


def _forbidden_paths(value: object, path: str = "$") -> list[str]:
    forbidden = {
        "monthly_metrics",
        "predictions",
        "stock_scores",
        "holdings",
        "orders",
        "test_year_drilldown",
    }
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key) in forbidden:
                found.append(child_path)
            found.extend(_forbidden_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_forbidden_paths(child, f"{path}[{index}]"))
    return found


def validate_round3_nonfinancial_shadow_result(
    payload: Mapping[str, object],
) -> None:
    if payload.get("schema_id") != SHADOW_RESULT_SCHEMA_ID:
        raise ValueError("round3_shadow_result_schema_mismatch")
    if payload.get("trial_id") != SHADOW_TRIAL_ID:
        raise ValueError("round3_shadow_result_trial_mismatch")
    if payload.get("status") != "completed":
        raise ValueError("round3_shadow_result_not_completed")
    if payload.get("complete_validation_years") != list(COMPLETE_VALIDATION_YEARS):
        raise ValueError("round3_shadow_result_years_changed")
    folds = payload.get("fold_results")
    if not isinstance(folds, list) or len(folds) != len(COMPLETE_VALIDATION_YEARS):
        raise ValueError("round3_shadow_result_five_fold_results_required")
    for raw, year in zip(folds, COMPLETE_VALIDATION_YEARS, strict=True):
        if not isinstance(raw, Mapping) or raw.get("validation_year") != year:
            raise ValueError("round3_shadow_result_fold_year_order_changed")
        if raw.get("train_end") != f"{year - 1}-12-31":
            raise ValueError(f"round3_shadow_result_train_prefix_mismatch:{year}")
        if raw.get("test_start") != f"{year}-01-01" or raw.get("test_end") != f"{year}-12-31":
            raise ValueError(f"round3_shadow_result_test_window_mismatch:{year}")
    strategies = payload.get("strategy_metrics")
    if not isinstance(strategies, list) or {raw.get("strategy_id") for raw in strategies if isinstance(raw, Mapping)} != {
        INCUMBENT_STRATEGY_ID,
        CHALLENGER_STRATEGY_ID,
    }:
        raise ValueError("round3_shadow_result_paired_strategy_metrics_required")
    if payload.get("input_counts") != _INPUT_COUNTS:
        raise ValueError("round3_shadow_result_input_counts_changed")
    if payload.get("declared_input_omission") != _OMISSION:
        raise ValueError("round3_shadow_result_omission_changed")
    assessment = payload.get("replacement_assessment")
    if not isinstance(assessment, Mapping):
        raise ValueError("round3_shadow_result_assessment_missing")
    if (
        assessment.get("eligible_for_promotion_review") is not False
        or assessment.get("formal_replacement_allowed") is not False
        or assessment.get("incumbent_pointer_changed") is not False
    ):
        raise ValueError("round3_shadow_result_replacement_authority_invalid")
    expected_assessment_digest = canonical_digest({key: value for key, value in assessment.items() if key != "canonical_digest"})
    if assessment.get("canonical_digest") != expected_assessment_digest:
        raise ValueError("round3_shadow_assessment_digest_mismatch")
    if payload.get("incomplete_preview_year") != 2026 or payload.get("incomplete_preview_scored") is not False:
        raise ValueError("round3_shadow_2026_preview_must_remain_unscored")
    black_box = payload.get("market_black_box_policy")
    if not isinstance(black_box, Mapping) or (
        black_box.get("test_year_outcomes_hidden_during_fit") is not True
        or black_box.get("test_year_drilldown_persisted") is not False
        or black_box.get("only_annual_and_paired_aggregate_metrics_persisted") is not True
    ):
        raise ValueError("round3_shadow_result_black_box_policy_invalid")
    forbidden = _forbidden_paths(payload)
    if forbidden:
        raise ValueError("round3_shadow_forbidden_detail:" + ",".join(forbidden))
    _validate_false_authority(payload.get("authority"))
    if payload.get("winner_strategy_id") not in {
        None,
        INCUMBENT_STRATEGY_ID,
        CHALLENGER_STRATEGY_ID,
    }:
        raise ValueError("round3_shadow_result_winner_invalid")
    _validate_digest(payload)


def _validate_false_authority(value: object) -> None:
    expected = round3_execution_false_authority()
    if not isinstance(value, Mapping) or dict(value) != expected:
        raise ValueError("round3_shadow_authority_must_remain_false")


def shadow_input_counts() -> dict[str, int]:
    return dict(_INPUT_COUNTS)


def shadow_declared_omission() -> dict[str, object]:
    return dict(_OMISSION)


__all__ = [
    "SHADOW_CONTRACT_SCHEMA_ID",
    "SHADOW_PREFLIGHT_SCHEMA_ID",
    "SHADOW_RESULT_SCHEMA_ID",
    "SHADOW_TRIAL_ID",
    "STRICT_FINANCIAL_BLOCKER",
    "build_round3_nonfinancial_shadow_assessment",
    "build_round3_nonfinancial_shadow_contract",
    "build_round3_nonfinancial_shadow_preflight",
    "shadow_declared_omission",
    "shadow_input_counts",
    "validate_round3_nonfinancial_shadow_contract",
    "validate_round3_nonfinancial_shadow_preflight",
    "validate_round3_nonfinancial_shadow_result",
]
