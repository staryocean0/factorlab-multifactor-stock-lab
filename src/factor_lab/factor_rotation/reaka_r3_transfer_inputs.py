"""Bounded 2021--2025 K1 feature-store assembly; no model fitting or labels.

This adapter consumes a separately generated, source-bound feature bundle. It
DOES NOT implement the missing local raw-data/OT producer, infer a formula from
an identifier, or certify PIT. Historical values and symbol/fold identities are
checked before publishing an isolated, label-free store.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

import numpy as np

TASK = "LCL-R3-TRANSFER-INPUT-20260907-01"
SCHEMA = "factorlab.r3_transfer_feature_store@1.0"
BUNDLE_SCHEMA = "factorlab.r3_transfer_source_bundle@1.0"
OFFSETS = np.arange(-180, 1, 20, dtype=np.int64)
ANCHOR = np.datetime64("2008-12-01", "D")
END = np.datetime64("2025-12-31", "D")
START = np.datetime64("2021-01-01", "D")
VARIANTS = ("full_reference", *(f"crossfit_fold_{i}" for i in range(5)))
FLOAT_ARRAYS = ("epsilon_history", "state_values", "stock_factor_exposures", "exposure_reliability")
MASK_ARRAYS = ("state_available", "exposure_available")
DATA_ARRAYS = (*FLOAT_ARRAYS, *MASK_ARRAYS)
AXIS_FILES = ("calendar.npy", "symbols.npy", "factor_ids.json", "variant_ids.json", "exposure_decision_positions.npy")
REFERENCE_FILES = (*AXIS_FILES, *(n + ".npy" for n in DATA_ARRAYS), "inference_rows.npy", "feature_registry.json")
BUNDLE_FILES = (*AXIS_FILES, *(n + ".npy" for n in DATA_ARRAYS), "symbol_fold_ids.npy", "producer_sources.json")


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def read_json(path: Path) -> Any:
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError(f"duplicate JSON key: {k}")
            out[k] = v
        return out
    def reject(x):
        raise ValueError(f"nonfinite JSON constant: {x}")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique, parse_constant=reject)


def write_json(path: Path, obj: Any) -> None:
    with path.open("x", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def checked_file(root: Path, name: str) -> Path:
    p = (root / name).resolve()
    if root.resolve() not in p.parents or not p.is_file():
        raise ValueError(f"missing or escaping bundle file: {name}")
    return p


def bind_file(path: Path, expected: str) -> str:
    if not isinstance(expected, str) or len(expected) != 71 or not expected.startswith("sha256:"):
        raise ValueError(f"explicit raw SHA256 required: {path.name}")
    observed = sha_file(path)
    if observed != expected:
        raise ValueError(f"SHA256 mismatch: {path}")
    return observed


def snapshot_loaded_sources(modules: Mapping[str, ModuleType], output: Path) -> dict[str, Any]:
    """Call in the actual local producer after importing its numerical modules.

    Captures current loaded files (including untracked/dirty files), not a claim
    that they were part of a historical Git HEAD. Does not import arbitrary code.
    The caller must include directly used numerical helpers and its bridge.
    """
    if not modules:
        raise ValueError("at least one actual loaded producer module required")
    files = []
    for role, module in modules.items():
        if not isinstance(module, ModuleType) or not getattr(module, "__file__", None):
            raise ValueError(f"loaded file-backed module required: {role}")
        p = Path(module.__file__).resolve()
        if p.suffix != ".py" or not p.is_file():
            raise ValueError(f"Python source file required: {role}")
        files.append({"role": str(role), "module": module.__name__, "path": str(p),
                      "raw_sha256": sha_file(p), "bytes": p.stat().st_size})
    body = {"schema_id": "factorlab.r3_loaded_producer_sources@1.0", "files": files,
            "binding": "current_loaded_source_files_not_historical_HEAD", "PIT_certified": False}
    write_json(output, body)
    return body


def verify_sources(path: Path) -> dict[str, Any]:
    body = read_json(path)
    if body.get("schema_id") != "factorlab.r3_loaded_producer_sources@1.0" or not body.get("files"):
        raise ValueError("actual producer source snapshot required")
    roles = set()
    for row in body["files"]:
        if row["role"] in roles:
            raise ValueError("duplicate producer role")
        roles.add(row["role"])
        bind_file(Path(row["path"]), row["raw_sha256"])
    return {"files_verified": len(roles), "roles": sorted(roles),
            "scope": "reported_loaded_files_rehashed_not_full_execution_trace",
            "historical_source_identity_certified": False}


def integer(a: np.ndarray, name: str, ndim: int) -> np.ndarray:
    if a.ndim != ndim or a.dtype.kind not in "iu":
        raise ValueError(f"{name}: integer {ndim}D required")
    if a.dtype.kind == "u" and a.size and a.max() > np.iinfo(np.int64).max:
        raise ValueError(f"{name}: integer overflow")
    return np.asarray(a, dtype=np.int64)


def calendar(a: np.ndarray) -> np.ndarray:
    if a.ndim != 1 or a.dtype.kind != "M" or not a.size or np.isnat(a).any():
        raise ValueError("nonempty datetime calendar required")
    days = a.astype("datetime64[D]")
    if not np.array_equal(days.astype(a.dtype), a) or (np.diff(days) <= np.timedelta64(0, "D")).any():
        raise ValueError("calendar must contain unique increasing midnight dates")
    return days


def identifiers(a: Any, name: str) -> list[str]:
    v = np.asarray(a)
    if v.ndim != 1 or not len(v) or v.dtype.kind not in "US":
        raise ValueError(f"{name}: nonempty string vector required")
    out = v.astype(str).tolist()
    if any(not s or s.strip() != s for s in out) or len(set(out)) != len(out):
        raise ValueError(f"{name}: blank or duplicate identifiers")
    return out


def permutation(reference: list[str], source: list[str], name: str) -> np.ndarray:
    if set(reference) != set(source) or len(reference) != len(source):
        raise ValueError(f"{name}: source universe differs; no post-hoc dropping/appending")
    lookup = {s: i for i, s in enumerate(source)}
    return np.asarray([lookup[s] for s in reference], dtype=np.int64)


def no_overlap(output: Path, inputs: list[Path]) -> None:
    for p in inputs:
        p = p.resolve()
        if output == p or output in p.parents or p in output.parents:
            raise ValueError(f"output/input overlap: {p}")


def _load(root: Path, name: str) -> np.ndarray:
    return np.load(checked_file(root, name), mmap_mode="r", allow_pickle=False)


def _axes(root: Path) -> dict[str, Any]:
    return {"calendar": calendar(_load(root, "calendar.npy")),
            "symbols": identifiers(_load(root, "symbols.npy"), "symbols"),
            "factors": identifiers(read_json(checked_file(root, "factor_ids.json"))["factor_ids"], "factors"),
            "variants": identifiers(read_json(checked_file(root, "variant_ids.json"))["variant_ids"], "variants"),
            "decisions": integer(_load(root, "exposure_decision_positions.npy"), "decisions", 1)}


def _validate_reference_axes(a: dict[str, Any]) -> None:
    cal, d = a["calendar"], a["decisions"]
    if cal[-1] != np.datetime64("2020-12-31") or len(a["factors"]) != 14 or tuple(a["variants"]) != VARIANTS:
        raise ValueError("reference must be the bound 2020 K1 14-factor/six-variant store")
    if (cal == ANCHOR).sum() != 1 or not len(d) or d[0] < 0 or d[-1] >= len(cal) or (np.diff(d) <= 0).any():
        raise ValueError("invalid reference anchor/decisions")
    anchor = int(np.flatnonzero(cal == ANCHOR)[0])
    if ((d - anchor) % 5 != 0).any():
        raise ValueError("reference D5 lattice drift")


def _normalizer(path: Path) -> dict[str, Any]:
    norm = read_json(path)
    for key in ("return", "beta", "reliability"):
        mean, scale = norm[key + "_mean"], norm[key + "_scale"]
        if not np.isfinite(mean) or not np.isfinite(scale) or scale <= 0:
            raise ValueError("invalid frozen normalizer")
    if norm.get("fit_end_year") != 2016 or norm.get("target_used") is not False:
        raise ValueError("normalizer must remain the target-free 2016 fit artifact")
    return norm


def _shape(name: str, t: int, s: int, d: int) -> tuple[int, ...]:
    if name == "epsilon_history":
        return t, s
    if name.startswith("state_"):
        return 6, t, 14
    return d, s, 14


def _map_chunk(a: np.ndarray, name: str, lo: int, hi: int, maps: dict[str, np.ndarray]) -> np.ndarray:
    if name == "epsilon_history":
        return np.asarray(a[lo:hi])[:, maps["symbols"]]
    if name.startswith("state_"):
        return np.asarray(a[:, lo:hi])[maps["variants"]][:, :, maps["factors"]]
    return np.asarray(a[lo:hi])[:, maps["symbols"]][:, :, maps["factors"]]


def _reference_slice(a: np.ndarray, name: str, lo: int, hi: int) -> np.ndarray:
    return np.asarray(a[:, lo:hi] if name.startswith("state_") else a[lo:hi])


def _copy_checked_array(name: str, ref: Path, src: Path, dst: Path,
                        ra: dict[str, Any], sa: dict[str, Any], maps: dict[str, np.ndarray], block: int) -> dict[str, Any]:
    a, b = _load(ref, name + ".npy"), _load(src, name + ".npy")
    shape_r = _shape(name, len(ra["calendar"]), len(ra["symbols"]), len(ra["decisions"]))
    shape_s = _shape(name, len(sa["calendar"]), len(sa["symbols"]), len(sa["decisions"]))
    dtype = np.dtype("uint8" if name in MASK_ARRAYS else "float32")
    if a.shape != shape_r or b.shape != shape_s or a.dtype != dtype or b.dtype != dtype:
        raise ValueError(f"shape/dtype drift: {name}")
    n_ref = shape_r[1] if name.startswith("state_") else shape_r[0]
    n_all = shape_s[1] if name.startswith("state_") else shape_s[0]
    out = np.lib.format.open_memmap(dst / (name + ".npy"), mode="w+", dtype=dtype, shape=shape_s)
    cells = 0
    for lo in range(0, n_all, block):
        hi = min(n_all, lo + block)
        x = _map_chunk(b, name, lo, hi, maps)
        if name in MASK_ARRAYS:
            if not np.isin(x, (0, 1)).all():
                raise ValueError(f"nonbinary mask: {name}")
        elif name == "epsilon_history":
            if np.isinf(x).any():
                raise ValueError("infinite epsilon history")
        elif not np.isfinite(x).all():
            raise ValueError(f"nonfinite feature (do not silently fill): {name}")
        if name == "exposure_reliability" and ((x < 0).any() or (x > 1).any()):
            raise ValueError("raw reliability outside [0,1]")
        stop = min(hi, n_ref)
        if lo < stop:
            prefix = x[:, :stop - lo] if name.startswith("state_") else x[:stop - lo]
            old = _reference_slice(a, name, lo, stop)
            if not np.array_equal(prefix, old, equal_nan=True):
                raise ValueError(f"historical prefix changed: {name} [{lo}:{stop}]")
            cells += prefix.size
        if name.startswith("state_"):
            out[:, lo:hi] = x
        else:
            out[lo:hi] = x
    out.flush()
    del out
    return {"historical_cells_compared": int(cells), "comparison": "exact_value_and_NaN_support", "passed": True}


def _zero_unavailable(store: Path, block: int) -> None:
    for val, mask in (("state_values", "state_available"), ("stock_factor_exposures", "exposure_available"),
                      ("exposure_reliability", "exposure_available")):
        a, m = _load(store, val + ".npy"), _load(store, mask + ".npy")
        n = a.shape[1] if val.startswith("state_") else a.shape[0]
        for lo in range(0, n, block):
            x = _reference_slice(a, val, lo, lo + block)
            y = _reference_slice(m, mask, lo, lo + block)
            if np.any(x[y == 0] != 0):
                raise ValueError(f"unavailable {val} must retain original zero encoding")


def _construct_rows(store: Path, ref: Path, old_len: int) -> dict[str, Any]:
    cal = calendar(_load(store, "calendar.npy"))
    dec = integer(_load(store, "exposure_decision_positions.npy"), "decisions", 1)
    eps, available = _load(store, "epsilon_history.npy"), _load(store, "exposure_available.npy")
    rows = integer(_load(ref, "inference_rows.npy"), "reference rows", 2)
    if rows.shape[1] != 4 or not len(rows) or (rows[:, 0] < 180).any() or (rows[:, 0] >= old_len).any():
        raise ValueError("invalid reference inference rows")
    years = cal.astype("datetime64[Y]").astype(int) + 1970
    anchor = int(np.flatnonzero(cal == ANCHOR)[0])
    if (rows[:, 1] < 0).any() or (rows[:, 1] >= eps.shape[1]).any() or not np.array_equal(rows[:, 2], years[rows[:, 0]]):
        raise ValueError("invalid reference row symbols/years")
    if len(np.unique(rows[:, :2], axis=0)) != len(rows) or not np.array_equal(rows[:, 3], ((rows[:, 0] - anchor) // 5) % 4):
        raise ValueError("duplicate reference rows or changed phase")
    parts = [rows]
    support = []
    for di in np.flatnonzero(dec >= old_len):
        day = int(dec[di]); endpoints = day + OFFSETS
        positions = np.searchsorted(dec, endpoints)
        if (endpoints < 0).any() or (positions >= len(dec)).any() or not np.array_equal(dec[positions], endpoints):
            raise ValueError("historical context must remain on exact D5 endpoints")
        history_ok = np.isfinite(eps[endpoints]).all(axis=0)
        current_ok = np.asarray(available[di]).any(axis=1)
        keep = np.flatnonzero(history_ok & current_ok)
        support.append({"date": str(cal[day]), "day_position": day, "universe": eps.shape[1],
                        "included": int(len(keep)), "history_missing": int((~history_ok).sum()),
                        "current_exposure_missing": int((history_ok & ~current_ok).sum())})
        if len(keep):
            parts.append(np.column_stack((np.full(len(keep), day), keep, np.full(len(keep), years[day]),
                                          np.full(len(keep), ((day - anchor) // 5) % 4))))
    all_rows = np.concatenate(parts).astype(np.int64)
    pred = np.arange(len(rows), len(all_rows), dtype=np.int64)
    if not len(pred):
        raise ValueError("no 2021--2025 feature support; do not publish empty success")
    maturity = pred[all_rows[pred, 0] + 20 < len(cal)]
    np.save(store / "inference_rows.npy", all_rows, allow_pickle=False)
    np.save(store / "prediction_indices.npy", pred, allow_pickle=False)
    np.save(store / "maturity_eligible_indices.npy", maturity, allow_pickle=False)
    write_json(store / "daily_support.json", support)
    return {"original_rows_preserved": len(rows), "prediction_rows": len(pred),
            "prediction_days": len(np.unique(all_rows[pred, 0])), "maturity_eligible_rows": len(maturity),
            "maturity_rule": "decision_position+20 < len(bounded_calendar)",
            "maturity_is_not_finite_target_or_event_availability": True,
            "support_rule": "finite_ten_H20_history_endpoints_AND_current_any_exposure", "labels_used_for_support": False}


def prepare_clock(spec: Mapping[str, Any], clock: str, dst: Path, *, block: int = 64) -> dict[str, Any]:
    """Assemble one clock into an unpublished staging directory."""
    if clock not in ("1430", "1445") or type(block) is not int or block <= 0:
        raise ValueError("invalid clock or chunk size")
    ref, src = Path(spec["reference_store"]).resolve(), Path(spec["source_bundle"]).resolve()
    selection, norm = Path(spec["frozen_selection"]).resolve(), Path(spec["frozen_normalizer"]).resolve()
    if ref == src:
        raise ValueError("source bundle must be separate from reference store")
    no_overlap(dst.resolve(), [ref, src, selection.parent, norm.parent])
    bindings = {}
    for key, p in (("reference_manifest", ref / "manifest.json"), ("bundle_manifest", src / "bundle.json"),
                   ("selection", selection), ("normalizer", norm)):
        bindings[key] = bind_file(p, spec[key + "_sha256"])
    rm, bm = read_json(ref / "manifest.json"), read_json(src / "bundle.json")
    if bm.get("schema_id") != BUNDLE_SCHEMA or bm.get("clock") != clock:
        raise ValueError("bundle schema/clock mismatch")
    if bm.get("calendar_end") != "2025-12-31":
        raise ValueError("bounded 2025 bundle required; mixed 2026 product forbidden")
    expected_meta = {"reference_manifest_sha256": bindings["reference_manifest"],
                     "frozen_selection_sha256": bindings["selection"], "frozen_normalizer_sha256": bindings["normalizer"],
                     "selection_freeze_end": "2016-12-31", "carrier_universe_policy": "incumbent_cohort_before_crossfit",
                     "fold_policy": "explicit_incumbent_symbol_position_mod5", "new_model_fits": 0,
                     "selection_refit": False, "normalizer_refit": False, "labels_used_for_features": False}
    for k, v in expected_meta.items():
        if type(bm.get(k)) is not type(v) or bm[k] != v:
            raise ValueError(f"bundle recipe declaration mismatch: {k}")
    if bm.get("historical_prefix_origin") not in ("recomputed_from_bound_producer", "reused_accepted_arrays"):
        raise ValueError("declare whether the historical prefix was replayed or copied")
    if str(rm.get("decision_clock", "")).replace(":", "") != clock:
        raise ValueError("reference clock mismatch")
    ra, sa = _axes(ref), _axes(src)
    _validate_reference_axes(ra)
    if sa["calendar"][-1] != END or not np.array_equal(sa["calendar"][:len(ra["calendar"])], ra["calendar"]):
        raise ValueError("calendar prefix or 2025 endpoint mismatch")
    if not len(sa["decisions"]) or (np.diff(sa["decisions"]) <= 0).any():
        raise ValueError("source decision positions must be unique/increasing")
    anchor = int(np.flatnonzero(sa["calendar"] == ANCHOR)[0])
    added = np.arange(len(ra["calendar"]), len(sa["calendar"]), dtype=np.int64)
    added = added[(added - anchor) % 5 == 0]
    if not np.array_equal(sa["decisions"], np.concatenate((ra["decisions"], added))):
        raise ValueError("source D5 lattice missing/reanchored/reordered")
    maps = {n: permutation(ra[n], sa[n], n) for n in ("symbols", "factors", "variants")}
    folds = integer(_load(src, "symbol_fold_ids.npy"), "symbol folds", 1)
    if len(folds) != len(sa["symbols"]) or not np.array_equal(folds[maps["symbols"]], np.arange(len(ra["symbols"])) % 5):
        raise ValueError("fold identity changed before feature mapping")
    _normalizer(norm)
    reg = read_json(ref / "feature_registry.json")
    if reg.get("feature_dim") != 71 or len(reg.get("channels", [])) != 71:
        raise ValueError("71-channel incumbent registry required")
    # Calendar metadata is checked before hashing feature payloads; no extra files traversed.
    watched = {p: sha_file(p) for p in (ref / "manifest.json", src / "bundle.json", selection, norm)}
    for root, names, expected in ((ref, REFERENCE_FILES, rm.get("artifact_digests", {})),
                                  (src, BUNDLE_FILES, bm.get("artifact_digests", {}))):
        for n in names:
            p = checked_file(root, n)
            watched[p] = bind_file(p, expected.get(n))
    sources = verify_sources(src / "producer_sources.json")
    dst.mkdir(parents=True, exist_ok=False)
    for name in ("symbols.npy", "factor_ids.json", "variant_ids.json", "feature_registry.json"):
        shutil.copyfile(ref / name, dst / name)
    np.save(dst / "calendar.npy", sa["calendar"].astype("datetime64[ns]"), allow_pickle=False)
    np.save(dst / "exposure_decision_positions.npy", sa["decisions"], allow_pickle=False)
    prefix = {name: _copy_checked_array(name, ref, src, dst, ra, sa, maps, block) for name in DATA_ARRAYS}
    _zero_unavailable(dst, block)
    rows = _construct_rows(dst, ref, len(ra["calendar"]))
    shutil.copyfile(selection, dst / "frozen_selection.json")
    shutil.copyfile(norm, dst / "normalizer.json")
    write_json(dst / "mapping.json", {n + "_source_indices_in_reference_order": m.tolist() for n, m in maps.items()})
    # Post-read hashes detect ordinary concurrent edits; this is not an adversarial filesystem proof.
    for p, digest in watched.items():
        if sha_file(p) != digest:
            raise ValueError(f"input changed during assembly: {p}")
    verify_sources(src / "producer_sources.json")
    artifacts = {p.name: sha_file(p) for p in dst.iterdir() if p.is_file()}
    result = {"schema_id": SCHEMA, "clock": clock, "status": "prepared_features_only_not_scored",
              "calendar_start": str(sa["calendar"][0]), "calendar_end": str(END), "symbol_count": len(ra["symbols"]),
              "factor_count": 14, "feature_dim": 71, "sequence_points": 10, "bindings": bindings,
              "prefix_checks": prefix, "historical_prefix_origin": bm["historical_prefix_origin"],
              "prefix_check_is_independent_producer_replay": False,
              "rows": rows, "producer_sources": sources,
              "artifact_digests": artifacts, "raw_producer_execution": "local_report_not_reexecuted_by_assembler",
              "new_model_fits": 0, "new_inference": 0, "checkpoint_reload": 0,
              "labels_read": False, "fresh_oos": False, "PIT_certified": False, "production_authority": False}
    write_json(dst / "manifest.json", result)
    return result


def run(spec: Mapping[str, Any]) -> dict[str, Any]:
    if spec.get("schema_id") != "factorlab.r3_transfer_input_run@1.0" or set(spec.get("clocks", {})) != {"1430", "1445"}:
        raise ValueError("run spec must contain exactly both clocks")
    output = Path(spec["output_root"]).resolve()
    inputs = []
    for c in spec["clocks"].values():
        inputs.extend(Path(c[k]).resolve() for k in ("reference_store", "source_bundle"))
        inputs.extend(Path(c[k]).resolve().parent for k in ("frozen_selection", "frozen_normalizer"))
    no_overlap(output, inputs)
    output.mkdir(parents=True, exist_ok=False)  # Exclusive reservation, no overwrite or resume-by-guessing.
    stage = output / ".staging"
    try:
        results = {c: prepare_clock(spec["clocks"][c], c, stage / c) for c in ("1430", "1445")}
        # Clock-level missingness may differ; identity axes must not.
        for name in ("calendar.npy", "symbols.npy", "factor_ids.json", "variant_ids.json", "exposure_decision_positions.npy"):
            if sha_file(stage / "1430" / name) != sha_file(stage / "1445" / name):
                raise ValueError(f"two-clock axes differ: {name}")
        os.rename(stage, output / "stores")
        body = {"schema_id": "factorlab.r3_transfer_input_result@1.0", "task_id": TASK,
                "status": "prepared_features_only_not_scored", "clocks": results,
                "new_model_fits": 0, "new_inference": 0, "checkpoint_reload": 0,
                "future_labels_read": False, "fresh_oos": False, "PIT_certified": False,
                "generalization_evaluation_executed": False, "production_authority": False}
        write_json(output / "result.json", body)
        return body
    except Exception as exc:
        if stage.exists():
            shutil.rmtree(stage)
        write_json(output / "failure.json", {"status": "failed_not_published", "error": f"{type(exc).__name__}: {exc}",
                                             "new_model_fits": 0, "new_inference": 0})
        raise


class TransferFeatureStore:
    """Compatible assemble_inputs interface, deliberately without target access."""
    def __init__(self, root: Path):
        self.root = Path(root)
        manifest = read_json(self.root / "manifest.json")
        if manifest.get("schema_id") != SCHEMA:
            raise ValueError("not a transfer feature store")
        for name, h in manifest["artifact_digests"].items():
            bind_file(checked_file(self.root, name), h)
        for name in ("calendar", "symbols", "inference_rows", "exposure_decision_positions", *DATA_ARRAYS):
            setattr(self, name, _load(self.root, name + ".npy"))
        self.factor_ids = tuple(read_json(self.root / "factor_ids.json")["factor_ids"])
        self.normalizer = _normalizer(self.root / "normalizer.json")

    def assemble_inputs(self, indices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        idx = integer(np.asarray(indices), "indices", 1)
        if not len(idx) or (idx < 0).any() or (idx >= len(self.inference_rows)).any():
            raise ValueError("nonempty in-range input indices required")
        rows = np.asarray(self.inference_rows[idx])
        endpoints = rows[:, 0, None] + OFFSETS[None, :]
        si = rows[:, 1, None]; vi = (rows[:, 1] % 5 + 1)[:, None]
        di = np.searchsorted(self.exposure_decision_positions, endpoints)
        if (endpoints < 0).any() or (di >= len(self.exposure_decision_positions)).any() or not np.array_equal(self.exposure_decision_positions[di], endpoints):
            raise ValueError("invalid context endpoint")
        history = np.asarray(self.epsilon_history[endpoints, si], dtype=np.float32)
        state = np.asarray(self.state_values[vi, endpoints], dtype=np.float32)
        mask = np.asarray(self.state_available[vi, endpoints], dtype=np.float32)
        em = np.asarray(self.exposure_available[di, si], dtype=np.float32)
        beta = np.asarray(self.stock_factor_exposures[di, si], dtype=np.float32) * em
        rel = np.asarray(self.exposure_reliability[di, si], dtype=np.float32) * em
        age = np.zeros((*endpoints.shape, 1), dtype=np.float32)
        return history, np.concatenate((state, mask, beta, rel, em, age), axis=2)

    def normalized_inputs(self, indices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        h, x = self.assemble_inputs(indices)
        n = self.normalizer
        h = ((h - n["return_mean"]) / n["return_scale"]).astype(np.float32)
        for lo, hi, key in ((28, 42, "beta"), (42, 56, "reliability")):
            x[:, :, lo:hi] = ((x[:, :, lo:hi] - n[key + "_mean"]) / n[key + "_scale"]) * x[:, :, 56:70]
        return h, x

    def assemble_batch(self, indices: np.ndarray):
        raise RuntimeError("target access forbidden: label join is a separate post-score step")
