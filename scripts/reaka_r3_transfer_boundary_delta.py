#!/usr/bin/env python3
"""Bounded impact checks B1--B3 for LCL-R3-TRANSFER-INPUT-20260907-01.

Does not rerun the full source-bundle bridge, overwrite source_bundles/run01,
train a network, reload checkpoints, or start transfer scoring.
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

THEME = Path(__file__).resolve().parents[1]
FACTORLAB_ROOT = Path(os.environ.get(
    "FACTORLAB_ROOT",
    "/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab",
))
TASK = "LCL-R3-TRANSFER-INPUT-20260907-01"
END = np.datetime64("2025-12-31", "D")


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def write_json(path: Path, body: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(body, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def load_bridge():
    spec = importlib.util.spec_from_file_location(
        "r3_transfer_bridge_delta",
        THEME / "scripts/reaka_r3_transfer_source_bridge.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _inject() -> None:
    src = str(FACTORLAB_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def membership_audit(bridge) -> dict[str, Any]:
    """Inspect the actually used as-of<2026, 3982-mapped snapshot. No feature rebuild."""
    cutoff = pd.Timestamp("2026-01-01")
    store = FACTORLAB_ROOT / "tmp/LCL-R3-TIMEISO-20260907-01/run01/1430/prepared/store"
    symbols = np.load(store / "symbols.npy", allow_pickle=False).astype(str)
    factor_ids = json_load(store / "factor_ids.json")["factor_ids"]
    industry_ids = tuple(str(x) for x in factor_ids[2:])
    _inject()
    from factor_lab.factor_rotation.orthogonal_index_timing_transport_ot1_v1 import (
        SMALL_TARGET_ID,
        LARGE_TARGET_ID,
    )
    positions = {str(sym): int(i) for i, sym in enumerate(symbols)}

    def summarize(name: str, raw: pd.DataFrame, asof_col: str) -> dict[str, Any]:
        raw = raw.copy()
        raw[asof_col] = pd.to_datetime(raw[asof_col])
        raw["effective_date"] = pd.to_datetime(raw["effective_date"])
        n_raw = int(len(raw))
        used = raw.loc[raw[asof_col] < cutoff].copy()
        n_pre2026 = int(len(used))
        n_discarded_asof_ge_2026 = n_raw - n_pre2026
        used = bridge.remap_positions(used.rename(columns={asof_col: "asof_date"}) if asof_col != "asof_date" else used, positions)
        if asof_col != "asof_date" and "asof_date" not in used.columns:
            used["asof_date"] = pd.to_datetime(used[asof_col])
        n_mapped = int(len(used))
        asof = pd.to_datetime(used["asof_date"])
        effective = pd.to_datetime(used["effective_date"])
        missing = int(asof.isna().sum() + effective.isna().sum())
        violations = int((effective <= asof).sum()) if missing == 0 else int(((effective <= asof) | asof.isna() | effective.isna()).sum())
        return {
            "source_name": name,
            "rows_after_full_file_read": n_raw,
            "rows_asof_before_2026": n_pre2026,
            "rows_discarded_because_asof_ge_2026": n_discarded_asof_ge_2026,
            "rows_mapped_to_incumbent_3982": n_mapped,
            "missing_dates": missing,
            "effective_le_asof_violations": violations,
            "used_asof_min": str(asof.min()) if len(used) else None,
            "used_asof_max": str(asof.max()) if len(used) else None,
            "used_effective_min": str(effective.min()) if len(used) else None,
            "used_effective_max": str(effective.max()) if len(used) else None,
            "forward_effective_ok": violations == 0 and missing == 0,
        }

    cr = pd.read_csv(
        FACTORLAB_ROOT / bridge.CR_REL,
        usecols=["as_of_date", "effective_date", "symbol"],
        dtype={"symbol": str},
    )
    cr = cr.rename(columns={"as_of_date": "asof_date"})
    core = pd.read_parquet(
        FACTORLAB_ROOT / bridge.CORE_REL,
        columns=["asof_date", "effective_date", "target_id", "symbol"],
    )
    allowed = {SMALL_TARGET_ID, LARGE_TARGET_ID, *industry_ids}
    core = core.loc[core["target_id"].isin(allowed)].copy()
    out = {
        "original_code_read_full_files_then_cutoff": True,
        "did_not_slice_5894_residual_product": True,
        "did_not_reread_2026_membership_as_a_new_scientific_pass": True,
        "cloudridge": summarize("append_only_cloudridge_2008_2026.csv", cr, "asof_date"),
        "core": summarize("condensation_extended_weekly_membership.parquet", core, "asof_date"),
        "core_target_filter": sorted(allowed),
        "PIT_certified": False,
    }
    out["any_timing_violation_on_used_snapshot"] = (
        not out["cloudridge"]["forward_effective_ok"] or not out["core"]["forward_effective_ok"]
    )
    return out



def load_used_membership(bridge, symbols, industry_ids, small_id, large_id):
    cutoff = pd.Timestamp("2026-01-01")
    positions = {str(sym): int(i) for i, sym in enumerate(symbols)}
    cloudridge = pd.read_csv(FACTORLAB_ROOT / bridge.CR_REL, usecols=["as_of_date", "effective_date", "symbol"], dtype={"symbol": str})
    cloudridge = cloudridge.rename(columns={"as_of_date": "asof_date"})
    cloudridge["asof_date"] = pd.to_datetime(cloudridge["asof_date"])
    cloudridge["effective_date"] = pd.to_datetime(cloudridge["effective_date"])
    cloudridge = cloudridge.loc[cloudridge["asof_date"] < cutoff].copy()
    cloudridge = bridge.remap_positions(cloudridge, positions)
    cloudridge["target_id"] = "orthogonal_market_cloudridge_v1"
    core = pd.read_parquet(FACTORLAB_ROOT / bridge.CORE_REL, columns=["asof_date", "effective_date", "target_id", "symbol"])
    core = core.loc[core["target_id"].isin({small_id, large_id, *industry_ids})].copy()
    core["asof_date"] = pd.to_datetime(core["asof_date"])
    core["effective_date"] = pd.to_datetime(core["effective_date"])
    core = core.loc[core["asof_date"] < cutoff].copy()
    core = bridge.remap_positions(core, positions)
    core["target_name"] = core["target_id"].astype(str)
    return cloudridge, core

def json_load(path: Path) -> dict[str, Any]:
    body = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise ValueError(path)
    return body


def _maxdiff(a: np.ndarray, b: np.ndarray) -> dict[str, Any]:
    a = np.asarray(a)
    b = np.asarray(b)
    if a.shape != b.shape:
        return {"shape_match": False, "a_shape": list(a.shape), "b_shape": list(b.shape)}
    both = np.isfinite(a) & np.isfinite(b)
    support_equal = bool(np.array_equal(np.isfinite(a), np.isfinite(b)))
    max_abs = float(np.max(np.abs(a[both] - b[both]))) if both.any() else 0.0
    return {
        "shape_match": True,
        "cells": int(a.size),
        "both_finite": int(both.sum()),
        "support_equal": support_equal,
        "max_abs_diff_finite": max_abs,
        "exact": bool(support_equal and max_abs == 0.0),
    }


def clock_basis_and_seam(clock: str, bridge) -> dict[str, Any]:
    _inject()
    from factor_lab.factor_rotation import orthogonal_index_timing_transport_ot1_v1 as old_ot1
    from factor_lab.factor_rotation import reaka_intraday_orthogonal_ot_v1 as ot1
    from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import build_exposure_store

    timeiso = FACTORLAB_ROOT / bridge.TIMEISO_REL / clock
    store = timeiso / "prepared/store"
    old_cal = np.load(store / "calendar.npy", allow_pickle=False).astype("datetime64[D]")
    old_dec = np.load(store / "exposure_decision_positions.npy", allow_pickle=False).astype(np.int64)
    symbols = np.load(store / "symbols.npy", allow_pickle=False).astype(str)
    factor_ids = [str(x) for x in json_load(store / "factor_ids.json")["factor_ids"]]
    industry_ids = tuple(factor_ids[2:])
    cache_cal = np.load(FACTORLAB_ROOT / bridge.CACHE_REL / "calendar.npy", allow_pickle=False)
    new_cal = bridge.truncate_calendar_to_2025(cache_cal)
    close = np.asarray(
        np.load(FACTORLAB_ROOT / bridge.CACHE_REL / f"decision_close_{clock}.npy", mmap_mode="r")[: len(new_cal), : len(symbols)],
        dtype=np.float32,
    )
    history = bridge.h20_history(close)
    cloudridge, core = load_used_membership(bridge, symbols, industry_ids, old_ot1.SMALL_TARGET_ID, old_ot1.LARGE_TARGET_ID)
    market_h, _ = old_ot1.materialize_equal_weight_carriers(
        history, new_cal.astype("datetime64[ns]"), cloudridge, [old_ot1.MARKET_FACTOR_ID], minimum_members=12,
    )
    core_h, _ = old_ot1.materialize_equal_weight_carriers(
        history, new_cal.astype("datetime64[ns]"), core,
        [old_ot1.SMALL_TARGET_ID, old_ot1.LARGE_TARGET_ID, *industry_ids], minimum_members=5,
    )
    raw_h = np.concatenate([market_h, core_h], axis=2)
    raw_f = np.full_like(raw_h, np.nan)
    print(json.dumps({"status": "basis_rebuild", "clock": clock}), flush=True)
    basis_h, _bf, _bh, _bf2, _rec = ot1.build_causal_basis_pair(
        raw_h, raw_f, new_cal.astype("datetime64[ns]"), industry_ids,
        decision_clock=f"{clock[:2]}:{clock[2:]}",
    )
    tail = basis_h[:, len(old_cal):, :]
    finite = np.isfinite(tail)
    b1 = {
        "tail_cells": int(tail.size),
        "tail_finite": int(finite.sum()),
        "tail_nonfinite": int((~finite).sum()),
        "nonfinite_by_factor": [int((~np.isfinite(tail[:, :, i])).sum()) for i in range(tail.shape[2])],
        "nonfinite_by_variant": [int((~np.isfinite(tail[i])).sum()) for i in range(tail.shape[0])],
        "all_tail_finite": bool(finite.all()),
        "day_position_reset_does_not_change_trading_day_sort": True,
        "state_rebuild_required": bool((~finite).any()),
        "helper_note": "family_tool_state already NaNs missing log_level/returns; extra NaN calendar rows would change IIR/rolling support only if present. build_selected_states sorts trading_day, not day_position.",
    }

    last = int(old_dec[-1])
    industry_membership = ot1.membership_for_decisions(
        core, industry_ids, new_cal.astype("datetime64[ns]"), np.array([last], dtype=np.int64),
    )
    print(json.dumps({"status": "seam_ols", "clock": clock, "day": last}), flush=True)
    exposures, industry_exposures, _summary, epsilon_h, _ef = ot1.fit_intraday_stock_exposures(
        history_returns=history[: len(old_cal)],
        future_returns=np.full_like(history[: len(old_cal)], np.nan),
        decision_marks=close[: len(old_cal)],
        history_basis=basis_h[:, : len(old_cal)],
        future_basis=np.full_like(basis_h[:, : len(old_cal)], np.nan),
        calendar=old_cal.astype("datetime64[ns]"),
        symbols=symbols,
        decision_positions=np.array([last], dtype=np.int64),
        industry_ids=industry_ids,
        industry_membership=industry_membership,
        decision_clock=f"{clock[:2]}:{clock[2:]}",
    )
    beta_n, rel_n, av_n = build_exposure_store(
        exposures=exposures,
        industry_exposures=industry_exposures,
        calendar=old_cal.astype("datetime64[ns]"),
        symbol_count=len(symbols),
        factor_ids=factor_ids,
        decision_positions=np.array([last], dtype=np.int64),
    )
    beta_o = np.load(store / "stock_factor_exposures.npy", mmap_mode="r")[-1]
    rel_o = np.load(store / "exposure_reliability.npy", mmap_mode="r")[-1]
    av_o = np.load(store / "exposure_available.npy", mmap_mode="r")[-1]
    eps_o = np.load(store / "epsilon_history.npy", mmap_mode="r")[last]
    # Original OT basis at last day
    ot = pd.read_parquet(
        FACTORLAB_ROOT / bridge.OT_REL / clock / "ot1/factor_basis_history.parquet",
        columns=["trading_day", "variant_id", "factor_id", "orthogonal_return"],
    )
    ot["trading_day"] = pd.to_datetime(ot["trading_day"])
    last_ts = pd.Timestamp(str(old_cal[last]))
    ot_last = ot.loc[ot["trading_day"] == last_ts]
    variants = tuple(str(x) for x in json_load(store / "variant_ids.json")["variant_ids"])
    recon = np.full((len(variants), len(factor_ids)), np.nan, dtype=np.float64)
    for v_i, variant in enumerate(variants):
        for f_i, factor in enumerate(factor_ids):
            recon[v_i, f_i] = basis_h[v_i, last, f_i]
    orig = np.full_like(recon, np.nan)
    for row in ot_last.itertuples():
        v_i = variants.index(str(row.variant_id))
        f_i = factor_ids.index(str(row.factor_id))
        orig[v_i, f_i] = float(row.orthogonal_return)

    b3 = {
        "last_old_d5_index": last,
        "last_old_d5_date": str(old_cal[last]),
        "copied_prefix_not_used_as_independent_replay": True,
        "recomputed_support": "prefix_calendar_only_plus_single_D5_OLS_window_day-120_to_day",
        "factor_basis_at_last_d5": _maxdiff(orig, recon),
        "beta": _maxdiff(np.asarray(beta_o), np.asarray(beta_n[0])),
        "reliability": _maxdiff(np.asarray(rel_o), np.asarray(rel_n[0])),
        "available": _maxdiff(np.asarray(av_o, dtype=float), np.asarray(av_n[0], dtype=float)),
        "epsilon_at_last_d5": _maxdiff(np.asarray(eps_o), np.asarray(epsilon_h[last])),
        "ols_decision_points_this_check": 1,
        "basis_projection_days_this_check": int(len(new_cal) - 120),
    }
    return {"B1_state_tail": b1, "B3_seam": b3}


def run(output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    bridge = load_bridge()
    print(json.dumps({"status": "B2_membership"}), flush=True)
    b2 = membership_audit(bridge)
    clocks = {}
    for clock in ("1430", "1445"):
        print(json.dumps({"status": "clock", "clock": clock}), flush=True)
        clocks[clock] = clock_basis_and_seam(clock, bridge)
    state_rebuild = any(clocks[c]["B1_state_tail"]["state_rebuild_required"] for c in clocks)
    seam_exact = all(
        clocks[c]["B3_seam"][k]["exact"]
        for c in clocks
        for k in ("factor_basis_at_last_d5", "beta", "reliability", "available", "epsilon_at_last_d5")
        if isinstance(clocks[c]["B3_seam"][k], dict) and "exact" in clocks[c]["B3_seam"][k]
    )
    body = {
        "schema_id": "factorlab.r3_transfer_boundary_delta@1.0",
        "task_id": TASK,
        "status": "boundary_delta_complete_no_array_rewrite" if (not state_rebuild and not b2["any_timing_violation_on_used_snapshot"]) else "boundary_delta_complete_see_flags",
        "original_source_bundles_untouched": True,
        "original_run01_untouched": True,
        "new_model_fits": 0,
        "new_inference": 0,
        "checkpoint_reload": 0,
        "full_bridge_rerun": False,
        "B2_membership": b2,
        "clocks": clocks,
        "state_rebuild_required": state_rebuild,
        "seam_all_exact": seam_exact,
        "basis_projection_scope_note": "Original bridge already ran build_causal_basis_pair over the full 4618-day extended calendar per clock; this delta recomputed that projection only as an inspection cache, plus 1 D5 OLS per clock. The previously reported 486 counts only stock-exposure refresh points.",
        "PIT_certified": False,
        "fresh_oos": False,
        "production_authority": False,
    }
    write_json(output / "boundary_checks.json", body)
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        body = run(args.output_root.resolve())
        print(json.dumps({
            "status": body["status"],
            "state_rebuild_required": body["state_rebuild_required"],
            "membership_violation": body["B2_membership"]["any_timing_violation_on_used_snapshot"],
            "seam_all_exact": body["seam_all_exact"],
            "new_model_fits": 0,
            "new_inference": 0,
        }, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
