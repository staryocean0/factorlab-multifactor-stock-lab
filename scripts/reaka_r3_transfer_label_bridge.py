#!/usr/bin/env python3
"""Build bounded 2021--2025 H20 financial-epsilon label bundles; no model access."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FACTORLAB_ROOT = Path(os.environ.get("FACTORLAB_ROOT", "/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab"))
FEATURE_BRIDGE = ROOT / "scripts/reaka_r3_transfer_source_bridge.py"
TRANSFER_MOD = ROOT / "src/factor_lab/factor_rotation/reaka_r3_transfer_inputs.py"
TASK = "LCL-R3-TRANSFER-EVAL-20260908-01"


def load_file(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def future_h20(close: np.ndarray, horizon: int = 20) -> np.ndarray:
    values = np.asarray(close, dtype=np.float32)
    if values.ndim != 2 or horizon <= 0 or len(values) <= horizon:
        raise ValueError("invalid close/horizon")
    out = np.full(values.shape, np.nan, dtype=np.float32)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        out[:-horizon] = values[horizon:] / values[:-horizon] - 1.0
    out[~np.isfinite(out)] = np.nan
    return out


def anchor_decisions(old_decisions: np.ndarray, calendar: np.ndarray, count: int = 5) -> np.ndarray:
    d = np.asarray(old_decisions, dtype=np.int64)
    cal = np.asarray(calendar).astype("datetime64[D]")
    years = cal.astype("datetime64[Y]").astype(int) + 1970
    eligible = d[(years[d] >= 2018) & (years[d] <= 2020)]
    if len(eligible) < count:
        raise ValueError("insufficient old target anchors")
    picks = np.unique(np.linspace(0, len(eligible) - 1, count, dtype=np.int64))
    if len(picks) != count:
        raise ValueError("anchor quantiles collapsed")
    return eligible[picks]


def maxdiff(reference: np.ndarray, candidate: np.ndarray, atol: float = 1e-7) -> dict[str, Any]:
    a, b = np.asarray(reference), np.asarray(candidate)
    if a.shape != b.shape:
        raise ValueError("anchor shape drift")
    fa, fb = np.isfinite(a), np.isfinite(b)
    mismatch = int(np.count_nonzero(fa != fb))
    both = fa & fb
    err = np.abs(a[both].astype(float) - b[both].astype(float))
    max_abs = float(err.max()) if len(err) else 0.0
    return {"support_mismatches": mismatch, "finite_cells_compared": int(both.sum()),
            "max_abs_error": max_abs, "above_tolerance": int(np.count_nonzero(err > atol)),
            "passed": mismatch == 0 and not bool((err > atol).any())}


def build_clock(clock: str, feature_root: Path, output: Path) -> dict[str, Any]:
    bridge = load_file("r3_transfer_source_bridge_for_labels", FEATURE_BRIDGE)
    transfer = load_file("r3_transfer_inputs_for_labels", TRANSFER_MOD)
    src = str(FACTORLAB_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from factor_lab.factor_rotation import orthogonal_index_timing_transport_ot1_v1 as old_ot1
    from factor_lab.factor_rotation import reaka_intraday_orthogonal_ot_v1 as ot1
    from factor_lab.factor_rotation import orthogonal_factor_timing_state_v1 as timing
    from factor_lab.filtering import timing_validation as filters
    from factor_lab.factor_rotation import reaka_intraday_k1_preflight_v1 as k1

    timeiso = FACTORLAB_ROOT / bridge.TIMEISO_REL / clock
    ref = timeiso / "prepared/store"
    feature = feature_root / "stores" / clock
    fm = transfer.read_json(feature / "manifest.json")
    if fm.get("status") != "prepared_features_only_not_scored" or fm.get("calendar_end") != "2025-12-31":
        raise ValueError("accepted transfer feature store required")
    calendar = np.load(feature / "calendar.npy", allow_pickle=False).astype("datetime64[D]")
    symbols = np.load(feature / "symbols.npy", allow_pickle=False).astype(str)
    factor_ids = [str(x) for x in transfer.read_json(feature / "factor_ids.json")["factor_ids"]]
    decisions = np.load(feature / "exposure_decision_positions.npy", allow_pickle=False).astype(np.int64)
    old_cal = np.load(ref / "calendar.npy", allow_pickle=False).astype("datetime64[D]")
    old_dec = np.load(ref / "exposure_decision_positions.npy", allow_pickle=False).astype(np.int64)
    if len(symbols) != 3982 or len(factor_ids) != 14 or not np.array_equal(calendar[:len(old_cal)], old_cal):
        raise ValueError("transfer/reference identity drift")

    cache_cal = np.load(FACTORLAB_ROOT / bridge.CACHE_REL / "calendar.npy", allow_pickle=False)
    bounded = bridge.truncate_calendar_to_2025(cache_cal)
    if not np.array_equal(calendar, bounded):
        raise ValueError("feature/label bounded calendar drift")
    cache_sym = np.load(FACTORLAB_ROOT / bridge.CACHE_REL / "symbols.npy", allow_pickle=False).astype(str)
    if not np.array_equal(cache_sym[:len(symbols)], symbols):
        raise ValueError("label price source is not incumbent-prefix universe")
    close = np.asarray(np.load(FACTORLAB_ROOT / bridge.CACHE_REL / f"decision_close_{clock}.npy",
                               mmap_mode="r")[:len(calendar), :len(symbols)], dtype=np.float32)
    history = bridge.h20_history(close)
    future = future_h20(close)

    industry_ids = tuple(factor_ids[2:])
    cloudridge, core = bridge._load_memberships(symbols, industry_ids, old_ot1.SMALL_TARGET_ID, old_ot1.LARGE_TARGET_ID)
    market_h, _ = old_ot1.materialize_equal_weight_carriers(
        history, calendar.astype("datetime64[ns]"), cloudridge, [old_ot1.MARKET_FACTOR_ID], minimum_members=12)
    core_h, _ = old_ot1.materialize_equal_weight_carriers(
        history, calendar.astype("datetime64[ns]"), core,
        [old_ot1.SMALL_TARGET_ID, old_ot1.LARGE_TARGET_ID, *industry_ids], minimum_members=5)
    market_f, _ = old_ot1.materialize_equal_weight_carriers(
        future, calendar.astype("datetime64[ns]"), cloudridge, [old_ot1.MARKET_FACTOR_ID], minimum_members=12)
    core_f, _ = old_ot1.materialize_equal_weight_carriers(
        future, calendar.astype("datetime64[ns]"), core,
        [old_ot1.SMALL_TARGET_ID, old_ot1.LARGE_TARGET_ID, *industry_ids], minimum_members=5)
    raw_h = np.concatenate([market_h, core_h], axis=2)
    raw_f = np.concatenate([market_f, core_f], axis=2)
    basis_h, basis_f, *_ = ot1.build_causal_basis_pair(
        raw_h, raw_f, calendar.astype("datetime64[ns]"), industry_ids,
        decision_clock=f"{clock[:2]}:{clock[2:]}")

    tail_dec = decisions[decisions >= len(old_cal)]
    fit_days = np.concatenate((old_dec[-1:], tail_dec))
    membership = ot1.membership_for_decisions(core, industry_ids, calendar.astype("datetime64[ns]"), fit_days)
    _e, _ie, _s, _eh, epsilon_f = ot1.fit_intraday_stock_exposures(
        history_returns=history, future_returns=future, decision_marks=close,
        history_basis=basis_h, future_basis=basis_f, calendar=calendar.astype("datetime64[ns]"),
        symbols=symbols, decision_positions=fit_days, industry_ids=industry_ids,
        industry_membership=membership, decision_clock=f"{clock[:2]}:{clock[2:]}")

    ref_future = np.load(ref / "epsilon_future.npy", mmap_mode="r")
    target = np.full((len(calendar), len(symbols)), np.nan, dtype=np.float32)
    target[:len(old_cal)] = np.asarray(ref_future, dtype=np.float32)
    target[len(old_cal):] = np.asarray(epsilon_f[len(old_cal):], dtype=np.float32)

    anchors = anchor_decisions(old_dec, old_cal, 5)
    anchor_membership = ot1.membership_for_decisions(core, industry_ids, calendar.astype("datetime64[ns]"), anchors)
    _ae, _aie, _as, _aeh, anchor_future = ot1.fit_intraday_stock_exposures(
        history_returns=history, future_returns=future, decision_marks=close,
        history_basis=basis_h, future_basis=basis_f, calendar=calendar.astype("datetime64[ns]"),
        symbols=symbols, decision_positions=anchors, industry_ids=industry_ids,
        industry_membership=anchor_membership, decision_clock=f"{clock[:2]}:{clock[2:]}")
    checks = []
    support_mismatches = 0
    max_abs = 0.0
    all_pass = True
    for day in anchors:
        row = maxdiff(np.asarray(ref_future[day]), np.asarray(anchor_future[day]))
        row.update({"day_position": int(day), "date": str(old_cal[day])})
        checks.append(row)
        support_mismatches += row["support_mismatches"]
        max_abs = max(max_abs, row["max_abs_error"])
        all_pass &= row["passed"]
    anchor_body = {"schema_id": "factorlab.r3_transfer_target_anchor_checks@1.0",
                   "clock": clock, "selection_rule": "five_equal_index_quantiles_of_2018_2020_old_D5_blind_to_target_values",
                   "anchors_checked": len(checks), "support_mismatches": support_mismatches,
                   "max_abs_error": max_abs, "passed": bool(all_pass), "anchors": checks}
    if not all_pass:
        raise ValueError("target producer does not reproduce accepted old anchors")

    output.mkdir(parents=True, exist_ok=False)
    np.save(output / "calendar.npy", calendar.astype("datetime64[ns]"), allow_pickle=False)
    np.save(output / "symbols.npy", symbols, allow_pickle=False)
    np.save(output / "symbol_fold_ids.npy", np.arange(len(symbols), dtype=np.int64) % 5, allow_pickle=False)
    transfer.write_json(output / "factor_ids.json", {"factor_ids": factor_ids})
    np.save(output / "epsilon_future.npy", target, allow_pickle=False)
    transfer.write_json(output / "target_anchor_checks.json", anchor_body)
    transfer.snapshot_loaded_sources({
        "label_bridge": sys.modules[__name__],
        "feature_bridge": bridge,
        "intraday_ot_producer": ot1,
        "timing_helper": timing,
        "ot1_helper": old_ot1,
        "filter_implementation": filters,
        "k1_store_helpers": k1,
    }, output / "producer_sources.json")
    names = ("calendar.npy","symbols.npy","factor_ids.json","symbol_fold_ids.npy",
             "epsilon_future.npy","producer_sources.json","target_anchor_checks.json")
    bundle = {"schema_id": "factorlab.r3_transfer_label_bundle@1.0", "clock": clock,
              "calendar_end": "2025-12-31", "contains_2026": False,
              "target_definition": "H20_financial_residual_epsilon_future_K1_v1",
              "horizon_trading_positions": 20, "fold_policy": "explicit_incumbent_symbol_position_mod5",
              "labels_used_for_features": False, "historical_prefix_origin": "reused_accepted_arrays",
              "tail_producer": "bounded_current_intraday_OT_same_3982_cohort",
              "new_model_fits": 0, "artifact_digests": {n: transfer.sha_file(output/n) for n in names}}
    transfer.write_json(output / "bundle.json", bundle)
    return {"clock": clock, "calendar_days": len(calendar), "symbols": len(symbols),
            "tail_decisions": len(tail_dec), "anchors_checked": len(checks),
            "bundle_sha256": transfer.sha_file(output/"bundle.json")}


def run(feature_root: Path, output_root: Path) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError(output_root)
    output_root.mkdir(parents=True)
    clocks = {c: build_clock(c, feature_root, output_root/c) for c in ("1430","1445")}
    body = {"schema_id":"factorlab.r3_transfer_label_bridge_result@1.0","task_id":TASK,
            "status":"bounded_label_bundles_prepared","clocks":clocks,
            "new_model_fits":0,"model_inference":0,"checkpoint_reload":0,
            "contains_2026":False,"fresh_oos":False,"PIT_certified":False}
    mod=load_file("r3_transfer_inputs_writer",TRANSFER_MOD)
    mod.write_json(output_root/"result.json",body)
    return body


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--feature-root",type=Path,required=True)
    p.add_argument("--output-root",type=Path,required=True)
    args=p.parse_args()
    try:
        body=run(args.feature_root.resolve(),args.output_root.resolve())
        print(json.dumps({"status":body["status"],"new_model_fits":0,"model_inference":0}))
        return 0
    except Exception as exc:
        print(json.dumps({"status":"failed","error":f"{type(exc).__name__}: {exc}"},ensure_ascii=False))
        return 1

if __name__=="__main__":
    raise SystemExit(main())
