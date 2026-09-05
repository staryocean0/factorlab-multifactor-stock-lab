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

from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    canonical_valid,
    read_json,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/ops/evidence/reaka_v2_stage3_state_episode_atlas_v1_20260904"
FORMAL = ROOT / "output/factor-rotation/reaka_v2_stage3_state_episode_atlas_v1_2011_2025/formal"


def main() -> int:
    _reject_legacy_entrypoint(__file__)
    validation = read_json(EVIDENCE / "validation_report.json")
    result = read_json(FORMAL / "result.json")
    certificate = read_json(FORMAL / "state_learnability_certificate.json")
    if not all(canonical_valid(item) for item in (validation, result, certificate)):
        raise PermissionError("reaka_v2_stage3_close_input_digest_invalid")
    if validation.get("status") != "passed":
        raise PermissionError("reaka_v2_stage3_validation_not_passed")
    acceptance = write_json(
        EVIDENCE / "controller_acceptance.json",
        {
            "schema_id": "factorlab.reaka_v2_stage3_state_episode_atlas_controller_acceptance@1.0",
            "status": "accepted_stage3_slow_context_route_waiting_user_stage4_checkpoint",
            "validation_digest": validation["canonical_digest"],
            "result_digest": result["canonical_digest"],
            "certificate_digest": certificate["canonical_digest"],
            "mathematical_verdict": (
                "monthly state is observable but directional persistent episodes are insufficient for distinct discrete Koopman operators"
            ),
            "financial_role_allowed_next": "stage4_pairing_candidate_only",
            "composite_learnability_route": "slow_context_low_rank_modulator",
            "stage4_execution_allowed": False,
            "stage5_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "strategy_pointer_change_allowed": False,
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    old_round = read_json(ROOT / "docs/ops/reaka_strategy_round_registry@1.0.json")
    round_registry = write_json(
        ROOT / "docs/ops/reaka_strategy_round_registry@1.1.json",
        {
            "schema_id": "factorlab.reaka_strategy_round_registry@1.1",
            "status": "v2_stage3_complete_waiting_user_stage4_checkpoint",
            "supersedes": "docs/ops/reaka_strategy_round_registry@1.0.json",
            "supersedes_digest": old_round["canonical_digest"],
            "current_version_id": "REAKA_STRATEGY_V2_STATE_WEIGHTED_ORTHOGONAL_14",
            "predecessor_version_id": "REAKA_STRATEGY_V1_K1_ONLY",
            "what_changed": "only_added_previous_month_cloudridge_trend_context",
            "current_stage": "stage3_state_episode_atlas_complete",
            "current_contract": "docs/ops/reaka_v2_stage3_state_episode_atlas@1.0.json",
            "current_result": ("output/factor-rotation/reaka_v2_stage3_state_episode_atlas_v1_2011_2025/formal/result.json"),
            "controller_acceptance": ("docs/ops/evidence/reaka_v2_stage3_state_episode_atlas_v1_20260904/controller_acceptance.json"),
            "v1_preserved_historical_queryable": True,
            "k1_only_checkpoint_reuse_allowed": False,
            "paper_training_executed": False,
            "next_checkpoint": "user_review_then_result_free_stage4_pairing_contract",
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    old_authority = read_json(ROOT / "docs/ops/reaka_strategy_authority_registry@109.0.json")
    authority = write_json(
        ROOT / "docs/ops/reaka_strategy_authority_registry@110.0.json",
        {
            "schema_id": "factorlab.reaka_strategy_authority_registry@110.0",
            "status": "REAKA_V2_stage3_complete_waiting_user_stage4_checkpoint",
            "supersedes": {
                "path": "docs/ops/reaka_strategy_authority_registry@109.0.json",
                "canonical_digest": old_authority["canonical_digest"],
                "revoked_next_action": "stage6_paper_preflight_and_k_admission_retrain",
                "reason": "stage6_opened_without_state_learnability_certificate",
            },
            "round_registry": "docs/ops/reaka_strategy_round_registry@1.1.json",
            "round_registry_digest": round_registry["canonical_digest"],
            "current_version_id": "REAKA_STRATEGY_V2_STATE_WEIGHTED_ORTHOGONAL_14",
            "current_contract": "docs/ops/reaka_v2_stage3_state_episode_atlas@1.0.json",
            "controller_acceptance_digest": acceptance["canonical_digest"],
            "next_legal_action": "user_review_then_freeze_stage4_pairing_contract",
            "stage4_execution_allowed": False,
            "stage5_execution_allowed": False,
            "stage6_execution_allowed": False,
            "k1_only_checkpoint_reuse_allowed": False,
            "linear_exposure_score_has_trading_authority": False,
            "account_execution_allowed": False,
            "strategy_pointer_change_allowed": False,
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    old_succession = read_json(ROOT / "docs/ops/reaka_controller_succession_audit@270.0.json")
    write_json(
        ROOT / "docs/ops/reaka_controller_succession_audit@271.0.json",
        {
            "schema_id": "factorlab.reaka_controller_succession_audit@271.0",
            "status": "v2_stage3_complete_waiting_user_stage4_checkpoint",
            "supersedes": "docs/ops/reaka_controller_succession_audit@270.0.json",
            "supersedes_digest": old_succession["canonical_digest"],
            "authority_registry_digest": authority["canonical_digest"],
            "round_registry_digest": round_registry["canonical_digest"],
            "controller_acceptance_digest": acceptance["canonical_digest"],
            "stage3_verdict": "slow_context_low_rank_modulator_not_discrete_operator",
            "next_legal_action": "user_review_then_freeze_stage4_pairing_contract",
            "stage4_execution_allowed": False,
            "stage5_execution_allowed": False,
            "stage6_execution_allowed": False,
            "model_training_executed": False,
            "account_executed": False,
            "production_authority": False,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
