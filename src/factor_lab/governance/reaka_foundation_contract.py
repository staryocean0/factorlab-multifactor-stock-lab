"""Current, data-independent REAKA foundation contract for this bounded lab.

This checks declared semantics and exact reviewed source bytes. It does not
certify market data, historical evidence, statistical utility or live readiness.
Historical validators keep their frozen meaning; they do not define current.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CURRENT_MANIFEST = "docs/ops/reaka_multifactor_current_manifest@1.3.json"
SEMANTICS_PATH = "docs/ops/reaka_foundation_semantics@1.1.json"
CURRENT_WORKFLOW = "docs/user/reaka_multifactor_current_workflow_v1_3.md"
CURRENT_WHITEPAPER = "docs/ops/reaka_foundation_whitepaper_v1_3.md"
CURRENT_STATUS = "foundation_contract_active_research_execution_blocked"
NEXT_ACTION = "maintain_foundation_and_wait_for_user_data_completion_notice"

INVARIANTS = {
    "self_developed_factors_allowed": True,
    "observable_state_equals_latent_operator_state": False,
    "observable_condition_is_operator_label": False,
    "gate_is_financial_factor_weight": False,
    "larger_gate_emphasizes_return_encoding": True,
    "model_learns_operator_matrices": True,
    "model_learns_operator_assignments": True,
    "model_automatically_changes_instantiated_operator_count": False,
    "stage3_may_select_operator_count": False,
    "effective_operator_usage_is_post_training_evidence": True,
    "portfolio_top_k_is_operator_count": False,
    "financial_residual_equals_latent_residual": False,
    "account_other_is_pure_alpha": False,
    "residual_predictor_is_mandatory": False,
    "residual_must_be_nonzero": False,
    "residual_must_be_predictable": False,
    "residual_must_improve_financial_result": False,
    "zero_conditional_mean_implies_scale_failure": False,
    "mlp_mean_energy_comparable_to_diffusion_draw_energy": False,
    "teacher_forced_denoising_is_history_only_forecast_evidence": False,
    "stage4_realized_contribution_is_forward_predictive_increment": False,
    "raw_matrix_difference_proves_operator_identification": False,
    "k_then_residual_policy_equals_paper_joint_training": False,
    "higher_capacity_failure_is_implied_by_lower_capacity_failure": False,
    "mathematical_validity_implies_positive_financial_result": False,
}
CLOSED_ACTIONS = (
    "train", "stage3_execute", "stage4_execute", "account_execute",
    "capacity_select", "evidence_promote", "production",
)
ENTRY_DOCS = ("AGENTS.md", "README.md", "docs/INDEX.md", "ai-readme.md", "docs/user/cloud_execution_prompt.md")
LEGACY_LAUNCHERS = {
    f"scripts/factor_rotation/{name}.py" for name in (
        "build_reaka_multifactor_infrastructure_v1", "build_reaka_v2_stage3_observable_context_v2",
        "build_reaka_v2_stage4_observable_factor_pairing_v1", "close_reaka_multifactor_infrastructure_v1",
        "close_reaka_v2_stage3_observable_context_v2", "close_reaka_v2_stage3_state_episode_atlas_v1",
        "close_reaka_v2_stage4_observable_factor_pairing_v1", "freeze_reaka_v2_stage3_state_episode_atlas_v1",
        "run_reaka_v2_stage3_observable_context_v2", "run_reaka_v2_stage3_state_episode_atlas_v1",
        "run_reaka_v2_stage4_observable_factor_pairing_v1", "validate_reaka_multifactor_infrastructure_v1",
        "validate_reaka_v2_stage3_observable_context_v2", "validate_reaka_v2_stage3_state_episode_atlas_v1",
        "validate_reaka_v2_stage4_observable_factor_pairing_v1",
    )
} | {"scripts/build_strategy_slice_rebuild_workflow.py", "scripts/build_strategy_progressive_development_workflow.py"}
SURFACE_MINIMUM = {
    "documentation": set(ENTRY_DOCS) | {
        SEMANTICS_PATH, "docs/governance/package_scope.json", "docs/governance/data_usage_declaration.json",
    },
    "whitepaper": {CURRENT_WHITEPAPER},
    "code": {
        "src/factor_lab/governance/reaka_foundation_contract.py",
        "src/factor_lab/governance/reaka_residual_certificate.py",
        "src/factor_lab/factor_rotation/reaka_financial_residual.py",
        "src/factor_lab/factor_rotation/reaka_paper_v1.py",
        "src/factor_lab/factor_rotation/reaka_stage6_daily_engine.py",
        "src/factor_lab/factor_rotation/reaka_v2_stage4_observable_factor_pairing_v1.py",
        "src/factor_lab/factor_rotation/reaka_v2_stage3_state_episode_atlas_v1.py",
        "src/factor_lab/factor_rotation/reaka_v2_stage3_observable_context_v2.py",
        "src/factor_lab/factor_rotation/reaka_k1_only_index_regime_atlas_v1.py",
        "src/factor_lab/factor_rotation/reaka_stage6_parameter_calibration.py",
        "src/factor_lab/factor_rotation/reaka_paper_v1_runtime.py",
    },
    "tests": {
        "tests/unit/test_reaka_foundation_contract.py",
        "tests/unit/test_reaka_paper_math_contract.py",
        "tests/unit/test_reaka_residual_certificate.py",
        "tests/unit/test_reaka_stage6_health_estimand.py",
        "tests/unit/test_reaka_financial_residual.py",
        "tests/unit/test_reaka_legacy_entrypoints.py",
        "tests/unit/test_reaka_v2_stage4_observable_factor_pairing_v1.py",
        "tests/test_theme_boundaries.py",
    },
    "workflow": {
        CURRENT_WORKFLOW, "scripts/validate_reaka_foundation.py",
        "scripts/validate_theme_package.py", ".github/workflows/ci.yml",
        ".github/workflows/foundation-audit.yml",
    } | LEGACY_LAUNCHERS,
}


def canonical_digest(payload: dict[str, Any]) -> str:
    body = {k: v for k, v in payload.items() if k != "canonical_digest"}
    return "sha256:" + hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode()).hexdigest()


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return payload


def validate_foundation(root: Path) -> dict[str, Any]:
    """Read only; missing, malformed or drifted surfaces are hard failures."""
    root = Path(root).resolve()
    errors: list[str] = []
    checked_files: set[str] = set()

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    try:
        manifest = _read_json(root / CURRENT_MANIFEST)
        semantics = _read_json(root / SEMANTICS_PATH)
        for label, document in (("manifest", manifest), ("semantics", semantics)):
            check(document.get("canonical_digest") == canonical_digest(document), f"{label}: canonical digest mismatch")
        check(manifest.get("schema_id") == "factorlab.reaka_multifactor_current_manifest@1.3", "wrong current schema")
        check(semantics.get("schema_id") == "factorlab.reaka_foundation_semantics@1.1", "wrong semantics schema")
        check(manifest.get("scope") == "bounded_repository_foundation_only", "current scope drift")
        check(manifest.get("status") == CURRENT_STATUS, "current status drift")
        check(manifest.get("next_legal_action") == NEXT_ACTION, "next action drift")
        check(manifest.get("semantics") == SEMANTICS_PATH, "semantics routing drift")
        check(manifest.get("current_workflow") == CURRENT_WORKFLOW, "workflow routing drift")
        check(manifest.get("current_whitepaper") == CURRENT_WHITEPAPER, "whitepaper routing drift")
        actual = semantics.get("invariants", {})
        check(isinstance(actual, dict) and set(actual) == set(INVARIANTS), "semantic invariant inventory drift")
        for key, value in INVARIANTS.items():
            check(isinstance(actual, dict) and actual.get(key) is value, f"semantic invariant drift: {key}")
        for document in (manifest, semantics):
            check(document.get("allowed_actions") == ["foundation_read", "foundation_repair", "synthetic_test"], "allowed action drift")
            actions = document.get("research_actions", {})
            check(isinstance(actions, dict) and set(actions) == set(CLOSED_ACTIONS), "research action inventory drift")
            for action in CLOSED_ACTIONS:
                check(isinstance(actions, dict) and actions.get(action) is False, f"research execution unexpectedly open: {action}")
            for key in ("fresh_oos", "user_financial_receipt_signed", "local_factorlab_pointer_changed"):
                check(document.get(key) is False, f"authority drift: {key}")
        check(manifest.get("historical_evidence_status") == "blocked_duplicate_stage4_months_and_incomplete_source_closure", "historical evidence misclassified")
        check(manifest.get("data_readiness") == "not_evaluated_by_foundation_validation", "data readiness conflated with infrastructure")
        check(manifest.get("scientific_acceptance") == "not_established", "scientific acceptance overstated")
        check(manifest.get("unlisted_files") == "historical_or_reference_no_current_normative_authority", "unlisted authority drift")
        surfaces = manifest.get("five_in_one", {})
        check(isinstance(surfaces, dict) and set(surfaces) == set(SURFACE_MINIMUM), "five-in-one inventory drift")
        if not isinstance(surfaces, dict):
            surfaces = {}
        for surface, required in SURFACE_MINIMUM.items():
            rows = surfaces.get(surface, [])
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                errors.append(f"malformed surface: {surface}")
                continue
            paths = [row.get("path") for row in rows]
            if any(not isinstance(path, str) for path in paths):
                errors.append(f"invalid surface path: {surface}")
                continue
            check(len(paths) == len(set(paths)), f"duplicate paths: {surface}")
            check(required <= set(paths), f"missing required surface paths: {surface}: {sorted(required - set(paths))}")
            for row in rows:
                relative = row["path"]
                path = root / relative
                if Path(relative).is_absolute() or ".." in Path(relative).parts or not path.resolve().is_relative_to(root):
                    errors.append(f"unsafe source path: {relative}")
                    continue
                if not path.is_file():
                    errors.append(f"missing source: {relative}")
                    continue
                check(row.get("file_digest") == file_digest(path), f"source drift: {relative}")
                checked_files.add(relative)
        for relative in ENTRY_DOCS:
            path = root / relative
            if path.is_file():
                check(CURRENT_MANIFEST in path.read_text(encoding="utf-8"), f"entry not routed to current: {relative}")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors.append(f"contract unreadable: {type(exc).__name__}: {exc}")
    return {
        "schema_id": "factorlab.reaka_foundation_validation@1.0",
        "current_manifest": CURRENT_MANIFEST,
        "infrastructure_consistency": "passed" if not errors else "failed",
        "checked_source_files": len(checked_files),
        "errors": errors,
        "data_readiness": "not_evaluated",
        "historical_evidence_readiness": "blocked",
        "scientific_acceptance": "not_established",
        "research_execution_allowed": False,
        "production_authority": False,
    }


def require_research_action(root: Path, action: str) -> None:
    """Fail before historical execution/fit/write. No CLI override opens it."""
    report = validate_foundation(root)
    if report["errors"]:
        raise PermissionError("REAKA foundation invalid; run scripts/validate_reaka_foundation.py: " + "; ".join(report["errors"][:3]))
    # All research execution is closed in this version. Unknown actions are
    # rejected too; future work needs an explicit, reviewed successor contract.
    raise PermissionError(f"REAKA current@1.3 blocks research action {action!r}; only foundation repair and synthetic tests are active")


def reject_legacy_entrypoint(path: str | Path) -> None:
    raise RuntimeError(
        f"REAKA archived entrypoint {Path(path).name}: historical contracts and evidence are immutable. "
        "Use scripts/validate_reaka_foundation.py for current@1.3; this launcher has no current execution authority."
    )
