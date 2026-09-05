"""Project-level temporal integrity contracts for research and publication."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import Final

from factor_lab.core.errors import ValidationError
from factor_lab.governance.evidence_resolver import (
    EvidenceCatalog,
    resolve_evidence_refs,
)

TEMPORAL_EVALUATION_STAGES: Final[tuple[str, ...]] = (
    "diagnostic",
    "discovery",
    "validation",
    "lockbox",
)
DIAGNOSTIC_ONLY_MODES: Final[tuple[str, ...]] = (
    "leave_one_year_out",
    "random_cross_validation",
)
PROMOTION_ELIGIBLE_MODES: Final[tuple[str, ...]] = (
    "expanding_past_only",
    "rolling_past_only",
    "purged_expanding_past_only",
    "purged_rolling_past_only",
)
STRICT_EVIDENCE_STATUSES: Final[frozenset[str]] = frozenset({"passed"})
STRICT_PREPROCESSING_SCOPES: Final[frozenset[str]] = frozenset(
    {"train_only", "not_applicable"}
)
STRICT_EVIDENCE_REF_FIELDS: Final[tuple[str, ...]] = (
    "data_usage_ledger_ref",
    "selection_freeze_manifest_ref",
    "preprocessing_fit_manifest_ref",
    "feature_availability_audit_ref",
    "label_separation_audit_ref",
    "universe_pit_audit_ref",
    "multiple_testing_report_ref",
    "evaluation_result_ref",
)
LOCKBOX_EVIDENCE_REF_FIELDS: Final[tuple[str, ...]] = (
    "lockbox_open_receipt_ref",
    "lockbox_access_receipt_ref",
)
AT5_TEMPORAL_POLICY_ID: Final = "chronological_nested_selection_and_lockbox@5"
AT5_EVIDENCE_ARTIFACT_TYPES: Final[dict[str, str]] = {
    "data_usage_ledger_ref": "data_usage_ledger",
    "selection_freeze_manifest_ref": "selection_freeze_manifest",
    "preprocessing_fit_manifest_ref": "preprocessing_fit_manifest",
    "feature_availability_audit_ref": "feature_availability_audit",
    "label_separation_audit_ref": "label_separation_audit",
    "universe_pit_audit_ref": "universe_pit_audit",
    "multiple_testing_report_ref": "multiple_testing_report",
    "evaluation_result_ref": "evaluation_result",
    "lockbox_open_receipt_ref": "lockbox_open_receipt",
    "lockbox_access_receipt_ref": "lockbox_access_receipt",
}


@dataclass(frozen=True, slots=True)
class TemporalSelectionValidationPolicy:
    """Policy separating search, selection, validation, and final lockbox use."""

    policy_id: str
    stage_order: tuple[str, ...]
    diagnostic_only_modes: tuple[str, ...]
    promotion_eligible_modes: tuple[str, ...]
    required_outputs: tuple[str, ...]
    blocked_patterns: tuple[str, ...]
    assistant_obligation: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


CANONICAL_TEMPORAL_SELECTION_VALIDATION_POLICY: Final = (
    TemporalSelectionValidationPolicy(
        policy_id="chronological_nested_selection_and_lockbox@4",
        stage_order=TEMPORAL_EVALUATION_STAGES,
        diagnostic_only_modes=DIAGNOSTIC_ONLY_MODES,
        promotion_eligible_modes=PROMOTION_ELIGIBLE_MODES,
        required_outputs=(
            "temporal_evaluation_contract",
            "data_usage_ledger",
            "selection_freeze_manifest",
            "preprocessing_fit_manifest",
            "feature_availability_audit",
            "label_separation_audit",
            "universe_pit_audit",
            "multiple_testing_report",
            "evaluation_result",
            "one_shot_lockbox_manifest",
        ),
        blocked_patterns=(
            "future_years_in_training_for_historical_test",
            "loyo_used_as_production_oos",
            "same_validation_rows_reused_for_formula_or_parameter_selection",
            "previously_consumed_rows_relabelled_as_validation_or_lockbox",
            "evaluation_starts_before_candidate_or_prior_stage_freeze",
            "full_sample_preprocessing_before_temporal_split",
            "label_or_forward_return_present_in_runtime_features",
            "non_pit_universe_used_for_promotion",
            "multiple_testing_status_missing_or_blocked",
            "discovery_stage_emits_production_candidate",
            "lockbox_opened_before_candidate_freeze",
            "lockbox_reopened_after_result_review",
            "declared_evaluation_window_not_yet_completed",
            "lockbox_candidate_differs_from_prior_validation_candidate",
        ),
        assistant_obligation=(
            "Treat LOYO and random CV as diagnostics only. Promotion evidence must "
            "use past-only folds, train-only preprocessing, as-of feature audits, "
            "label separation, PIT universe evidence, multiple-testing governance, "
            "a frozen candidate, and a one-shot lockbox that starts after freeze."
        ),
    )
)
CANONICAL_TEMPORAL_SELECTION_VALIDATION_POLICY_V5: Final = (
    TemporalSelectionValidationPolicy(
        policy_id=AT5_TEMPORAL_POLICY_ID,
        stage_order=TEMPORAL_EVALUATION_STAGES,
        diagnostic_only_modes=DIAGNOSTIC_ONLY_MODES,
        promotion_eligible_modes=PROMOTION_ELIGIBLE_MODES,
        required_outputs=(
            *CANONICAL_TEMPORAL_SELECTION_VALIDATION_POLICY.required_outputs,
            "lockbox_open_receipt",
            "lockbox_access_receipt",
            "resolved_evidence_report",
        ),
        blocked_patterns=(
            *CANONICAL_TEMPORAL_SELECTION_VALIDATION_POLICY.blocked_patterns,
            "unresolved_evidence_ref_used_for_promotion",
            "lockbox_open_self_reported_without_receipt",
            "lockbox_data_access_unbrokered",
        ),
        assistant_obligation=(
            "Use @5 only when every strict evidence ref resolves through the "
            "EvidenceResolver with matching schema/checksum/type/fingerprint/"
            "lineage. @4 remains historical/diagnostic and cannot support a "
            "production candidate."
        ),
    )
)


def canonical_temporal_selection_validation_policy() -> dict[str, object]:
    """Return the canonical project-level temporal integrity policy."""

    return CANONICAL_TEMPORAL_SELECTION_VALIDATION_POLICY.to_dict()


def canonical_temporal_selection_validation_policy_v5() -> dict[str, object]:
    """Return the promotion-capable @5 temporal integrity policy."""

    return CANONICAL_TEMPORAL_SELECTION_VALIDATION_POLICY_V5.to_dict()


def validate_temporal_evaluation_contract(
    contract: Mapping[str, object],
) -> dict[str, object]:
    """Fail closed when temporal evidence is used outside its declared role."""

    policy = CANONICAL_TEMPORAL_SELECTION_VALIDATION_POLICY
    policy_id = str(contract.get("policy_id", ""))
    stage = str(contract.get("stage", ""))
    mode = str(contract.get("evaluation_mode", ""))
    train_years = _normalized_years(contract.get("train_years"))
    test_years = _normalized_years(contract.get("test_years"))
    lockbox_years = _normalized_years(contract.get("lockbox_years"))
    lockbox_status = str(contract.get("lockbox_status", ""))
    production_claim = str(contract.get("production_claim", ""))
    candidate_frozen_value = contract.get("candidate_frozen")
    selected_on_test_rows_value = contract.get(
        "formula_or_parameter_selected_on_test_rows"
    )
    test_rows_previously_consumed_value = contract.get(
        "test_rows_previously_consumed_by_search"
    )
    candidate_frozen = candidate_frozen_value is True
    selected_on_test_rows = selected_on_test_rows_value is True
    test_rows_previously_consumed = test_rows_previously_consumed_value is True
    evaluation_reuse_count_value = contract.get("evaluation_reuse_count")
    evaluation_reuse_count = _normalized_nonnegative_int(
        evaluation_reuse_count_value
    )
    evaluation_sample_count_value = contract.get("evaluation_sample_count")
    candidate_fingerprint = str(contract.get("candidate_fingerprint", "")).strip()
    selection_freeze_date = _normalized_iso_date(
        contract.get("selection_freeze_date")
    )
    train_end_date = _normalized_iso_date(contract.get("train_end_date"))
    test_start_date = _normalized_iso_date(contract.get("test_start_date"))
    test_end_date = _normalized_iso_date(contract.get("test_end_date"))
    evaluation_completed_date = _normalized_iso_date(
        contract.get("evaluation_completed_date")
    )
    preprocessing_fit_scope = str(contract.get("preprocessing_fit_scope", ""))
    feature_availability_status = str(
        contract.get("feature_availability_status", "")
    )
    label_separation_status = str(contract.get("label_separation_status", ""))
    universe_pit_status = str(contract.get("universe_pit_status", ""))
    multiple_testing_status = str(contract.get("multiple_testing_status", ""))

    blockers: list[str] = []
    warnings: list[str] = []
    if policy_id != policy.policy_id:
        blockers.append("current_temporal_policy_id_required")
    if stage not in policy.stage_order:
        blockers.append("unknown_temporal_evaluation_stage")
    for field_name, value in (
        ("candidate_frozen", candidate_frozen_value),
        (
            "formula_or_parameter_selected_on_test_rows",
            selected_on_test_rows_value,
        ),
        (
            "test_rows_previously_consumed_by_search",
            test_rows_previously_consumed_value,
        ),
    ):
        if not isinstance(value, bool):
            blockers.append(f"{field_name}_must_be_boolean")
    if not _is_nonnegative_int(evaluation_reuse_count_value):
        blockers.append("evaluation_reuse_count_must_be_nonnegative_integer")
    if mode in policy.diagnostic_only_modes and stage != "diagnostic":
        blockers.append("diagnostic_mode_used_for_candidate_promotion")
    if stage in {"discovery", "validation", "lockbox"} and mode not in (
        policy.promotion_eligible_modes
    ):
        blockers.append("non_chronological_mode_used_for_temporal_claim")
    year_overlap = set(train_years).intersection(test_years)
    if year_overlap and not (
        train_end_date and test_start_date and train_end_date < test_start_date
    ):
        blockers.append("train_test_year_overlap_without_date_separation")
    if (
        stage in {"discovery", "validation", "lockbox"}
        and train_years
        and test_years
        and max(train_years) >= min(test_years)
        and not (
            train_end_date
            and test_start_date
            and train_end_date < test_start_date
        )
    ):
        blockers.append("future_or_same_year_training_for_historical_test")
    if stage in {"validation", "lockbox"} and selected_on_test_rows:
        blockers.append("formula_or_parameter_selected_on_test_rows")
    if stage in {"validation", "lockbox"} and test_rows_previously_consumed:
        blockers.append("previously_consumed_rows_used_for_promotion_evidence")
    if stage in {"validation", "lockbox"} and evaluation_reuse_count > 1:
        blockers.append("evaluation_rows_reused_for_selection")
    if stage in {"validation", "lockbox"}:
        if evaluation_reuse_count != 1:
            blockers.append("evaluation_must_be_consumed_exactly_once")
        if not _is_positive_int(evaluation_sample_count_value):
            blockers.append("evaluation_sample_count_must_be_positive_integer")
        if not evaluation_completed_date:
            blockers.append("evaluation_completed_date_missing")
        if (
            test_end_date
            and evaluation_completed_date
            and evaluation_completed_date < test_end_date
        ):
            blockers.append("evaluation_completed_before_test_window_ended")
        if (
            evaluation_completed_date
            and evaluation_completed_date > date.today().isoformat()
        ):
            blockers.append("evaluation_completed_date_is_in_the_future")
        if not train_years and not train_end_date:
            blockers.append("training_window_missing")
        if not test_years and not (test_start_date and test_end_date):
            blockers.append("evaluation_window_missing")
        if not candidate_fingerprint:
            blockers.append("candidate_fingerprint_missing")
        if not selection_freeze_date:
            blockers.append("selection_freeze_date_missing")
        if not train_end_date:
            blockers.append("train_end_date_missing")
        if not test_start_date:
            blockers.append("test_start_date_missing")
        if not test_end_date:
            blockers.append("test_end_date_missing")
        if (
            selection_freeze_date
            and test_start_date
            and test_start_date <= selection_freeze_date
        ):
            blockers.append("test_rows_start_before_or_on_selection_freeze")
        if train_end_date and test_start_date and train_end_date >= test_start_date:
            blockers.append("training_rows_reach_evaluation_window")
        if (
            train_end_date
            and selection_freeze_date
            and selection_freeze_date < train_end_date
        ):
            blockers.append("candidate_frozen_before_training_window_ended")
        if test_start_date and test_end_date and test_end_date < test_start_date:
            blockers.append("test_end_before_test_start")
        if preprocessing_fit_scope not in STRICT_PREPROCESSING_SCOPES:
            blockers.append("preprocessing_not_fit_on_train_only_rows")
        for ref_field in STRICT_EVIDENCE_REF_FIELDS:
            if not str(contract.get(ref_field, "")).strip():
                blockers.append(f"{ref_field}_missing")
        _append_strict_status_blocker(
            blockers,
            feature_availability_status,
            "feature_availability_audit_required",
        )
        _append_strict_status_blocker(
            blockers,
            label_separation_status,
            "label_separation_audit_required",
        )
        _append_strict_status_blocker(
            blockers,
            universe_pit_status,
            "universe_pit_audit_required",
        )
        _append_strict_status_blocker(
            blockers,
            multiple_testing_status,
            "multiple_testing_governance_required",
        )
    if stage in {"diagnostic", "discovery", "validation"}:
        if production_claim != "forbidden":
            blockers.append(f"{stage}_stage_production_claim")
    if stage == "validation" and not candidate_frozen:
        blockers.append("validation_candidate_not_frozen")
    if stage in {"diagnostic", "discovery", "validation"}:
        if lockbox_status != "untouched":
            blockers.append("lockbox_touched_before_lockbox_stage")
        if set(lockbox_years).intersection((*train_years, *test_years)):
            blockers.append("lockbox_rows_consumed_before_lockbox_stage")
    if stage == "lockbox":
        if not candidate_frozen:
            blockers.append("lockbox_candidate_not_frozen")
        if lockbox_status != "opened_once":
            blockers.append("lockbox_status_must_be_opened_once")
        if evaluation_reuse_count != 1:
            blockers.append("lockbox_must_be_consumed_exactly_once")
        if production_claim != "review_required":
            blockers.append("lockbox_requires_review_required_claim")
        if not lockbox_years and not str(
            contract.get("lockbox_sample_fingerprint", "")
        ).strip():
            blockers.append("lockbox_sample_identity_missing")
        if train_years and set(lockbox_years).intersection(train_years):
            blockers.append("lockbox_train_year_overlap")
        if lockbox_years and test_years and set(lockbox_years) != set(test_years):
            blockers.append("lockbox_years_must_equal_test_years")
        if not str(contract.get("prior_validation_report_ref", "")).strip():
            blockers.append("prior_validation_report_ref_missing")
        if not str(contract.get("lockbox_manifest_ref", "")).strip():
            blockers.append("lockbox_manifest_ref_missing")
        prior_validation_fingerprint = str(
            contract.get("prior_validation_candidate_fingerprint", "")
        ).strip()
        if not prior_validation_fingerprint:
            blockers.append("prior_validation_candidate_fingerprint_missing")
        elif prior_validation_fingerprint != candidate_fingerprint:
            blockers.append("lockbox_candidate_differs_from_prior_validation_candidate")
        prior_validation_end_date = _normalized_iso_date(
            contract.get("prior_validation_end_date")
        )
        if not prior_validation_end_date:
            blockers.append("prior_validation_end_date_missing")
        elif (
            selection_freeze_date
            and prior_validation_end_date > selection_freeze_date
        ):
            blockers.append("lockbox_frozen_before_prior_validation_ended")
    if stage == "diagnostic" and mode in policy.diagnostic_only_modes:
        warnings.append("diagnostic_split_may_use_future_rows_and_has_no_promotion_value")
    if stage == "diagnostic" and test_rows_previously_consumed:
        warnings.append("historically_consumed_rows_used_for_diagnostic_replay_only")

    status = "eligible" if not blockers else "blocked"
    return {
        "policy_id": policy.policy_id,
        "status": status,
        "stage": stage,
        "evaluation_mode": mode,
        "blockers": blockers,
        "warnings": warnings,
        "production_claim": (
            "review_required"
            if stage == "lockbox" and status == "eligible"
            else "forbidden"
        ),
        "production_authority": False,
        "evidence_summary": {
            "candidate_fingerprint": candidate_fingerprint,
            "selection_freeze_date": selection_freeze_date,
            "train_end_date": train_end_date,
            "test_start_date": test_start_date,
            "test_end_date": test_end_date,
            "evaluation_completed_date": evaluation_completed_date,
            "evaluation_sample_count": _normalized_nonnegative_int(
                evaluation_sample_count_value
            ),
            "lockbox_sample_fingerprint": str(
                contract.get("lockbox_sample_fingerprint", "")
            ).strip(),
            "prior_validation_report_ref": str(
                contract.get("prior_validation_report_ref", "")
            ).strip(),
            "prior_validation_candidate_fingerprint": str(
                contract.get("prior_validation_candidate_fingerprint", "")
            ).strip(),
            "prior_validation_end_date": _normalized_iso_date(
                contract.get("prior_validation_end_date")
            ),
            "evidence_refs": {
                field: str(contract.get(field, "")).strip()
                for field in STRICT_EVIDENCE_REF_FIELDS
            },
        },
    }


def validate_temporal_evaluation_contract_v5(
    contract: Mapping[str, object],
    *,
    evidence_catalog: EvidenceCatalog | None = None,
) -> dict[str, object]:
    """Validate @5 temporal evidence by resolving every required ref."""

    contract_policy_id = str(contract.get("policy_id", ""))
    legacy_shape_contract = dict(contract)
    legacy_shape_contract["policy_id"] = (
        CANONICAL_TEMPORAL_SELECTION_VALIDATION_POLICY.policy_id
    )
    shape_report = validate_temporal_evaluation_contract(legacy_shape_contract)
    blockers = _string_list(shape_report.get("blockers"))
    warnings = _string_list(shape_report.get("warnings"))
    if contract_policy_id != AT5_TEMPORAL_POLICY_ID:
        blockers.append("at5_temporal_policy_id_required")

    stage = str(shape_report.get("stage", ""))
    evidence_ref_fields: list[str] = list(STRICT_EVIDENCE_REF_FIELDS)
    if stage == "lockbox":
        evidence_ref_fields.extend(LOCKBOX_EVIDENCE_REF_FIELDS)
    evidence_refs = {
        field: str(contract.get(field, "")).strip() for field in evidence_ref_fields
    }
    evidence_resolution = resolve_evidence_refs(
        evidence_refs,
        catalog=evidence_catalog,
        expected_artifact_types=AT5_EVIDENCE_ARTIFACT_TYPES,
        expected_candidate_fingerprint=str(
            contract.get("candidate_fingerprint", "")
        ).strip(),
        expected_dataset_ref=str(contract.get("dataset_ref", "")).strip(),
        expected_source_vintage_ref=str(
            contract.get("source_vintage_ref", "")
        ).strip(),
    )
    for field_name, resolution in evidence_resolution.items():
        for blocker in _string_list(resolution.get("blockers")):
            blockers.append(f"{field_name}:{blocker}")

    status = "eligible" if not blockers else "blocked"
    production_claim = (
        "review_required"
        if stage == "lockbox" and status == "eligible"
        else "forbidden"
    )
    return {
        **shape_report,
        "policy_id": AT5_TEMPORAL_POLICY_ID,
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "production_claim": production_claim,
        "production_authority": False,
        "evidence_resolution": evidence_resolution,
    }


def require_temporal_evaluation_contract(
    contract: Mapping[str, object],
    *,
    required_stage: str | None = None,
) -> dict[str, object]:
    """Raise unless a temporal contract is eligible for its declared stage."""

    report = validate_temporal_evaluation_contract(contract)
    blockers = _string_list(report.get("blockers"))
    if required_stage is not None and report["stage"] != required_stage:
        blockers.append(f"required_temporal_stage_{required_stage}")
    if blockers:
        raise ValidationError(
            "Temporal integrity gate blocked: "
            + ", ".join(str(item) for item in blockers)
        )
    return report


def require_temporal_evaluation_contract_v5(
    contract: Mapping[str, object],
    *,
    evidence_catalog: EvidenceCatalog | None = None,
    required_stage: str | None = None,
) -> dict[str, object]:
    """Raise unless an @5 temporal contract is eligible for its stage."""

    report = validate_temporal_evaluation_contract_v5(
        contract,
        evidence_catalog=evidence_catalog,
    )
    blockers = _string_list(report.get("blockers"))
    if required_stage is not None and report["stage"] != required_stage:
        blockers.append(f"required_temporal_stage_{required_stage}")
    if blockers:
        raise ValidationError(
            "Temporal integrity @5 gate blocked: "
            + ", ".join(str(item) for item in blockers)
        )
    return report


def temporal_report_supports_production(report: Mapping[str, object]) -> bool:
    """Return whether a reviewed lockbox report may enter a production gate."""

    return bool(
        report.get("policy_id")
        == CANONICAL_TEMPORAL_SELECTION_VALIDATION_POLICY.policy_id
        and report.get("status") == "eligible"
        and report.get("stage") == "lockbox"
        and report.get("production_claim") == "review_required"
        and report.get("blockers") == []
        and not report.get("production_authority", False)
    )


def _append_strict_status_blocker(
    blockers: list[str],
    status: str,
    blocker: str,
) -> None:
    if status not in STRICT_EVIDENCE_STATUSES:
        blockers.append(blocker)


def _normalized_years(value: object) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    years: set[int] = set()
    for year in value:
        if isinstance(year, bool):
            continue
        if isinstance(year, (int, str)):
            years.add(int(year))
    return tuple(sorted(years))


def _string_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item) for item in value]


def _normalized_nonnegative_int(value: object) -> int:
    if type(value) is int:
        return max(value, 0)
    return 0


def _is_nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _is_positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _normalized_iso_date(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ""
    candidate = value[:10]
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return ""


__all__ = [
    "CANONICAL_TEMPORAL_SELECTION_VALIDATION_POLICY",
    "CANONICAL_TEMPORAL_SELECTION_VALIDATION_POLICY_V5",
    "DIAGNOSTIC_ONLY_MODES",
    "LOCKBOX_EVIDENCE_REF_FIELDS",
    "PROMOTION_ELIGIBLE_MODES",
    "STRICT_EVIDENCE_REF_FIELDS",
    "TEMPORAL_EVALUATION_STAGES",
    "TemporalSelectionValidationPolicy",
    "canonical_temporal_selection_validation_policy",
    "canonical_temporal_selection_validation_policy_v5",
    "require_temporal_evaluation_contract",
    "require_temporal_evaluation_contract_v5",
    "temporal_report_supports_production",
    "validate_temporal_evaluation_contract",
    "validate_temporal_evaluation_contract_v5",
]
