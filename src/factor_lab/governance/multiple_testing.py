"""Multiple-testing and overfit governance helper."""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from typing import Literal, TypedDict


class BenjaminiHochbergSummary(TypedDict):
    """Benjamini-Hochberg FDR adjustment summary."""

    significant_count: int
    adjusted_p_values: list[float]
    fdr_level: float


class MultipleTestingReport(TypedDict):
    """Conservative multiple-testing governance report."""

    governance_verdict: Literal["pass", "review_required", "high_risk"]
    warning_flags: list[str]
    adjusted_evidence_summary: (
        BenjaminiHochbergSummary | Literal["insufficient_for_formal_adjustment"]
    )
    total_tests_estimated: int | None
    search_scope_complete: bool
    search_scope: dict[str, int | None]
    documentation_note: str


def evaluate_benjamini_hochberg(
    p_values: Sequence[float], fdr_level: float = 0.05
) -> BenjaminiHochbergSummary:
    """Apply Benjamini-Hochberg procedure for FDR control."""
    if not p_values:
        return {
            "significant_count": 0,
            "adjusted_p_values": [],
            "fdr_level": fdr_level,
        }

    m = len(p_values)
    sorted_indices = sorted(range(m), key=lambda i: p_values[i])
    sorted_p_values = [p_values[i] for i in sorted_indices]

    significant_count = 0
    for k, p in enumerate(sorted_p_values, 1):
        if p <= (k / m) * fdr_level:
            significant_count = k

    # Adjust p-values: min(1.0, p * m / k) in reverse order
    adjusted = [1.0] * m
    min_adj = 1.0
    for k in range(m, 0, -1):
        p = sorted_p_values[k - 1]
        adj = min(min_adj, p * m / k)
        min_adj = adj
        adjusted[sorted_indices[k - 1]] = adj

    return {
        "significant_count": significant_count,
        "adjusted_p_values": adjusted,
        "fdr_level": fdr_level,
    }


def build_multiple_testing_report(
    candidate_count: int | None,
    param_search_count: int | None,
    protocol_variant_count: int | None,
    top_k: int,
    best_score: float,
    score_distribution: Sequence[float] | None = None,
    p_values: Sequence[float] | None = None,
) -> MultipleTestingReport:
    """
    Evaluate multiple testing risk and generate a conservative governance report.
    This is the V1 governance control; formal White Reality Check / deflated Sharpe
    can be added as subsequent enhancements.
    """
    search_scope = {
        "candidate_count": candidate_count,
        "param_search_count": param_search_count,
        "protocol_variant_count": protocol_variant_count,
    }
    search_scope_complete = all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 1
        for value in search_scope.values()
    )
    if not search_scope_complete:
        return {
            "governance_verdict": "high_risk",
            "warning_flags": [
                "selection_search_scope_missing",
                "multiple_testing_risk_unknown",
            ],
            "adjusted_evidence_summary": "insufficient_for_formal_adjustment",
            "total_tests_estimated": None,
            "search_scope_complete": False,
            "search_scope": search_scope,
            "documentation_note": (
                "Candidate, parameter, and protocol trial counts are mandatory. "
                "Unknown search scope cannot be treated as a one-test evaluation."
            ),
        }
    assert isinstance(candidate_count, int) and not isinstance(candidate_count, bool)
    assert isinstance(param_search_count, int) and not isinstance(
        param_search_count, bool
    )
    assert isinstance(protocol_variant_count, int) and not isinstance(
        protocol_variant_count, bool
    )
    normalized_candidate_count = int(candidate_count)
    normalized_param_search_count = int(param_search_count)
    normalized_protocol_variant_count = int(protocol_variant_count)
    total_tests = (
        normalized_candidate_count
        * normalized_param_search_count
        * normalized_protocol_variant_count
    )
    warnings: list[str] = []

    if total_tests > 100:
        warnings.append("too_many_candidates")

    if total_tests > 10 and best_score < 0.05:
        warnings.append("weak_best_score_after_search")

    if total_tests > 1 and normalized_protocol_variant_count < 2:
        warnings.append("insufficient_protocol_variants")

    if score_distribution and len(score_distribution) >= 2:
        if len(score_distribution) > top_k:
            top_scores = sorted(score_distribution, reverse=True)[:top_k]
        else:
            top_scores = score_distribution

        if len(top_scores) >= 2:
            stdev = statistics.stdev(top_scores)
            if stdev < 1e-4:
                warnings.append("concentrated_top_k")

    if "too_many_candidates" in warnings or "weak_best_score_after_search" in warnings:
        warnings.append("multiple_testing_risk_high")

    verdict: Literal["pass", "review_required", "high_risk"] = "pass"
    if "multiple_testing_risk_high" in warnings:
        verdict = "high_risk"
    elif warnings:
        verdict = "review_required"

    if p_values and len(p_values) > 0:
        adjusted_summary = evaluate_benjamini_hochberg(p_values)
    else:
        adjusted_summary = "insufficient_for_formal_adjustment"

    return {
        "governance_verdict": verdict,
        "warning_flags": warnings,
        "adjusted_evidence_summary": adjusted_summary,
        "total_tests_estimated": total_tests,
        "search_scope_complete": True,
        "search_scope": search_scope,
        "documentation_note": (
            "This is V1 conservative governance report. "
            "Formal White Reality Check / deflated Sharpe is a future enhancement."
        ),
    }
