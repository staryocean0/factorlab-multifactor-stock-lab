from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src/factor_lab/factor_rotation/reaka_r3_transfer_inputs.py"
spec = importlib.util.spec_from_file_location("transfer_under_test", SOURCE)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rehash_bundle(case):
    p = case["src"] / "bundle.json"
    body = json.loads(p.read_text())
    body["artifact_digests"] = {n: m.sha_file(case["src"] / n) for n in m.BUNDLE_FILES}
    dump(p, body)
    case["spec"]["bundle_manifest_sha256"] = m.sha_file(p)


def array_change(case, name, function):
    p = case["src"] / name
    a = np.load(p, allow_pickle=False)
    b = function(a)
    np.save(p, a if b is None else b, allow_pickle=False)
    rehash_bundle(case)


def bundle_change(case, key, value):
    p = case["src"] / "bundle.json"
    body = json.loads(p.read_text()); body[key] = value
    dump(p, body); case["spec"]["bundle_manifest_sha256"] = m.sha_file(p)


def make_case(tmp, clock="1430", shuffled=False):
    root = tmp / clock; ref = root / "reference"; src = root / "bundle"; artifact = root / "frozen"
    for p in (ref, src, artifact): p.mkdir(parents=True)
    dates = np.arange(np.datetime64("2008-12-01"), np.datetime64("2026-01-01"))
    dates = dates[np.is_busday(dates)]  # Synthetic weekdays, NOT a Chinese exchange calendar.
    old_len = int(np.searchsorted(dates, np.datetime64("2021-01-01")))
    t, s = len(dates), 5
    dec = np.arange(0, t, 5, dtype=np.int64); old_dec = dec[dec < old_len]
    symbols = np.array([f"S{i}" for i in range(s)])
    factors = [f"f{i}" for i in range(14)]; variants = list(m.VARIANTS)
    arrays = {"calendar.npy": dates.astype("datetime64[ns]"), "symbols.npy": symbols,
              "exposure_decision_positions.npy": dec,
              "epsilon_history.npy": (np.arange(t)[:, None] * .00001 + np.arange(s)[None, :] * .001).astype(np.float32),
              "state_values.npy": np.broadcast_to(np.arange(14, dtype=np.float32)[None, None, :] / 14, (6, t, 14)).copy(),
              "state_available.npy": np.ones((6, t, 14), dtype=np.uint8),
              "stock_factor_exposures.npy": np.full((len(dec), s, 14), 0.25, np.float32),
              "exposure_reliability.npy": np.full((len(dec), s, 14), 0.4, np.float32),
              "exposure_available.npy": np.ones((len(dec), s, 14), np.uint8)}
    # A real sparse channel, plus state warmup: neither may be silently overwritten.
    arrays["exposure_available.npy"][:, 0, 13] = 0
    for n in ("stock_factor_exposures.npy", "exposure_reliability.npy"):
        arrays[n][:, 0, 13] = 0
    arrays["state_available.npy"][:, :10] = 0; arrays["state_values.npy"][:, :10] = 0
    old_rows = np.array([[d, i, 2020, (d // 5) % 4] for d in old_dec[-2:] for i in range(s)], dtype=np.int64)
    for n, a in arrays.items():
        if n in ("calendar.npy", "epsilon_history.npy"):
            old = a[:old_len]
        elif n.startswith("state_"):
            old = a[:, :old_len]
        elif n.startswith("exposure_") or n.startswith("stock_factor_"):
            old = a[:len(old_dec)]
        else:
            old = a
        np.save(ref / n, old, allow_pickle=False)
    np.save(ref / "inference_rows.npy", old_rows, allow_pickle=False)
    dump(ref / "factor_ids.json", {"factor_ids": factors})
    dump(ref / "variant_ids.json", {"variant_ids": variants})
    dump(ref / "feature_registry.json", {"feature_dim": 71, "channels": [{"position": i} for i in range(71)]})
    dump(ref / "manifest.json", {"decision_clock": clock[:2] + ":" + clock[2:],
                                "artifact_digests": {n: m.sha_file(ref / n) for n in m.REFERENCE_FILES}})
    sp = np.arange(s)[::-1] if shuffled else np.arange(s)
    fp = np.arange(14)[::-1] if shuffled else np.arange(14)
    vp = np.roll(np.arange(6), 2) if shuffled else np.arange(6)
    for n, a in arrays.items():
        if n == "symbols.npy": a = a[sp]
        elif n == "epsilon_history.npy": a = a[:, sp]
        elif n.startswith("state_"): a = a[vp][:, :, fp]
        elif n in ("stock_factor_exposures.npy", "exposure_reliability.npy", "exposure_available.npy"):
            a = a[:, sp][:, :, fp]
        np.save(src / n, a, allow_pickle=False)
    np.save(src / "symbol_fold_ids.npy", sp % 5, allow_pickle=False)
    dump(src / "factor_ids.json", {"factor_ids": [factors[i] for i in fp]})
    dump(src / "variant_ids.json", {"variant_ids": [variants[i] for i in vp]})
    producer = root / "untracked_producer.py"; producer.write_text("def producer():\n    return 1\n")
    module = ModuleType("synthetic_loaded_producer"); module.__file__ = str(producer)
    m.snapshot_loaded_sources({"producer_bridge": module}, src / "producer_sources.json")
    selection = artifact / "selected_tools.json"
    dump(selection, [{"family": "synthetic", "tool": "frozen_synthetic_tool_not_a_market_algorithm"}])
    norm = artifact / "normalizer.json"
    dump(norm, {"fit_end_year": 2016, "target_used": False, "return_mean": 0.1, "return_scale": 0.3,
                "beta_mean": 0.2, "beta_scale": 0.4, "reliability_mean": 0.3, "reliability_scale": 0.1})
    bm = {"schema_id": m.BUNDLE_SCHEMA, "clock": clock, "calendar_end": "2025-12-31",
          "reference_manifest_sha256": m.sha_file(ref / "manifest.json"), "frozen_selection_sha256": m.sha_file(selection),
          "frozen_normalizer_sha256": m.sha_file(norm), "selection_freeze_end": "2016-12-31",
          "carrier_universe_policy": "incumbent_cohort_before_crossfit", "fold_policy": "explicit_incumbent_symbol_position_mod5",
          "historical_prefix_origin": "reused_accepted_arrays",
          "new_model_fits": 0, "selection_refit": False, "normalizer_refit": False, "labels_used_for_features": False,
          "artifact_digests": {n: m.sha_file(src / n) for n in m.BUNDLE_FILES}}
    dump(src / "bundle.json", bm)
    spec = {"reference_store": str(ref), "source_bundle": str(src), "frozen_selection": str(selection),
            "frozen_normalizer": str(norm), "reference_manifest_sha256": m.sha_file(ref / "manifest.json"),
            "bundle_manifest_sha256": m.sha_file(src / "bundle.json"), "selection_sha256": m.sha_file(selection),
            "normalizer_sha256": m.sha_file(norm)}
    return {"ref": ref, "src": src, "spec": spec, "original": arrays, "old_len": old_len, "producer": producer,
            "output": tmp / f"prepared_{clock}", "clock": clock}


@pytest.fixture
def case(tmp_path):
    return make_case(tmp_path)


def build(case):
    return m.prepare_clock(case["spec"], case["clock"], case["output"])


def test_shuffled_storage_maps_to_original_positions_and_exact_prefix(tmp_path):
    c = make_case(tmp_path, shuffled=True); result = build(c)
    assert result["symbol_count"] == 5
    for n in (*m.DATA_ARRAYS, "symbols"):
        assert np.array_equal(np.load(c["output"] / (n + ".npy")), c["original"][n + ".npy"], equal_nan=(n != "symbols"))
    assert all(x["passed"] for x in result["prefix_checks"].values())
    assert np.array_equal(np.load(c["output"] / "inference_rows.npy")[:10], np.load(c["ref"] / "inference_rows.npy"))


def test_scalar_assembly_and_normalization_agree_all_71_channels(case):
    build(case); store = m.TransferFeatureStore(case["output"])
    pred = np.load(case["output"] / "prediction_indices.npy")
    idx = pred[[0, 1, 4, 9, -1]]
    h, x = store.assemble_inputs(idx)
    eh, ex = np.empty_like(h), np.zeros_like(x)
    dec = {int(v): i for i, v in enumerate(store.exposure_decision_positions)}
    for b, row in enumerate(store.inference_rows[idx]):
        day, symbol = int(row[0]), int(row[1]); fold = symbol % 5 + 1
        for j, offset in enumerate(range(-180, 1, 20)):
            d = day + offset; ei = dec[d]; eh[b, j] = store.epsilon_history[d, symbol]
            for f in range(14):
                em = store.exposure_available[ei, symbol, f]
                ex[b, j, f] = store.state_values[fold, d, f]
                ex[b, j, f + 14] = store.state_available[fold, d, f]
                ex[b, j, f + 28] = store.stock_factor_exposures[ei, symbol, f] * em
                ex[b, j, f + 42] = store.exposure_reliability[ei, symbol, f] * em
                ex[b, j, f + 56] = em
    assert np.array_equal(h, eh); assert np.array_equal(x, ex)
    nh, nx = store.normalized_inputs(idx); norm = store.normalizer
    eh = ((eh - norm["return_mean"]) / norm["return_scale"]).astype(np.float32)
    for lo, hi, k in ((28, 42, "beta"), (42, 56, "reliability")):
        ex[:, :, lo:hi] = ((ex[:, :, lo:hi] - norm[k + "_mean"]) / norm[k + "_scale"]) * ex[:, :, 56:70]
    assert np.array_equal(nh, eh); assert np.array_equal(nx, ex)
    with pytest.raises(RuntimeError, match="target access"): store.assemble_batch(idx)
    assert not hasattr(store, "epsilon_future")


def test_original_files_are_unchanged_and_label_files_are_not_opened(case, monkeypatch):
    original = {p: m.sha_file(p) for p in case["ref"].iterdir()}
    for p in (case["ref"], case["src"]):
        (p / "epsilon_future.npy").write_bytes(b"this is not an npy; opening it must fail")
    real_load = m.np.load
    def guarded(path, *args, **kwargs):
        assert "epsilon_future" not in str(path) and "labelled" not in str(path)
        return real_load(path, *args, **kwargs)
    monkeypatch.setattr(m.np, "load", guarded)
    result = build(case)
    assert not result["labels_read"]
    assert all(m.sha_file(p) == h for p, h in original.items())


def test_maturity_uses_twenty_calendar_positions_not_label_values(case):
    build(case)
    rows = np.load(case["output"] / "inference_rows.npy")
    pred = np.load(case["output"] / "prediction_indices.npy")
    mat = np.load(case["output"] / "maturity_eligible_indices.npy")
    n = len(case["original"]["calendar.npy"])
    assert np.array_equal(mat, pred[rows[pred, 0] + 20 < n])
    assert len(mat) < len(pred)
    assert set(rows[pred, 2]) == {2021, 2022, 2023, 2024, 2025}


def test_missing_history_drops_only_declared_support_without_label_filter(case):
    old = case["old_len"]
    array_change(case, "epsilon_history.npy", lambda a: a.__setitem__((slice(old, None), 0), np.nan))
    result = build(case)
    support = json.loads((case["output"] / "daily_support.json").read_text())
    assert all(s["history_missing"] == 1 for s in support)
    assert all(s["included"] == 4 for s in support)
    assert result["rows"]["labels_used_for_support"] is False


def test_dynamic_tail_mask_is_preserved_not_forced_to_one(case):
    old = case["old_len"]
    array_change(case, "state_available.npy", lambda a: a.__setitem__((slice(None), slice(old, None), 2), 0))
    array_change(case, "state_values.npy", lambda a: a.__setitem__((slice(None), slice(old, None), 2), 0))
    build(case)
    assert (np.load(case["output"] / "state_available.npy")[:, old:, 2] == 0).all()


@pytest.mark.parametrize("name", m.DATA_ARRAYS)
def test_changed_historical_prefix_rejected_in_each_feature(case, name):
    def alter(a):
        if name.startswith("state_"): a[1, 100, 1] = 0 if name in m.MASK_ARRAYS else 5
        elif a.ndim == 2: a[100, 0] = 7
        else: a[100, 1, 1] = 0 if name in m.MASK_ARRAYS else 0.9
    array_change(case, name + ".npy", alter)
    with pytest.raises(ValueError, match="historical prefix changed"): build(case)


def test_nan_support_change_in_history_prefix_is_not_hidden(case):
    array_change(case, "epsilon_history.npy", lambda a: a.__setitem__((100, 0), np.nan))
    with pytest.raises(ValueError, match="historical prefix changed"): build(case)


def test_shuffled_storage_with_recomputed_position_modulo_fold_is_rejected(tmp_path):
    c = make_case(tmp_path, shuffled=True)
    array_change(c, "symbol_fold_ids.npy", lambda a: np.arange(len(a)) % 5)
    with pytest.raises(ValueError, match="fold identity"): build(c)


@pytest.mark.parametrize("bad", ["duplicate", "replacement", "extra", "missing"])
def test_symbol_cohort_not_silently_changed(case, bad):
    def alter(a):
        if bad == "duplicate": a[0] = a[1]; return a
        if bad == "replacement": a[0] = "XX"; return a
        if bad == "extra": return np.append(a, "NEW")
        return a[:-1]
    array_change(case, "symbols.npy", alter)
    with pytest.raises(ValueError, match="duplicate|universe differs"): build(case)


@pytest.mark.parametrize("kind", ["calendar_prefix", "calendar_duplicate", "D5_missing", "D5_shift", "float_dtype",
                                  "nonbinary", "infinite_history", "nan_state", "bad_reliability", "nonzero_unavailable"])
def test_invalid_bundle_arrays_fail(case, kind):
    old = case["old_len"]
    if kind == "calendar_prefix": array_change(case, "calendar.npy", lambda a: a.__setitem__(100, a[100] + np.timedelta64(1, "D")))
    elif kind == "calendar_duplicate": array_change(case, "calendar.npy", lambda a: a.__setitem__(100, a[99]))
    elif kind == "D5_missing": array_change(case, "exposure_decision_positions.npy", lambda a: a[:-1])
    elif kind == "D5_shift": array_change(case, "exposure_decision_positions.npy", lambda a: a + 1)
    elif kind == "float_dtype": array_change(case, "state_values.npy", lambda a: a.astype(np.float64))
    elif kind == "nonbinary": array_change(case, "state_available.npy", lambda a: a.__setitem__((0, old, 0), 2))
    elif kind == "infinite_history": array_change(case, "epsilon_history.npy", lambda a: a.__setitem__((old, 0), np.inf))
    elif kind == "nan_state": array_change(case, "state_values.npy", lambda a: a.__setitem__((0, old, 0), np.nan))
    elif kind == "bad_reliability": array_change(case, "exposure_reliability.npy", lambda a: a.__setitem__((-1, 0, 0), 1.2))
    elif kind == "nonzero_unavailable": array_change(case, "exposure_reliability.npy", lambda a: a.__setitem__((-1, 0, 13), 0.4))
    with pytest.raises(ValueError): build(case)


@pytest.mark.parametrize("key,value", [("new_model_fits", 1), ("new_model_fits", False), ("labels_used_for_features", True),
                                      ("selection_refit", True), ("normalizer_refit", True),
                                      ("carrier_universe_policy", "all_stocks_then_slice"),
                                      ("selection_freeze_end", "2020-12-31")])
def test_declared_numeric_recipe_change_rejected(case, key, value):
    bundle_change(case, key, value)
    with pytest.raises(ValueError, match="recipe declaration"): build(case)


def test_declared_2026_bundle_rejected_before_array_payload_load(case, monkeypatch):
    bundle_change(case, "calendar_end", "2026-12-31")
    def forbidden(*a, **kw): raise AssertionError("arrays must not be opened")
    monkeypatch.setattr(m.np, "load", forbidden)
    with pytest.raises(ValueError, match="2025 bundle"): build(case)


def test_undeclared_2026_calendar_rejected_before_feature_hash(case, monkeypatch):
    array_change(case, "calendar.npy", lambda a: np.append(a, np.datetime64("2026-01-02", "ns")))
    real = m.sha_file
    def guarded(path):
        assert not (path.parent == case["src"] and path.name == "state_values.npy")
        return real(path)
    monkeypatch.setattr(m, "sha_file", guarded)
    with pytest.raises(ValueError, match="calendar prefix or 2025"): build(case)


@pytest.mark.parametrize("part", ["normalizer", "selection", "reference_manifest", "bundle_manifest"])
def test_external_bindings_required_and_not_just_self_embedded(case, part):
    case["spec"][part + "_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="SHA256 mismatch"): build(case)


def test_edited_actual_producer_file_fails_even_without_git_head_change(case):
    case["producer"].write_text("def producer(): return 2\n")
    with pytest.raises(ValueError, match="SHA256 mismatch"): build(case)


def test_snapshot_records_loaded_untracked_file_not_a_historical_commit(tmp_path):
    path = tmp_path / "untracked.py"; path.write_text("value=3\n")
    mod = ModuleType("test_loaded"); mod.__file__ = str(path)
    out = tmp_path / "sources.json"
    body = m.snapshot_loaded_sources({"bridge": mod}, out)
    assert body["binding"] == "current_loaded_source_files_not_historical_HEAD"
    assert m.verify_sources(out)["historical_source_identity_certified"] is False
    with pytest.raises(FileExistsError): m.snapshot_loaded_sources({"bridge": mod}, out)


def test_empty_loaded_module_snapshot_rejected(tmp_path):
    with pytest.raises(ValueError): m.snapshot_loaded_sources({}, tmp_path / "s.json")
    with pytest.raises(ValueError): m.snapshot_loaded_sources({"bad": ModuleType("nofile")}, tmp_path / "s.json")


def test_duplicate_json_and_symlink_escape_rejected(tmp_path):
    p = tmp_path / "bad.json"; p.write_text('{"x": 1, "x": 2}')
    with pytest.raises(ValueError, match="duplicate"): m.read_json(p)
    folder = tmp_path / "bundle"; folder.mkdir(); (folder / "x.json").symlink_to(p)
    with pytest.raises(ValueError, match="escaping"): m.checked_file(folder, "x.json")


def test_no_overwrite_and_no_output_input_overlap(case):
    spec = {"schema_id": "factorlab.r3_transfer_input_run@1.0", "output_root": str(case["ref"] / "nested"),
            "clocks": {c: case["spec"] for c in ("1430", "1445")}}
    with pytest.raises(ValueError, match="overlap"): m.run(spec)
    spec["output_root"] = str(case["output"]); case["output"].mkdir()
    with pytest.raises(FileExistsError): m.run(spec)


def test_second_clock_failure_does_not_publish_first_clock(tmp_path):
    a, b = make_case(tmp_path, "1430"), make_case(tmp_path, "1445")
    b["spec"]["selection_sha256"] = "sha256:" + "0" * 64
    out = tmp_path / "result"
    spec = {"schema_id": "factorlab.r3_transfer_input_run@1.0", "output_root": str(out),
            "clocks": {"1430": a["spec"], "1445": b["spec"]}}
    with pytest.raises(ValueError): m.run(spec)
    assert (out / "failure.json").exists()
    assert not (out / "result.json").exists() and not (out / "stores").exists() and not (out / ".staging").exists()


def test_fresh_process_full_two_clock_build_and_read_only_reload(tmp_path):
    cases = {c: make_case(tmp_path, c, shuffled=True) for c in ("1430", "1445")}
    spec = {"schema_id": "factorlab.r3_transfer_input_run@1.0", "output_root": str(tmp_path / "result"),
            "clocks": {c: k["spec"] for c, k in cases.items()}}
    p = tmp_path / "run.json"; dump(p, spec)
    proc = subprocess.run([sys.executable, str(ROOT / "scripts/reaka_r3_build_transfer_inputs.py"), "--spec", str(p)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads((tmp_path / "result/result.json").read_text())
    assert result["new_model_fits"] == result["new_inference"] == result["checkpoint_reload"] == 0
    assert not result["PIT_certified"] and not result["generalization_evaluation_executed"]
    for c in cases:
        s = m.TransferFeatureStore(tmp_path / f"result/stores/{c}")
        idx = np.load(s.root / "prediction_indices.npy")[:3]
        assert s.normalized_inputs(idx)[1].shape == (3, 10, 71)


def test_no_training_or_label_dependency_imports():
    tree = ast.parse(SOURCE.read_text())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): imported.extend(x.name for x in node.names)
        if isinstance(node, ast.ImportFrom): imported.append(node.module or "")
    assert not any(any(word in name for word in ("torch", "training", "evaluation", "sklearn")) for name in imported)


def test_prefix_origin_must_not_be_implicitly_called_a_replay(case):
    bundle_change(case, "historical_prefix_origin", "unspecified")
    with pytest.raises(ValueError, match="replayed or copied"): build(case)


def test_prefix_copy_does_not_claim_independent_producer_replay(case):
    result = build(case)
    assert result["historical_prefix_origin"] == "reused_accepted_arrays"
    assert not result["prefix_check_is_independent_producer_replay"]


def test_empty_new_support_is_failure_not_success(case):
    old = case["old_len"]
    array_change(case, "epsilon_history.npy", lambda a: a.__setitem__((slice(old, None), slice(None)), np.nan))
    with pytest.raises(ValueError, match="no 2021--2025 feature support"): build(case)


def test_loaded_store_detects_output_corruption(case):
    build(case)
    with (case["output"] / "normalizer.json").open("a") as f: f.write(" ")
    with pytest.raises(ValueError, match="SHA256 mismatch"): m.TransferFeatureStore(case["output"])
