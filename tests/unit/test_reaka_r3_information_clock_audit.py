from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/reaka_r3_information_clock_audit.py"
spec = importlib.util.spec_from_file_location("infoclock", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture_arrays():
    n, symbols = 2400, 5
    calendar = np.arange(np.datetime64("2015-01-01"), np.datetime64("2015-01-01") + n)
    days = [200, 220, 1150, 1170, 2250]
    rows = np.array([[d, s, int(str(calendar[d])[:4]), i % 4]
                     for i, d in enumerate(days) for s in range(symbols)], dtype=np.int64)
    return {"calendar.npy": calendar, "inference_rows.npy": rows,
            "state_values.npy": np.zeros((6, n, 14), np.float32),
            "state_available.npy": np.ones((6, n, 14), np.uint8),
            "exposure_decision_positions.npy": np.arange(n, dtype=np.int64),
            "exposure_reliability.npy": np.full((n, symbols, 14), 0.5, np.float32),
            "exposure_available.npy": np.ones((n, symbols, 14), np.uint8)}


def save_fixture(root, arrays):
    root.mkdir(parents=True)
    for key, value in arrays.items():
        np.save(root / key, value, allow_pickle=False)


def time_row():
    return dict(feature="state_mask", decision_at="2018-01-03T14:30:00+08:00",
                dependency_max_at="2018-01-02T15:00:00+08:00",
                available_at="2018-01-03T08:00:00+08:00", source_ref="commit/path:lines")


def test_h20_offsets_not_ten_days():
    assert m.OFFSETS.tolist() == list(range(-180, 1, 20))


def test_constant_mask_is_reported_not_called_a_signal():
    result = m.profile_arrays(fixture_arrays())
    p = result["periods"]["consumed_discovery"]
    assert p["state_mask"]["all_factor_channels_constant"]
    assert p["state_mask"]["constant_factor_positions"] == list(range(14))
    assert p["crossfold_differing_checks"] == 0
    assert p["within_same_fold_stock_variation_possible_by_schema"] is False


def test_dynamic_fold_patterns_are_separate_from_constant_channels():
    a = fixture_arrays(); a["state_available.npy"][1, :, 0] = 0
    p = m.profile_arrays(a)["periods"]["consumed_discovery"]
    assert p["state_mask"]["constant_factor_positions"] == list(range(1, 14))
    assert p["crossfold_differing_checks"] == 20


def test_full_reference_variant_zero_is_not_consumed():
    a = fixture_arrays(); a["state_available.npy"][0] = 7
    assert m.profile_arrays(a)["periods"]["consumed_discovery"]["state_mask"]["all_factor_channels_constant"]


def test_reliability_is_masked_exactly_like_original_store():
    a = fixture_arrays(); a["exposure_available.npy"][:, :, 3] = 0
    p = m.profile_arrays(a)["periods"]["consumed_discovery"]
    assert p["masked_reliability"]["mean"][3] == 0
    assert p["masked_reliability"]["mean"][0] == 0.5


def test_chunking_does_not_change_profile():
    a = fixture_arrays()
    assert m.profile_arrays(a, batch_size=2) == m.profile_arrays(a, batch_size=100)


def test_2017_is_context_only_not_a_reported_period():
    a = fixture_arrays(); a["inference_rows.npy"] = np.array([[800, 0, 2017, 0]])
    r = m.profile_arrays(a)
    assert all(p["inference_rows"] == 0 for p in r["periods"].values())


def test_empty_extension_is_not_imputed_or_certified():
    a = fixture_arrays(); a["inference_rows.npy"] = a["inference_rows.npy"][:20]
    r = m.profile_arrays(a)
    assert not r["extension_rows_present"]
    assert r["periods"]["consumed_extension"]["state_mask"]["status"] == "no_support"


@pytest.mark.parametrize("kind", ["year", "phase", "negative_symbol", "endpoint", "duplicate",
                                 "calendar_order", "nonbinary", "nan_reliability", "nan_state",
                                 "exposure_duplicate", "nonexact_exposure"])
def test_invalid_inputs_fail_without_silent_filter(kind):
    a = fixture_arrays()
    if kind == "year": a["inference_rows.npy"][0, 2] = 2017
    elif kind == "phase": a["inference_rows.npy"][0, 3] = 5
    elif kind == "negative_symbol": a["inference_rows.npy"][0, 1] = -1
    elif kind == "endpoint": a["inference_rows.npy"][0, 0] = 100
    elif kind == "duplicate": a["inference_rows.npy"][1] = a["inference_rows.npy"][0]
    elif kind == "calendar_order": a["calendar.npy"][1] = a["calendar.npy"][0]
    elif kind == "nonbinary": a["state_available.npy"][1, :, 0] = 2
    elif kind == "nan_reliability": a["exposure_reliability.npy"][:, :, 0] = np.nan
    elif kind == "nan_state": a["state_values.npy"][1, :, 0] = np.nan
    elif kind == "exposure_duplicate": a["exposure_decision_positions.npy"][1] = 0
    elif kind == "nonexact_exposure":
        a["exposure_decision_positions.npy"] = a["exposure_decision_positions.npy"][1:]
        a["exposure_reliability.npy"] = a["exposure_reliability.npy"][1:]
        a["exposure_available.npy"] = a["exposure_available.npy"][1:]
        a["inference_rows.npy"][0, 0] = 180
    with pytest.raises(ValueError): m.profile_arrays(a)


def test_2026_store_is_rejected():
    a = fixture_arrays(); a["calendar.npy"][-1] = np.datetime64("2026-01-01")
    with pytest.raises(ValueError, match="withheld"): m.profile_arrays(a)


def test_timestamp_requires_source_and_explicit_zone():
    r = time_row(); del r["source_ref"]
    assert m.audit_time_rows([r])["status"] == "unknown"
    r = time_row(); r["available_at"] = "2018-01-03T08:00:00"
    assert m.audit_time_rows([r])["status"] == "violations_found"


def test_empty_time_evidence_not_a_pass():
    assert m.audit_time_rows([])["status"] == "unknown"


@pytest.mark.parametrize("field,value", [
    ("available_at", "2026-05-04T00:00:00+08:00"),
    ("dependency_max_at", "2018-01-04T15:00:00+08:00"),
    ("available_at", "2017-12-01T00:00:00+08:00")])
def test_future_lake_ingestion_and_impossible_order_rejected(field, value):
    r = time_row(); r[field] = value
    assert m.audit_time_rows([r])["status"] == "violations_found"


def test_timezone_equivalence_and_no_pit_claim():
    r = time_row(); r["decision_at"] = "2018-01-03T06:30:00Z"
    out = m.audit_time_rows([r])
    assert out["status"] == "supplied_rows_order_consistent_not_PIT_certified"
    assert out["PIT_certified"] is False


def test_prefix_comparison_uses_bilateral_support():
    a = np.array([1., 2., np.nan]); ma = np.array([1, 1, 0])
    assert m.compare_prefix(a, a, ma, ma)["passed"]
    mb = np.array([1, 0, 0])
    assert not m.compare_prefix(a, a, ma, mb)["passed"]


def test_empty_or_all_unavailable_prefix_not_a_pass():
    with pytest.raises(ValueError): m.compare_prefix(np.array([]), np.array([]), np.array([]), np.array([]))
    assert not m.compare_prefix(np.zeros(2), np.zeros(2), np.zeros(2), np.zeros(2))["passed"]


def test_prefix_invalid_active_nan_and_difference_fail():
    assert not m.compare_prefix(np.array([np.nan]), np.array([1.]), np.ones(1), np.ones(1))["passed"]
    assert not m.compare_prefix(np.array([2.]), np.array([1.]), np.ones(1), np.ones(1))["passed"]


def test_original_store_remains_unchanged_and_no_target_needed(tmp_path):
    root = tmp_path / "store"; save_fixture(root, fixture_arrays())
    hashes = {n: m.sha_file(root / n) for n in m.FILES}
    out = m.audit_store(root, hashes)
    assert out["unbound_to_historical_receipt"] == []
    assert hashes == {n: m.sha_file(root / n) for n in m.FILES}
    assert not (root / "epsilon_future.npy").exists()


def test_wrong_binding_rejected(tmp_path):
    root = tmp_path / "store"; save_fixture(root, fixture_arrays())
    with pytest.raises(ValueError, match="digest mismatch"):
        m.audit_store(root, {"calendar.npy": "sha256:wrong"})


def test_duplicate_json_keys_rejected(tmp_path):
    p = tmp_path / "x.json"; p.write_text('{"x":1,"x":2}')
    with pytest.raises(ValueError, match="duplicate"): m.read_json(p)


def test_output_no_overwrite_or_input_overlap(tmp_path):
    spec = {"schema_id": "factorlab.r3_information_clock_audit@1.0",
            "stores": {c: {"root": str(tmp_path / c)} for c in ("1430", "1445")},
            "output_root": str(tmp_path / "1430" / "out")}
    with pytest.raises(ValueError, match="overlap"): m.run(spec)
    spec["output_root"] = str(tmp_path / "already"); Path(spec["output_root"]).mkdir()
    with pytest.raises(FileExistsError): m.run(spec)


def test_cli_target_free_end_to_end_in_fresh_process(tmp_path):
    for c in ("1430", "1445"): save_fixture(tmp_path / c, fixture_arrays())
    spec = {"schema_id": "factorlab.r3_information_clock_audit@1.0",
            "stores": {c: {"root": str(tmp_path / c)} for c in ("1430", "1445")},
            "output_root": str(tmp_path / "out")}
    p = tmp_path / "spec.json"; p.write_text(json.dumps(spec))
    proc = subprocess.run([sys.executable, str(SCRIPT), "--spec", str(p)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    result = json.loads((tmp_path / "out/audit.json").read_text())
    assert result["new_fits"] == result["new_inference"] == result["future_labels_read"] == 0
    assert result["time_evidence"]["status"] == "unknown"
    assert result["PIT_certified"] is False


def test_constant_feature_can_change_ranking_without_new_information():
    # Same fixed nonlinear toy function; no fit, financial data or causal claim.
    returns = np.array([-2., -0.5, 1.])
    no_feature = returns ** 2
    constant_feature = (returns + np.ones(3)) ** 2
    assert not np.array_equal(np.argsort(no_feature), np.argsort(constant_feature))
    assert np.std(np.ones(3)) == 0
