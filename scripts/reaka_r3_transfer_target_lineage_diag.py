#!/usr/bin/env python3
"""Read-only target-lineage diagnosis for R3 transfer evaluation.

This script does not build label sidecars, load model checkpoints, train models,
or score the 2021--2025 transfer period. It decomposes why the current bounded
label producer does not reproduce the accepted TIMEISO epsilon_future target.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FACTORLAB_ROOT = Path(os.environ.get(
    "FACTORLAB_ROOT",
    "/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab",
))
BRIDGE_PATH = ROOT / "scripts/reaka_r3_transfer_source_bridge.py"
HORIZON = 20
TASK = "LCL-R3-TRANSFER-TARGET-LINEAGE-20260908-01"


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def load_file(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def future_h20(close: np.ndarray, horizon: int = HORIZON) -> np.ndarray:
    values = np.asarray(close, dtype=np.float32)
    if values.ndim != 2 or horizon <= 0 or len(values) <= horizon:
        raise ValueError("invalid close/horizon")
    out = np.full(values.shape, np.nan, dtype=np.float32)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        out[:-horizon] = values[horizon:] / values[:-horizon] - 1.0
    out[~np.isfinite(out)] = np.nan
    return out


def structural_mature_anchors(
    decisions: np.ndarray,
    calendar: np.ndarray,
    count: int = 5,
    horizon: int = HORIZON,
) -> np.ndarray:
    """Blind anchors chosen only from date and structural t+H maturity.

    No target values or target finite-support values participate in selection.
    """
    d = np.asarray(decisions, dtype=np.int64)
    cal = np.asarray(calendar).astype("datetime64[D]")
    if d.ndim != 1 or cal.ndim != 1 or count <= 0 or horizon <= 0:
        raise ValueError("invalid anchor inputs")
    if len(d) and ((d < 0).any() or (d >= len(cal)).any()):
        raise ValueError("decision outside calendar")
    years = cal.astype("datetime64[Y]").astype(int) + 1970
    eligible = d[(years[d] >= 2018) & (years[d] <= 2020) & (d + horizon < len(cal))]
    if len(eligible) < count:
        raise ValueError("insufficient structurally mature old anchors")
    picks = np.unique(np.linspace(0, len(eligible) - 1, count, dtype=np.int64))
    if len(picks) != count:
        raise ValueError("anchor quantiles collapsed")
    return eligible[picks]


def maxdiff(reference: np.ndarray, candidate: np.ndarray, atol: float = 1e-7) -> dict[str, Any]:
    a = np.asarray(reference)
    b = np.asarray(candidate)
    if a.shape != b.shape:
        return {
            "shape_match": False,
            "reference_shape": list(a.shape),
            "candidate_shape": list(b.shape),
            "passed": False,
        }
    fa = np.isfinite(a)
    fb = np.isfinite(b)
    mismatch = int(np.count_nonzero(fa != fb))
    both = fa & fb
    err = np.abs(a[both].astype(np.float64) - b[both].astype(np.float64))
    max_abs = float(err.max()) if len(err) else 0.0
    above = int(np.count_nonzero(err > atol))
    return {
        "shape_match": True,
        "support_mismatches": mismatch,
        "finite_cells_compared": int(both.sum()),
        "max_abs_error": max_abs,
        "above_tolerance": above,
        "tolerance": atol,
        "passed": mismatch == 0 and above == 0,
    }


def summarize_rows(
    reference: np.ndarray,
    candidate: np.ndarray,
    anchors: np.ndarray,
    calendar: np.ndarray,
    atol: float = 1e-7,
) -> dict[str, Any]:
    rows = []
    passed = True
    max_abs = 0.0
    support = 0
    above = 0
    for day in anchors:
        body = maxdiff(np.asarray(reference[int(day)]), np.asarray(candidate[int(day)]), atol=atol)
        body["day_position"] = int(day)
        body["date"] = str(np.asarray(calendar).astype("datetime64[D]")[int(day)])
        rows.append(body)
        passed &= bool(body.get("passed", False))
        max_abs = max(max_abs, float(body.get("max_abs_error", 0.0)))
        support += int(body.get("support_mismatches", 0))
        above += int(body.get("above_tolerance", 0))
    return {
        "passed": bool(passed),
        "max_abs_error": max_abs,
        "support_mismatches": support,
        "above_tolerance": above,
        "anchors": rows,
    }


def basis_from_frame(
    path: Path,
    calendar: np.ndarray,
    variants: tuple[str, ...],
    factor_ids: tuple[str, ...],
) -> np.ndarray:
    frame = pd.read_parquet(
        path,
        columns=["trading_day", "variant_id", "factor_id", "orthogonal_return"],
    )
    frame = frame.copy()
    frame["trading_day"] = pd.to_datetime(frame["trading_day"])
    day_map = {pd.Timestamp(day): i for i, day in enumerate(np.asarray(calendar).astype("datetime64[ns]"))}
    vmap = {v: i for i, v in enumerate(variants)}
    fmap = {f: i for i, f in enumerate(factor_ids)}
    out = np.full((len(variants), len(calendar), len(factor_ids)), np.nan, dtype=np.float64)
    seen: set[tuple[int, int, int]] = set()
    for row in frame.itertuples(index=False):
        day = day_map.get(pd.Timestamp(row.trading_day))
        vi = vmap.get(str(row.variant_id))
        fi = fmap.get(str(row.factor_id))
        if day is None or vi is None or fi is None:
            continue
        key = (vi, day, fi)
        if key in seen:
            raise ValueError(f"duplicate basis coordinate in {path}: {key}")
        seen.add(key)
        value = float(row.orthogonal_return)
        if np.isfinite(value):
            out[key] = value
    return out


def summarize_basis(
    old_basis: np.ndarray,
    rebuilt_basis: np.ndarray,
    anchors: np.ndarray,
    calendar: np.ndarray,
) -> dict[str, Any]:
    # Move day axis first for summarize_rows.
    old_rows = np.moveaxis(np.asarray(old_basis), 1, 0)
    new_rows = np.moveaxis(np.asarray(rebuilt_basis), 1, 0)
    return summarize_rows(old_rows, new_rows, anchors, calendar)


def find_required_future_raw(p6_root: Path, clock: str) -> Path:
    expected = p6_root / f"future_h20_raw_{clock}.npy"
    if expected.exists():
        return expected
    candidates = sorted(p6_root.glob(f"*future*{clock}*.npy"))
    names = [p.name for p in candidates[:20]]
    raise FileNotFoundError(
        f"missing {expected}; bounded candidates={names}. Do not substitute a different file silently."
    )


def clock_diag(clock: str, bridge) -> dict[str, Any]:
    src = str(FACTORLAB_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from factor_lab.factor_rotation import orthogonal_index_timing_transport_ot1_v1 as old_ot1
    from factor_lab.factor_rotation import reaka_intraday_orthogonal_ot_v1 as ot1
    from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import build_exposure_store

    timeiso = FACTORLAB_ROOT / bridge.TIMEISO_REL / clock
    store = timeiso / "prepared/store"
    old_ot_root = FACTORLAB_ROOT / bridge.OT_REL / clock / "ot1"
    p6_root = FACTORLAB_ROOT / bridge.P6_REL
    old_cal = np.load(store / "calendar.npy", allow_pickle=False).astype("datetime64[D]")
    old_dec = np.load(store / "exposure_decision_positions.npy", allow_pickle=False).astype(np.int64)
    symbols = np.load(store / "symbols.npy", allow_pickle=False).astype(str)
    factor_ids = tuple(str(x) for x in json.loads((store / "factor_ids.json").read_text(encoding="utf-8"))["factor_ids"])
    variants = tuple(str(x) for x in json.loads((store / "variant_ids.json").read_text(encoding="utf-8"))["variant_ids"])
    anchors = structural_mature_anchors(old_dec, old_cal, count=5)

    residual_npz = old_ot_root / "stock_residual_surfaces.npz"
    with np.load(residual_npz, allow_pickle=False) as payload:
        residual_calendar = np.asarray(payload["calendar"], dtype="datetime64[D]")
        residual_symbols = np.asarray(payload["symbols"], dtype=str)
        ref_eh = np.asarray(payload["epsilon_history"], dtype=np.float32)
        ref_ef = np.asarray(payload["epsilon_future"], dtype=np.float32)
    if not np.array_equal(residual_calendar, old_cal) or not np.array_equal(residual_symbols, symbols):
        raise ValueError("old OT residual surface identity differs from TIMEISO store")
    store_ef = np.load(store / "epsilon_future.npy", mmap_mode="r")
    store_eh = np.load(store / "epsilon_history.npy", mmap_mode="r")
    residual_to_store_future = summarize_rows(ref_ef, store_ef, anchors, old_cal)
    residual_to_store_history = summarize_rows(ref_eh, store_eh, anchors, old_cal)

    p6_close = np.asarray(np.load(p6_root / f"decision_close_{clock}.npy", mmap_mode="r"), dtype=np.float32)
    p6_hist = np.asarray(np.load(p6_root / f"history_h20_raw_{clock}.npy", mmap_mode="r"), dtype=np.float32)
    p6_future_path = find_required_future_raw(p6_root, clock)
    p6_future = np.asarray(np.load(p6_future_path, mmap_mode="r"), dtype=np.float32)
    if p6_close.shape != ref_eh.shape or p6_hist.shape != ref_eh.shape or p6_future.shape != ref_ef.shape:
        raise ValueError("P6 raw array shape differs from old residual surface")

    cache_cal = np.load(FACTORLAB_ROOT / bridge.CACHE_REL / "calendar.npy", allow_pickle=False)
    ext_cal = bridge.truncate_calendar_to_2025(cache_cal)
    if not np.array_equal(ext_cal[: len(old_cal)], old_cal):
        raise ValueError("extended calendar prefix drift")
    cache_sym = np.load(FACTORLAB_ROOT / bridge.CACHE_REL / "symbols.npy", allow_pickle=False).astype(str)
    if not np.array_equal(cache_sym[: len(symbols)], symbols):
        raise ValueError("extended symbol prefix drift")
    close = np.asarray(
        np.load(FACTORLAB_ROOT / bridge.CACHE_REL / f"decision_close_{clock}.npy", mmap_mode="r")[: len(ext_cal), : len(symbols)],
        dtype=np.float32,
    )
    bridge._prefix_close_ok(p6_close, close[: len(old_cal)])
    history = bridge.h20_history(close)
    future = future_h20(close)
    bridge._prefix_close_ok(p6_hist, history[: len(old_cal)])
    raw_future_compare = summarize_rows(p6_future, future[: len(old_cal)], anchors, old_cal)

    old_basis_h = basis_from_frame(old_ot_root / "factor_basis_history.parquet", old_cal, variants, factor_ids)
    old_basis_f = basis_from_frame(old_ot_root / "factor_basis_future.parquet", old_cal, variants, factor_ids)

    industry_ids = tuple(factor_ids[2:])
    cloudridge, core = bridge._load_memberships(symbols, industry_ids, old_ot1.SMALL_TARGET_ID, old_ot1.LARGE_TARGET_ID)
    market_h, _ = old_ot1.materialize_equal_weight_carriers(
        history, ext_cal.astype("datetime64[ns]"), cloudridge, [old_ot1.MARKET_FACTOR_ID], minimum_members=12)
    core_h, _ = old_ot1.materialize_equal_weight_carriers(
        history, ext_cal.astype("datetime64[ns]"), core,
        [old_ot1.SMALL_TARGET_ID, old_ot1.LARGE_TARGET_ID, *industry_ids], minimum_members=5)
    market_f, _ = old_ot1.materialize_equal_weight_carriers(
        future, ext_cal.astype("datetime64[ns]"), cloudridge, [old_ot1.MARKET_FACTOR_ID], minimum_members=12)
    core_f, _ = old_ot1.materialize_equal_weight_carriers(
        future, ext_cal.astype("datetime64[ns]"), core,
        [old_ot1.SMALL_TARGET_ID, old_ot1.LARGE_TARGET_ID, *industry_ids], minimum_members=5)
    raw_h = np.concatenate([market_h, core_h], axis=2)
    raw_f = np.concatenate([market_f, core_f], axis=2)
    rebuilt_h, rebuilt_f, *_ = ot1.build_causal_basis_pair(
        raw_h, raw_f, ext_cal.astype("datetime64[ns]"), industry_ids,
        decision_clock=f"{clock[:2]}:{clock[2:]}")
    basis_history_compare = summarize_basis(old_basis_h, rebuilt_h[:, : len(old_cal)], anchors, old_cal)
    basis_future_compare = summarize_basis(old_basis_f, rebuilt_f[:, : len(old_cal)], anchors, old_cal)

    membership_old_cal = ot1.membership_for_decisions(
        core, industry_ids, old_cal.astype("datetime64[ns]"), anchors)
    replay_exp, replay_ind, _summary, replay_eh, replay_ef = ot1.fit_intraday_stock_exposures(
        history_returns=p6_hist,
        future_returns=p6_future,
        decision_marks=p6_close,
        history_basis=old_basis_h,
        future_basis=old_basis_f,
        calendar=old_cal.astype("datetime64[ns]"),
        symbols=symbols,
        decision_positions=anchors,
        industry_ids=industry_ids,
        industry_membership=membership_old_cal,
        decision_clock=f"{clock[:2]}:{clock[2:]}",
    )
    replay_beta, replay_rel, replay_av = build_exposure_store(
        exposures=replay_exp,
        industry_exposures=replay_ind,
        calendar=old_cal.astype("datetime64[ns]"),
        symbol_count=len(symbols),
        factor_ids=factor_ids,
        decision_positions=anchors,
    )
    old_beta = np.load(store / "stock_factor_exposures.npy", mmap_mode="r")
    old_rel = np.load(store / "exposure_reliability.npy", mmap_mode="r")
    old_av = np.load(store / "exposure_available.npy", mmap_mode="r")
    old_idx = np.searchsorted(old_dec, anchors)
    if not np.array_equal(old_dec[old_idx], anchors):
        raise ValueError("anchor is not exact old D5")
    replay_exposure = {
        "beta": maxdiff(np.asarray(old_beta[old_idx]), replay_beta),
        "reliability": maxdiff(np.asarray(old_rel[old_idx]), replay_rel),
        "available": maxdiff(np.asarray(old_av[old_idx], dtype=np.float32), replay_av.astype(np.float32)),
    }
    replay_history = summarize_rows(ref_eh, replay_eh, anchors, old_cal)
    replay_future = summarize_rows(ref_ef, replay_ef, anchors, old_cal)

    membership_ext = ot1.membership_for_decisions(
        core, industry_ids, ext_cal.astype("datetime64[ns]"), anchors)
    rebuilt_exp, rebuilt_ind, _summary2, rebuilt_eh, rebuilt_ef = ot1.fit_intraday_stock_exposures(
        history_returns=history,
        future_returns=future,
        decision_marks=close,
        history_basis=rebuilt_h,
        future_basis=rebuilt_f,
        calendar=ext_cal.astype("datetime64[ns]"),
        symbols=symbols,
        decision_positions=anchors,
        industry_ids=industry_ids,
        industry_membership=membership_ext,
        decision_clock=f"{clock[:2]}:{clock[2:]}",
    )
    rebuilt_beta, rebuilt_rel, rebuilt_av = build_exposure_store(
        exposures=rebuilt_exp,
        industry_exposures=rebuilt_ind,
        calendar=ext_cal.astype("datetime64[ns]"),
        symbol_count=len(symbols),
        factor_ids=factor_ids,
        decision_positions=anchors,
    )
    rebuilt_exposure = {
        "beta": maxdiff(np.asarray(old_beta[old_idx]), rebuilt_beta),
        "reliability": maxdiff(np.asarray(old_rel[old_idx]), rebuilt_rel),
        "available": maxdiff(np.asarray(old_av[old_idx], dtype=np.float32), rebuilt_av.astype(np.float32)),
    }
    rebuilt_history = summarize_rows(ref_eh, rebuilt_eh[: len(old_cal)], anchors, old_cal)
    rebuilt_future = summarize_rows(ref_ef, rebuilt_ef[: len(old_cal)], anchors, old_cal)

    if not replay_future["passed"]:
        diagnosis = "historical_artifact_replay_failed_recover_historical_producer_or_membership_before_extension"
    elif not raw_future_compare["passed"]:
        diagnosis = "raw_future_H20_path_diverges"
    elif not basis_future_compare["passed"]:
        diagnosis = "future_factor_basis_path_diverges"
    elif not rebuilt_exposure["beta"]["passed"]:
        diagnosis = "historical_exposure_path_diverges_under_rebuilt_inputs"
    elif not rebuilt_future["passed"]:
        diagnosis = "future_residual_path_diverges_after_prior_layers_match"
    else:
        diagnosis = "no_divergence_detected_at_fixed_anchors"

    return {
        "clock": clock,
        "anchors": [
            {"day_position": int(day), "date": str(old_cal[int(day)]), "structurally_mature": bool(day + HORIZON < len(old_cal))}
            for day in anchors
        ],
        "identity": {
            "timeiso_store_manifest": sha_file(store / "manifest.json"),
            "old_stock_residual_surfaces": sha_file(residual_npz),
            "old_factor_basis_history": sha_file(old_ot_root / "factor_basis_history.parquet"),
            "old_factor_basis_future": sha_file(old_ot_root / "factor_basis_future.parquet"),
            "p6_decision_close": sha_file(p6_root / f"decision_close_{clock}.npy"),
            "p6_history_h20_raw": sha_file(p6_root / f"history_h20_raw_{clock}.npy"),
            "p6_future_h20_raw": sha_file(p6_future_path),
            "current_intraday_ot_source": sha_file(Path(ot1.__file__).resolve()),
            "current_bridge_source": sha_file(Path(bridge.__file__).resolve()),
        },
        "old_OT_residual_to_TIMEISO_store": {
            "history": residual_to_store_history,
            "future": residual_to_store_future,
        },
        "raw_future_H20_P6_vs_extended_close_formula": raw_future_compare,
        "factor_basis_history_old_vs_rebuilt": basis_history_compare,
        "factor_basis_future_old_vs_rebuilt": basis_future_compare,
        "historical_artifact_replay_with_current_OT_code": {
            "exposure": replay_exposure,
            "epsilon_history": replay_history,
            "epsilon_future": replay_future,
        },
        "rebuilt_extended_path_at_same_old_anchors": {
            "exposure": rebuilt_exposure,
            "epsilon_history": rebuilt_history,
            "epsilon_future": rebuilt_future,
        },
        "diagnosis": diagnosis,
        "new_model_fits": 0,
        "model_scores": 0,
        "sidecars_built": 0,
        "contains_2026_target": False,
    }


def self_test() -> dict[str, Any]:
    cal = np.arange(np.datetime64("2017-01-01"), np.datetime64("2021-01-01"), dtype="datetime64[D]")
    d = np.arange(0, len(cal), 5, dtype=np.int64)
    a = structural_mature_anchors(d, cal, 5)
    assert len(a) == 5
    assert (a + HORIZON < len(cal)).all()
    assert maxdiff(np.array([1.0, np.nan]), np.array([1.0 + 1e-8, np.nan]))["passed"]
    assert not maxdiff(np.array([1.0, np.nan]), np.array([1.0, 0.0]))["passed"]
    return {"status": "self_test_passed", "anchors": [int(x) for x in a]}


def run(output_root: Path) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError(output_root)
    output_root.mkdir(parents=True)
    bridge = load_file("r3_transfer_source_bridge_target_diag", BRIDGE_PATH)
    clocks = {clock: clock_diag(clock, bridge) for clock in ("1430", "1445")}
    result = {
        "schema_id": "factorlab.r3_transfer_target_lineage_diag@1.0",
        "task_id": TASK,
        "status": "target_lineage_diagnosed_no_scores",
        "clocks": clocks,
        "new_model_fits": 0,
        "checkpoint_reloads": 0,
        "model_scores": 0,
        "label_sidecars": 0,
        "contains_2026_target": False,
        "fresh_oos": False,
        "PIT_certified": False,
        "production_authority": False,
    }
    (output_root / "target_lineage_diag.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            print(json.dumps(self_test(), ensure_ascii=False))
            return 0
        if args.output_root is None:
            raise ValueError("--output-root required unless --self-test")
        body = run(args.output_root.resolve())
        print(json.dumps({"status": body["status"], "task_id": TASK}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
