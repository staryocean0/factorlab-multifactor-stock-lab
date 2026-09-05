"""Immutable project contracts for strategy-bound factor-use discovery.

The contracts in this module account for information, hypotheses, trials and
selection.  They never admit a factor, authorize execution, or grant
production authority.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Final, cast

from factor_lab.governance.canonicalization import canonical_digest

CANONICALIZATION_VERSION: Final = "factorlab_canonical_json@1"
INFORMATION_EVIDENCE_SCHEMA_ID: Final = "strategy_factor_information_evidence@2.0"
ACTION_SPACE_SCHEMA_ID: Final = "strategy_factor_action_space@1.0"
USAGE_HYPOTHESIS_SCHEMA_ID: Final = "factor_usage_hypothesis@1.0"
USAGE_TRIAL_SCHEMA_ID: Final = "factor_usage_trial_evidence@1.0"
USAGE_CAMPAIGN_RECEIPT_SCHEMA_ID: Final = "factor_usage_campaign_receipt@1.0"
SEARCH_SCOPE_DIMENSION_SCHEMA_ID: Final = "search_scope_dimension_manifest@1.0"
USAGE_LIFECYCLE_EVENT_SCHEMA_ID: Final = "factor_usage_lifecycle_event@1.0"

_INFORMATION_VERDICTS = frozenset(
    {
        "informative_for_context",
        "not_informative_for_context",
        "inconclusive",
        "invalid_evidence",
    }
)
_TRIAL_STAGES = frozenset({"discovery", "selection"})
_TRIAL_VERDICTS = frozenset(
    {"rejected_usage", "promising_for_selection", "inconclusive", "invalid_evidence"}
)
_CAMPAIGN_OUTCOMES = frozenset(
    {
        "not_explored",
        "no_selection",
        "selected",
        "deferred",
        "not_applicable",
        "diagnostic_only",
    }
)
_OWNER_LAYERS = frozenset({"factor_identity", "strategy_usage"})
_SUBJECT_TYPES = frozenset({"hypothesis", "campaign", "binding", "claim"})


def _is_sha256_digest(value: object) -> bool:
    text = str(value).strip()
    return (
        len(text) == 71
        and text.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in text[7:])
    )


def build_strategy_factor_information_evidence(
    *,
    evidence_id: str,
    strategy_id: str,
    factor_ref: str,
    feature_refs: Sequence[str],
    universe: str,
    frequency: str,
    prediction_target: str,
    dataset_manifest_ref: str,
    temporal_policy_ref: str,
    search_scope_registry_id: str,
    data_usage_registry_id: str,
    validation_method: str,
    information_metrics: Mapping[str, object],
    robustness_result: Mapping[str, object],
    distinctness_result: Mapping[str, object],
    information_verdict: str,
    information_scope: str,
    evidence_refs: Sequence[str],
    failure_boundaries: Sequence[str] = (),
    field_labels_zh: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Record information value without prescribing a strategy use."""

    payload: dict[str, object] = {
        "artifact_type": "strategy_factor_information_evidence",
        "schema_id": INFORMATION_EVIDENCE_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "evidence_id": evidence_id,
        "strategy_id": strategy_id,
        "factor_ref": factor_ref,
        "feature_refs": list(feature_refs),
        "universe": universe,
        "frequency": frequency,
        "prediction_target": prediction_target,
        "dataset_manifest_ref": dataset_manifest_ref,
        "temporal_policy_ref": temporal_policy_ref,
        "search_scope_registry_id": search_scope_registry_id,
        "data_usage_registry_id": data_usage_registry_id,
        "validation_method": validation_method,
        "information_metrics": dict(information_metrics),
        "robustness_result": dict(robustness_result),
        "distinctness_result": dict(distinctness_result),
        "information_verdict": information_verdict,
        "information_scope": information_scope,
        "evidence_refs": list(evidence_refs),
        "failure_boundaries": list(failure_boundaries),
        "field_labels_zh": dict(field_labels_zh or _information_labels()),
    }
    return _seal(
        payload, "canonical_digest", validate_strategy_factor_information_evidence
    )


def validate_strategy_factor_information_evidence(
    payload: Mapping[str, object],
) -> dict[str, object]:
    blockers = _contract_blockers(
        payload,
        artifact_type="strategy_factor_information_evidence",
        schema_id=INFORMATION_EVIDENCE_SCHEMA_ID,
        digest_key="canonical_digest",
        required=(
            "evidence_id",
            "strategy_id",
            "factor_ref",
            "universe",
            "frequency",
            "prediction_target",
            "dataset_manifest_ref",
            "temporal_policy_ref",
            "search_scope_registry_id",
            "data_usage_registry_id",
            "validation_method",
            "information_scope",
        ),
    )
    if not _strings(payload.get("feature_refs")):
        blockers.append("feature_refs_required")
    for key in ("information_metrics", "robustness_result", "distinctness_result"):
        if not isinstance(payload.get(key), Mapping):
            blockers.append(f"{key}_object_required")
    if str(payload.get("information_verdict")) not in _INFORMATION_VERDICTS:
        blockers.append("information_verdict_invalid")
    if not _strings(payload.get("evidence_refs")):
        blockers.append("evidence_refs_required")
    if "usage_mode" in payload or "production_authority" in payload:
        blockers.append("information_evidence_forbidden_authority_or_usage")
    return _report(INFORMATION_EVIDENCE_SCHEMA_ID, blockers)


def build_strategy_factor_action_space(
    *,
    action_space_id: str,
    action_space_version: str,
    strategy_family_id: str,
    strategy_id: str,
    baseline_artifact_ref: str,
    baseline_digest: str,
    action_ids: Sequence[str],
    input_contract_refs: Sequence[str],
    output_contract_refs: Sequence[str],
    temporal_semantics_ref: str,
    cost_fill_semantics_ref: str,
    forbidden_actions: Sequence[str],
    extension_policy: Mapping[str, object],
    owner_ref: str,
    field_labels_zh: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Publish a versioned, strategy-owned action surface."""

    payload: dict[str, object] = {
        "artifact_type": "strategy_factor_action_space",
        "schema_id": ACTION_SPACE_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "action_space_id": action_space_id,
        "action_space_version": action_space_version,
        "strategy_family_id": strategy_family_id,
        "strategy_id": strategy_id,
        "baseline_artifact_ref": baseline_artifact_ref,
        "baseline_digest": baseline_digest,
        "action_ids": list(action_ids),
        "input_contract_refs": list(input_contract_refs),
        "output_contract_refs": list(output_contract_refs),
        "temporal_semantics_ref": temporal_semantics_ref,
        "cost_fill_semantics_ref": cost_fill_semantics_ref,
        "forbidden_actions": list(forbidden_actions),
        "extension_policy": dict(extension_policy),
        "owner_ref": owner_ref,
        "field_labels_zh": dict(field_labels_zh or _action_space_labels()),
    }
    return _seal(payload, "canonical_digest", validate_strategy_factor_action_space)


def validate_strategy_factor_action_space(
    payload: Mapping[str, object],
) -> dict[str, object]:
    blockers = _contract_blockers(
        payload,
        artifact_type="strategy_factor_action_space",
        schema_id=ACTION_SPACE_SCHEMA_ID,
        digest_key="canonical_digest",
        required=(
            "action_space_id",
            "action_space_version",
            "strategy_family_id",
            "strategy_id",
            "baseline_artifact_ref",
            "baseline_digest",
            "temporal_semantics_ref",
            "cost_fill_semantics_ref",
            "owner_ref",
        ),
    )
    actions = _strings(payload.get("action_ids"))
    if not actions:
        blockers.append("action_ids_required")
    elif len(actions) != len(set(actions)):
        blockers.append("action_ids_duplicate")
    elif any(":" not in action for action in actions):
        blockers.append("action_ids_must_be_namespaced")
    for key in ("input_contract_refs", "output_contract_refs"):
        if not _strings(payload.get(key)):
            blockers.append(f"{key}_required")
    if not isinstance(payload.get("extension_policy"), Mapping):
        blockers.append("extension_policy_object_required")
    for field in ("baseline_digest", "canonical_digest"):
        value = str(payload.get(field, "")).strip()
        if value and not _is_sha256_digest(value):
            blockers.append(f"{field}_invalid")
    return _report(ACTION_SPACE_SCHEMA_ID, blockers)


def build_factor_usage_hypothesis(
    *,
    campaign_id: str,
    usage_hypothesis_id: str,
    strategy_family_id: str,
    strategy_id: str,
    baseline_artifact_ref: str,
    baseline_digest: str,
    candidate_version: str,
    factor_asset_ref: str,
    factor_ref: str,
    factor_information_evidence_ref: str,
    action_space_ref: str,
    action_space_digest: str,
    action_id: str,
    information_shape: str,
    direction_spec: Mapping[str, object],
    transform_pipeline_ref: str,
    activation_contract: Mapping[str, object],
    threshold_contract: Mapping[str, object],
    regime_contract: Mapping[str, object],
    interaction_contract: Mapping[str, object],
    timing_contract: Mapping[str, object],
    cost_fill_semantics_ref: str,
    search_scope_registry_id: str,
    data_usage_registry_id: str,
    parent_multiplicity_family_id: str,
    claim_metric_schema_refs: Sequence[str],
    no_harm_schema_refs: Sequence[str],
    context_claim: str,
    failure_boundaries: Sequence[str],
    supersedes_definition_ref: str | None = None,
    field_labels_zh: Mapping[str, str] | None = None,
    notes: str | None = None,
) -> dict[str, object]:
    """Declare one immutable use definition and its semantic signature."""

    payload: dict[str, object] = {
        "artifact_type": "factor_usage_hypothesis",
        "schema_id": USAGE_HYPOTHESIS_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "campaign_id": campaign_id,
        "usage_hypothesis_id": usage_hypothesis_id,
        "strategy_family_id": strategy_family_id,
        "strategy_id": strategy_id,
        "baseline_artifact_ref": baseline_artifact_ref,
        "baseline_digest": baseline_digest,
        "candidate_version": candidate_version,
        "factor_asset_ref": factor_asset_ref,
        "factor_ref": factor_ref,
        "factor_information_evidence_ref": factor_information_evidence_ref,
        "action_space_ref": action_space_ref,
        "action_space_digest": action_space_digest,
        "action_id": action_id,
        "information_shape": information_shape,
        "direction_spec": dict(direction_spec),
        "transform_pipeline_ref": transform_pipeline_ref,
        "activation_contract": dict(activation_contract),
        "threshold_contract": dict(threshold_contract),
        "regime_contract": dict(regime_contract),
        "interaction_contract": dict(interaction_contract),
        "timing_contract": dict(timing_contract),
        "cost_fill_semantics_ref": cost_fill_semantics_ref,
        "search_scope_registry_id": search_scope_registry_id,
        "data_usage_registry_id": data_usage_registry_id,
        "parent_multiplicity_family_id": parent_multiplicity_family_id,
        "claim_metric_schema_refs": list(claim_metric_schema_refs),
        "no_harm_schema_refs": list(no_harm_schema_refs),
        "context_claim": context_claim,
        "failure_boundaries": list(failure_boundaries),
        "supersedes_definition_ref": supersedes_definition_ref,
        "field_labels_zh": dict(field_labels_zh or _hypothesis_labels()),
        "notes": notes,
    }
    payload["usage_signature_hash"] = canonical_digest(_usage_semantics(payload))
    definition = dict(payload)
    _ = definition.pop("usage_signature_hash", None)
    payload["definition_digest"] = canonical_digest(definition)
    # The generic checksum seals the complete artifact, including both derived
    # semantic digests.  Public validators therefore see the same sealed shape
    # that is published to the resolver.
    payload["checksum"] = canonical_digest(payload)
    report = validate_factor_usage_hypothesis(payload)
    if report["status"] != "valid":
        raise ValueError("; ".join(_strings(report["blockers"])))
    return payload


def validate_factor_usage_hypothesis(
    payload: Mapping[str, object],
) -> dict[str, object]:
    blockers = _contract_blockers(
        payload,
        artifact_type="factor_usage_hypothesis",
        schema_id=USAGE_HYPOTHESIS_SCHEMA_ID,
        digest_key="definition_digest",
        required=(
            "campaign_id",
            "usage_hypothesis_id",
            "strategy_family_id",
            "strategy_id",
            "baseline_artifact_ref",
            "baseline_digest",
            "candidate_version",
            "factor_asset_ref",
            "factor_ref",
            "factor_information_evidence_ref",
            "action_space_ref",
            "action_space_digest",
            "action_id",
            "information_shape",
            "transform_pipeline_ref",
            "cost_fill_semantics_ref",
            "search_scope_registry_id",
            "data_usage_registry_id",
            "parent_multiplicity_family_id",
            "context_claim",
            "usage_signature_hash",
        ),
        digest_excludes=("usage_signature_hash",),
    )
    for key in (
        "direction_spec",
        "activation_contract",
        "threshold_contract",
        "regime_contract",
        "interaction_contract",
        "timing_contract",
    ):
        if not isinstance(payload.get(key), Mapping):
            blockers.append(f"{key}_object_required")
    if not _strings(payload.get("claim_metric_schema_refs")):
        blockers.append("claim_metric_schema_refs_required")
    if not _strings(payload.get("no_harm_schema_refs")):
        blockers.append("no_harm_schema_refs_required")
    for key in ("baseline_digest", "action_space_digest", "usage_signature_hash"):
        if not _is_sha256_digest(payload.get(key)):
            blockers.append(f"{key}_invalid")
    if str(payload.get("usage_signature_hash")) != canonical_digest(
        _usage_semantics(payload)
    ):
        blockers.append("usage_signature_hash_mismatch")
    if "status" in payload or "verdict" in payload or "production_authority" in payload:
        blockers.append("immutable_hypothesis_contains_mutable_or_authority_field")
    return _report(USAGE_HYPOTHESIS_SCHEMA_ID, blockers)


def build_search_scope_dimension_manifest(
    *,
    scope_manifest_id: str,
    campaign_id: str,
    parent_multiplicity_family_id: str,
    dimensions: Sequence[Mapping[str, object]],
    registered_usage_signature_hashes: Sequence[str],
    explicit_sparse_combinations: Sequence[Mapping[str, object]] = (),
    omitted_dimensions: Sequence[Mapping[str, object]] = (),
    deferred_dimensions: Sequence[Mapping[str, object]] = (),
    field_labels_zh: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Register namespaced dimensions and the actual signature coverage."""

    payload: dict[str, object] = {
        "artifact_type": "search_scope_dimension_manifest",
        "schema_id": SEARCH_SCOPE_DIMENSION_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "scope_manifest_id": scope_manifest_id,
        "campaign_id": campaign_id,
        "parent_multiplicity_family_id": parent_multiplicity_family_id,
        "dimensions": [_normalize_scope_dimension(item) for item in dimensions],
        "registered_usage_signature_hashes": list(registered_usage_signature_hashes),
        "explicit_sparse_combinations": [
            _normalize_sparse_combination(item) for item in explicit_sparse_combinations
        ],
        "omitted_dimensions": [dict(item) for item in omitted_dimensions],
        "deferred_dimensions": [dict(item) for item in deferred_dimensions],
        "field_labels_zh": dict(field_labels_zh or _search_scope_labels()),
    }
    hash_payload = dict(payload)
    _ = hash_payload.pop("field_labels_zh", None)
    payload["search_space_hash"] = canonical_digest(hash_payload)
    return _seal(payload, "manifest_digest", validate_search_scope_dimension_manifest)


def validate_search_scope_dimension_manifest(
    payload: Mapping[str, object],
) -> dict[str, object]:
    blockers = _contract_blockers(
        payload,
        artifact_type="search_scope_dimension_manifest",
        schema_id=SEARCH_SCOPE_DIMENSION_SCHEMA_ID,
        digest_key="manifest_digest",
        required=(
            "scope_manifest_id",
            "campaign_id",
            "parent_multiplicity_family_id",
            "search_space_hash",
        ),
    )
    dimensions_value = payload.get("dimensions")
    dimensions = _mapping_sequence(dimensions_value)
    if not dimensions:
        blockers.append("scope_dimensions_required")
    elif not isinstance(dimensions_value, Sequence) or len(dimensions) != len(
        dimensions_value
    ):
        blockers.append("scope_dimensions_invalid")
    seen: set[str] = set()
    candidate_index: dict[str, set[tuple[str, str]]] = {}
    for index, dimension in enumerate(dimensions):
        if set(dimension) != {
            "dimension_id",
            "owner_layer",
            "kind",
            "candidate_definitions",
            "expected_attempt_count",
            "actual_attempt_count",
            "selection_source",
        }:
            blockers.append(f"scope_dimension_fields_invalid:{index}")
        dimension_id = str(dimension.get("dimension_id", "")).strip()
        if not dimension_id or ":" not in dimension_id:
            blockers.append(f"scope_dimension_id_namespaced_required:{index}")
        elif dimension_id in seen:
            blockers.append("scope_dimension_id_duplicate")
        seen.add(dimension_id)
        if str(dimension.get("owner_layer")) not in _OWNER_LAYERS:
            blockers.append(f"scope_dimension_owner_layer_invalid:{index}")
        kind = str(dimension.get("kind", "")).strip()
        if ":" not in kind:
            blockers.append(f"scope_dimension_kind_namespaced_required:{index}")
        expected = _non_negative_int(dimension.get("expected_attempt_count"))
        actual = _non_negative_int(dimension.get("actual_attempt_count"))
        if expected is None or actual is None or actual > expected:
            blockers.append(f"scope_dimension_coverage_invalid:{index}")
        definitions_value = dimension.get("candidate_definitions")
        definitions = _mapping_sequence(definitions_value)
        definition_pairs: list[tuple[str, str]] = []
        definitions_invalid = (
            not definitions
            or not isinstance(definitions_value, Sequence)
            or isinstance(definitions_value, (str, bytes))
            or len(definitions) != len(definitions_value)
        )
        for definition in definitions:
            if not set(definition).issubset({"ref", "digest", "checksum"}):
                definitions_invalid = True
            candidate_ref = str(definition.get("ref", "")).strip()
            candidate_digest = str(definition.get("digest", "")).strip()
            checksum = str(definition.get("checksum", "")).strip()
            if (
                not candidate_ref
                or not _is_sha256_digest(candidate_digest)
                or (checksum and checksum != candidate_digest)
            ):
                definitions_invalid = True
            definition_pairs.append((candidate_ref, candidate_digest))
        if definitions_invalid:
            blockers.append(f"scope_dimension_candidate_definitions_invalid:{index}")
        if len({item[0] for item in definition_pairs}) != len(definition_pairs):
            blockers.append(f"scope_dimension_candidate_ref_duplicate:{index}")
        if len({item[1] for item in definition_pairs}) != len(definition_pairs):
            blockers.append(f"scope_dimension_candidate_digest_duplicate:{index}")
        candidate_index[dimension_id] = set(definition_pairs)
        if not str(dimension.get("selection_source", "")).strip():
            blockers.append(f"scope_dimension_selection_source_required:{index}")
    for group_key in ("omitted_dimensions", "deferred_dimensions"):
        for index, item in enumerate(_mapping_sequence(payload.get(group_key))):
            if set(item) != {"dimension_id", "rationale"}:
                blockers.append(f"{group_key}_fields_invalid:{index}")
            if (
                not str(item.get("dimension_id", "")).strip()
                or not str(item.get("rationale", "")).strip()
            ):
                blockers.append(f"{group_key}_rationale_required:{index}")
    signatures = _strings(payload.get("registered_usage_signature_hashes"))
    if len(signatures) != len(set(signatures)) or any(
        not _is_sha256_digest(value) for value in signatures
    ):
        blockers.append("registered_usage_signature_hashes_invalid")
    combinations_value = payload.get("explicit_sparse_combinations")
    combinations = _mapping_sequence(combinations_value)
    if (
        not isinstance(combinations_value, Sequence)
        or isinstance(combinations_value, (str, bytes))
        or len(combinations) != len(combinations_value)
    ):
        blockers.append("explicit_sparse_combinations_invalid")
    combination_signatures: list[str] = []
    hypothesis_refs: list[str] = []
    manifest_dimension_ids = tuple(
        str(item.get("dimension_id", "")).strip() for item in dimensions
    )
    for index, combination in enumerate(combinations):
        if set(combination) != {
            "usage_signature_hash",
            "hypothesis_ref",
            "hypothesis_definition_digest",
            "dimension_ids",
            "candidate_selections",
        }:
            blockers.append(f"explicit_sparse_combination_fields_invalid:{index}")
        combination_signature = str(combination.get("usage_signature_hash", "")).strip()
        hypothesis_ref = str(combination.get("hypothesis_ref", "")).strip()
        hypothesis_digest = str(
            combination.get("hypothesis_definition_digest", "")
        ).strip()
        combination_signatures.append(combination_signature)
        hypothesis_refs.append(hypothesis_ref)
        if not _is_sha256_digest(combination_signature):
            blockers.append(f"explicit_sparse_usage_signature_hash_invalid:{index}")
        if not hypothesis_ref:
            blockers.append(f"explicit_sparse_hypothesis_ref_required:{index}")
        if not _is_sha256_digest(hypothesis_digest):
            blockers.append(
                f"explicit_sparse_hypothesis_definition_digest_invalid:{index}"
            )

        dimension_ids = _strings(combination.get("dimension_ids"))
        if dimension_ids != manifest_dimension_ids:
            blockers.append(f"explicit_sparse_dimension_ids_mismatch:{index}")
        if len(dimension_ids) != len(set(dimension_ids)):
            blockers.append(f"explicit_sparse_dimension_ids_duplicate:{index}")

        selections_value = combination.get("candidate_selections")
        selections = _mapping_sequence(selections_value)
        if (
            not isinstance(selections_value, Sequence)
            or isinstance(selections_value, (str, bytes))
            or len(selections) != len(selections_value)
        ):
            blockers.append(f"explicit_sparse_candidate_selections_invalid:{index}")
        selection_dimension_ids: list[str] = []
        for selection_index, selection in enumerate(selections):
            if not set(selection).issubset(
                {"dimension_id", "candidate_ref", "candidate_digest", "checksum"}
            ):
                blocker = "explicit_sparse_candidate_selection_fields_invalid"
                blockers.append(f"{blocker}:{index}:{selection_index}")
            selection_dimension_id = str(selection.get("dimension_id", "")).strip()
            candidate_ref = str(selection.get("candidate_ref", "")).strip()
            candidate_digest = str(selection.get("candidate_digest", "")).strip()
            checksum = str(selection.get("checksum", "")).strip()
            selection_dimension_ids.append(selection_dimension_id)
            if (
                not selection_dimension_id
                or not candidate_ref
                or not _is_sha256_digest(candidate_digest)
                or (checksum and checksum != candidate_digest)
            ):
                blocker = "explicit_sparse_candidate_selection_invalid"
                blockers.append(f"{blocker}:{index}:{selection_index}")
                continue
            if selection_dimension_id not in candidate_index:
                blocker = "explicit_sparse_candidate_dimension_unknown"
                blockers.append(f"{blocker}:{index}:{selection_index}")
            elif (candidate_ref, candidate_digest) not in candidate_index[
                selection_dimension_id
            ]:
                blocker = "explicit_sparse_candidate_not_registered"
                blockers.append(f"{blocker}:{index}:{selection_index}")
        if tuple(selection_dimension_ids) != manifest_dimension_ids:
            blockers.append(f"explicit_sparse_candidate_dimensions_mismatch:{index}")
        if len(selection_dimension_ids) != len(set(selection_dimension_ids)):
            blockers.append(f"explicit_sparse_candidate_dimension_duplicate:{index}")

    if len(combination_signatures) != len(set(combination_signatures)):
        blockers.append("explicit_sparse_usage_signature_duplicate")
    if len(hypothesis_refs) != len(set(hypothesis_refs)):
        blockers.append("explicit_sparse_hypothesis_ref_duplicate")
    if set(combination_signatures) != set(signatures) or len(
        combination_signatures
    ) != len(signatures):
        blockers.append("registered_usage_signature_combination_mismatch")
    expected_hash_payload = dict(payload)
    _ = expected_hash_payload.pop("manifest_digest", None)
    _ = expected_hash_payload.pop("checksum", None)
    _ = expected_hash_payload.pop("search_space_hash", None)
    _ = expected_hash_payload.pop("field_labels_zh", None)
    if str(payload.get("search_space_hash")) != canonical_digest(expected_hash_payload):
        blockers.append("search_space_hash_mismatch")
    return _report(SEARCH_SCOPE_DIMENSION_SCHEMA_ID, blockers)


def build_factor_usage_trial_evidence(
    *,
    campaign_id: str,
    trial_id: str,
    attempt_id: str,
    dimension_ids: Sequence[str],
    hypothesis_ref: str,
    hypothesis_definition_digest: str,
    registered_usage_signature_hash: str,
    stage: str,
    strategy_id: str,
    factor_ref: str,
    baseline_artifact_ref: str,
    baseline_digest: str,
    dataset_manifest_ref: str,
    window_contract_ref: str,
    fold_contract_ref: str,
    search_scope_manifest_ref: str,
    search_scope_registry_id: str,
    data_usage_registry_id: str,
    parent_multiplicity_family_id: str,
    metrics: Mapping[str, object],
    no_harm_result: Mapping[str, object],
    failure_scope: str,
    verdict: str,
    artifact_refs: Sequence[str],
    failure_boundaries: Sequence[str] = (),
    field_labels_zh: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Record one pre-freeze discovery/selection trial."""

    payload: dict[str, object] = {
        "artifact_type": "factor_usage_trial_evidence",
        "schema_id": USAGE_TRIAL_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "campaign_id": campaign_id,
        "trial_id": trial_id,
        "attempt_id": attempt_id,
        "dimension_ids": list(dimension_ids),
        "hypothesis_ref": hypothesis_ref,
        "hypothesis_definition_digest": hypothesis_definition_digest,
        "registered_usage_signature_hash": registered_usage_signature_hash,
        "stage": stage,
        "strategy_id": strategy_id,
        "factor_ref": factor_ref,
        "baseline_artifact_ref": baseline_artifact_ref,
        "baseline_digest": baseline_digest,
        "dataset_manifest_ref": dataset_manifest_ref,
        "window_contract_ref": window_contract_ref,
        "fold_contract_ref": fold_contract_ref,
        "search_scope_manifest_ref": search_scope_manifest_ref,
        "search_scope_registry_id": search_scope_registry_id,
        "data_usage_registry_id": data_usage_registry_id,
        "parent_multiplicity_family_id": parent_multiplicity_family_id,
        "metrics": dict(metrics),
        "no_harm_result": dict(no_harm_result),
        "failure_scope": failure_scope,
        "verdict": verdict,
        "artifact_refs": list(artifact_refs),
        "failure_boundaries": list(failure_boundaries),
        "field_labels_zh": dict(field_labels_zh or _trial_labels()),
    }
    return _seal(payload, "trial_digest", validate_factor_usage_trial_evidence)


def validate_factor_usage_trial_evidence(
    payload: Mapping[str, object],
) -> dict[str, object]:
    blockers = _contract_blockers(
        payload,
        artifact_type="factor_usage_trial_evidence",
        schema_id=USAGE_TRIAL_SCHEMA_ID,
        digest_key="trial_digest",
        required=(
            "campaign_id",
            "trial_id",
            "attempt_id",
            "hypothesis_ref",
            "hypothesis_definition_digest",
            "registered_usage_signature_hash",
            "strategy_id",
            "factor_ref",
            "baseline_artifact_ref",
            "baseline_digest",
            "dataset_manifest_ref",
            "window_contract_ref",
            "fold_contract_ref",
            "search_scope_manifest_ref",
            "search_scope_registry_id",
            "data_usage_registry_id",
            "parent_multiplicity_family_id",
            "failure_scope",
        ),
    )
    stage = str(payload.get("stage"))
    if stage not in _TRIAL_STAGES:
        blockers.append("trial_stage_invalid")
        if stage in {"validation", "prospective", "lockbox"}:
            blockers.append("prefreeze_validation_forbidden")
    if str(payload.get("verdict")) not in _TRIAL_VERDICTS:
        blockers.append("trial_verdict_invalid")
    for key in (
        "hypothesis_definition_digest",
        "registered_usage_signature_hash",
        "baseline_digest",
    ):
        if not _is_sha256_digest(payload.get(key)):
            blockers.append(f"{key}_invalid")
    if not isinstance(payload.get("metrics"), Mapping):
        blockers.append("metrics_object_required")
    if not isinstance(payload.get("no_harm_result"), Mapping):
        blockers.append("no_harm_result_object_required")
    if not _strings(payload.get("artifact_refs")):
        blockers.append("artifact_refs_required")
    dimension_ids = _strings(payload.get("dimension_ids"))
    if not dimension_ids or len(dimension_ids) != len(set(dimension_ids)):
        blockers.append("trial_dimension_ids_required_unique")
    elif any(":" not in item for item in dimension_ids):
        blockers.append("trial_dimension_ids_must_be_namespaced")
    if "production_authority" in payload:
        blockers.append("trial_cannot_grant_production_authority")
    return _report(USAGE_TRIAL_SCHEMA_ID, blockers)


def build_factor_usage_campaign_receipt(
    *,
    campaign_id: str,
    receipt_id: str,
    factor_information_evidence_ref: str,
    factor_family_governance_ref: str,
    strategy_family_id: str,
    strategy_id: str,
    factor_ref: str,
    baseline_artifact_ref: str,
    baseline_digest: str,
    action_space_ref: str,
    dimension_manifest_ref: str,
    search_scope_registry_id: str,
    data_usage_registry_id: str,
    parent_multiplicity_family_id: str,
    registered_hypothesis_refs: Sequence[str],
    registered_usage_signature_hashes: Sequence[str],
    trial_refs: Sequence[str],
    attempt_ledger_refs: Sequence[str],
    coverage_claim: Mapping[str, object],
    campaign_outcome: str,
    selected_hypothesis_ref: str | None,
    selection_event_ref: str,
    rationale: str,
    field_labels_zh: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Aggregate registered campaign accounting without claiming global optimality."""

    payload: dict[str, object] = {
        "artifact_type": "factor_usage_campaign_receipt",
        "schema_id": USAGE_CAMPAIGN_RECEIPT_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "campaign_id": campaign_id,
        "receipt_id": receipt_id,
        "factor_information_evidence_ref": factor_information_evidence_ref,
        "factor_family_governance_ref": factor_family_governance_ref,
        "strategy_family_id": strategy_family_id,
        "strategy_id": strategy_id,
        "factor_ref": factor_ref,
        "baseline_artifact_ref": baseline_artifact_ref,
        "baseline_digest": baseline_digest,
        "action_space_ref": action_space_ref,
        "dimension_manifest_ref": dimension_manifest_ref,
        "search_scope_registry_id": search_scope_registry_id,
        "data_usage_registry_id": data_usage_registry_id,
        "parent_multiplicity_family_id": parent_multiplicity_family_id,
        "registered_hypothesis_refs": list(registered_hypothesis_refs),
        "registered_usage_signature_hashes": list(registered_usage_signature_hashes),
        "trial_refs": list(trial_refs),
        "attempt_ledger_refs": list(attempt_ledger_refs),
        "coverage_claim": dict(coverage_claim),
        "campaign_outcome": campaign_outcome,
        "selected_hypothesis_ref": selected_hypothesis_ref,
        "selection_scope_statement": "preferred_within_registered_scope",
        "selection_event_ref": selection_event_ref,
        "rationale": rationale,
        "field_labels_zh": dict(field_labels_zh or _campaign_labels()),
    }
    return _seal(payload, "receipt_digest", validate_factor_usage_campaign_receipt)


def validate_factor_usage_campaign_receipt(
    payload: Mapping[str, object],
) -> dict[str, object]:
    blockers = _contract_blockers(
        payload,
        artifact_type="factor_usage_campaign_receipt",
        schema_id=USAGE_CAMPAIGN_RECEIPT_SCHEMA_ID,
        digest_key="receipt_digest",
        required=(
            "campaign_id",
            "receipt_id",
            "factor_information_evidence_ref",
            "factor_family_governance_ref",
            "strategy_family_id",
            "strategy_id",
            "factor_ref",
            "baseline_artifact_ref",
            "baseline_digest",
            "action_space_ref",
            "dimension_manifest_ref",
            "search_scope_registry_id",
            "data_usage_registry_id",
            "parent_multiplicity_family_id",
            "selection_event_ref",
            "rationale",
        ),
    )
    hypotheses = _strings(payload.get("registered_hypothesis_refs"))
    signatures = _strings(payload.get("registered_usage_signature_hashes"))
    trials = _strings(payload.get("trial_refs"))
    if len(hypotheses) != len(set(hypotheses)) or len(signatures) != len(
        set(signatures)
    ):
        blockers.append("registered_hypothesis_or_signature_duplicate")
    if len(hypotheses) != len(signatures):
        blockers.append("registered_hypothesis_signature_count_mismatch")
    if any(not _is_sha256_digest(item) for item in signatures):
        blockers.append("registered_usage_signature_hashes_invalid")
    if not _is_sha256_digest(payload.get("baseline_digest")):
        blockers.append("baseline_digest_invalid")
    outcome = str(payload.get("campaign_outcome"))
    if outcome not in _CAMPAIGN_OUTCOMES:
        blockers.append("campaign_outcome_invalid")
    selected = str(payload.get("selected_hypothesis_ref") or "").strip()
    if outcome == "selected":
        if not selected or selected not in hypotheses:
            blockers.append("selected_hypothesis_must_be_registered")
        if not trials:
            blockers.append("selected_hypothesis_trial_required")
    elif selected:
        blockers.append("non_selected_campaign_cannot_select_hypothesis")
    if outcome == "not_explored" and trials:
        blockers.append("not_explored_cannot_have_trials")
    if (
        str(payload.get("selection_scope_statement"))
        != "preferred_within_registered_scope"
    ):
        blockers.append("selection_scope_statement_invalid")
    if "global_best_usage" in payload or payload.get("production_authority") is True:
        blockers.append("campaign_forbidden_global_best_or_authority")
    if not isinstance(payload.get("coverage_claim"), Mapping):
        blockers.append("coverage_claim_object_required")
    return _report(USAGE_CAMPAIGN_RECEIPT_SCHEMA_ID, blockers)


def build_factor_usage_lifecycle_event(
    *,
    event_id: str,
    subject_type: str,
    subject_ref: str,
    event_type: str,
    prior_event_ref: str | None,
    evidence_ref: str,
    occurred_at: str,
    actor: str,
    source: str,
    field_labels_zh: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Append an immutable lifecycle transition event."""

    payload: dict[str, object] = {
        "artifact_type": "factor_usage_lifecycle_event",
        "schema_id": USAGE_LIFECYCLE_EVENT_SCHEMA_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "event_id": event_id,
        "subject_type": subject_type,
        "subject_ref": subject_ref,
        "event_type": event_type,
        "prior_event_ref": prior_event_ref,
        "evidence_ref": evidence_ref,
        "occurred_at": occurred_at,
        "actor": actor,
        "source": source,
        "field_labels_zh": dict(field_labels_zh or _event_labels()),
    }
    return _seal(payload, "event_digest", validate_factor_usage_lifecycle_event)


def validate_factor_usage_lifecycle_event(
    payload: Mapping[str, object],
) -> dict[str, object]:
    blockers = _contract_blockers(
        payload,
        artifact_type="factor_usage_lifecycle_event",
        schema_id=USAGE_LIFECYCLE_EVENT_SCHEMA_ID,
        digest_key="event_digest",
        required=(
            "event_id",
            "subject_type",
            "subject_ref",
            "event_type",
            "evidence_ref",
            "occurred_at",
            "actor",
            "source",
        ),
    )
    if str(payload.get("subject_type")) not in _SUBJECT_TYPES:
        blockers.append("subject_type_invalid")
    if "status" in payload:
        blockers.append("lifecycle_event_cannot_store_projection_status")
    return _report(USAGE_LIFECYCLE_EVENT_SCHEMA_ID, blockers)


def _usage_semantics(payload: Mapping[str, object]) -> dict[str, object]:
    keys = (
        "strategy_family_id",
        "strategy_id",
        "factor_asset_ref",
        "factor_ref",
        "baseline_artifact_ref",
        "baseline_digest",
        "action_space_digest",
        "action_id",
        "direction_spec",
        "transform_pipeline_ref",
        "activation_contract",
        "threshold_contract",
        "regime_contract",
        "interaction_contract",
        "timing_contract",
        "cost_fill_semantics_ref",
        "claim_metric_schema_refs",
        "no_harm_schema_refs",
    )
    return {key: payload.get(key) for key in keys}


def _seal(
    payload: dict[str, object],
    digest_key: str,
    validator: Callable[[Mapping[str, object]], dict[str, object]],
) -> dict[str, object]:
    payload[digest_key] = canonical_digest(payload)
    # Publish the same semantic digest through the resolver-wide checksum key.
    # The typed digest remains the domain contract; ``checksum`` makes the
    # artifact independently resolvable without caller-supplied attestations.
    payload["checksum"] = payload[digest_key]
    report = validator(payload)
    if report["status"] != "valid":
        raise ValueError("; ".join(_strings(report["blockers"])))
    return payload


def _contract_blockers(
    payload: Mapping[str, object],
    *,
    artifact_type: str,
    schema_id: str,
    digest_key: str,
    required: Sequence[str],
    digest_excludes: Sequence[str] = (),
) -> list[str]:
    blockers = [
        f"{key}_required" for key in required if not str(payload.get(key, "")).strip()
    ]
    if str(payload.get("artifact_type")) != artifact_type:
        blockers.append("artifact_type_invalid")
    if str(payload.get("schema_id")) != schema_id:
        blockers.append("schema_id_invalid")
    if str(payload.get("canonicalization_version")) != CANONICALIZATION_VERSION:
        blockers.append("canonicalization_version_invalid")
    labels = payload.get("field_labels_zh")
    if not isinstance(labels, Mapping) or not labels:
        blockers.append("field_labels_zh_required")
    supplied = str(payload.get(digest_key, "")).strip()
    if not supplied:
        blockers.append(f"{digest_key}_required")
    elif not _is_sha256_digest(supplied):
        blockers.append(f"{digest_key}_invalid")
    else:
        digest_payload = dict(payload)
        _ = digest_payload.pop(digest_key, None)
        _ = digest_payload.pop("checksum", None)
        for key in digest_excludes:
            _ = digest_payload.pop(key, None)
        if supplied != canonical_digest(digest_payload):
            blockers.append(f"{digest_key}_mismatch")
    checksum = str(payload.get("checksum", "")).strip()
    if checksum:
        checksum_payload = dict(payload)
        _ = checksum_payload.pop("checksum", None)
        if not _is_sha256_digest(checksum):
            blockers.append("checksum_invalid")
        elif checksum not in {supplied, canonical_digest(checksum_payload)}:
            blockers.append("checksum_mismatch")
    return blockers


def _report(schema_id: str, blockers: Sequence[str]) -> dict[str, object]:
    return {
        "artifact_type": "factor_usage_discovery_validation",
        "schema_id": schema_id,
        "status": "blocked" if blockers else "valid",
        "blockers": list(blockers),
    }


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _mapping_sequence(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(
        cast(Mapping[str, object], item) for item in value if isinstance(item, Mapping)
    )


def _normalize_scope_dimension(item: Mapping[str, object]) -> dict[str, object]:
    normalized = dict(item)
    normalized["candidate_definitions"] = [
        dict(definition)
        for definition in _mapping_sequence(item.get("candidate_definitions"))
    ]
    return normalized


def _normalize_sparse_combination(item: Mapping[str, object]) -> dict[str, object]:
    normalized = dict(item)
    normalized["dimension_ids"] = list(_strings(item.get("dimension_ids")))
    normalized["candidate_selections"] = [
        dict(selection)
        for selection in _mapping_sequence(item.get("candidate_selections"))
    ]
    return normalized


def _non_negative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _information_labels() -> dict[str, str]:
    return {"evidence_id": "信息证据编号", "information_verdict": "信息价值结论"}


def _action_space_labels() -> dict[str, str]:
    return {"action_space_id": "动作空间编号", "action_ids": "动作编号"}


def _hypothesis_labels() -> dict[str, str]:
    return {"usage_hypothesis_id": "用途假设编号", "action_id": "动作编号"}


def _search_scope_labels() -> dict[str, str]:
    return {"scope_manifest_id": "搜索范围清单编号", "dimensions": "搜索维度"}


def _trial_labels() -> dict[str, str]:
    return {"trial_id": "用途试验编号", "verdict": "用途试验结论"}


def _campaign_labels() -> dict[str, str]:
    return {"campaign_id": "用途研究活动编号", "campaign_outcome": "活动结论"}


def _event_labels() -> dict[str, str]:
    return {"event_id": "生命周期事件编号", "event_type": "事件类型"}


__all__ = [
    "ACTION_SPACE_SCHEMA_ID",
    "CANONICALIZATION_VERSION",
    "INFORMATION_EVIDENCE_SCHEMA_ID",
    "SEARCH_SCOPE_DIMENSION_SCHEMA_ID",
    "USAGE_CAMPAIGN_RECEIPT_SCHEMA_ID",
    "USAGE_HYPOTHESIS_SCHEMA_ID",
    "USAGE_LIFECYCLE_EVENT_SCHEMA_ID",
    "USAGE_TRIAL_SCHEMA_ID",
    "build_factor_usage_campaign_receipt",
    "build_factor_usage_hypothesis",
    "build_factor_usage_lifecycle_event",
    "build_factor_usage_trial_evidence",
    "build_search_scope_dimension_manifest",
    "build_strategy_factor_action_space",
    "build_strategy_factor_information_evidence",
    "validate_factor_usage_campaign_receipt",
    "validate_factor_usage_hypothesis",
    "validate_factor_usage_lifecycle_event",
    "validate_factor_usage_trial_evidence",
    "validate_search_scope_dimension_manifest",
    "validate_strategy_factor_action_space",
    "validate_strategy_factor_information_evidence",
]
