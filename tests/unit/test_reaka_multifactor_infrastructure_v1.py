from __future__ import annotations

import copy
from pathlib import Path

import pytest

from factor_lab.governance.reaka_multifactor_infrastructure_v1 import (
    CURRENT_MANIFEST_PATH,
    ONTOLOGY_PATH,
    SEMANTIC_INVARIANTS,
    STATE_MACHINE_V2_PATH,
    read_json,
    validate_current_manifest,
    validate_handoff_text,
    validate_markdown_links,
    validate_semantic_checksum_text,
    validate_semantic_ontology,
    validate_stage_payload,
    validate_state_machine_v2,
)

ROOT = Path(__file__).resolve().parents[2]


def test_current_ontology_and_state_machine_validate() -> None:
    ontology = read_json(ONTOLOGY_PATH)
    state_machine = read_json(STATE_MACHINE_V2_PATH)
    validate_semantic_ontology(ontology)
    validate_state_machine_v2(state_machine)
    assert ontology["semantic_invariants"] == SEMANTIC_INVARIANTS


def test_stage3_cannot_emit_operator_count_or_K_authority() -> None:
    with pytest.raises(ValueError, match="stage3_operator_authority_forbidden"):
        validate_stage_payload(
            "stage3_observable_context_support",
            {"observable_context_support_certificate": {"K2_allowed": False}},
        )
    with pytest.raises(ValueError, match="stage3_operator_authority_forbidden"):
        validate_stage_payload(
            "stage3_observable_context_support",
            {"discrete_operator_expert_allowed": False},
        )


def test_real_stage3_v1_operator_inference_is_rejected_by_v2() -> None:
    old_certificate = read_json(
        ROOT / "output/factor-rotation/reaka_v2_stage3_state_episode_atlas_v1_2011_2025/formal/state_learnability_certificate.json"
    )
    with pytest.raises(ValueError, match="stage3_operator_authority_forbidden"):
        validate_stage_payload("stage3_observable_context_support", old_certificate)


def test_observable_state_cannot_equal_latent_operator_state() -> None:
    broken = copy.deepcopy(read_json(ONTOLOGY_PATH))
    invariants = dict(SEMANTIC_INVARIANTS)
    invariants["observable_state_equals_latent_operator_state"] = True
    broken["semantic_invariants"] = invariants
    with pytest.raises(ValueError, match="semantic_invariants_invalid"):
        validate_semantic_ontology(broken)


def test_user_cannot_supply_operator_count() -> None:
    broken = copy.deepcopy(read_json(ONTOLOGY_PATH))
    invariants = dict(SEMANTIC_INVARIANTS)
    invariants["user_supplies_operator_count"] = True
    broken["semantic_invariants"] = invariants
    with pytest.raises(ValueError, match="semantic_invariants_invalid"):
        validate_semantic_ontology(broken)


def test_current_manifest_has_one_owner_per_role_and_excludes_revoked_paths() -> None:
    manifest = read_json(CURRENT_MANIFEST_PATH)
    validate_current_manifest(manifest)
    roots = manifest["normative_roots"]
    assert isinstance(roots, list)
    current_paths = {str(item["path"]) for item in roots}
    assert "docs/ops/state_factor_research_state_machine@1.0.json" not in current_paths
    assert "docs/user/reaka_strategy_v2_external_ai_handoff.md" not in current_paths


def test_duplicate_current_role_is_rejected() -> None:
    broken = copy.deepcopy(read_json(CURRENT_MANIFEST_PATH))
    roots = broken["normative_roots"]
    assert isinstance(roots, list)
    roots.append(copy.deepcopy(roots[0]))
    with pytest.raises(ValueError, match="duplicate_role_owner"):
        validate_current_manifest(broken)


def test_current_handoff_contains_complete_semantic_checksum() -> None:
    path = ROOT / "docs/user/reaka_strategy_v2_external_ai_handoff_v2.md"
    text = path.read_text(encoding="utf-8")
    validate_handoff_text(text)
    with pytest.raises(ValueError, match="handoff_checksum_missing"):
        validate_handoff_text(
            text.replace(
                "stage3_may_select_operator_count = false",
                "stage3_may_select_operator_count = true",
            )
        )


def test_current_workflow_uses_checksum_without_handoff_path_rule() -> None:
    text = (ROOT / "docs/user/reaka_multifactor_current_workflow.md").read_text(encoding="utf-8")
    validate_semantic_checksum_text(text)


def test_markdown_link_validator_rejects_missing_local_target(tmp_path: Path) -> None:
    document = tmp_path / "entry.md"
    document.write_text("[missing](not-there.md)\n", encoding="utf-8")
    with pytest.raises(ValueError, match="markdown_link_missing"):
        validate_markdown_links((document,))
