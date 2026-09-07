#!/usr/bin/env python3
"""Local producer bridge for LCL-R3-TRANSFER-INPUT-20260907-01.

Builds two-clock 2021--2025 same-definition feature source bundles from the
incumbent 3982-symbol TIMEISO identity plus bounded price/membership sources
truncated at 2025-12-31. Does not train networks, reload checkpoints, score
models, or consume the 5894/2026 residual-only product as a sliced substitute.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

THEME_ROOT = Path(__file__).resolve().parents[1]
FACTORLAB_ROOT = Path(os.environ.get(
    "FACTORLAB_ROOT",
    "/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab",
))
TASK = "LCL-R3-TRANSFER-INPUT-20260907-01"
END = np.datetime64("2025-12-31", "D")
START_TAIL = np.datetime64("2021-01-01", "D")
ANCHOR = np.datetime64("2008-12-01", "D")
HORIZON = 20
CACHE_REL = "output/factor-rotation/reaka_current_generation_blackbox_gpu_cache_v2_2007_2026"
P6_REL = "output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020/formal"
OT_REL = "output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020/formal"
TIMEISO_REL = "tmp/LCL-R3-TIMEISO-20260907-01/run01"
CR_REL = "output/factor-rotation/reaka_current_generation_blackbox_gpu_cache_v2_2007_2026/append_only_cloudridge_2008_2026.csv"
CORE_REL = "output/factor-rotation/reaka_residual_only_post2020_extension_v1_2009_2026/formal/condensation/extended_weekly_membership.parquet"
REGISTRY_REL = "docs/ops/factor_condensation_index_registry@1.0.json"


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def write_json(path: Path, body: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(body), ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    body = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise ValueError(f"JSON object required: {path}")
    return body


def h20_history(decision_close: np.ndarray) -> np.ndarray:
    out = np.full(decision_close.shape, np.nan, dtype=np.float32)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        out[HORIZON:] = decision_close[HORIZON:] / decision_close[:-HORIZON] - 1.0
    out[~np.isfinite(out)] = np.nan
    return out


def truncate_calendar_to_2025(calendar: np.ndarray) -> np.ndarray:
    days = calendar.astype("datetime64[D]")
    if days[0] != np.datetime64("2007-01-04", "D"):
        raise ValueError("unexpected calendar start")
    if END not in days:
        raise ValueError("calendar missing 2025-12-31")
    end = int(np.flatnonzero(days == END)[-1])
    out = days[: end + 1]
    if out[-1] != END or (out.astype("datetime64[Y]") == np.datetime64("2026")).any():
        raise ValueError("truncated calendar must end 2025-12-31 without 2026")
    return out


def d5_lattice(calendar: np.ndarray, old_len: int) -> np.ndarray:
    days = calendar.astype("datetime64[D]")
    anchor = np.flatnonzero(days == ANCHOR)
    if len(anchor) != 1:
        raise ValueError("D5 anchor missing")
    added = np.arange(old_len, len(days), dtype=np.int64)
    added = added[(added - int(anchor[0])) % 5 == 0]
    return added


def remap_positions(frame: pd.DataFrame, symbol_position: Mapping[str, int]) -> pd.DataFrame:
    local = frame.copy()
    local["symbol"] = local["symbol"].astype(str).str.zfill(6)
    local["symbol_position"] = local["symbol"].map(symbol_position)
    local = local.dropna(subset=["symbol_position"]).copy()
    local["symbol_position"] = local["symbol_position"].astype(np.int64)
    return local


def _inject_factorlab() -> None:
    src = str(FACTORLAB_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def _load_transfer():
    path = THEME_ROOT / "src/factor_lab/factor_rotation/reaka_r3_transfer_inputs.py"
    spec = importlib.util.spec_from_file_location("r3_transfer_inputs_bridge", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load transfer adapter")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _prefix_close_ok(reference: np.ndarray, candidate: np.ndarray) -> None:
    if reference.shape != candidate.shape:
        raise ValueError("prefix close shape mismatch")
    both = np.isfinite(reference) & np.isfinite(candidate)
    if both.any() and float(np.max(np.abs(reference[both] - candidate[both]))) > 0.0:
        raise ValueError("decision_close prefix drifted versus P6/TIMEISO identity")
    if (np.isfinite(reference) != np.isfinite(candidate)).any():
        raise ValueError("decision_close prefix support drifted")


def _load_memberships(symbols: np.ndarray, industry_ids: tuple[str, ...], small_id: str, large_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    cutoff = pd.Timestamp("2026-01-01")
    positions = {str(sym): int(i) for i, sym in enumerate(symbols)}
    cloudridge = pd.read_csv(
        FACTORLAB_ROOT / CR_REL,
        usecols=["as_of_date", "effective_date", "symbol"],
        dtype={"symbol": str},
    )
    cloudridge = cloudridge.rename(columns={"as_of_date": "asof_date"})
    cloudridge["asof_date"] = pd.to_datetime(cloudridge["asof_date"])
    cloudridge["effective_date"] = pd.to_datetime(cloudridge["effective_date"])
    cloudridge = cloudridge.loc[cloudridge["asof_date"] < cutoff].copy()
    cloudridge = remap_positions(cloudridge, positions)
    cloudridge["target_id"] = "orthogonal_market_cloudridge_v1"
    core = pd.read_parquet(
        FACTORLAB_ROOT / CORE_REL,
        columns=["asof_date", "effective_date", "target_id", "symbol"],
    )
    allowed = {small_id, large_id, *industry_ids}
    core = core.loc[core["target_id"].isin(allowed)].copy()
    core["asof_date"] = pd.to_datetime(core["asof_date"])
    core["effective_date"] = pd.to_datetime(core["effective_date"])
    core = core.loc[core["asof_date"] < cutoff].copy()
    core = remap_positions(core, positions)
    core["target_name"] = core["target_id"].astype(str)
    return cloudridge, core


def _basis_frame(clock: str, calendar: np.ndarray, basis: np.ndarray, factor_ids: list[str], variants: tuple[str, ...]) -> pd.DataFrame:
    rows = []
    days = pd.to_datetime(calendar.astype("datetime64[D]"))
    for v_i, variant in enumerate(variants):
        for f_i, factor in enumerate(factor_ids):
            values = basis[v_i, :, f_i]
            rows.append(pd.DataFrame({
                "decision_clock": clock[:2] + ":" + clock[2:],
                "return_role": "history",
                "variant_id": variant,
                "trading_day": days,
                "day_position": np.arange(len(calendar), dtype=np.int64),
                "factor_id": factor,
                "orthogonal_return": values,
                "available": np.isfinite(values),
                "uses_future_in_fit": False,
            }))
    return pd.concat(rows, ignore_index=True)


def build_clock(clock: str, output_bundle: Path, stats: dict[str, Any]) -> dict[str, Any]:
    _inject_factorlab()
    from factor_lab.factor_rotation import orthogonal_index_timing_transport_ot1_v1 as old_ot1
    from factor_lab.factor_rotation import reaka_intraday_orthogonal_ot_v1 as ot1
    from factor_lab.factor_rotation import orthogonal_factor_timing_state_v1 as timing
    from factor_lab.filtering import timing_validation as filters
    from factor_lab.factor_rotation import reaka_intraday_k1_preflight_v1 as k1
    from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import build_exposure_store, build_state_store
    transfer = _load_transfer()

    timeiso = FACTORLAB_ROOT / TIMEISO_REL / clock
    store = timeiso / "prepared/store"
    selection_path = timeiso / "prepared/selection/selected_tools.json"
    normalizer_path = timeiso / "experiment/normalizer.json"
    ref_manifest = store / "manifest.json"
    old_cal = np.load(store / "calendar.npy", allow_pickle=False).astype("datetime64[D]")
    old_dec = np.load(store / "exposure_decision_positions.npy", allow_pickle=False).astype(np.int64)
    symbols = np.load(store / "symbols.npy", allow_pickle=False).astype(str)
    factor_ids = [str(x) for x in read_json(store / "factor_ids.json")["factor_ids"]]
    variants = tuple(str(x) for x in read_json(store / "variant_ids.json")["variant_ids"])
    if variants != old_ot1.variant_ids():
        raise ValueError("variant identity drifted")
    industry_ids = tuple(factor_ids[2:])
    if len(symbols) != 3982 or len(factor_ids) != 14:
        raise ValueError("incumbent universe identity drifted")

    cache_cal = np.load(FACTORLAB_ROOT / CACHE_REL / "calendar.npy", allow_pickle=False)
    cache_sym = np.load(FACTORLAB_ROOT / CACHE_REL / "symbols.npy", allow_pickle=False).astype(str)
    if not np.array_equal(cache_sym[: len(symbols)], symbols):
        raise ValueError("cache is not an incumbent-prefix superset; refusing 5894-first fold")
    new_cal = truncate_calendar_to_2025(cache_cal)
    if not np.array_equal(new_cal[: len(old_cal)], old_cal):
        raise ValueError("extended calendar prefix drifted")
    added = d5_lattice(new_cal, len(old_cal))
    new_dec = np.concatenate((old_dec, added))
    close = np.asarray(
        np.load(FACTORLAB_ROOT / CACHE_REL / f"decision_close_{clock}.npy", mmap_mode="r")[: len(new_cal), : len(symbols)],
        dtype=np.float32,
    )
    p6_close = np.asarray(
        np.load(FACTORLAB_ROOT / P6_REL / f"decision_close_{clock}.npy", mmap_mode="r"),
        dtype=np.float32,
    )
    _prefix_close_ok(p6_close, close[: len(old_cal)])
    history = h20_history(close)
    p6_hist = np.asarray(np.load(FACTORLAB_ROOT / P6_REL / f"history_h20_raw_{clock}.npy", mmap_mode="r"), dtype=np.float32)
    _prefix_close_ok(p6_hist, history[: len(old_cal)])

    cloudridge, core = _load_memberships(symbols, industry_ids, old_ot1.SMALL_TARGET_ID, old_ot1.LARGE_TARGET_ID)
    market_h, _ = old_ot1.materialize_equal_weight_carriers(
        history, new_cal.astype("datetime64[ns]"), cloudridge, [old_ot1.MARKET_FACTOR_ID], minimum_members=12,
    )
    core_h, _ = old_ot1.materialize_equal_weight_carriers(
        history, new_cal.astype("datetime64[ns]"), core,
        [old_ot1.SMALL_TARGET_ID, old_ot1.LARGE_TARGET_ID, *industry_ids], minimum_members=5,
    )
    raw_h = np.concatenate([market_h, core_h], axis=2)
    raw_f = np.full_like(raw_h, np.nan)
    basis_h, _basis_f, _bh, _bf, _receipts = ot1.build_causal_basis_pair(
        raw_h, raw_f, new_cal.astype("datetime64[ns]"), industry_ids,
        decision_clock=f"{clock[:2]}:{clock[2:]}",
    )
    industry_membership = ot1.membership_for_decisions(core, industry_ids, new_cal.astype("datetime64[ns]"), new_dec)
    fit_days = np.concatenate((old_dec[-1:], added))
    stats["ols_decision_points"] = stats.get("ols_decision_points", 0) + int(len(fit_days))
    exposures, industry_exposures, _summary, epsilon_h, _epsilon_f = ot1.fit_intraday_stock_exposures(
        history_returns=history,
        future_returns=np.full_like(history, np.nan),
        decision_marks=close,
        history_basis=basis_h,
        future_basis=np.full_like(basis_h, np.nan),
        calendar=new_cal.astype("datetime64[ns]"),
        symbols=symbols,
        decision_positions=fit_days,
        industry_ids=industry_ids,
        industry_membership=industry_membership,
        decision_clock=f"{clock[:2]}:{clock[2:]}",
    )
    beta_new, rel_new, avail_new = build_exposure_store(
        exposures=exposures,
        industry_exposures=industry_exposures,
        calendar=new_cal.astype("datetime64[ns]"),
        symbol_count=len(symbols),
        factor_ids=factor_ids,
        decision_positions=fit_days,
    )
    # Drop the extra last-old D5 used only to carry residuals into 2021.
    beta_tail, rel_tail, avail_tail = beta_new[1:], rel_new[1:], avail_new[1:]
    if len(beta_tail) != len(added):
        raise ValueError("new D5 exposure count drifted")
    if not np.asarray(avail_tail).any():
        raise ValueError("new D5 exposure support is empty")

    old_eps = np.load(store / "epsilon_history.npy", mmap_mode="r")
    eps = np.full((len(new_cal), len(symbols)), np.nan, dtype=np.float32)
    eps[: len(old_cal)] = np.asarray(old_eps)
    eps[len(old_cal):] = np.asarray(epsilon_h[len(old_cal):], dtype=np.float32)

    old_beta = np.load(store / "stock_factor_exposures.npy", mmap_mode="r")
    old_rel = np.load(store / "exposure_reliability.npy", mmap_mode="r")
    old_av = np.load(store / "exposure_available.npy", mmap_mode="r")
    beta = np.concatenate((np.asarray(old_beta), np.asarray(beta_tail)), axis=0)
    rel = np.concatenate((np.asarray(old_rel), np.asarray(rel_tail)), axis=0)
    avail = np.concatenate((np.asarray(old_av), np.asarray(avail_tail)), axis=0)

    old_basis = pd.read_parquet(FACTORLAB_ROOT / OT_REL / clock / "ot1/factor_basis_history.parquet")
    old_basis = old_basis.loc[pd.to_datetime(old_basis["trading_day"]) <= pd.Timestamp("2020-12-31")].copy()
    new_basis = _basis_frame(clock, new_cal[len(old_cal):], basis_h[:, len(old_cal):, :], factor_ids, variants)
    history_basis = pd.concat((old_basis, new_basis), ignore_index=True)
    selection = pd.DataFrame(json.loads(selection_path.read_text(encoding="utf-8")))
    states = ot1.build_selected_states(
        history_basis=history_basis,
        selections=selection,
        decision_clock=f"{clock[:2]}:{clock[2:]}",
    )
    state_values, state_available = build_state_store(states, new_cal.astype("datetime64[ns]"), factor_ids)
    old_sv = np.load(store / "state_values.npy", mmap_mode="r")
    old_sa = np.load(store / "state_available.npy", mmap_mode="r")
    state_values[:, : len(old_cal)] = np.asarray(old_sv)
    state_available[:, : len(old_cal)] = np.asarray(old_sa)

    output_bundle.mkdir(parents=True, exist_ok=False)
    np.save(output_bundle / "calendar.npy", new_cal.astype("datetime64[ns]"), allow_pickle=False)
    np.save(output_bundle / "symbols.npy", symbols, allow_pickle=False)
    np.save(output_bundle / "exposure_decision_positions.npy", new_dec, allow_pickle=False)
    np.save(output_bundle / "epsilon_history.npy", eps.astype(np.float32), allow_pickle=False)
    np.save(output_bundle / "state_values.npy", np.asarray(state_values, dtype=np.float32), allow_pickle=False)
    np.save(output_bundle / "state_available.npy", np.asarray(state_available, dtype=np.uint8), allow_pickle=False)
    np.save(output_bundle / "stock_factor_exposures.npy", np.asarray(beta, dtype=np.float32), allow_pickle=False)
    np.save(output_bundle / "exposure_reliability.npy", np.asarray(rel, dtype=np.float32), allow_pickle=False)
    np.save(output_bundle / "exposure_available.npy", np.asarray(avail, dtype=np.uint8), allow_pickle=False)
    np.save(output_bundle / "symbol_fold_ids.npy", (np.arange(len(symbols), dtype=np.int64) % 5), allow_pickle=False)
    write_json(output_bundle / "factor_ids.json", {"factor_ids": factor_ids})
    write_json(output_bundle / "variant_ids.json", {"variant_ids": list(variants)})
    transfer.snapshot_loaded_sources(
        {
            "producer_bridge": sys.modules[__name__],
            "intraday_ot_producer": ot1,
            "timing_helper": timing,
            "ot1_helper": old_ot1,
            "filter_implementation": filters,
            "k1_store_helpers": k1,
        },
        output_bundle / "producer_sources.json",
    )
    bundle = {
        "schema_id": "factorlab.r3_transfer_source_bundle@1.0",
        "clock": clock,
        "calendar_end": "2025-12-31",
        "reference_manifest_sha256": sha_file(ref_manifest),
        "frozen_selection_sha256": sha_file(selection_path),
        "frozen_normalizer_sha256": sha_file(normalizer_path),
        "selection_freeze_end": "2016-12-31",
        "carrier_universe_policy": "incumbent_cohort_before_crossfit",
        "fold_policy": "explicit_incumbent_symbol_position_mod5",
        "historical_prefix_origin": "reused_accepted_arrays",
        "new_model_fits": 0,
        "selection_refit": False,
        "normalizer_refit": False,
        "labels_used_for_features": False,
        "artifact_digests": {},
    }
    names = (
        "calendar.npy", "symbols.npy", "factor_ids.json", "variant_ids.json",
        "exposure_decision_positions.npy", "epsilon_history.npy", "state_values.npy",
        "stock_factor_exposures.npy", "exposure_reliability.npy", "state_available.npy",
        "exposure_available.npy", "symbol_fold_ids.npy", "producer_sources.json",
    )
    bundle["artifact_digests"] = {name: sha_file(output_bundle / name) for name in names}
    write_json(output_bundle / "bundle.json", bundle)
    return {
        "clock": clock,
        "calendar_days": int(len(new_cal)),
        "symbols": int(len(symbols)),
        "old_d5": int(len(old_dec)),
        "new_d5": int(len(added)),
        "ols_points_including_boundary": int(len(fit_days)),
        "bundle_sha256": sha_file(output_bundle / "bundle.json"),
        "reference_manifest_sha256": bundle["reference_manifest_sha256"],
        "selection_sha256": bundle["frozen_selection_sha256"],
        "normalizer_sha256": bundle["frozen_normalizer_sha256"],
        "reference_store": str(store),
        "frozen_selection": str(selection_path),
        "frozen_normalizer": str(normalizer_path),
        "source_bundle": str(output_bundle),
    }


def run(output_root: Path) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError(output_root)
    output_root.mkdir(parents=True)
    stats: dict[str, Any] = {"ols_decision_points": 0}
    clocks = {}
    for clock in ("1430", "1445"):
        print(json.dumps({"status": "building_clock", "clock": clock}), flush=True)
        clocks[clock] = build_clock(clock, output_root / clock, stats)
    body = {
        "schema_id": "factorlab.r3_transfer_source_bridge_result@1.0",
        "task_id": TASK,
        "status": "source_bundles_prepared",
        "clocks": clocks,
        "ols_decision_points": stats["ols_decision_points"],
        "new_model_fits": 0,
        "new_inference": 0,
        "checkpoint_reload": 0,
        "labels_used_for_features": False,
        "historical_prefix_origin": "reused_accepted_arrays",
        "PIT_certified": False,
        "fresh_oos": False,
        "production_authority": False,
    }
    write_json(output_root / "bridge_result.json", body)
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        # Ensure snapshot_loaded_sources can hash this file as a loaded module.
        sys.modules.setdefault(__name__, sys.modules[__name__])
        result = run(args.output_root.resolve())
        print(json.dumps({"status": result["status"], "task_id": TASK, "new_model_fits": 0, "new_inference": 0}))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
