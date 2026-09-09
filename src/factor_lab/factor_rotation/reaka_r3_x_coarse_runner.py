"""Execute the R3 coarse H -> E -> F direct-X decomposition on accepted TIMEISO support.

Only E is newly fitted. Accepted F/H scores and receipts are immutable reference
artifacts from LCL-R3-TIMEISO-20260907-01. This module deliberately refuses to
fit F or H, change the 2018-2020 support, or expand the frozen seed/cycle budget.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

SEEDS = (11, 29, 47)
CLOCKS = ("1430", "1445")
MAX_NEW_FITS = 6
MAX_CYCLES_PER_FIT = 3
EXPECTED_TIMEISO_RUNNER_SHA256 = "sha256:ee7036f1925ab61ed88cc96e79a0ee06af9bb2a75812a1a58f4aa2d4a61c3708"
EXPECTED_CONDITION_VIEWS_SHA256 = "sha256:7d76a03785e2d03623342c63c360ddf7680835433294f5f511163d09fba2f921"
PAIR_FIELDS = (
    "recipe_digest", "selection_digest", "normalizer_digest",
    "train_rows_digest", "prediction_rows_digest", "pre_dmd_state_digest",
    "batch_order_digest",
)
STABLE_ENV_FIELDS = ("python", "platform", "numpy", "pandas", "torch", "device", "cuda_available")


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    body = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise ValueError(f"JSON object required: {path}")
    return body


def write_json(path: Path, body: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(body), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def current_environment(device: str = "cpu") -> dict[str, Any]:
    import pandas as pd_runtime
    import torch
    return {
        "python": __import__("sys").version,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd_runtime.__version__,
        "torch": torch.__version__,
        "device": device,
        "cuda_available": bool(torch.cuda.is_available()),
    }


def stable_environment_issues(accepted: Mapping[str, Any], current: Mapping[str, Any]) -> list[str]:
    return [key for key in STABLE_ENV_FIELDS if accepted.get(key) != current.get(key)]


def accepted_pair_common(f_receipt: Mapping[str, Any], h_receipt: Mapping[str, Any]) -> dict[str, Any]:
    fi = dict(f_receipt["identity"]); hi = dict(h_receipt["identity"])
    if fi.get("arm") != "F" or hi.get("arm") != "H":
        raise ValueError("accepted receipts must be F/H")
    for key in ("seed", "clock", *PAIR_FIELDS):
        if fi.get(key) != hi.get(key):
            raise ValueError(f"accepted F/H identity mismatch: {key}")
    return {key: fi[key] for key in ("seed", "clock", *PAIR_FIELDS)}


def _rt():
    from factor_lab.factor_rotation import reaka_intraday_k1_preflight_v1 as pf
    from factor_lab.factor_rotation import reaka_intraday_k1_training_v1 as tr
    from factor_lab.factor_rotation import reaka_r3_time_isolated_runner as timeiso
    from factor_lab.factor_rotation.reaka_r3_x_decomposition import x_view_model_class
    from factor_lab.factor_rotation.reaka_stage6_daily_engine import Stage6ReakaModel
    return pf, tr, timeiso, x_view_model_class, Stage6ReakaModel


def build_e_model(candidate: Mapping[str, Any], seed: int):
    _, tr, _, view, base_cls = _rt()
    base = tr.build_model(candidate, seed=seed)
    initial = {name: value.detach().cpu().clone() for name, value in base.state_dict().items()}
    digest = tr.state_digest(base)
    cls = view(base_cls, "E")
    model = cls(feature_dim=tr.FEATURE_DIM, config=base.config, arm_id="fixed_k_no_residual")
    model.load_state_dict(initial)
    if tr.state_digest(model) != digest:
        raise ValueError("E pre-DMD state does not equal base initialization")
    return model, digest


def load_scores(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as payload:
        return {key: np.asarray(payload[key]) for key in ("indices", "scores", "rows")}


def _same_score_coordinates(*items: Mapping[str, np.ndarray]) -> bool:
    first = items[0]
    return all(np.array_equal(first["indices"], row["indices"]) and np.array_equal(first["rows"], row["rows"]) for row in items[1:])


def daily_triplet(f: np.ndarray, e: np.ndarray, h: np.ndarray, targets: np.ndarray, rows: np.ndarray) -> pd.DataFrame:
    out: list[dict[str, Any]] = []
    for day in np.unique(rows[:, 0]):
        mask = rows[:, 0] == day
        if int(mask.sum()) < 30:
            continue
        vals = []
        for score in (f, e, h):
            rho = float(spearmanr(score[mask], targets[mask]).statistic)
            if not math.isfinite(rho):
                break
            vals.append(rho)
        if len(vals) != 3:
            continue
        rf, re, rh = vals
        out.append({
            "day_position": int(day), "rankic_F": rf, "rankic_E": re, "rankic_H": rh,
            "F_minus_E": rf - re, "E_minus_H": re - rh, "F_minus_H": rf - rh,
            "year": int(rows[mask, 2][0]), "phase": int(rows[mask, 3][0]), "n": int(mask.sum()),
        })
    if not out:
        raise ValueError("no finite paired days")
    return pd.DataFrame(out)


def summarize_daily(frame: pd.DataFrame) -> dict[str, Any]:
    body: dict[str, Any] = {"days": int(len(frame))}
    for key in ("F_minus_E", "E_minus_H", "F_minus_H"):
        values = frame[key].to_numpy(float)
        body[key] = {
            "mean": float(values.mean()), "median": float(np.median(values)),
            "win_days": int((values > 0).sum()), "loss_days": int((values < 0).sum()),
        }
    body["by_year"] = {
        str(int(year)): {key: float(group[key].mean()) for key in ("F_minus_E", "E_minus_H", "F_minus_H")}
        for year, group in frame.groupby("year", sort=True)
    }
    body["by_phase"] = {
        str(int(phase)): {key: float(group[key].mean()) for key in ("F_minus_E", "E_minus_H", "F_minus_H")}
        for phase, group in frame.groupby("phase", sort=True)
    }
    return body


def verify_accepted_fh_reconstruction(recomputed: pd.DataFrame, accepted_csv: Path, atol: float = 1e-12) -> None:
    accepted = pd.read_csv(accepted_csv)
    if not np.array_equal(recomputed["day_position"].to_numpy(), accepted["day_position"].to_numpy()):
        raise ValueError("accepted F/H day coordinates changed")
    if not np.allclose(recomputed["F_minus_H"].to_numpy(float), accepted["delta"].to_numpy(float), atol=atol, rtol=0.0):
        raise ValueError("accepted F/H reconstruction mismatch")


def validate_runtime_identity(accepted_run_root: Path, theme_root: Path, expected_factorlab_commit: str, factorlab_root: Path) -> dict[str, Any]:
    accepted_source = read_json(accepted_run_root / "source_snapshot.json")
    accepted_env = read_json(accepted_run_root / "environment.json")
    timeiso_path = theme_root / "src/factor_lab/factor_rotation/reaka_r3_time_isolated_runner.py"
    views_path = theme_root / "src/factor_lab/factor_rotation/reaka_r3_condition_views.py"
    if sha_file(timeiso_path) != EXPECTED_TIMEISO_RUNNER_SHA256 or accepted_source.get("runner_sha256") != EXPECTED_TIMEISO_RUNNER_SHA256:
        raise ValueError("accepted TIMEISO numerical runner identity changed")
    if sha_file(views_path) != EXPECTED_CONDITION_VIEWS_SHA256:
        raise ValueError("condition-view source identity changed")
    import subprocess
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=factorlab_root, capture_output=True, text=True)
    if head.returncode != 0 or head.stdout.strip() != expected_factorlab_commit:
        raise ValueError("FactorLab commit mismatch")
    current_env = current_environment("cpu")
    issues = stable_environment_issues(accepted_env, current_env)
    if issues:
        raise ValueError("stable environment mismatch: " + ",".join(issues))
    return {
        "accepted_source": accepted_source,
        "accepted_environment": accepted_env,
        "current_stable_environment": current_env,
        "timeiso_runner_sha256": EXPECTED_TIMEISO_RUNNER_SHA256,
        "condition_views_sha256": EXPECTED_CONDITION_VIEWS_SHA256,
        "factorlab_commit": expected_factorlab_commit,
    }


def reload_e_worker(store_root: Path, checkpoint_root: Path, normalizer_path: Path, candidate_path: Path,
                    seed: int, indices_path: Path, output_path: Path, device_name: str = "cpu") -> dict[str, Any]:
    pf, tr, timeiso, _, _ = _rt()
    store = pf.IntradayK1InputStore.load(store_root)
    candidate = read_json(candidate_path); normalizer = read_json(normalizer_path)
    model, _ = build_e_model(candidate, seed)
    tr.load_state_tree(model, checkpoint_root)
    scored = timeiso.score_no_labels(model, store, normalizer, np.load(indices_path, allow_pickle=False), device_name)
    timeiso.save_scores(output_path, scored)
    return {"score_count": int(len(scored["scores"])), "target_values_read": 0, "state_digest": tr.state_digest(model)}


def run_clock(accepted_run_root: Path, output_root: Path, clock: str, reload_script: Path) -> dict[str, Any]:
    pf, tr, timeiso, _, _ = _rt()
    accepted_clock = accepted_run_root / clock
    experiment = accepted_clock / "experiment"
    store_root = accepted_clock / "prepared/store"
    store = pf.IntradayK1InputStore.load(store_root)
    normalizer_path = experiment / "normalizer.json"; candidate_path = experiment / "candidate.json"
    normalizer = read_json(normalizer_path); candidate = read_json(candidate_path)
    _ = np.load(experiment / "prediction_indices.npy", allow_pickle=False)
    e_scores: list[dict[str, np.ndarray]] = []
    f_scores: list[dict[str, np.ndarray]] = []
    h_scores: list[dict[str, np.ndarray]] = []
    per_seed_rows: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []

    for seed in SEEDS:
        f_receipt = read_json(experiment / f"models/seed_{seed}/F/fit_receipt.json")
        h_receipt = read_json(experiment / f"models/seed_{seed}/H/fit_receipt.json")
        common = accepted_pair_common(f_receipt, h_receipt)
        model, pre_digest = build_e_model(candidate, seed)
        if pre_digest != common["pre_dmd_state_digest"]:
            raise ValueError(f"E pre-DMD digest mismatch with accepted pair: {clock}/{seed}")
        e_root = output_root / clock / f"models/seed_{seed}/E"
        model, fit = timeiso.fit_arm(model, store, normalizer, seed, MAX_CYCLES_PER_FIT, "cpu")
        checkpoint = e_root / "checkpoint"
        tr.save_state_tree(model, checkpoint)
        reload_spec = {
            "store_root": str(store_root), "checkpoint_root": str(checkpoint),
            "normalizer_path": str(normalizer_path), "candidate_path": str(candidate_path),
            "seed": seed, "indices_path": str(experiment / "prediction_indices.npy"),
            "output_path": str(e_root / "scores.npz"), "device_name": "cpu",
        }
        write_json(e_root / "reload_spec.json", reload_spec)
        import subprocess, sys
        proc = subprocess.run([sys.executable, str(reload_script), "--reload-e-worker", str(e_root / "reload_spec.json")], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"E reload worker failed: {clock}/{seed}: {proc.stderr[-1000:]} {proc.stdout[-1000:]}")
        e = load_scores(e_root / "scores.npz")
        f = load_scores(experiment / f"models/seed_{seed}/F/scores.npz")
        h = load_scores(experiment / f"models/seed_{seed}/H/scores.npz")
        if not _same_score_coordinates(f, e, h):
            raise ValueError(f"F/E/H score coordinates differ: {clock}/{seed}")
        fl = timeiso.attach_labels(store, f); el = timeiso.attach_labels(store, e); hl = timeiso.attach_labels(store, h)
        if not _same_score_coordinates(fl, el, hl):
            raise ValueError(f"F/E/H labelled coordinates differ: {clock}/{seed}")
        daily = daily_triplet(fl["scores"], el["scores"], hl["scores"], fl["targets"], fl["rows"])
        summary = summarize_daily(daily)
        per_seed_rows.append({"clock": clock, "seed": seed, **{k: v["mean"] for k, v in summary.items() if k in ("F_minus_E", "E_minus_H", "F_minus_H")}})
        identity = {"arm": "E", "seed": seed, "clock": clock, **{key: common[key] for key in PAIR_FIELDS}}
        identity["pre_dmd_state_digest"] = pre_digest
        receipt = {"fit": fit, "identity": identity, "checkpoint_state_digest": read_json(checkpoint / "manifest.json")["state_digest"]}
        write_json(e_root / "fit_receipt.json", receipt); receipts.append(receipt)
        f_scores.append(f); e_scores.append(e); h_scores.append(h)

    F = timeiso.attach_labels(store, timeiso.ensemble(f_scores))
    E = timeiso.attach_labels(store, timeiso.ensemble(e_scores))
    H = timeiso.attach_labels(store, timeiso.ensemble(h_scores))
    if not _same_score_coordinates(F, E, H):
        raise ValueError("F/E/H ensemble support mismatch")
    daily = daily_triplet(F["scores"], E["scores"], H["scores"], F["targets"], F["rows"])
    verify_accepted_fh_reconstruction(daily, accepted_clock / "paired_daily.csv")
    output_root.mkdir(parents=True, exist_ok=True)
    daily.to_csv(output_root / clock / "paired_daily.csv", index=False)
    pd.DataFrame(per_seed_rows).to_csv(output_root / clock / "per_seed.csv", index=False)
    result = {"clock": clock, "new_fits": 3, "summary": summarize_daily(daily), "per_seed": per_seed_rows,
              "accepted_FH_reconstruction_verified": True, "receipts": receipts}
    write_json(output_root / clock / "result.json", result)
    return result


def combine_clocks(output_root: Path) -> dict[str, Any]:
    frames = {clock: pd.read_csv(output_root / clock / "paired_daily.csv") for clock in CLOCKS}
    left, right = frames["1430"], frames["1445"]
    if not np.array_equal(left["day_position"].to_numpy(), right["day_position"].to_numpy()):
        raise ValueError("clock day coordinates differ")
    combined = pd.DataFrame({"day_position": left["day_position"]})
    for key in ("F_minus_E", "E_minus_H", "F_minus_H"):
        combined[key] = (left[key].to_numpy(float) + right[key].to_numpy(float)) / 2.0
    _, _, timeiso, _, _ = _rt()
    result: dict[str, Any] = {"days": int(len(combined))}
    for key in ("F_minus_E", "E_minus_H", "F_minus_H"):
        values = combined[key].to_numpy(float)
        result[key] = {
            "mean": float(values.mean()), "median": float(np.median(values)), "win_days": int((values > 0).sum()),
            "moving_block": {str(block): timeiso.block_ci(values, block) for block in (4, 8, 12)},
        }
    combined.to_csv(output_root / "combined_daily.csv", index=False)
    return result


def run(accepted_run_root: Path, output_root: Path, reload_script: Path, theme_root: Path,
        factorlab_root: Path, expected_factorlab_commit: str) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError(output_root)
    runtime = validate_runtime_identity(accepted_run_root, theme_root, expected_factorlab_commit, factorlab_root)
    output_root.mkdir(parents=True)
    write_json(output_root / "runtime_identity.json", runtime)
    clocks = {clock: run_clock(accepted_run_root, output_root, clock, reload_script) for clock in CLOCKS}
    total_fits = sum(int(row["new_fits"]) for row in clocks.values())
    if total_fits != MAX_NEW_FITS:
        raise AssertionError("coarse decomposition fit budget drift")
    final = {
        "schema_id": "factorlab.r3_x_coarse_result@1.0", "status": "completed_consumed_historical_only",
        "accepted_timeiso_root": str(accepted_run_root), "new_arm": "E", "new_fits": total_fits,
        "rerun_F": 0, "rerun_H": 0, "max_cycles_per_fit": MAX_CYCLES_PER_FIT,
        "clocks": clocks, "combined": combine_clocks(output_root),
        "interpretation": {
            "E_minus_H": "ordered conditional increment of exposure/reliability/exposure-mask package",
            "F_minus_E": "ordered conditional increment of state-values/state-mask package",
            "unique_additive_causal_attribution": False,
        },
        "fresh_oos": False, "full_pit_certified": False, "production_authority": False,
    }
    write_json(output_root / "result.json", final)
    return final
