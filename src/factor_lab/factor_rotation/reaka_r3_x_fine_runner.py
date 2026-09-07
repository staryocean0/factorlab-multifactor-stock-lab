"""Run the pre-registered R3 Stage-B fine direct-X decomposition.

Newly fitted arms only:
- STATE_VALUE_PLUS_E: channels 0:14 and 28:70
- BETA_ONLY: channels 28:42
- BETA_RELIABILITY: channels 28:56

Accepted H/E/F are immutable references. The runner refuses result-driven arm
changes, support changes, F/E/H refits, or F+M execution.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from factor_lab.factor_rotation import reaka_r3_x_coarse_runner as coarse

CLOCKS = ("1430", "1445")
SEEDS = (11, 29, 47)
NEW_ARMS = ("STATE_VALUE_PLUS_E", "BETA_ONLY", "BETA_RELIABILITY")
REFERENCE_ARMS = ("F", "E", "H")
MAX_CYCLES_PER_FIT = 3
MAX_NEW_FITS = len(CLOCKS) * len(SEEDS) * len(NEW_ARMS)  # 18
MAX_TOTAL_CYCLES = MAX_NEW_FITS * MAX_CYCLES_PER_FIT  # 54
CONTRASTS = (
    "STATE_VALUE_PLUS_E_minus_E",
    "F_minus_STATE_VALUE_PLUS_E",
    "BETA_ONLY_minus_H",
    "BETA_RELIABILITY_minus_BETA_ONLY",
    "E_minus_BETA_RELIABILITY",
)


def read_json(path: Path) -> dict[str, Any]:
    body = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise ValueError(f"JSON object required: {path}")
    return body


def write_json(path: Path, body: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(body), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def build_arm_model(candidate: Mapping[str, Any], seed: int, arm: str):
    if arm not in NEW_ARMS:
        raise ValueError(f"fine runner may fit only {NEW_ARMS}; got {arm}")
    _, tr, _, view, base_cls = coarse._rt()
    base = tr.build_model(candidate, seed=seed)
    initial = {name: value.detach().cpu().clone() for name, value in base.state_dict().items()}
    digest = tr.state_digest(base)
    cls = view(base_cls, arm)
    model = cls(feature_dim=tr.FEATURE_DIM, config=base.config, arm_id="fixed_k_no_residual")
    model.load_state_dict(initial)
    if tr.state_digest(model) != digest:
        raise ValueError(f"{arm} pre-DMD state does not equal base initialization")
    return model, digest


def load_scores(path: Path) -> dict[str, np.ndarray]:
    return coarse.load_scores(path)


def validate_xcoarse_reference(xcoarse_root: Path, timeiso_root: Path) -> dict[str, Any]:
    result = read_json(xcoarse_root / "result.json")
    runtime = read_json(xcoarse_root / "runtime_identity.json")
    if result.get("status") != "completed_consumed_historical_only":
        raise ValueError("xcoarse reference is not completed")
    if result.get("new_arm") != "E" or result.get("new_fits") != 6:
        raise ValueError("xcoarse reference fit budget drift")
    if result.get("rerun_F") != 0 or result.get("rerun_H") != 0:
        raise ValueError("xcoarse reference refit F/H")
    if runtime.get("factorlab_commit") != "b39bb12f43a46b165d18db93191a669234077444":
        raise ValueError("xcoarse FactorLab identity drift")
    if runtime.get("timeiso_runner_sha256") != coarse.EXPECTED_TIMEISO_RUNNER_SHA256:
        raise ValueError("xcoarse TIMEISO runner identity drift")
    if runtime.get("condition_views_sha256") != coarse.EXPECTED_CONDITION_VIEWS_SHA256:
        raise ValueError("xcoarse condition-view identity drift")
    accepted_path = Path(str(result.get("accepted_timeiso_root", "")))
    if accepted_path.name not in {"accepted_view", timeiso_root.name}:
        # Local xcoarse may use an overlay named accepted_view. We bind content via
        # per-clock reconstruction below instead of requiring path equality.
        raise ValueError("unexpected xcoarse accepted TIMEISO reference")
    return {"result": result, "runtime_identity": runtime}


def verify_xcoarse_reconstruction(frame: pd.DataFrame, accepted_csv: Path, atol: float = 1e-12) -> None:
    accepted = pd.read_csv(accepted_csv)
    if not np.array_equal(frame["day_position"].to_numpy(), accepted["day_position"].to_numpy()):
        raise ValueError("xcoarse day coordinates changed")
    for key in ("F_minus_E", "E_minus_H", "F_minus_H"):
        if not np.allclose(frame[key].to_numpy(float), accepted[key].to_numpy(float), atol=atol, rtol=0.0):
            raise ValueError(f"xcoarse reconstruction mismatch: {key}")


def daily_fine(scores: Mapping[str, np.ndarray], targets: np.ndarray, rows: np.ndarray) -> pd.DataFrame:
    required = ("F", "STATE_VALUE_PLUS_E", "E", "BETA_RELIABILITY", "BETA_ONLY", "H")
    if tuple(scores.keys()) != required:
        raise ValueError(f"score arm order must be {required}")
    out: list[dict[str, Any]] = []
    for day in np.unique(rows[:, 0]):
        mask = rows[:, 0] == day
        if int(mask.sum()) < 30:
            continue
        rho: dict[str, float] = {}
        for arm in required:
            value = float(spearmanr(scores[arm][mask], targets[mask]).statistic)
            if not math.isfinite(value):
                break
            rho[arm] = value
        if len(rho) != len(required):
            continue
        row = {
            "day_position": int(day), "year": int(rows[mask, 2][0]),
            "phase": int(rows[mask, 3][0]), "n": int(mask.sum()),
        }
        row.update({f"rankic_{arm}": rho[arm] for arm in required})
        row.update({
            "STATE_VALUE_PLUS_E_minus_E": rho["STATE_VALUE_PLUS_E"] - rho["E"],
            "F_minus_STATE_VALUE_PLUS_E": rho["F"] - rho["STATE_VALUE_PLUS_E"],
            "BETA_ONLY_minus_H": rho["BETA_ONLY"] - rho["H"],
            "BETA_RELIABILITY_minus_BETA_ONLY": rho["BETA_RELIABILITY"] - rho["BETA_ONLY"],
            "E_minus_BETA_RELIABILITY": rho["E"] - rho["BETA_RELIABILITY"],
            "F_minus_E": rho["F"] - rho["E"],
            "E_minus_H": rho["E"] - rho["H"],
            "F_minus_H": rho["F"] - rho["H"],
        })
        state_sum = row["STATE_VALUE_PLUS_E_minus_E"] + row["F_minus_STATE_VALUE_PLUS_E"]
        exposure_sum = row["BETA_ONLY_minus_H"] + row["BETA_RELIABILITY_minus_BETA_ONLY"] + row["E_minus_BETA_RELIABILITY"]
        if abs(state_sum - row["F_minus_E"]) > 1e-12:
            raise AssertionError("state fine contrasts do not close to F-E")
        if abs(exposure_sum - row["E_minus_H"]) > 1e-12:
            raise AssertionError("exposure fine contrasts do not close to E-H")
        out.append(row)
    if not out:
        raise ValueError("no finite fine paired days")
    return pd.DataFrame(out)


def summarize(frame: pd.DataFrame) -> dict[str, Any]:
    keys = (*CONTRASTS, "F_minus_E", "E_minus_H", "F_minus_H")
    body: dict[str, Any] = {"days": int(len(frame))}
    for key in keys:
        values = frame[key].to_numpy(float)
        body[key] = {
            "mean": float(values.mean()), "median": float(np.median(values)),
            "win_days": int((values > 0).sum()), "loss_days": int((values < 0).sum()),
        }
    body["by_year"] = {
        str(int(year)): {key: float(group[key].mean()) for key in keys}
        for year, group in frame.groupby("year", sort=True)
    }
    body["by_phase"] = {
        str(int(phase)): {key: float(group[key].mean()) for key in keys}
        for phase, group in frame.groupby("phase", sort=True)
    }
    return body


def reload_arm_worker(store_root: Path, checkpoint_root: Path, normalizer_path: Path, candidate_path: Path,
                      arm: str, seed: int, indices_path: Path, output_path: Path, device_name: str = "cpu") -> dict[str, Any]:
    if arm not in NEW_ARMS:
        raise ValueError("reload worker refuses non-fine arm")
    pf, tr, timeiso, _, _ = coarse._rt()
    store = pf.IntradayK1InputStore.load(store_root)
    candidate = read_json(candidate_path); normalizer = read_json(normalizer_path)
    model, _ = build_arm_model(candidate, seed, arm)
    tr.load_state_tree(model, checkpoint_root)
    scored = timeiso.score_no_labels(model, store, normalizer, np.load(indices_path, allow_pickle=False), device_name)
    timeiso.save_scores(output_path, scored)
    return {"arm": arm, "score_count": int(len(scored["scores"])), "target_values_read": 0, "state_digest": tr.state_digest(model)}


def _reference_paths(timeiso_clock: Path, xcoarse_clock: Path, seed: int) -> dict[str, Path]:
    experiment = timeiso_clock / "experiment"
    return {
        "F": experiment / f"models/seed_{seed}/F/scores.npz",
        "H": experiment / f"models/seed_{seed}/H/scores.npz",
        "E": xcoarse_clock / f"models/seed_{seed}/E/scores.npz",
    }


def run_clock(timeiso_root: Path, xcoarse_root: Path, output_root: Path, clock: str, reload_script: Path) -> dict[str, Any]:
    pf, tr, timeiso, _, _ = coarse._rt()
    timeiso_clock = timeiso_root / clock
    xcoarse_clock = xcoarse_root / clock
    experiment = timeiso_clock / "experiment"
    store_root = timeiso_clock / "prepared/store"
    store = pf.IntradayK1InputStore.load(store_root)
    normalizer_path = experiment / "normalizer.json"; candidate_path = experiment / "candidate.json"
    normalizer = read_json(normalizer_path); candidate = read_json(candidate_path)
    prediction_indices = experiment / "prediction_indices.npy"

    per_seed: list[dict[str, Any]] = []
    all_scores: dict[str, list[dict[str, np.ndarray]]] = {arm: [] for arm in ("F", *NEW_ARMS, "E", "H")}
    receipts: list[dict[str, Any]] = []

    for seed in SEEDS:
        f_receipt = read_json(experiment / f"models/seed_{seed}/F/fit_receipt.json")
        h_receipt = read_json(experiment / f"models/seed_{seed}/H/fit_receipt.json")
        common = coarse.accepted_pair_common(f_receipt, h_receipt)
        refs = _reference_paths(timeiso_clock, xcoarse_clock, seed)
        reference_scores = {arm: load_scores(path) for arm, path in refs.items()}
        if not coarse._same_score_coordinates(reference_scores["F"], reference_scores["E"], reference_scores["H"]):
            raise ValueError(f"reference F/E/H support mismatch: {clock}/{seed}")

        fine_seed_scores: dict[str, dict[str, np.ndarray]] = {}
        for arm in NEW_ARMS:
            model, pre_digest = build_arm_model(candidate, seed, arm)
            if pre_digest != common["pre_dmd_state_digest"]:
                raise ValueError(f"{arm} pre-DMD digest mismatch: {clock}/{seed}")
            arm_root = output_root / clock / f"models/seed_{seed}/{arm}"
            model, fit = timeiso.fit_arm(model, store, normalizer, seed, MAX_CYCLES_PER_FIT, "cpu")
            checkpoint = arm_root / "checkpoint"
            tr.save_state_tree(model, checkpoint)
            reload_spec = {
                "store_root": str(store_root), "checkpoint_root": str(checkpoint),
                "normalizer_path": str(normalizer_path), "candidate_path": str(candidate_path),
                "arm": arm, "seed": seed, "indices_path": str(prediction_indices),
                "output_path": str(arm_root / "scores.npz"), "device_name": "cpu",
            }
            write_json(arm_root / "reload_spec.json", reload_spec)
            import subprocess, sys
            proc = subprocess.run([sys.executable, str(reload_script), "--reload-fine-worker", str(arm_root / "reload_spec.json")], capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"fresh reload failed: {clock}/{seed}/{arm}: {proc.stderr[-1000:]} {proc.stdout[-1000:]}")
            fine = load_scores(arm_root / "scores.npz")
            if not coarse._same_score_coordinates(reference_scores["F"], fine):
                raise ValueError(f"fine support mismatch: {clock}/{seed}/{arm}")
            receipt = {
                "fit": fit,
                "identity": {"arm": arm, "seed": seed, "clock": clock, **{key: common[key] for key in coarse.PAIR_FIELDS}, "pre_dmd_state_digest": pre_digest},
                "checkpoint_state_digest": read_json(checkpoint / "manifest.json")["state_digest"],
            }
            write_json(arm_root / "fit_receipt.json", receipt)
            receipts.append(receipt); fine_seed_scores[arm] = fine

        ordered_raw = {
            "F": reference_scores["F"],
            "STATE_VALUE_PLUS_E": fine_seed_scores["STATE_VALUE_PLUS_E"],
            "E": reference_scores["E"],
            "BETA_RELIABILITY": fine_seed_scores["BETA_RELIABILITY"],
            "BETA_ONLY": fine_seed_scores["BETA_ONLY"],
            "H": reference_scores["H"],
        }
        labelled = {arm: timeiso.attach_labels(store, payload) for arm, payload in ordered_raw.items()}
        base = labelled["F"]
        if not all(coarse._same_score_coordinates(base, row) for row in labelled.values()):
            raise ValueError("labelled fine coordinates differ")
        frame = daily_fine({arm: labelled[arm]["scores"] for arm in ordered_raw}, base["targets"], base["rows"])
        row = {"clock": clock, "seed": seed}
        for key in CONRASTS if False else CONTRASTS:
            row[key] = float(frame[key].mean())
        per_seed.append(row)
        for arm, payload in ordered_raw.items():
            all_scores[arm].append(payload)

    ensemble_raw = {arm: timeiso.ensemble(items) for arm, items in all_scores.items()}
    ensemble = {arm: timeiso.attach_labels(store, payload) for arm, payload in ensemble_raw.items()}
    base = ensemble["F"]
    if not all(coarse._same_score_coordinates(base, row) for row in ensemble.values()):
        raise ValueError("ensemble fine support mismatch")
    frame = daily_fine({arm: ensemble[arm]["scores"] for arm in ("F", "STATE_VALUE_PLUS_E", "E", "BETA_RELIABILITY", "BETA_ONLY", "H")}, base["targets"], base["rows"])
    coarse_frame = frame[["day_position", "F_minus_E", "E_minus_H", "F_minus_H"]].copy()
    verify_xcoarse_reconstruction(coarse_frame, xcoarse_clock / "paired_daily.csv")
    frame.to_csv(output_root / clock / "paired_daily.csv", index=False)
    pd.DataFrame(per_seed).to_csv(output_root / clock / "per_seed.csv", index=False)
    result = {
        "clock": clock, "new_fits": len(SEEDS) * len(NEW_ARMS), "new_arms": list(NEW_ARMS),
        "reference_refits": {"F": 0, "E": 0, "H": 0},
        "xcoarse_reconstruction_verified": True,
        "summary": summarize(frame), "per_seed": per_seed, "receipts": receipts,
    }
    write_json(output_root / clock / "result.json", result)
    return result


def combine_clocks(output_root: Path) -> dict[str, Any]:
    frames = {clock: pd.read_csv(output_root / clock / "paired_daily.csv") for clock in CLOCKS}
    left, right = frames["1430"], frames["1445"]
    if not np.array_equal(left["day_position"].to_numpy(), right["day_position"].to_numpy()):
        raise ValueError("fine clock coordinates differ")
    combined = pd.DataFrame({"day_position": left["day_position"]})
    keys = (*CONTRASTS, "F_minus_E", "E_minus_H", "F_minus_H")
    for key in keys:
        combined[key] = (left[key].to_numpy(float) + right[key].to_numpy(float)) / 2.0
    # Arithmetic closure is a diagnostic, not a causal decomposition claim.
    if not np.allclose(combined[CONTRASTS[0]] + combined[CONTRASTS[1]], combined["F_minus_E"], atol=1e-12, rtol=0.0):
        raise AssertionError("combined state closure failed")
    if not np.allclose(combined[CONTRASTS[2]] + combined[CONTRASTS[3]] + combined[CONTRASTS[4]], combined["E_minus_H"], atol=1e-12, rtol=0.0):
        raise AssertionError("combined exposure closure failed")
    _, _, timeiso, _, _ = coarse._rt()
    result: dict[str, Any] = {"days": int(len(combined))}
    for key in keys:
        values = combined[key].to_numpy(float)
        result[key] = {
            "mean": float(values.mean()), "median": float(np.median(values)), "win_days": int((values > 0).sum()),
            "moving_block": {str(block): timeiso.block_ci(values, block) for block in (4, 8, 12)},
        }
    combined.to_csv(output_root / "combined_daily.csv", index=False)
    return result


def run(timeiso_root: Path, xcoarse_root: Path, output_root: Path, reload_script: Path,
        theme_root: Path, factorlab_root: Path, expected_factorlab_commit: str) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError(output_root)
    runtime = coarse.validate_runtime_identity(timeiso_root, theme_root, expected_factorlab_commit, factorlab_root)
    xref = validate_xcoarse_reference(xcoarse_root, timeiso_root)
    output_root.mkdir(parents=True)
    write_json(output_root / "runtime_identity.json", {"timeiso": runtime, "xcoarse": xref["runtime_identity"]})
    clocks = {clock: run_clock(timeiso_root, xcoarse_root, output_root, clock, reload_script) for clock in CLOCKS}
    total = sum(int(row["new_fits"]) for row in clocks.values())
    if total != MAX_NEW_FITS:
        raise AssertionError("fine fit budget drift")
    final = {
        "schema_id": "factorlab.r3_x_fine_result@1.0",
        "status": "completed_consumed_historical_only",
        "new_arms": list(NEW_ARMS), "new_fits": total,
        "reference_refits": {"F": 0, "E": 0, "H": 0},
        "max_cycles_per_fit": MAX_CYCLES_PER_FIT, "max_total_cycles": MAX_TOTAL_CYCLES,
        "clocks": clocks, "combined": combine_clocks(output_root),
        "interpretation": {
            "ordered_nested_contrasts_only": True,
            "unique_additive_causal_attribution": False,
            "result_driven_arm_search": False,
        },
        "F_plus_M_executed": False,
        "fresh_oos": False, "full_pit_certified": False, "production_authority": False,
    }
    write_json(output_root / "result.json", final)
    return final
