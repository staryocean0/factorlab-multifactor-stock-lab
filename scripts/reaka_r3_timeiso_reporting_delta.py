#!/usr/bin/env python3
"""Read-only reporting delta for LCL-R3-TIMEISO-20260907-01.

Loads existing scores.npz and K1 stores. Does not train, infer, or reload models.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import spearmanr

CLOCKS = ("1430", "1445")
SEEDS = (11, 29, 47)
ARMS = ("F", "H")
YEARS = (2018, 2019, 2020)
PHASES = (0, 1, 2, 3)
BASELINES = (
    "last_epsilon",
    "negative_last_epsilon",
    "mean10_epsilon",
    "negative_mean10_epsilon",
)
HISTORY_OFFSETS = tuple(range(-180, 1, 20))  # 10 H20-spaced endpoints, not 10 consecutive days
MIN_N = 30
TOP_N = 30


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"no rows for {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def rankz(values: np.ndarray) -> np.ndarray:
    from scipy.stats import rankdata

    ranks = rankdata(values)
    centered = ranks - ranks.mean()
    scale = centered.std()
    return centered / scale if scale > 0 else np.zeros_like(centered)


def daily_rankic(score: np.ndarray, target: np.ndarray) -> float | None:
    if len(score) < MIN_N:
        return None
    if not (np.isfinite(score).all() and np.isfinite(target).all()):
        return None
    value = float(spearmanr(score, target).statistic)
    return value if math.isfinite(value) else None


def decile_spread(score: np.ndarray, target: np.ndarray) -> float | None:
    if len(score) < MIN_N or not (np.isfinite(score).all() and np.isfinite(target).all()):
        return None
    order = np.argsort(score, kind="mergesort")
    count = max(1, len(target) // 10)
    return float(target[order[-count:]].mean() - target[order[:count]].mean())


def top30_minus_universe(score: np.ndarray, target: np.ndarray) -> float | None:
    if len(score) < TOP_N or not (np.isfinite(score).all() and np.isfinite(target).all()):
        return None
    order = np.argsort(score, kind="mergesort")
    return float(target[order[-TOP_N:]].mean() - target.mean())


def summarize_deltas(delta: np.ndarray) -> dict[str, Any]:
    finite = delta[np.isfinite(delta)]
    if not len(finite):
        return {"days": 0, "mean": None, "median": None, "win_days": 0, "loss_days": 0, "zero_or_tie_days": 0}
    return {
        "days": int(len(finite)),
        "mean": float(finite.mean()),
        "median": float(np.median(finite)),
        "win_days": int((finite > 0).sum()),
        "loss_days": int((finite < 0).sum()),
        "zero_or_tie_days": int((finite == 0).sum()),
    }


def load_scores(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as payload:
        return {
            "indices": np.asarray(payload["indices"], dtype=np.int64),
            "scores": np.asarray(payload["scores"], dtype=float),
            "rows": np.asarray(payload["rows"], dtype=np.int64),
        }


def attach_labels(
    scored: dict[str, np.ndarray],
    labelled: np.ndarray,
    inference_rows: np.ndarray,
    epsilon_future: np.ndarray,
) -> dict[str, np.ndarray]:
    flag = np.zeros(len(inference_rows), dtype=bool)
    flag[np.asarray(labelled, dtype=np.int64)] = True
    idx = np.asarray(scored["indices"], dtype=np.int64)
    keep = flag[idx]
    idx2 = idx[keep]
    rows = np.asarray(inference_rows[idx2], dtype=np.int64)
    years = rows[:, 2]
    if np.any((years < 2018) | (years > 2020)):
        raise ValueError("evaluation years escaped 2018-2020")
    if np.any(years == 2017):
        raise ValueError("2017 entered reporting support")
    target = np.asarray(epsilon_future[rows[:, 0], rows[:, 1]], dtype=float)
    if not np.isfinite(target).all():
        raise ValueError("nonfinite target on labelled support")
    return {
        "indices": idx2,
        "scores": np.asarray(scored["scores"], dtype=float)[keep],
        "rows": rows,
        "targets": target,
        "years": years,
        "phases": rows[:, 3],
        "days": rows[:, 0],
        "symbols": rows[:, 1],
    }


def ensemble_scores(items: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    if len(items) != 3:
        raise ValueError("ensemble requires exactly seeds 11/29/47")
    idx = items[0]["indices"]
    rows = items[0]["rows"]
    for item in items[1:]:
        if not np.array_equal(idx, item["indices"]) or not np.array_equal(rows, item["rows"]):
            raise ValueError("seed/arm coordinates differ")
    stack = np.stack([np.asarray(item["scores"], dtype=float) for item in items])
    out = np.zeros(len(idx), dtype=float)
    for day in np.unique(rows[:, 0]):
        mask = rows[:, 0] == day
        out[mask] = np.mean(np.stack([rankz(row[mask]) for row in stack]), axis=0)
    return {"indices": idx, "scores": out, "rows": rows}


def history_endpoints(days: np.ndarray, symbols: np.ndarray, history: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    offsets = np.asarray(HISTORY_OFFSETS, dtype=np.int64)
    if len(offsets) != 10:
        raise ValueError("mean10 must use 10 H20-spaced endpoints")
    if tuple(offsets.tolist()) != tuple(range(-180, 1, 20)):
        raise ValueError("history spacing drifted from H20 endpoints")
    points = days[:, None] + offsets[None, :]
    valid = (points >= 0) & (points < history.shape[0]) & (symbols[:, None] >= 0) & (symbols[:, None] < history.shape[1])
    values = np.full(points.shape, np.nan, dtype=float)
    ok = valid
    values[ok] = history[points[ok], np.broadcast_to(symbols[:, None], points.shape)[ok]]
    return values, ok.all(axis=1) & np.isfinite(values).all(axis=1)


def daily_table(score: np.ndarray, target: np.ndarray, rows: np.ndarray) -> list[dict[str, Any]]:
    out = []
    for day in np.unique(rows[:, 0]):
        mask = rows[:, 0] == day
        n = int(mask.sum())
        y = target[mask]
        s = score[mask]
        rankic = daily_rankic(s, y)
        if rankic is None:
            continue
        out.append(
            {
                "day_position": int(day),
                "year": int(rows[mask, 2][0]),
                "phase": int(rows[mask, 3][0]),
                "n": n,
                "rankic": rankic,
                "decile_spread": decile_spread(s, y),
                "top30_minus_universe": top30_minus_universe(s, y),
            }
        )
    return out


def subset_stats(days: list[dict[str, Any]], key: str = "rankic") -> dict[str, Any]:
    values = np.asarray([row[key] for row in days if row.get(key) is not None], dtype=float)
    if not len(values):
        return {"days": 0, "mean": None, "median": None, "win_days": None}
    return {"days": int(len(values)), "mean": float(values.mean()), "median": float(np.median(values))}


def paired_stats(f_days: list[dict[str, Any]], h_days: list[dict[str, Any]]) -> dict[str, Any]:
    f_map = {row["day_position"]: row for row in f_days}
    h_map = {row["day_position"]: row for row in h_days}
    common = sorted(set(f_map) & set(h_map))
    if not common:
        return {"days": 0, "mean_rankic_F": None, "mean_rankic_H": None, "mean_delta_rankic": None,
                "median_delta_rankic": None, "win_days": 0, "loss_days": 0, "zero_or_tie_days": 0}
    f = np.asarray([f_map[d]["rankic"] for d in common], dtype=float)
    h = np.asarray([h_map[d]["rankic"] for d in common], dtype=float)
    delta = f - h
    stats = summarize_deltas(delta)
    stats.update(
        {
            "mean_rankic_F": float(f.mean()),
            "mean_rankic_H": float(h.mean()),
            "mean_delta_rankic": stats.pop("mean"),
            "median_delta_rankic": stats.pop("median"),
        }
    )
    return stats


def load_clock(run_root: Path, clock: str) -> dict[str, Any]:
    spec = json.loads((run_root / clock / "experiment/models/seed_11/F/reload_spec.json").read_text())
    store = Path(spec["store_root"])
    inference_rows = np.load(store / "inference_rows.npy", mmap_mode="r")
    labelled = np.load(store / "labelled_row_indices.npy", mmap_mode="r")
    epsilon_future = np.load(store / "epsilon_future.npy", mmap_mode="r")
    epsilon_history = np.load(store / "epsilon_history.npy", mmap_mode="r")
    calendar = np.load(store / "calendar.npy", allow_pickle=False)
    raw = {}
    for seed in SEEDS:
        for arm in ARMS:
            path = run_root / clock / "experiment/models" / f"seed_{seed}" / arm / "scores.npz"
            scored = load_scores(path)
            years = scored["rows"][:, 2]
            if np.any((years < 2018) | (years > 2020) | (years == 2017)):
                raise ValueError(f"{clock} seed {seed} arm {arm} has illegal evaluation years")
            raw[(seed, arm)] = scored
    idx0 = raw[(11, "F")]["indices"]
    for seed in SEEDS:
        for arm in ARMS:
            if not np.array_equal(raw[(seed, arm)]["indices"], idx0):
                raise ValueError("score coordinates differ across seed/arm")
            if not np.array_equal(raw[(seed, arm)]["rows"], raw[(11, "F")]["rows"]):
                raise ValueError("score rows differ across seed/arm")
    labelled_by_arm_seed = {
        (seed, arm): attach_labels(raw[(seed, arm)], labelled, inference_rows, epsilon_future)
        for seed in SEEDS
        for arm in ARMS
    }
    support0 = labelled_by_arm_seed[(11, "F")]["indices"]
    for item in labelled_by_arm_seed.values():
        if not np.array_equal(item["indices"], support0):
            raise ValueError("labelled support differs across seed/arm")
    f_ens_raw = ensemble_scores([raw[(seed, "F")] for seed in SEEDS])
    h_ens_raw = ensemble_scores([raw[(seed, "H")] for seed in SEEDS])
    f_ens = attach_labels(f_ens_raw, labelled, inference_rows, epsilon_future)
    h_ens = attach_labels(h_ens_raw, labelled, inference_rows, epsilon_future)
    if not np.array_equal(f_ens["indices"], h_ens["indices"]):
        raise ValueError("ensemble labelled support differs")
    return {
        "clock": clock,
        "store": store,
        "calendar": calendar,
        "epsilon_history": epsilon_history,
        "labelled_seed": labelled_by_arm_seed,
        "f_ens": f_ens,
        "h_ens": h_ens,
        "support_rows": int(len(support0)),
    }


def per_seed_block(clock: str, seed: int, f: dict[str, np.ndarray], h: dict[str, np.ndarray]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    f_days = daily_table(f["scores"], f["targets"], f["rows"])
    h_days = daily_table(h["scores"], h["targets"], h["rows"])
    overall = paired_stats(f_days, h_days)
    overall.update({"clock": clock, "seed": seed, "scope": "all"})
    rows = [overall]
    detail = []
    f_map = {row["day_position"]: row for row in f_days}
    h_map = {row["day_position"]: row for row in h_days}
    for day in sorted(set(f_map) & set(h_map)):
        detail.append(
            {
                "clock": clock,
                "seed": seed,
                "day_position": day,
                "year": f_map[day]["year"],
                "phase": f_map[day]["phase"],
                "n": f_map[day]["n"],
                "rankic_F": f_map[day]["rankic"],
                "rankic_H": h_map[day]["rankic"],
                "delta": f_map[day]["rankic"] - h_map[day]["rankic"],
            }
        )
    year_phase = []
    for year in YEARS:
        f_y = [row for row in f_days if row["year"] == year]
        h_y = [row for row in h_days if row["year"] == year]
        item = paired_stats(f_y, h_y)
        item.update({"clock": clock, "seed": seed, "scope": "year", "year": year, "phase": None})
        year_phase.append(item)
    for phase in PHASES:
        f_p = [row for row in f_days if row["phase"] == phase]
        h_p = [row for row in h_days if row["phase"] == phase]
        item = paired_stats(f_p, h_p)
        item.update({"clock": clock, "seed": seed, "scope": "phase", "year": None, "phase": phase})
        year_phase.append(item)
    return {"overall": overall, "year_phase": year_phase}, year_phase + [overall]


def secondary_from_days(f_days: list[dict[str, Any]], h_days: list[dict[str, Any]], clock: str, scope: str, year=None, phase=None) -> dict[str, Any]:
    f_map = {row["day_position"]: row for row in f_days}
    h_map = {row["day_position"]: row for row in h_days}
    common = sorted(set(f_map) & set(h_map))
    def col(name):
        f = np.asarray([f_map[d][name] for d in common], dtype=float)
        h = np.asarray([h_map[d][name] for d in common], dtype=float)
        delta = f - h
        return {
            f"mean_{name}_F": float(np.nanmean(f)),
            f"mean_{name}_H": float(np.nanmean(h)),
            f"mean_{name}_delta": float(np.nanmean(delta)),
            f"median_{name}_delta": float(np.nanmedian(delta)),
            f"{name}_win_days": int(np.nansum(delta > 0)),
        }
    out = {"clock": clock, "scope": scope, "year": year, "phase": phase, "days": len(common)}
    out.update(col("decile_spread"))
    out.update(col("top30_minus_universe"))
    return out


def baseline_vectors(panel: dict[str, np.ndarray], history: np.ndarray) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    values, complete = history_endpoints(panel["days"], panel["symbols"], history)
    note = {
        "required_endpoints": 10,
        "spacing": "H20_20_trading_day_endpoints_not_10_consecutive_sessions",
        "rows_total": int(len(panel["days"])),
        "rows_with_complete_history": int(complete.sum()),
        "rows_missing_history": int((~complete).sum()),
        "missing_reason": "endpoint index out of calendar or nonfinite epsilon_history",
        "signs_fixed_a_priori": True,
    }
    last = values[:, -1]
    mean10 = values.mean(axis=1)
    return {
        "last_epsilon": last,
        "negative_last_epsilon": -last,
        "mean10_epsilon": mean10,
        "negative_mean10_epsilon": -mean10,
        "complete": complete,
    }, note


def run(run_root: Path, out_dir: Path) -> dict[str, Any]:
    if out_dir.exists() and any(out_dir.iterdir()) and out_dir.resolve() == run_root.resolve():
        raise ValueError("refuse to write into the original run root")
    out_dir.mkdir(parents=True, exist_ok=True)
    per_seed_summary = []
    year_phase_rows = []
    secondary_rows = []
    baseline_rows = []
    reconstruction = {}
    for clock in CLOCKS:
        packed = load_clock(run_root, clock)
        f_ens_days = daily_table(packed["f_ens"]["scores"], packed["f_ens"]["targets"], packed["f_ens"]["rows"])
        h_ens_days = daily_table(packed["h_ens"]["scores"], packed["h_ens"]["targets"], packed["h_ens"]["rows"])
        recon = paired_stats(f_ens_days, h_ens_days)
        reconstruction[clock] = recon
        secondary_rows.append(secondary_from_days(f_ens_days, h_ens_days, clock, "all"))
        for year in YEARS:
            secondary_rows.append(
                secondary_from_days(
                    [r for r in f_ens_days if r["year"] == year],
                    [r for r in h_ens_days if r["year"] == year],
                    clock,
                    "year",
                    year=year,
                )
            )
        for phase in PHASES:
            secondary_rows.append(
                secondary_from_days(
                    [r for r in f_ens_days if r["phase"] == phase],
                    [r for r in h_ens_days if r["phase"] == phase],
                    clock,
                    "phase",
                    phase=phase,
                )
            )
        for seed in SEEDS:
            block, rows = per_seed_block(
                clock,
                seed,
                packed["labelled_seed"][(seed, "F")],
                packed["labelled_seed"][(seed, "H")],
            )
            per_seed_summary.append(block["overall"])
            year_phase_rows.extend([row for row in rows if row.get("scope") in {"year", "phase"}])
        bases, note = baseline_vectors(packed["f_ens"], packed["epsilon_history"])
        complete = bases["complete"]
        rows = packed["f_ens"]["rows"][complete]
        target = packed["f_ens"]["targets"][complete]
        f_score = packed["f_ens"]["scores"][complete]
        h_score = packed["h_ens"]["scores"][complete]
        f_days = daily_table(f_score, target, rows)
        h_days = daily_table(h_score, target, rows)
        for name in BASELINES:
            b_days = daily_table(bases[name][complete], target, rows)
            vs_h = paired_stats(h_days, b_days)  # mean_rankic_F here is H, mean_rankic_H is baseline
            vs_f = paired_stats(f_days, b_days)
            b_spread = [row["decile_spread"] for row in b_days if row["decile_spread"] is not None]
            b_top = [row["top30_minus_universe"] for row in b_days if row["top30_minus_universe"] is not None]
            item = {
                "clock": clock,
                "baseline": name,
                "sign_fixed_a_priori": True,
                "days": vs_f["days"],
                "support_rows_before_history_filter": packed["support_rows"],
                "support_rows_common_finite": int(complete.sum()),
                "mean_rankic": vs_f["mean_rankic_H"],
                "median_rankic": float(np.median([row["rankic"] for row in b_days])) if b_days else None,
                "mean_decile_spread": float(np.mean(b_spread)) if b_spread else None,
                "mean_top30_minus_universe": float(np.mean(b_top)) if b_top else None,
                "mean_rankic_H_minus_baseline": vs_h["mean_delta_rankic"],
                "mean_rankic_F_minus_baseline": vs_f["mean_delta_rankic"],
                "history_note": note["missing_reason"] if note["rows_missing_history"] else "all_labelled_rows_had_10_H20_endpoints",
            }
            for year in YEARS:
                b_y = [row for row in b_days if row["year"] == year]
                item[f"mean_rankic_{year}"] = float(np.mean([row["rankic"] for row in b_y])) if b_y else None
                item[f"days_{year}"] = len(b_y)
            baseline_rows.append(item)
            note_clock = dict(note)
            note_clock["clock"] = clock
            item["history_filter"] = note_clock
    payload = {
        "task": "LCL-R3-TIMEISO-20260907-01",
        "kind": "read_only_reporting_delta",
        "new_fits": 0,
        "new_inference": 0,
        "checkpoint_reload": 0,
        "modified_original_scores_or_store": False,
        "fresh_oos": False,
        "PIT_certified": False,
        "production_authority": False,
        "ensemble_reconstruction_not_new_market_evidence": reconstruction,
        "per_seed": per_seed_summary,
    }
    write_json(out_dir / "per_seed_summary.json", {"task": payload["task"], "new_fits": 0, "new_inference": 0, "rows": per_seed_summary})
    write_csv(out_dir / "per_seed_year_phase.csv", year_phase_rows)
    write_csv(out_dir / "ensemble_secondary_metrics.csv", secondary_rows)
    # flatten history_filter for csv
    csv_baselines = []
    for row in baseline_rows:
        item = {k: v for k, v in row.items() if k != "history_filter"}
        filt = row["history_filter"]
        item["rows_total"] = filt["rows_total"]
        item["rows_with_complete_history"] = filt["rows_with_complete_history"]
        item["rows_missing_history"] = filt["rows_missing_history"]
        csv_baselines.append(item)
    write_csv(out_dir / "baseline_comparison.csv", csv_baselines)
    write_json(out_dir / "reporting_delta_summary.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run_root = args.run_root.resolve()
    out = args.output_dir.resolve()
    if out == run_root or out.is_relative_to(run_root / "1430") or out.is_relative_to(run_root / "1445"):
        raise ValueError("write reporting delta outside original score/store trees")
    payload = run(run_root, out)
    print(json.dumps({"status": "completed", "new_fits": 0, "new_inference": 0, "clocks": list(payload["ensemble_reconstruction_not_new_market_evidence"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
