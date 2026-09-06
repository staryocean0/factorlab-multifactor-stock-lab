from __future__ import annotations

from typing import cast

import numpy as np

from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    COMPATIBILITY_REQUIRED_FIELDS,
    FEATURE_DIM,
    build_inference_rows,
    feature_registry,
    parameter_instantiation,
    select_backend,
    validate_contract,
)
from factor_lab.governance.canonicalization import canonical_digest


def test_inference_universe_is_not_filtered_by_future_target() -> None:
    calendar = np.arange(np.datetime64("2008-12-01"), np.datetime64("2009-09-01")).astype("datetime64[ns]")
    decisions = np.arange(180, len(calendar), 5, dtype=np.int64)
    history = np.ones((len(calendar), 3), dtype=np.float32)
    future = np.full_like(history, np.nan)
    future[decisions[-1], 0] = 0.01
    exposure = np.ones((len(decisions), 3, 14), dtype=np.uint8)
    rows, labelled = build_inference_rows(
        calendar=calendar,
        epsilon_history=history,
        epsilon_future=future,
        decision_positions=decisions,
        exposure_available=exposure,
    )
    assert len(rows) == len(decisions) * 3
    assert len(labelled) == 1
    assert set(rows[:, 3]) == {0, 1, 2, 3}


def test_feature_registry_has_exact_71_channels_and_no_forbidden_role() -> None:
    registry = feature_registry([f"factor_{index}" for index in range(14)])
    assert registry["feature_dim"] == FEATURE_DIM
    assert len(cast(list[object], registry["channels"])) == FEATURE_DIM
    assert registry["price_volume_channels"] == []
    assert registry["LAT_channels"] == []
    assert registry["oracle_or_target_channels"] == []


def test_parameter_instantiation_has_exact_22_explicit_values() -> None:
    compatibility = {
        "capacity_root_candidates": [{"latent_dimension": 8, "hidden_dimension": 8}],
        "canonical_digest": "sha256:compatibility",
    }
    lr = {
        "status": "passed",
        "selected_learning_rates": {"d8_h8": 0.01},
        "canonical_digest": "sha256:lr",
    }
    backend = {
        "selected_backend": "cpu",
        "canonical_digest": "sha256:backend",
    }
    result = parameter_instantiation(
        compatibility=compatibility,
        lr_receipt=lr,
        backend_receipt=backend,
        governance_receipts={
            "workflow_gate_digest": "sha256:workflow",
            "financial_alignment_gate_digest": "sha256:financial",
            "root_scope_gate_digest": "sha256:root",
        },
    )
    assert result["parameter_count"] == 22
    assert len(cast(dict[str, object], result["parameter_values"])) == 22
    assert result["user_math_inputs_required"] == []
    assert result["formal_training_allowed"] is False


def test_contract_gate_rejects_training_or_non_r0() -> None:
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_intraday_K1_preflight@1.0",
        "decision_clocks": ["14:30", "14:45"],
        "operator_count": 1,
        "residual_identity": "r0_exact_zero",
        "formal_training_allowed": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    assert validate_contract(payload) == []
    payload["formal_training_allowed"] = True
    body = {key: value for key, value in payload.items() if key != "canonical_digest"}
    payload["canonical_digest"] = canonical_digest(body)
    assert "K1_preflight_formal_training_must_be_closed" in validate_contract(payload)


def test_compatibility_schema_binds_capacity_and_post_training_obligations() -> None:
    required = set(COMPATIBILITY_REQUIRED_FIELDS)
    assert {
        "q_x",
        "q_s",
        "capacity_support",
        "post_training_operator_obligations",
    } <= required


def test_backend_selection_requires_stable_ten_percent_speed_margin() -> None:
    assert select_backend(parity_passed=True, cpu_seconds=1.0, rocm_seconds=0.95)[0] == "cpu"
    assert select_backend(parity_passed=True, cpu_seconds=1.0, rocm_seconds=0.8)[0] == "rocm"
    assert select_backend(parity_passed=False, cpu_seconds=1.0, rocm_seconds=0.5)[0] == "cpu"
