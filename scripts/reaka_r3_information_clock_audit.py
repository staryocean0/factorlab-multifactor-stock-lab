#!/usr/bin/env python3
"""Target-free R3 mask/reliability audit. No model, label, or training imports.

Profiles the exact ten H20-spaced contexts used by K1. Counts are context slots,
not independent financial observations. Timestamp/prefix evidence has separate
statuses; neither a hash nor a successful run certifies historical PIT.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

TASK = "LCL-R3-INFOCLOCK-20260907-01"
OFFSETS = np.arange(-180, 1, 20, dtype=np.int64)
PERIODS = {"fit_context": (2011, 2016), "consumed_discovery": (2018, 2020),
           "consumed_extension": (2021, 2025)}
FILES = ("calendar.npy", "inference_rows.npy", "state_values.npy",
         "state_available.npy", "exposure_decision_positions.npy",
         "exposure_reliability.npy", "exposure_available.npy")


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    def unique(items):
        body = {}
        for key, value in items:
            if key in body:
                raise ValueError(f"duplicate JSON key: {key}")
            body[key] = value
        return body
    body = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    if not isinstance(body, dict):
        raise ValueError("JSON object required")
    return body


def write_json_new(path: Path, body: Mapping[str, Any]) -> None:
    text = json.dumps(dict(body), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def _integer(values: np.ndarray, name: str, ndim: int) -> np.ndarray:
    if values.ndim != ndim or values.dtype.kind not in "iu":
        raise ValueError(f"{name}: integer {ndim}D array required")
    if values.dtype.kind == "u" and values.size and values.max() > np.iinfo(np.int64).max:
        raise ValueError(f"{name}: index overflow")
    return values.astype(np.int64, copy=False)


def _binary(values: np.ndarray, name: str) -> None:
    if not np.isin(values, (0, 1)).all():
        raise ValueError(f"{name}: nonbinary or nonfinite mask")


def _signature(path: Path) -> tuple[int, int, int]:
    s = path.stat()
    return s.st_size, s.st_mtime_ns, s.st_ino


def _utc(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("explicit timezone required")
    return value.astimezone(timezone.utc)


def audit_time_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate supplied evidence rows; not a producer trace or full-data proof."""
    if not isinstance(rows, list) or any(not isinstance(x, dict) for x in rows):
        raise ValueError("time evidence must be a list of objects")
    outcomes = []
    for row in rows:
        status, reason = "unknown", "missing time/source evidence"
        try:
            if not all(row.get(k) for k in ("feature", "decision_at", "dependency_max_at",
                                           "available_at", "source_ref")):
                raise KeyError("required field missing")
            decision, dependency, available = map(_utc, (row["decision_at"],
                                                       row["dependency_max_at"], row["available_at"]))
            if dependency > decision or available > decision:
                status, reason = "violation", "future dependency or late availability"
            elif dependency > available:
                status, reason = "violation", "claimed availability precedes dependency"
            else:
                status, reason = "reported_order_consistent", "source-backed row still needs scope review"
        except (ValueError, TypeError) as exc:
            status, reason = "invalid", str(exc)
        except KeyError:
            pass
        outcomes.append({"feature": row.get("feature"), "source_ref": row.get("source_ref"),
                         "status": status, "reason": reason})
    bad = any(x["status"] in ("violation", "invalid") for x in outcomes)
    return {"status": "violations_found" if bad else
            "unknown" if not outcomes or any(x["status"] == "unknown" for x in outcomes)
            else "supplied_rows_order_consistent_not_PIT_certified",
            "rows": outcomes, "PIT_certified": False}


def compare_prefix(original: np.ndarray, rebuilt: np.ndarray,
                   original_available: np.ndarray, rebuilt_available: np.ndarray,
                   *, atol: float = 1e-7) -> dict[str, Any]:
    """A caller must bind common coordinates and the actual producer separately."""
    if not np.isfinite(atol) or atol < 0:
        raise ValueError("invalid tolerance")
    arrays = list(map(np.asarray, (original, rebuilt, original_available, rebuilt_available)))
    a, b, ma, mb = arrays
    if not a.size or any(x.shape != a.shape for x in arrays):
        raise ValueError("nonempty identical shapes required")
    _binary(ma, "original available"); _binary(mb, "rebuilt available")
    active_a, active_b = ma.astype(bool), mb.astype(bool)
    mask_mismatch = int(np.count_nonzero(active_a != active_b))
    finite_a, finite_b = np.isfinite(a), np.isfinite(b)
    invalid = int(np.count_nonzero(active_a & ~finite_a) + np.count_nonzero(active_b & ~finite_b))
    common = active_a & active_b & finite_a & finite_b
    error = np.abs(a[common].astype(float) - b[common].astype(float))
    passed = not mask_mismatch and not invalid and bool(common.any()) and not bool((error > atol).any())
    return {"passed": passed, "status": "matched_on_bound_support" if passed else "not_matched_or_empty",
            "available_mask_mismatches": mask_mismatch, "nonfinite_active_values": invalid,
            "compared_cells": int(common.sum()), "above_tolerance": int((error > atol).sum()),
            "max_abs_error": float(error.max()) if len(error) else None,
            "proves_producer_causality": False}


def _accumulator(width: int) -> dict[str, Any]:
    return {"count": 0, "min": np.full(width, np.inf), "max": np.full(width, -np.inf),
            "sum": np.zeros(width), "zeros": np.zeros(width, dtype=np.int64)}


def _add(acc: dict[str, Any], values: np.ndarray) -> None:
    flat = np.asarray(values, float).reshape(-1, len(acc["min"]))
    if not len(flat) or not np.isfinite(flat).all():
        raise ValueError("empty or nonfinite consumed feature")
    acc["count"] += len(flat)
    acc["min"] = np.minimum(acc["min"], flat.min(axis=0))
    acc["max"] = np.maximum(acc["max"], flat.max(axis=0))
    acc["sum"] += flat.sum(axis=0)
    acc["zeros"] += (flat == 0).sum(axis=0)


def _finish(acc: dict[str, Any]) -> dict[str, Any]:
    n = acc["count"]
    if not n:
        return {"status": "no_support", "context_slots_per_factor": 0}
    constant = acc["min"] == acc["max"]
    return {"status": "profiled", "context_slots_per_factor": n,
            "min": acc["min"].tolist(), "max": acc["max"].tolist(),
            "mean": (acc["sum"] / n).tolist(), "zero_fraction": (acc["zeros"] / n).tolist(),
            "constant_factor_positions": np.flatnonzero(constant).tolist(),
            "all_factor_channels_constant": bool(constant.all())}


def profile_arrays(arrays: Mapping[str, np.ndarray], *, batch_size: int = 4096) -> dict[str, Any]:
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("positive integer batch_size required")
    cal = np.asarray(arrays["calendar.npy"])
    if cal.ndim != 1 or cal.dtype.kind != "M" or not len(cal) or np.isnat(cal).any():
        raise ValueError("invalid datetime calendar")
    if np.any(np.diff(cal) <= np.timedelta64(0, "ns")):
        raise ValueError("calendar must strictly increase")
    years = cal.astype("datetime64[Y]").astype(int) + 1970
    if years.max() > 2025:
        raise ValueError("2026+ store is withheld: use an already bounded store")
    rows = _integer(np.asarray(arrays["inference_rows.npy"]), "rows", 2)
    if rows.shape[1] != 4 or not len(rows):
        raise ValueError("nonempty four-column inference rows required")
    d, s = rows[:, 0], rows[:, 1]
    if (d < 180).any() or (d >= len(cal)).any() or (s < 0).any():
        raise ValueError("history endpoint or symbol outside support")
    if not np.array_equal(rows[:, 2], years[d]) or not np.isin(rows[:, 3], (0, 1, 2, 3)).all():
        raise ValueError("row year/phase metadata invalid")
    if len(np.unique(rows[:, :2], axis=0)) != len(rows):
        raise ValueError("duplicate day/symbol coordinates")
    positions = _integer(np.asarray(arrays["exposure_decision_positions.npy"]), "exposure positions", 1)
    if not len(positions) or (positions < 0).any() or (positions >= len(cal)).any() or (np.diff(positions) <= 0).any():
        raise ValueError("invalid exposure positions")
    state = arrays["state_values.npy"]; mask = arrays["state_available.npy"]
    rel = arrays["exposure_reliability.npy"]; expmask = arrays["exposure_available.npy"]
    if mask.shape != (6, len(cal), 14) or state.shape != mask.shape:
        raise ValueError("expected six variants, calendar, 14 state factors")
    if rel.ndim != 3 or rel.shape != expmask.shape or rel.shape[0] != len(positions) or rel.shape[2] != 14 or s.max() >= rel.shape[1]:
        raise ValueError("exposure dimensions or symbol index invalid")
    result = {}
    for name, (first, last) in PERIODS.items():
        selected = np.flatnonzero((rows[:, 2] >= first) & (rows[:, 2] <= last))
        sm, sv, rr = (_accumulator(14) for _ in range(3))
        active_rel = 0
        for start in range(0, len(selected), batch_size):
            local = rows[selected[start:start + batch_size]]
            endpoints = local[:, 0, None] + OFFSETS[None, :]
            folds = (local[:, 1] % 5 + 1)[:, None]
            mi = np.asarray(mask[folds, endpoints]); vi = np.asarray(state[folds, endpoints])
            _binary(mi, "consumed state mask")
            if not np.isfinite(vi).all():
                raise ValueError("nonfinite state value enters original K1 assembly")
            exi = np.searchsorted(positions, endpoints, side="left")
            if (exi >= len(positions)).any() or not np.array_equal(positions[exi], endpoints):
                raise ValueError("exposure endpoint not exact D5")
            ei = np.asarray(expmask[exi, local[:, 1, None]])
            ri = np.asarray(rel[exi, local[:, 1, None]])
            _binary(ei, "consumed exposure mask")
            effective = ri * ei  # Exactly mirrors K1; NaN * 0 is not silently filled.
            active_rel += int(np.count_nonzero(ei))
            _add(sm, mi); _add(sv, vi); _add(rr, effective)
        # Distinguish calendar/fold dependence from within-fold stock information.
        variation_checks = differing = 0
        for day in np.unique(rows[selected, 0]):
            subset = rows[selected][rows[selected, 0] == day]
            used = np.unique(subset[:, 1] % 5 + 1)
            block = np.asarray(mask[used[:, None], (day + OFFSETS)[None, :]])
            _binary(block, "fold mask")
            variation_checks += 10 * 14
            differing += int(np.count_nonzero(block.max(axis=0) != block.min(axis=0)))
        result[name] = {"years": [first, last], "inference_rows": int(len(selected)),
                        "decision_days": int(len(np.unique(rows[selected, 0]))),
                        "state_mask": _finish(sm), "state_values": _finish(sv),
                        "masked_reliability": _finish(rr), "active_reliability_context_cells": active_rel,
                        "crossfold_endpoint_factor_checks": variation_checks,
                        "crossfold_differing_checks": differing,
                        "within_same_fold_stock_variation_possible_by_schema": False}
    return {"periods": result, "calendar_start": str(cal[0]), "calendar_end": str(cal[-1]),
            "extension_rows_present": bool(result["consumed_extension"]["inference_rows"]),
            "all_counts_are_overlapping_contexts_not_independent_samples": True}


def audit_store(root: Path, expected_hashes: Mapping[str, str] | None = None) -> dict[str, Any]:
    expected = dict(expected_hashes or {})
    unknown_names = set(expected) - set(FILES)
    if unknown_names:
        raise ValueError(f"unrecognized binding files: {sorted(unknown_names)}")
    # Hash only the seven target-free arrays consumed by this audit, not the data lake.
    paths = {name: root / name for name in FILES}
    before = {n: _signature(p) for n, p in paths.items()}
    observed = {n: sha_file(p) for n, p in paths.items()}
    for name, value in expected.items():
        if value != observed[name]:
            raise ValueError(f"input digest mismatch: {name}")
    arrays = {n: np.load(p, mmap_mode="r", allow_pickle=False) for n, p in paths.items()}
    body = profile_arrays(arrays)
    if any(before[n] != _signature(p) for n, p in paths.items()):
        raise ValueError("input changed while reading")
    body.update({"input_raw_sha256": observed,
                 "external_hash_bindings_checked": sorted(expected),
                 "unbound_to_historical_receipt": sorted(set(FILES) - set(expected)),
                 "identity_capture_is_not_historical_provenance": True})
    return body


def run(spec: Mapping[str, Any]) -> dict[str, Any]:
    if spec.get("schema_id") != "factorlab.r3_information_clock_audit@1.0":
        raise ValueError("wrong spec schema")
    stores = spec.get("stores", {})
    if set(stores) != {"1430", "1445"}:
        raise ValueError("both clocks required; no silent partial audit")
    out = Path(spec["output_root"]).resolve()
    roots = {c: Path(v["root"]).resolve() for c, v in stores.items()}
    if any(out == r or r in out.parents or out in r.parents for r in roots.values()):
        raise ValueError("output must not overlap an input store")
    if out.exists():
        raise FileExistsError(out)
    # No directory or output is written until all reads/structural checks finish.
    clocks = {c: audit_store(roots[c], stores[c].get("expected_hashes")) for c in ("1430", "1445")}
    timing = audit_time_rows(spec.get("time_evidence", []))
    status = "completed_with_time_violations" if timing["status"] == "violations_found" else "completed_with_limits"
    body = {"schema_id": "factorlab.r3_information_clock_result@1.0", "task_id": TASK,
            "status": status, "clocks": clocks, "time_evidence": timing,
            "new_fits": 0, "new_inference": 0, "checkpoint_reload": 0,
            "future_labels_read": 0, "scores_read": 0, "PIT_certified": False,
            "fresh_oos": False, "production_authority": False,
            "generalization_evaluation_executed": False}
    out.mkdir(parents=True, exist_ok=False)
    write_json_new(out / "audit.json", body)
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args()
    try:
        body = run(read_json(args.spec))
        print(json.dumps({"status": body["status"], "task_id": TASK}, ensure_ascii=False))
        return 2 if body["status"] == "completed_with_time_violations" else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
