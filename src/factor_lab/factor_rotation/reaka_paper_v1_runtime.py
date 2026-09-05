# pyright: reportAny=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportArgumentType=false, reportReturnType=false
# pyright: reportGeneralTypeIssues=false, reportCallIssue=false
# pyright: reportAttributeAccessIssue=false, reportMissingTypeStubs=false
"""Aggregate-only diagnostic runner for the formula-faithful REAKA successor.

The 2021--2025 Round-3A exam was already opened by the earlier proxy.  This
runner therefore establishes implementation conformance and replayability; it
cannot issue another scientific vote, replace the incumbent pointer, or grant
production authority regardless of the observed return.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from factor_lab.factor_rotation.macro_regime_dual_strategy_round2 import (
    Round2Config,
    build_round2_panel,
    evaluate_predictions,
    fold_indices,
    prediction_frame,
)
from factor_lab.factor_rotation.macro_regime_dual_strategy_round3_execution import (
    COMPLETE_VALIDATION_YEARS,
)
from factor_lab.factor_rotation.macro_regime_dual_strategy_round3_runtime import (
    Round3FeatureBundle,
    Round3TargetBundle,
)
from factor_lab.factor_rotation.reaka_paper_v1 import (
    REAKA_PAPER_STRATEGY_ID,
    FactorLabReakaAdapterConfig,
    ReakaPaperConfig,
    build_reaka_paper_replication_contract,
    fit_reaka_paper_challenger,
)
from factor_lab.governance.canonicalization import canonical_digest
from factor_lab.governance.reaka_foundation_contract import require_research_action

REAKA_PAPER_ARM_ID: Final = "dual_lstm_gate_aks_conditional_ddpm_joint_v1"
REAKA_PAPER_DIAGNOSTIC_SCHEMA_ID: Final = "macro_regime_dual_strategy_reaka_paper_v1_diagnostic@1.0"
REAKA_PAPER_DIAGNOSTIC_TRIAL_ID: Final = "macro_regime_reaka_paper_v1_consumed_round3a_diagnostic_2021_2025"
_FALSE_AUTHORITY: Final[dict[str, bool]] = {
    "asset_selection_allowed": False,
    "individual_stock_scoring_allowed": False,
    "portfolio_construction_allowed": False,
    "portfolio_execution": False,
    "holdings_created": False,
    "orders_created": False,
    "production_authority": False,
}


@dataclass(frozen=True, slots=True)
class ReakaPaperDiagnosticConfig:
    """Frozen before this implementation-only replay opens model outcomes."""

    model: ReakaPaperConfig = field(default_factory=ReakaPaperConfig)
    adapter: FactorLabReakaAdapterConfig = field(default_factory=FactorLabReakaAdapterConfig)
    validation_years: tuple[int, ...] = COMPLETE_VALIDATION_YEARS
    seeds: tuple[int, ...] = (11, 29, 47)
    minimum_feature_coverage: float = 0.50
    top_bottom_fraction: float = 0.20
    long_only_count: int = 50
    one_way_cost_bps: float = 15.0
    bootstrap_replicates: int = 5000
    bootstrap_block_months: int = 3

    def validate(self) -> None:
        self.model.validate()
        self.adapter.validate()
        if self.validation_years != COMPLETE_VALIDATION_YEARS:
            raise ValueError("reaka_paper_consumed_exam_years_must_remain_frozen")
        if not self.seeds or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("reaka_paper_seed_identity_invalid")
        if not 0.0 < self.minimum_feature_coverage <= 1.0:
            raise ValueError("reaka_paper_feature_coverage_invalid")
        if not 0.0 < self.top_bottom_fraction < 0.5:
            raise ValueError("reaka_paper_top_bottom_fraction_invalid")
        if self.long_only_count < 1 or self.one_way_cost_bps < 0.0:
            raise ValueError("reaka_paper_portfolio_policy_invalid")

    def evaluation_config(self) -> Round2Config:
        self.validate()
        return Round2Config(
            lookback_months=2,
            minimum_feature_coverage=self.minimum_feature_coverage,
            duplicate_resolution_policy=("round3a_fixed_unique_lineage_consumed_diagnostic"),
            latent_dim=self.model.latent_dim,
            encoder_hidden_dim=self.model.network_hidden_dim,
            operator_count=self.model.operator_count,
            base_epochs=self.model.training_epochs,
            residual_epochs=self.model.training_epochs,
            diffusion_steps=self.model.diffusion_steps,
            batch_size=self.model.batch_size,
            learning_rate=self.model.learning_rate,
            validation_years=self.validation_years,
            seeds=self.seeds,
            top_bottom_fraction=self.top_bottom_fraction,
            long_only_count=self.long_only_count,
            one_way_cost_bps=self.one_way_cost_bps,
            bootstrap_replicates=self.bootstrap_replicates,
            bootstrap_block_months=self.bootstrap_block_months,
        )

    def as_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "model": self.model.as_dict(),
            "adapter": self.adapter.as_dict(),
            "validation_years": list(self.validation_years),
            "seeds": list(self.seeds),
            "minimum_feature_coverage": self.minimum_feature_coverage,
            "top_bottom_fraction": self.top_bottom_fraction,
            "long_only_count": self.long_only_count,
            "one_way_cost_bps": self.one_way_cost_bps,
            "bootstrap_replicates": self.bootstrap_replicates,
            "bootstrap_block_months": self.bootstrap_block_months,
        }


def build_reaka_paper_diagnostic_spec(
    *,
    config: ReakaPaperDiagnosticConfig | None = None,
    ancestor_evidence_digest: str,
) -> dict[str, object]:
    """Freeze a diagnostic-only descendant spec before fitting the new graph."""

    frozen = config or ReakaPaperDiagnosticConfig()
    frozen.validate()
    if not _is_digest(ancestor_evidence_digest):
        raise ValueError("reaka_paper_ancestor_evidence_digest_invalid")
    paper_contract = build_reaka_paper_replication_contract(
        config=frozen.model,
        input_profile="factorlab_round3a_monthly_adapter",
    )
    payload: dict[str, object] = {
        "schema_id": "macro_regime_dual_strategy_reaka_paper_v1_spec@1.0",
        "implementation_id": "reaka_paper_architecture_v1",
        "strategy_id": REAKA_PAPER_STRATEGY_ID,
        "arm_id": REAKA_PAPER_ARM_ID,
        "paper_contract_digest": paper_contract["canonical_digest"],
        "paper_contract": paper_contract,
        "config": frozen.as_dict(),
        "ancestor_consumed_scope": {
            "period": "2021-2025",
            "ancestor_evidence_digest": ancestor_evidence_digest,
            "historical_scope_previously_consumed": True,
            "derived_from_evidence_ref": (
                "docs/ops/evidence/macro_regime_v1_vs_reaka_v1/round3a_nonfinancial_shadow_execution_20260810/shadow_result.json"
            ),
        },
        "run_classification": {
            "implementation_sanity": True,
            "diagnostic_only": True,
            "fresh_oos": False,
            "scientific_vote_allowed": False,
            "scientific_claim_count_delta": 0,
            "eligible_for_promotion_review": False,
            "formal_replacement_allowed": False,
            "production_authority": False,
        },
        "search_policy": {
            "hyperparameter_search_count": 0,
            "result_conditioned_parameter_change_allowed": False,
            "retry_policy": "exact_replay_or_bug_fix_only",
        },
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def run_reaka_paper_round3a_diagnostic(
    *,
    features: Round3FeatureBundle,
    targets: Round3TargetBundle,
    spec: Mapping[str, object],
    config: ReakaPaperDiagnosticConfig | None = None,
) -> dict[str, object]:
    """Run the frozen successor on consumed history and retain aggregates only."""
    require_research_action(Path(__file__).resolve().parents[3], "train")

    frozen = config or ReakaPaperDiagnosticConfig()
    frozen.validate()
    validate_reaka_paper_diagnostic_spec(spec, config=frozen)
    if features.receipt.get("input_variant") != ("nonfinancial_shadow_declared_ablation"):
        raise ValueError("reaka_paper_diagnostic_requires_round3a_feature_bundle")
    evaluation_config = frozen.evaluation_config()
    panel = build_round2_panel(
        month_dates=features.month_dates,
        symbols=features.symbols,
        factor_ids=features.factor_ids,
        raw_features=features.raw_features,
        targets=targets.targets,
        target_available_at=targets.target_available_at,
        tradeable=targets.tradeable,
        config=evaluation_config,
    )
    prediction_parts: list[pd.DataFrame] = []
    fold_results: list[dict[str, object]] = []
    for year in frozen.validation_years:
        train_indices, test_indices = fold_indices(
            panel,
            validation_year=year,
        )
        seed_results = [
            fit_reaka_paper_challenger(
                panel=panel,
                train_indices=train_indices,
                test_indices=test_indices,
                config=frozen.model,
                adapter_config=frozen.adapter,
                seed=seed,
            )
            for seed in frozen.seeds
        ]
        reference_indices = seed_results[0].sample_indices
        if any(not np.array_equal(reference_indices, result.sample_indices) for result in seed_results[1:]):
            raise ValueError("reaka_paper_seed_evaluation_coordinate_drift")
        scores = np.mean(
            np.vstack([result.scores for result in seed_results]),
            axis=0,
        )
        predictions = prediction_frame(
            panel,
            sample_indices=reference_indices,
            scores=scores,
            strategy_id=REAKA_PAPER_STRATEGY_ID,
            arm_id=REAKA_PAPER_ARM_ID,
            seed=None,
            validation_year=year,
        )
        annual_metrics, _ = evaluate_predictions(
            predictions,
            config=evaluation_config,
        )
        prediction_parts.append(predictions)
        fold_results.append(
            {
                "validation_year": year,
                "train_end": f"{year - 1}-12-31",
                "test_start": f"{year}-01-01",
                "test_end": f"{year}-12-31",
                "train_candidate_row_count": int(train_indices.size),
                "test_candidate_row_count": int(test_indices.size),
                "scored_test_row_count": int(reference_indices.size),
                "annual_metrics": annual_metrics,
                "seed_fit_receipts": [
                    _fit_receipt(result.diagnostics, seed=seed)
                    for seed, result in zip(
                        frozen.seeds,
                        seed_results,
                        strict=True,
                    )
                ],
            }
        )
    predictions = pd.concat(prediction_parts, ignore_index=True)
    metrics, _ = evaluate_predictions(predictions, config=evaluation_config)
    result: dict[str, object] = {
        "schema_id": REAKA_PAPER_DIAGNOSTIC_SCHEMA_ID,
        "trial_id": REAKA_PAPER_DIAGNOSTIC_TRIAL_ID,
        "status": "completed",
        "strategy_id": REAKA_PAPER_STRATEGY_ID,
        "arm_id": REAKA_PAPER_ARM_ID,
        "spec_digest": spec["canonical_digest"],
        "complete_validation_years": list(frozen.validation_years),
        "fold_results": fold_results,
        "strategy_metrics": metrics,
        "paper_architecture_conformance": {
            "status": "paper_architecture_complete_with_frozen_assumptions",
            "formula_graph_complete": True,
            "paper_numeric_replication_claimed": False,
            "paper_dataset_replication_claimed": False,
            "factorlab_input_adapter": "monthly_172_feature_plus_lagged_historical_20_session_return",
        },
        "scientific_classification": {
            "historical_scope_previously_consumed": True,
            "implementation_sanity": True,
            "diagnostic_only": True,
            "fresh_oos": False,
            "scientific_vote_allowed": False,
            "scientific_claim_count_delta": 0,
            "eligible_for_promotion_review": False,
            "formal_replacement_allowed": False,
        },
        "input_receipts": {
            "feature_receipt_digest": features.receipt.get("canonical_digest"),
            "market_outcome_receipt_digest": targets.receipt.get("canonical_digest"),
            "stock_feature_count": len(features.factor_ids),
            "macro_context_used_by_paper_core": False,
        },
        "config": frozen.as_dict(),
        "authority": dict(_FALSE_AUTHORITY),
    }
    result["canonical_digest"] = canonical_digest(result)
    validate_reaka_paper_diagnostic_result(result)
    return result


def validate_reaka_paper_diagnostic_spec(
    payload: Mapping[str, object],
    *,
    config: ReakaPaperDiagnosticConfig | None = None,
) -> None:
    frozen = config or ReakaPaperDiagnosticConfig()
    frozen.validate()
    if payload.get("schema_id") != ("macro_regime_dual_strategy_reaka_paper_v1_spec@1.0"):
        raise ValueError("reaka_paper_spec_schema_invalid")
    if payload.get("strategy_id") != REAKA_PAPER_STRATEGY_ID:
        raise ValueError("reaka_paper_spec_strategy_invalid")
    if payload.get("config") != frozen.as_dict():
        raise ValueError("reaka_paper_spec_config_drift")
    ancestor = payload.get("ancestor_consumed_scope")
    classification = payload.get("run_classification")
    if not isinstance(ancestor, Mapping) or (ancestor.get("historical_scope_previously_consumed") is not True):
        raise ValueError("reaka_paper_spec_consumed_ancestry_missing")
    _require_false_claims(classification)
    if payload.get("canonical_digest") != canonical_digest({key: value for key, value in payload.items() if key != "canonical_digest"}):
        raise ValueError("reaka_paper_spec_digest_mismatch")


def validate_reaka_paper_diagnostic_result(payload: Mapping[str, object]) -> None:
    if payload.get("schema_id") != REAKA_PAPER_DIAGNOSTIC_SCHEMA_ID:
        raise ValueError("reaka_paper_result_schema_invalid")
    if payload.get("strategy_id") != REAKA_PAPER_STRATEGY_ID:
        raise ValueError("reaka_paper_result_strategy_invalid")
    if payload.get("complete_validation_years") != list(COMPLETE_VALIDATION_YEARS):
        raise ValueError("reaka_paper_result_exam_year_drift")
    conformance = payload.get("paper_architecture_conformance")
    if not isinstance(conformance, Mapping) or (conformance.get("status") != "paper_architecture_complete_with_frozen_assumptions"):
        raise ValueError("reaka_paper_result_conformance_incomplete")
    _require_false_claims(payload.get("scientific_classification"))
    authority = payload.get("authority")
    if authority != _FALSE_AUTHORITY:
        raise ValueError("reaka_paper_result_authority_must_remain_false")
    if payload.get("canonical_digest") != canonical_digest({key: value for key, value in payload.items() if key != "canonical_digest"}):
        raise ValueError("reaka_paper_result_digest_mismatch")


def _fit_receipt(
    diagnostics: Mapping[str, object],
    *,
    seed: int,
) -> dict[str, object]:
    allowed = (
        "fit_kind",
        "strategy_id",
        "input_factor_count",
        "train_row_count",
        "test_row_count",
        "dropped_train_window_count",
        "dropped_test_window_count",
        "last_epoch_joint_losses",
        "joint_loss_exact_sum",
        "separate_postfit_residual_training",
        "ranking_head",
        "operator_count",
        "operator_occupancy",
        "operator_digest",
        "gate_mean",
        "sampled_residual_energy",
        "initial_gaussian_noise_energy",
        "reverse_process_started_from_gaussian_noise",
        "test_current_outcomes_used_during_fit",
        "historical_return_availability_checked_per_decision",
        "paper_contract_digest",
    )
    receipt = {key: diagnostics[key] for key in allowed if key in diagnostics}
    receipt["seed"] = seed
    receipt["canonical_digest"] = canonical_digest(receipt)
    return receipt


def _require_false_claims(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("reaka_paper_false_claim_mapping_required")
    false_fields = (
        "fresh_oos",
        "scientific_vote_allowed",
        "eligible_for_promotion_review",
        "formal_replacement_allowed",
    )
    for field_name in false_fields:
        if value.get(field_name) is not False:
            raise ValueError(f"reaka_paper_{field_name}_must_be_false")
    if value.get("scientific_claim_count_delta") != 0:
        raise ValueError("reaka_paper_scientific_claim_count_must_not_change")


def _is_digest(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    suffix = value.removeprefix("sha256:")
    return len(suffix) == 64 and all(character in "0123456789abcdef" for character in suffix)


__all__ = [
    "REAKA_PAPER_ARM_ID",
    "REAKA_PAPER_DIAGNOSTIC_SCHEMA_ID",
    "REAKA_PAPER_DIAGNOSTIC_TRIAL_ID",
    "ReakaPaperDiagnosticConfig",
    "build_reaka_paper_diagnostic_spec",
    "run_reaka_paper_round3a_diagnostic",
    "validate_reaka_paper_diagnostic_result",
    "validate_reaka_paper_diagnostic_spec",
]
