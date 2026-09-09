#!/usr/bin/env python3
from __future__ import annotations

# ruff: noqa: E402
# Retired materializers cannot recreate historical current/evidence authority.
# Keep this check before legacy imports, including optional project dependencies.
import sys as _foundation_sys
from pathlib import Path as _FoundationPath

_FOUNDATION_ROOT = _FoundationPath(__file__).resolve().parents[2]
if str(_FOUNDATION_ROOT / "src") not in _foundation_sys.path:
    _foundation_sys.path.insert(0, str(_FOUNDATION_ROOT / "src"))
from factor_lab.governance.reaka_foundation_contract import (  # noqa: E402
    reject_legacy_entrypoint as _reject_legacy_entrypoint,
)

if __name__ == "__main__":
    _reject_legacy_entrypoint(__file__)

from pathlib import Path
from typing import cast

from factor_lab.governance.reaka_multifactor_infrastructure_v1 import (
    CURRENT_MANIFEST_PATH,
    ONTOLOGY_PATH,
    ROLLBACK_V2_PATH,
    SEMANTIC_INVARIANTS,
    SIX_SURFACE_PATH,
    STAGE3_CORRECTION_PATH,
    STATE_MACHINE_V2_PATH,
    canonical_valid,
    read_json,
    validate_current_manifest,
    validate_handoff_text,
    validate_markdown_links,
    validate_semantic_checksum_text,
    validate_semantic_ontology,
    validate_source_closure,
    validate_state_machine_v2,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/ops/evidence/reaka_multifactor_infrastructure_v1_20260904"


def main() -> int:
    _reject_legacy_entrypoint(__file__)
    paths = (
        ONTOLOGY_PATH,
        SIX_SURFACE_PATH,
        STATE_MACHINE_V2_PATH,
        ROLLBACK_V2_PATH,
        STAGE3_CORRECTION_PATH,
        CURRENT_MANIFEST_PATH,
    )
    payloads = {path: read_json(path) for path in paths}
    for path, payload in payloads.items():
        if not canonical_valid(payload):
            raise ValueError(f"reaka_multifactor_canonical_invalid:{path}")
        validate_source_closure(payload)

    ontology = payloads[ONTOLOGY_PATH]
    six_surface = payloads[SIX_SURFACE_PATH]
    state_machine = payloads[STATE_MACHINE_V2_PATH]
    rollback = payloads[ROLLBACK_V2_PATH]
    correction = payloads[STAGE3_CORRECTION_PATH]
    manifest = payloads[CURRENT_MANIFEST_PATH]
    validate_semantic_ontology(ontology)
    validate_state_machine_v2(state_machine)
    validate_current_manifest(manifest)

    expected_surfaces = {
        "user_document",
        "whitepaper",
        "machine_contract",
        "source_code",
        "tests",
        "scripts",
    }
    if set(cast(dict[str, object], six_surface["surfaces"])) != expected_surfaces:
        raise ValueError("reaka_multifactor_six_surface_inventory_invalid")
    if rollback.get("stage3_operator_count_decision_authority") is not False:
        raise ValueError("reaka_multifactor_rollback_transferred_K_authority")
    if rollback.get("operator_count_selection_stage") != ("stage6_model_training_and_operator_capacity"):
        raise ValueError("reaka_multifactor_rollback_K_stage_invalid")
    if correction.get("stage3_operator_count_decision_authority") is not False:
        raise ValueError("reaka_multifactor_stage3_correction_K_authority")
    if correction.get("stage3_measurement_reexecution_required") is not False:
        raise ValueError("reaka_multifactor_stage3_raw_measurement_unnecessarily_revoked")

    handoff = (ROOT / "docs/user/reaka_strategy_v2_external_ai_handoff_v2.md").read_text(encoding="utf-8")
    validate_handoff_text(handoff)
    current_workflow = (ROOT / "docs/user/reaka_multifactor_current_workflow.md").read_text(encoding="utf-8")
    validate_semantic_checksum_text(current_workflow)
    validate_markdown_links(
        (
            ROOT / "docs/user/reaka_multifactor_current_workflow.md",
            ROOT / "docs/user/reaka_multifactor_infrastructure_systematic_optimization_plan.md",
            ROOT / "docs/user/state_factor_research_state_machine_v2_workflow.md",
            ROOT / "docs/user/reaka_strategy_v2_external_ai_handoff_v2.md",
            ROOT / "docs/ops/reaka_multifactor_semantic_ontology_whitepaper.md",
            ROOT / "docs/ops/reaka_multifactor_six_surface_infrastructure_whitepaper.md",
            ROOT / "docs/ops/state_factor_research_state_machine_v2_whitepaper.md",
            ROOT / "docs/ops/reaka_prediction_content_rollback_v2_whitepaper.md",
            ROOT / "docs/ops/reaka_multifactor_model_assembly_v2_whitepaper.md",
        )
    )
    index_requirements = (
        (ROOT / "README.md", "REAKA 多因子选股当前唯一入口"),
        (ROOT / "ai-readme.md", "REAKA 当前唯一开发入口"),
        (ROOT / "docs/00-index.md", "REAKA 当前唯一开发入口"),
        (ROOT / "docs/user/README.md", "REAKA多因子选股当前唯一工作流"),
    )
    for index_path, marker in index_requirements:
        text = index_path.read_text(encoding="utf-8")
        if text.count(marker) != 1:
            raise ValueError(f"reaka_multifactor_current_entry_count:{index_path}")
        if "reaka_multifactor_current_workflow.md" not in text:
            raise ValueError(f"reaka_multifactor_current_entry_path:{index_path}")

    roots = cast(list[object], manifest["normative_roots"])
    current_paths = {str(cast(dict[str, object], item)["path"]) for item in roots}
    for old in cast(list[str], manifest["revoked_current_normative_paths"]):
        if old in current_paths:
            raise ValueError(f"reaka_multifactor_revoked_path_current:{old}")
    if manifest.get("semantic_invariants") != SEMANTIC_INVARIANTS:
        raise ValueError("reaka_multifactor_manifest_checksum_invalid")

    write_json(
        EVIDENCE / "validation_report.json",
        {
            "schema_id": "factorlab.reaka_multifactor_infrastructure_validation@1.0",
            "status": "passed",
            "validated_contracts": {str(path.relative_to(ROOT)): payload["canonical_digest"] for path, payload in payloads.items()},
            "semantic_invariants": SEMANTIC_INVARIANTS,
            "normative_root_count": len(roots),
            "current_entry_count": 1,
            "top_level_index_count": len(index_requirements),
            "new_markdown_links_valid": True,
            "stage3_operator_count_decision_authority": False,
            "old_stage3_measurements_retained": True,
            "old_stage3_operator_inference_revoked": True,
            "stage4_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
