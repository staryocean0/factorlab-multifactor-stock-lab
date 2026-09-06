from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from factor_lab.factor_rotation.reaka_r3_time_isolation import (
    ARTIFACT_ROLES, PAIR_FIELDS, artifact_inventory, compare_pair_identity,
    fit_history_mask, selection_mask, strict_json, validate_plan,
    verify_artifact_inventory,
)

ROOT = Path(__file__).resolve().parents[2]
FREEZE = "2016-12-31T23:59:59+08:00"
START = "2009-01-01T00:00:00+08:00"


def test_decision_year_alone_cannot_admit_next_year_outcome():
    decisions = ["2016-12-15T14:30:00+08:00"] * 3
    result = selection_mask(decisions,
        ["2016-12-30T14:31:00+08:00", "2017-01-16T14:31:00+08:00", None],
        decisions, freeze_at=FREEZE, start_at=START)
    assert result == [True, False, False]


def test_timezone_offsets_compare_instants_not_wall_clock_strings():
    assert selection_mask(["2016-12-31T07:00:00Z"],
        ["2016-12-31T16:00:00Z"], ["2016-12-31T06:30:00Z"],
        freeze_at=FREEZE, start_at=START) == [False]


@pytest.mark.parametrize("stamp", ["2016-12-30", "2016-12-30T14:30:00", "not-a-time"])
def test_missing_time_semantics_not_accepted(stamp):
    with pytest.raises(ValueError):
        selection_mask([stamp], [stamp], [stamp], freeze_at=FREEZE, start_at=START)


def test_future_signal_input_and_unknown_availability_excluded():
    d = "2016-01-02T14:30:00+08:00"
    assert selection_mask([d, d], [d, d], ["2016-01-02T14:31:00+08:00", None],
        freeze_at=FREEZE, start_at=START) == [False, False]


def test_maturity_before_decision_is_not_usable():
    assert selection_mask(["2016-01-02T14:30:00+08:00"],
        ["2016-01-01T14:30:00+08:00"], ["2016-01-01T14:30:00+08:00"],
        freeze_at=FREEZE, start_at=START) == [False]


def test_fit_eligibility_does_not_read_future_labels():
    import inspect
    assert "maturities" not in inspect.signature(fit_history_mask).parameters
    dates = ["2016-12-30T14:30:00+08:00", "2017-01-03T14:30:00+08:00"]
    assert fit_history_mask(dates, dates, fit_start_at=START, freeze_at=FREEZE) == [True, False]


def test_changing_excluded_future_outcomes_cannot_change_prefix_selection_input():
    dates = ["2016-01-02T14:30:00+08:00", "2018-01-02T14:30:00+08:00"]
    mask = selection_mask(dates, dates, dates, freeze_at=FREEZE, start_at=START)
    for future in (-1e99, 0.0, 1e99):
        admitted = [y for y, keep in zip([1.0, future], mask) if keep]
        assert admitted == [1.0]
    # This proves only metadata slicing, not the unimplemented real selector.


def test_empty_and_misaligned_rows_not_fake_observations():
    assert selection_mask([], [], [], freeze_at=FREEZE, start_at=START) == []
    with pytest.raises(ValueError):
        selection_mask([FREEZE], [], [], freeze_at=FREEZE, start_at=START)


def plan():
    return json.loads((ROOT / "docs/ops/r3_time_isolated_evaluation_plan_20260906.json").read_text())


def test_actual_plan_is_design_only():
    result = validate_plan(plan())
    assert result["design_consistency"] == "passed", result
    assert result["data_readiness"] == "not_evaluated"
    assert result["runner_integration_verified"] is False
    assert result["market_experiment_executed"] is False


@pytest.mark.parametrize("key", ["real_fit_executed", "local_task_dispatched", "fresh_oos", "read_2026", "production_authority"])
def test_plan_cannot_promote_itself_by_flags(key):
    p = plan(); p[key] = True
    assert validate_plan(p)["errors"]
    p[key] = 0
    assert validate_plan(p)["errors"]


@pytest.mark.parametrize("field,value", [("evaluation_start", "2016-01-01"),
    ("evaluation_start", "2017-01-01"), ("evaluation_end", "2025-12-31"),
    ("label_policy", "decision_year_only"), ("post_freeze_model_update", True)])
def test_design_period_and_label_policy_counterexamples(field, value):
    p = plan(); p["time"][field] = value
    assert validate_plan(p)["errors"]


def test_unmatched_environment_old_f_reuse_and_extra_fit_budget_are_detected():
    for key, value in (("shared_backend", False), ("reuse_old_scores_as_primary", True)):
        p = plan(); p[key] = value
        assert validate_plan(p)["errors"]
    p = plan(); p["future_budget"]["max_new_fits"] = 24
    assert validate_plan(p)["errors"]


def pair():
    x = {k: "sha256:" + "a" * 64 for k in PAIR_FIELDS}
    x.update(seed=11, clock="1430")
    return {**x, "arm": "F"}, {**x, "arm": "H"}


def test_pair_allows_different_trained_states_but_same_pre_dmd_state():
    a, b = pair()
    a["trained_state"] = "F-weights"; b["trained_state"] = "H-weights"
    assert compare_pair_identity(a, b) == []
    b["pre_dmd_state_digest"] = "sha256:" + "b" * 64
    assert compare_pair_identity(a, b)


@pytest.mark.parametrize("key", ["environment_digest", "normalizer_digest", "source_digest", "selection_digest", "prediction_rows_digest"])
def test_same_recipe_name_cannot_override_actual_pair_identity(key):
    a, b = pair(); b[key] = "sha256:" + "b" * 64
    assert compare_pair_identity(a, b)


def test_missing_and_malformed_equal_digests_fail():
    a, b = pair(); a["source_digest"] = b["source_digest"] = "same-local-version"
    assert compare_pair_identity(a, b)
    a, b = pair(); a["seed"] = b["seed"] = True
    assert compare_pair_identity(a, b)


@pytest.fixture
def saved(tmp_path):
    files = {}
    for role in ARTIFACT_ROLES - {"checkpoint"}:
        files[role] = role + ".json"
        (tmp_path / files[role]).write_text('{"synthetic":true}')
    files["checkpoint"] = "checkpoint"
    (tmp_path / "checkpoint").mkdir()
    (tmp_path / "checkpoint/tensor_000.bin").write_bytes(b"synthetic-weight-bytes")
    (tmp_path / "checkpoint/manifest.json").write_text('{"tensor_count":1}')
    return tmp_path, files


def test_inventory_checks_bytes_not_pit_or_actual_model_reload(saved):
    root, files = saved
    inventory = artifact_inventory(root, files)
    assert verify_artifact_inventory(root, inventory) == []
    assert inventory["reload_verified"] is False
    assert inventory["scientific_acceptance"] is False
    assert len(inventory["files"]) == 8


def test_changed_weight_with_unchanged_manifest_fails(saved):
    root, files = saved; inventory = artifact_inventory(root, files)
    (root / "checkpoint/tensor_000.bin").write_bytes(b"different-weights")
    assert verify_artifact_inventory(root, inventory)


def test_missing_checkpoint_cannot_be_replaced_by_score_files(saved):
    root, files = saved; files.pop("checkpoint")
    with pytest.raises(ValueError):
        artifact_inventory(root, files)


def test_added_tensor_not_silently_ignored(saved):
    root, files = saved; inventory = artifact_inventory(root, files)
    (root / "checkpoint/extra.bin").write_bytes(b"extra")
    assert verify_artifact_inventory(root, inventory)


def test_self_reported_digest_is_not_accepted_without_body_hash(saved):
    root, files = saved; inventory = artifact_inventory(root, files)
    source = root / files["normalizer"]
    source.write_text('{"canonical_digest":"old","mean":999}')
    assert verify_artifact_inventory(root, inventory)


@pytest.mark.parametrize("relative", ["../outside", "/etc/passwd", "C:\\model", "."])
def test_artifact_escape_refused(saved, relative):
    root, files = saved; files["checkpoint"] = relative
    with pytest.raises(ValueError):
        artifact_inventory(root, files)


def test_artifact_symlinks_refused(saved):
    root, files = saved
    (root / "checkpoint/link").symlink_to(root / files["scores"])
    with pytest.raises(ValueError):
        artifact_inventory(root, files)


@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"a":NaN}', '[]'])
def test_strict_json_rejects_ambiguous_records(text):
    with pytest.raises(ValueError):
        strict_json(text)


def test_cli_checks_only_plan_without_factorlab_or_torch():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/check_reaka_r3_time_isolated_plan.py")],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body["market_experiment_executed"] is False
