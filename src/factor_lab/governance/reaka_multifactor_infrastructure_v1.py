"""Governance for the REAKA multifactor current documentation closure."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, cast

from factor_lab.governance.canonicalization import canonical_digest

ROOT: Final = Path(__file__).resolve().parents[3]

ONTOLOGY_PATH: Final = ROOT / "docs/ops/reaka_multifactor_semantic_ontology@1.0.json"
SIX_SURFACE_PATH: Final = ROOT / "docs/ops/reaka_multifactor_six_surface_infrastructure@1.0.json"
STATE_MACHINE_V2_PATH: Final = ROOT / "docs/ops/state_factor_research_state_machine@2.0.json"
ROLLBACK_V2_PATH: Final = ROOT / "docs/ops/reaka_prediction_content_rollback@2.0.json"
STAGE3_CORRECTION_PATH: Final = ROOT / "docs/ops/reaka_v2_stage3_observable_context_authority_correction@1.0.json"
CURRENT_MANIFEST_PATH: Final = ROOT / "docs/ops/reaka_multifactor_current_manifest@1.0.json"

SEMANTIC_INVARIANTS: Final[dict[str, bool]] = {
    "observable_state_equals_latent_operator_state": False,
    "user_supplies_operator_count": False,
    "model_learns_operator_matrices": True,
    "model_learns_operator_assignments": True,
    "stage3_may_select_operator_count": False,
    "effective_operator_count_is_post_training_evidence": True,
    "portfolio_top_k_is_operator_count": False,
}

STAGE3_FORBIDDEN_KEYS: Final = frozenset(
    {
        "K2_allowed",
        "K3_allowed",
        "operator_count_N",
        "operator_count_N_selected",
        "N_effective",
        "discrete_operator_expert_allowed",
        "unshrunk_full_matrix_allowed",
        "standalone_rank_expert_allowed",
        "operator_supervision_mapping",
        "state_to_operator_mapping",
    }
)

SOURCE_FILES: Final = (
    "docs/user/reaka_multifactor_infrastructure_systematic_optimization_plan.md",
    "docs/user/reaka_multifactor_current_workflow.md",
    "docs/user/state_factor_research_state_machine_v2_workflow.md",
    "docs/user/reaka_strategy_v2_external_ai_handoff_v2.md",
    "docs/ops/reaka_multifactor_semantic_ontology_whitepaper.md",
    "docs/ops/reaka_multifactor_six_surface_infrastructure_whitepaper.md",
    "docs/ops/state_factor_research_state_machine_v2_whitepaper.md",
    "docs/ops/reaka_prediction_content_rollback_v2_whitepaper.md",
    "docs/ops/reaka_multifactor_model_assembly_v2_whitepaper.md",
    "docs/ops/reaka_operator_identifiability_whitepaper.md",
    "docs/ops/reaka_operator_identifiability@1.0.json",
    "docs/ops/koopman_residual_admission@1.0.json",
    "src/factor_lab/governance/reaka_multifactor_infrastructure_v1.py",
    "scripts/factor_rotation/build_reaka_multifactor_infrastructure_v1.py",
    "scripts/factor_rotation/validate_reaka_multifactor_infrastructure_v1.py",
    "scripts/factor_rotation/close_reaka_multifactor_infrastructure_v1.py",
    "tests/unit/test_reaka_multifactor_infrastructure_v1.py",
)


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def read_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def with_digest(payload: Mapping[str, object]) -> dict[str, object]:
    result = dict(payload)
    result.pop("canonical_digest", None)
    result["canonical_digest"] = canonical_digest(result)
    return result


def write_json(path: Path, payload: Mapping[str, object]) -> dict[str, object]:
    result = with_digest(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def canonical_valid(payload: Mapping[str, object]) -> bool:
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    return stored == canonical_digest(body)


def source_closure() -> dict[str, str]:
    return {relative: file_digest(ROOT / relative) for relative in SOURCE_FILES}


def recursive_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(recursive_keys(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            keys.update(recursive_keys(child))
    return keys


def validate_semantic_ontology(payload: Mapping[str, object]) -> None:
    if payload.get("semantic_invariants") != SEMANTIC_INVARIANTS:
        raise ValueError("reaka_multifactor_semantic_invariants_invalid")
    objects = cast(dict[str, object], payload.get("objects"))
    required = {
        "product_target",
        "factor",
        "S_obs",
        "S_factor",
        "H_x_H_y",
        "Z_S_latent",
        "K_i",
        "N_max",
        "N_effective",
        "residual",
        "score",
        "account",
    }
    if set(objects) != required:
        raise ValueError("reaka_multifactor_semantic_object_inventory_invalid")
    s_obs = cast(dict[str, object], objects["S_obs"])
    k_i = cast(dict[str, object], objects["K_i"])
    n_effective = cast(dict[str, object], objects["N_effective"])
    if s_obs.get("formation") != "user_and_project_PIT_input":
        raise ValueError("reaka_multifactor_S_obs_owner_invalid")
    if k_i.get("formation") != "learned_by_model":
        raise ValueError("reaka_multifactor_K_i_owner_invalid")
    if n_effective.get("formation") != "post_training_sequential_admission":
        raise ValueError("reaka_multifactor_N_effective_owner_invalid")


def validate_stage_payload(stage: str, payload: Mapping[str, object]) -> None:
    if stage != "stage3_observable_context_support":
        return
    forbidden = recursive_keys(payload) & STAGE3_FORBIDDEN_KEYS
    if forbidden:
        raise ValueError("reaka_multifactor_stage3_operator_authority_forbidden:" + ",".join(sorted(forbidden)))


def validate_state_machine_v2(payload: Mapping[str, object]) -> None:
    if payload.get("semantic_invariants") != SEMANTIC_INVARIANTS:
        raise ValueError("reaka_multifactor_state_machine_semantics_invalid")
    stages = cast(list[object], payload.get("stages"))
    by_id = {str(cast(dict[str, object], stage)["stage"]): cast(dict[str, object], stage) for stage in stages}
    stage3 = by_id.get("stage3_observable_context_support")
    stage6 = by_id.get("stage6_model_training_and_operator_capacity")
    if stage3 is None or stage6 is None:
        raise ValueError("reaka_multifactor_state_machine_stage_missing")
    if stage3.get("operator_count_decision_authority") is not False:
        raise ValueError("reaka_multifactor_stage3_operator_authority_open")
    if set(cast(list[str], stage3.get("forbidden_outputs"))) != STAGE3_FORBIDDEN_KEYS:
        raise ValueError("reaka_multifactor_stage3_forbidden_output_set_invalid")
    if stage6.get("operator_count_decision_authority") is not True:
        raise ValueError("reaka_multifactor_stage6_operator_authority_missing")
    validate_stage_payload("stage3_observable_context_support", cast(dict[str, object], stage3["example_valid_output"]))


def validate_semantic_checksum_text(text: str) -> None:
    for key, expected in SEMANTIC_INVARIANTS.items():
        line = f"{key} = {str(expected).lower()}"
        if line not in text:
            raise ValueError(f"reaka_multifactor_handoff_checksum_missing:{line}")


def validate_handoff_text(text: str) -> None:
    validate_semantic_checksum_text(text)
    required_paths = (
        "docs/user/reaka_multifactor_current_workflow.md",
        "docs/ops/reaka_multifactor_current_manifest@1.0.json",
    )
    if any(path not in text for path in required_paths):
        raise ValueError("reaka_multifactor_handoff_current_root_missing")
    forbidden_claims = (
        "外部状态 episode 决定 K",
        "三个外部状态对应三个 K",
        "用户选择 operator count",
    )
    if any(claim in text for claim in forbidden_claims):
        raise ValueError("reaka_multifactor_handoff_forbidden_claim")


def validate_markdown_links(paths: Sequence[Path]) -> None:
    link_pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    for document in paths:
        for raw_target in link_pattern.findall(document.read_text(encoding="utf-8")):
            target = raw_target.strip()
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            relative = target.split("#", 1)[0]
            if relative and not (document.parent / relative).resolve().exists():
                raise ValueError(f"reaka_multifactor_markdown_link_missing:{document}:{target}")


def validate_current_manifest(payload: Mapping[str, object]) -> None:
    if payload.get("semantic_invariants") != SEMANTIC_INVARIANTS:
        raise ValueError("reaka_multifactor_manifest_semantics_invalid")
    if payload.get("default_unlisted_classification") != ("historical_or_specialized_no_current_normative_authority"):
        raise ValueError("reaka_multifactor_manifest_default_authority_invalid")
    roots = cast(list[object], payload.get("normative_roots"))
    roles: list[str] = []
    paths: list[str] = []
    for item in roots:
        entry = cast(dict[str, object], item)
        role = str(entry["role"])
        relative = str(entry["path"])
        roles.append(role)
        paths.append(relative)
        path = ROOT / relative
        if not path.is_file():
            raise ValueError(f"reaka_multifactor_manifest_path_missing:{relative}")
        if entry.get("file_digest") != file_digest(path):
            raise ValueError(f"reaka_multifactor_manifest_digest_drift:{relative}")
        if path.suffix == ".json" and not canonical_valid(read_json(path)):
            raise ValueError(f"reaka_multifactor_manifest_canonical_invalid:{relative}")
    if len(roles) != len(set(roles)):
        raise ValueError("reaka_multifactor_manifest_duplicate_role_owner")
    if len(paths) != len(set(paths)):
        raise ValueError("reaka_multifactor_manifest_duplicate_path")
    if roles.count("current_entry") != 1:
        raise ValueError("reaka_multifactor_manifest_current_entry_not_unique")
    if payload.get("next_legal_action") != "user_review_then_freeze_stage4_contract":
        raise ValueError("reaka_multifactor_manifest_next_action_invalid")
    revoked = set(cast(list[str], payload.get("revoked_current_normative_paths")))
    if revoked & set(paths):
        raise ValueError("reaka_multifactor_manifest_revoked_path_is_current")


def validate_source_closure(payload: Mapping[str, object]) -> None:
    if payload.get("source_closure") != source_closure():
        raise ValueError("reaka_multifactor_source_closure_drift")
