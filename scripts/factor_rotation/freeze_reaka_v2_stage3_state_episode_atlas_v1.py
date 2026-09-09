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

import argparse
from pathlib import Path
from typing import cast

from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    canonical_valid,
    read_json,
    write_json,
)
from factor_lab.factor_rotation.reaka_v2_stage3_state_episode_atlas_v1 import (
    CONTRACT,
    INPUT_ROOT,
    SCIENCE_FILES,
    STATE_ATLAS_CONTRACT,
    STATE_MACHINE_CONTRACT,
    source_closure,
)


def main() -> int:
    _reject_legacy_entrypoint(__file__)
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if CONTRACT.exists() and not args.overwrite:
        raise FileExistsError(f"contract_exists:{CONTRACT}")
    state_machine = read_json(STATE_MACHINE_CONTRACT)
    atlas = read_json(STATE_ATLAS_CONTRACT)
    round_registry = read_json(Path("docs/ops/reaka_strategy_round_registry@1.0.json"))
    for name, payload in (
        ("state_machine", state_machine),
        ("state_atlas", atlas),
        ("round_registry", round_registry),
    ):
        if not canonical_valid(payload):
            raise PermissionError(f"upstream_digest_invalid:{name}")
    input_manifests: dict[str, object] = {}
    for tree in ("formal", "isolated"):
        input_manifests[tree] = {}
        for clock in ("1430", "1445"):
            manifest = read_json(INPUT_ROOT / tree / clock / "manifest.json")
            if not canonical_valid(manifest):
                raise PermissionError(f"input_manifest_invalid:{tree}:{clock}")
            cast(dict[str, object], input_manifests[tree])[clock] = manifest["canonical_digest"]
    payload = {
        "schema_id": "factorlab.reaka_v2_stage3_state_episode_atlas@1.0",
        "status": "result_free_stage3_contract_frozen",
        "stage": "stage3_state_episode_atlas",
        "version_id": "REAKA_STRATEGY_V2_STATE_WEIGHTED_ORTHOGONAL_14",
        "predecessor_version_id": "REAKA_STRATEGY_V1_K1_ONLY",
        "rollback_reason": "observable_state_definition_changed",
        "governance_rollback_table": ("docs/ops/reaka_paper_parameter_governance_whitepaper.md#7.2"),
        "revokes_next_action_only": {
            "authority_registry": "docs/ops/reaka_strategy_authority_registry@109.0.json",
            "succession": "docs/ops/reaka_controller_succession_audit@270.0.json",
            "reason": "stage6_opened_without_state_learnability_certificate",
        },
        "state_identity": {
            "scope": "global_market",
            "carrier": "CN_A_CLOUDRIDGE_BETA_EQW",
            "grain": "monthly",
            "decision_state_source": "previous_calendar_month",
            "trend_deadband_sigma_multiple": 1.0,
            "trend_states": ["up", "sideways", "down"],
            "minimum_persistent_segment_months": 2,
            "volatility_role": "diagnostic_label_only_not_episode_split",
            "new_factor_identity_added": False,
        },
        "development_boundary": {
            "decision_month_min": "2011-05",
            "decision_month_max": "2016-12",
            "role": "development_material_state_certificate",
        },
        "data_usage": {
            "2008_2011_04": "cloudridge_and_input_warmup_only",
            "2011_05_2016_12": "development_material_state_certificate",
            "2017": "development_listing_not_pass_evidence",
            "2018_2025": "consumed_repeat_comparison_no_retune",
            "2026": "unread_as_decision_year",
        },
        "stage3_required_items": [
            "state_scope_global_sector_or_asset",
            "independent_episode_count",
            "transition_count",
            "state_switch_count",
            "duration_and_prevalence",
            "temporal_vs_cross_sectional_support",
            "state_learnability_certificate",
        ],
        "learnability_policy_digest": state_machine["canonical_digest"],
        "upstream_state_atlas_digest": atlas["canonical_digest"],
        "round_registry_digest": round_registry["canonical_digest"],
        "input_manifest_digests": input_manifests,
        "diagnostic_model_capacity": {
            "latent_dimension": 8,
            "proposed_operator_count": 2,
            "operator_parameterization": "full",
            "purpose": "learnability_dof_test_only_not_training_authority",
        },
        "output_inventory": [*SCIENCE_FILES, "result.json"],
        "formal_isolated_byte_identity_required": True,
        "authority": {
            "stage3_execution_allowed": True,
            "stage4_execution_allowed": False,
            "stage5_execution_allowed": False,
            "model_training_allowed": False,
            "account_execution_allowed": False,
            "new_factor_search_allowed": False,
            "strategy_pointer_change_allowed": False,
            "production_authority": False,
        },
        "fresh_oos": False,
        "production_authority": False,
        "source_closure": source_closure(),
    }
    write_json(CONTRACT, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
