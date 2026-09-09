"""Frozen-model 2021--2025 transfer scoring and independent label sidecars.

The model-scoring worker receives no label path. Labels are mapped in a separate
sidecar and are opened only after all 24 score jobs have completed. This module
does not train, select checkpoints, refit normalizers, or read 2026 to complete
2025 labels.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

TASK = "LCL-R3-TRANSFER-EVAL-20260908-01"
LABEL_SCHEMA = "factorlab.r3_transfer_label_bundle@1.0"
SIDECAR_SCHEMA = "factorlab.r3_transfer_label_sidecar@1.0"
RESULT_SCHEMA = "factorlab.r3_transfer_evaluation@1.0"
CLOCKS = ("1430", "1445")
SEEDS = (11, 29, 47)
ARMS = ("F", "STATE_VALUE_PLUS_E", "BETA_ONLY", "BETA_RELIABILITY")
PRIMARY = (
    "F_minus_STATE_VALUE_PLUS_E",
    "BETA_RELIABILITY_minus_BETA_ONLY",
)
ARM_PAIRS = {
    "F_minus_STATE_VALUE_PLUS_E": ("F", "STATE_VALUE_PLUS_E"),
    "BETA_RELIABILITY_minus_BETA_ONLY": ("BETA_RELIABILITY", "BETA_ONLY"),
}
TOP_N = 30
EXPECTED_FACTORLAB_COMMIT = "b39bb12f43a46b165d18db93191a669234077444"
EXPECTED_TIMEISO_RUNNER_SHA256 = "sha256:ee7036f1925ab61ed88cc96e79a0ee06af9bb2a75812a1a58f4aa2d4a61c3708"
EXPECTED_CONDITION_VIEWS_SHA256 = "sha256:7d76a03785e2d03623342c63c360ddf7680835433294f5f511163d09fba2f921"
EXPECTED_X_DECOMP_GIT_BLOB = "040182c3f8571083a83d8df3cd852f82dc1f4e48"
STABLE_ENV_FIELDS = ("python", "platform", "numpy", "pandas", "torch", "device", "cuda_available")


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    def reject(value):
        raise ValueError(f"nonfinite JSON constant: {value}")
    obj = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique, parse_constant=reject)
    if not isinstance(obj, dict):
        raise ValueError(f"JSON object required: {path}")
    return obj


def write_json_new(path: Path, obj: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        f.write(json.dumps(dict(obj), ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def bind_file(path: Path, expected: str) -> str:
    if not isinstance(expected, str) or not expected.startswith("sha256:") or len(expected) != 71:
        raise ValueError(f"explicit SHA256 required: {path}")
    observed = sha_file(path)
    if observed != expected:
        raise ValueError(f"SHA256 mismatch: {path}")
    return observed


def _git_blob(path: Path) -> str:
    p = subprocess.run(["git", "hash-object", str(path)], capture_output=True, text=True)
    if p.returncode:
        raise ValueError(f"cannot hash source: {path}: {p.stderr[-300:]}")
    return p.stdout.strip()


def rankz(values: np.ndarray) -> np.ndarray:
    v = np.asarray(values, float)
    r = rankdata(v)
    centered = r - r.mean()
    scale = centered.std()
    return centered / scale if scale > 0 else np.zeros_like(centered)


def block_ci(values: np.ndarray, block: int, draws: int = 5000, seed: int = 61207) -> dict[str, Any]:
    x = np.asarray(values, float)
    if x.ndim != 1 or len(x) < block or block <= 0 or not np.isfinite(x).all():
        raise ValueError("invalid moving-block input")
    rng = np.random.default_rng(seed)
    starts = np.arange(len(x) - block + 1)
    n = math.ceil(len(x) / block)
    means = np.empty(draws, float)
    for i in range(draws):
        means[i] = np.concatenate([x[s:s+block] for s in rng.choice(starts, n, replace=True)])[:len(x)].mean()
    return {"mean": float(x.mean()), "lower": float(np.quantile(means, .025)),
            "upper": float(np.quantile(means, .975)), "block_length": block,
            "draws": draws, "seed": seed}


def _load_str(path: Path) -> list[str]:
    a = np.load(path, allow_pickle=False)
    if a.ndim != 1 or a.dtype.kind not in "US":
        raise ValueError(f"string axis required: {path}")
    out = a.astype(str).tolist()
    if len(set(out)) != len(out):
        raise ValueError(f"duplicate identifiers: {path}")
    return out


def _json_axis(path: Path, key: str) -> list[str]:
    values = read_json(path).get(key)
    if not isinstance(values, list) or not values or any(not isinstance(x, str) for x in values):
        raise ValueError(f"invalid axis: {path}/{key}")
    if len(set(values)) != len(values):
        raise ValueError(f"duplicate axis: {path}/{key}")
    return list(values)


def _perm(reference: list[str], source: list[str], name: str) -> np.ndarray:
    if len(reference) != len(source) or set(reference) != set(source):
        raise ValueError(f"{name} identity differs")
    lookup = {x: i for i, x in enumerate(source)}
    return np.asarray([lookup[x] for x in reference], dtype=np.int64)


def _compare_prefix_float32(reference: np.ndarray, candidate: np.ndarray, atol: float = 1e-7,
                            block: int = 128) -> dict[str, Any]:
    if reference.dtype != np.float32 or candidate.dtype != np.float32:
        raise ValueError("float32 target matrices required")
    if reference.ndim != 2 or candidate.ndim != 2 or reference.shape[1] != candidate.shape[1]:
        raise ValueError("target prefix shape mismatch")
    if reference.shape[0] > candidate.shape[0]:
        raise ValueError("target bundle shorter than reference")
    compared = support_mismatch = above = 0
    max_abs = 0.0
    for lo in range(0, len(reference), block):
        hi = min(len(reference), lo + block)
        a = np.asarray(reference[lo:hi])
        b = np.asarray(candidate[lo:hi])
        fa, fb = np.isfinite(a), np.isfinite(b)
        support_mismatch += int(np.count_nonzero(fa != fb))
        both = fa & fb
        if both.any():
            err = np.abs(a[both].astype(float) - b[both].astype(float))
            compared += int(len(err))
            above += int(np.count_nonzero(err > atol))
            max_abs = max(max_abs, float(err.max()))
    return {"passed": support_mismatch == 0 and above == 0,
            "finite_cells_compared": compared, "support_mismatches": support_mismatch,
            "above_tolerance": above, "atol": atol, "max_abs_error": max_abs,
            "independent_producer_replay": False}


def build_label_sidecar(feature_store: Path, label_bundle: Path, reference_label_store: Path,
                        output: Path, *, expected_bundle_sha256: str,
                        expected_reference_manifest_sha256: str) -> dict[str, Any]:
    """Map a target-only bundle to feature coordinates; never inspect model scores."""
    feature_store, label_bundle, reference_label_store = map(Path, (feature_store, label_bundle, reference_label_store))
    if output.exists():
        raise FileExistsError(output)
    fm = read_json(feature_store / "manifest.json")
    if fm.get("schema_id") != "factorlab.r3_transfer_feature_store@1.0" or fm.get("status") != "prepared_features_only_not_scored":
        raise ValueError("accepted transfer feature store required")
    bm_path = label_bundle / "bundle.json"
    bind_file(bm_path, expected_bundle_sha256)
    bm = read_json(bm_path)
    if bm.get("schema_id") != LABEL_SCHEMA:
        raise ValueError("wrong label bundle schema")
    if bm.get("calendar_end") != "2025-12-31" or bm.get("contains_2026") is not False:
        raise ValueError("bounded 2025 label bundle required; no 2026 completion")
    if bm.get("target_definition") != "H20_financial_residual_epsilon_future_K1_v1":
        raise ValueError("target definition drift")
    if bm.get("horizon_trading_positions") != 20 or bm.get("labels_used_for_features") is not False:
        raise ValueError("label horizon/feature-separation declaration drift")
    if bm.get("fold_policy") != "explicit_incumbent_symbol_position_mod5":
        raise ValueError("label fold identity drift")
    required = ("calendar.npy", "symbols.npy", "factor_ids.json", "symbol_fold_ids.npy",
                "epsilon_future.npy", "producer_sources.json", "target_anchor_checks.json")
    artifacts = bm.get("artifact_digests", {})
    for name in required:
        bind_file(label_bundle / name, artifacts.get(name))

    anchor_checks = read_json(label_bundle / "target_anchor_checks.json")
    if anchor_checks.get("schema_id") != "factorlab.r3_transfer_target_anchor_checks@1.0" or anchor_checks.get("passed") is not True:
        raise ValueError("bounded target producer anchor checks required")
    if int(anchor_checks.get("anchors_checked", 0)) < 5 or int(anchor_checks.get("support_mismatches", -1)) != 0:
        raise ValueError("insufficient target producer anchor coverage")
    if float(anchor_checks.get("max_abs_error", float("inf"))) > 1e-7:
        raise ValueError("target producer anchor values drift")

    ref_manifest = reference_label_store / "manifest.json"
    bind_file(ref_manifest, expected_reference_manifest_sha256)
    feature_calendar = np.load(feature_store / "calendar.npy", allow_pickle=False).astype("datetime64[D]")
    source_calendar = np.load(label_bundle / "calendar.npy", allow_pickle=False).astype("datetime64[D]")
    ref_calendar = np.load(reference_label_store / "calendar.npy", allow_pickle=False).astype("datetime64[D]")
    if not np.array_equal(feature_calendar, source_calendar) or not np.array_equal(feature_calendar[:len(ref_calendar)], ref_calendar):
        raise ValueError("label calendar identity/prefix drift")
    if source_calendar[-1] != np.datetime64("2025-12-31") or (source_calendar.astype("datetime64[Y]") == np.datetime64("2026")).any():
        raise ValueError("2026 present in label bundle")

    fs = _load_str(feature_store / "symbols.npy")
    ss = _load_str(label_bundle / "symbols.npy")
    rs = _load_str(reference_label_store / "symbols.npy")
    if fs != rs:
        raise ValueError("feature store no longer uses accepted symbol order")
    smap = _perm(fs, ss, "label symbols")
    ff = _json_axis(feature_store / "factor_ids.json", "factor_ids")
    sf = _json_axis(label_bundle / "factor_ids.json", "factor_ids")
    rf = _json_axis(reference_label_store / "factor_ids.json", "factor_ids")
    if ff != rf or ff != sf:
        raise ValueError("label factor identity drift")
    folds = np.asarray(np.load(label_bundle / "symbol_fold_ids.npy", allow_pickle=False))
    if folds.ndim != 1 or folds.dtype.kind not in "iu" or len(folds) != len(ss):
        raise ValueError("invalid label fold vector")
    if not np.array_equal(folds[smap].astype(np.int64), np.arange(len(fs), dtype=np.int64) % 5):
        raise ValueError("label producer fold identity drift")

    src = np.load(label_bundle / "epsilon_future.npy", mmap_mode="r", allow_pickle=False)
    ref = np.load(reference_label_store / "epsilon_future.npy", mmap_mode="r", allow_pickle=False)
    if src.dtype != np.float32 or src.shape != (len(source_calendar), len(ss)):
        raise ValueError("epsilon_future target shape/dtype drift")
    if ref.dtype != np.float32 or ref.shape != (len(ref_calendar), len(rs)):
        raise ValueError("reference epsilon_future shape/dtype drift")
    mapped = np.asarray(src[:, smap])
    prefix = _compare_prefix_float32(np.asarray(ref), mapped[:len(ref_calendar)])
    if not prefix["passed"]:
        raise ValueError("historical target prefix differs from accepted K1 target")

    rows = np.asarray(np.load(feature_store / "inference_rows.npy", allow_pickle=False), dtype=np.int64)
    maturity = np.asarray(np.load(feature_store / "maturity_eligible_indices.npy", allow_pickle=False), dtype=np.int64)
    pred = np.asarray(np.load(feature_store / "prediction_indices.npy", allow_pickle=False), dtype=np.int64)
    if not len(pred) or not np.array_equal(pred, np.arange(pred[0], pred[-1] + 1, dtype=np.int64)):
        raise ValueError("prediction indices must retain contiguous appended support")
    if (maturity < pred[0]).any() or (maturity > pred[-1]).any():
        raise ValueError("maturity indices outside prediction support")
    r = rows[maturity]
    target = mapped[r[:, 0], r[:, 1]].astype(np.float32)
    finite = np.isfinite(target)
    eval_idx = maturity[finite]
    eval_rows = rows[eval_idx]
    eval_targets = target[finite]
    if not len(eval_idx):
        raise ValueError("no finite mature 2021--2025 labels")
    years = eval_rows[:, 2]
    if years.min() < 2021 or years.max() > 2025:
        raise ValueError("evaluation labels outside frozen years")
    if np.isinf(mapped).any():
        raise ValueError("infinite target values in bundle")

    output.mkdir(parents=True)
    np.save(output / "evaluation_indices.npy", eval_idx, allow_pickle=False)
    np.save(output / "rows.npy", eval_rows, allow_pickle=False)
    np.save(output / "targets.npy", eval_targets, allow_pickle=False)
    manifest = {"schema_id": SIDECAR_SCHEMA, "status": "prepared_postscore_labels_not_model_input",
                "clock": bm.get("clock"), "calendar_end": "2025-12-31",
                "target_definition": bm["target_definition"], "horizon_trading_positions": 20,
                "prediction_rows_scored_later": int(len(pred)), "maturity_candidates": int(len(maturity)),
                "finite_evaluation_rows": int(len(eval_idx)), "evaluation_days": int(len(np.unique(eval_rows[:, 0]))),
                "years": sorted(np.unique(years).astype(int).tolist()), "prefix_check": prefix,
                "labels_used_for_feature_support": False, "labels_available_to_score_worker": False,
                "uses_2026_to_complete_2025": False, "fresh_oos": False, "PIT_certified": False}
    for p in (output / "evaluation_indices.npy", output / "rows.npy", output / "targets.npy"):
        manifest.setdefault("artifact_digests", {})[p.name] = sha_file(p)
    write_json_new(output / "manifest.json", manifest)
    return manifest


def make_score_jobs(timeiso_root: Path, xfine_root: Path, feature_root: Path, output_root: Path,
                    repo_root: Path, factorlab_root: Path) -> list[dict[str, Any]]:
    """Return exactly 24 label-free worker specs."""
    jobs = []
    for clock in CLOCKS:
        feature = feature_root / "stores" / clock
        candidate = timeiso_root / clock / "experiment/candidate.json"
        for seed in SEEDS:
            for arm in ARMS:
                if arm == "F":
                    root = timeiso_root / clock / "experiment/models" / f"seed_{seed}" / "F"
                else:
                    root = xfine_root / clock / "models" / f"seed_{seed}" / arm
                jobs.append({"schema_id": "factorlab.r3_transfer_score_worker@1.0",
                             "clock": clock, "seed": seed, "arm": arm,
                             "feature_store": str(feature), "candidate_path": str(candidate),
                             "checkpoint_root": str(root / "checkpoint"),
                             "fit_receipt": str(root / "fit_receipt.json"),
                             "output_path": str(output_root / "scores" / clock / f"seed_{seed}" / arm / "scores.npz"),
                             "receipt_path": str(output_root / "scores" / clock / f"seed_{seed}" / arm / "score_receipt.json"),
                             "repo_root": str(repo_root), "factorlab_root": str(factorlab_root),
                             "device_name": "cpu"})
    if len(jobs) != 24:
        raise AssertionError("transfer score budget drift")
    if any(any("label" in key.lower() or "target" in key.lower() for key in job) for job in jobs):
        raise AssertionError("label path leaked into score worker spec")
    return jobs


def current_environment() -> dict[str, Any]:
    import torch
    return {"python": sys.version, "platform": platform.platform(), "numpy": np.__version__,
            "pandas": pd.__version__, "torch": torch.__version__, "device": "cpu",
            "cuda_available": bool(torch.cuda.is_available())}


def validate_environment(accepted: Mapping[str, Any]) -> None:
    observed = current_environment()
    bad = [key for key in STABLE_ENV_FIELDS if accepted.get(key) != observed.get(key)]
    if bad:
        raise ValueError("accepted numerical environment drift: " + ",".join(bad))


def _build_model(candidate: Mapping[str, Any], seed: int, arm: str):
    from factor_lab.factor_rotation import reaka_intraday_k1_training_v1 as tr
    from factor_lab.factor_rotation import reaka_r3_time_isolated_runner as timeiso
    from factor_lab.factor_rotation.reaka_r3_x_decomposition import x_view_model_class
    from factor_lab.factor_rotation.reaka_stage6_daily_engine import Stage6ReakaModel
    if arm == "F":
        model, _h, _digest = timeiso.matched_models(candidate, seed)
        return model
    if arm not in ARMS[1:]:
        raise ValueError("unregistered transfer arm")
    base = tr.build_model(candidate, seed=seed)
    initial = {k: v.detach().cpu().clone() for k, v in base.state_dict().items()}
    cls = x_view_model_class(Stage6ReakaModel, arm)
    model = cls(feature_dim=tr.FEATURE_DIM, config=base.config, arm_id="fixed_k_no_residual")
    model.load_state_dict(initial)
    return model


def _receipt_identity(receipt: Mapping[str, Any], clock: str, seed: int, arm: str) -> dict[str, Any]:
    ident = dict(receipt.get("identity", {}))
    if ident.get("clock") != clock or ident.get("seed") != seed or ident.get("arm") != arm:
        raise ValueError("checkpoint receipt identity mismatch")
    if receipt.get("fit", {}).get("future_target_values_read") != 0:
        raise ValueError("accepted fit receipt read future target")
    return ident


def run_score_worker(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Fresh-process score worker. It has no label/target input by construction."""
    if spec.get("schema_id") != "factorlab.r3_transfer_score_worker@1.0":
        raise ValueError("wrong score worker schema")
    if spec.get("clock") not in CLOCKS or spec.get("seed") not in SEEDS or spec.get("arm") not in ARMS:
        raise ValueError("score worker identity drift")
    if spec.get("device_name") != "cpu":
        raise ValueError("transfer scoring frozen to CPU")
    repo = Path(spec["repo_root"]).resolve()
    factorlab = Path(spec["factorlab_root"]).resolve()
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=factorlab, capture_output=True, text=True)
    if proc.returncode or proc.stdout.strip() != EXPECTED_FACTORLAB_COMMIT:
        raise ValueError("FactorLab commit mismatch")
    timeiso_path = repo / "src/factor_lab/factor_rotation/reaka_r3_time_isolated_runner.py"
    condition_path = repo / "src/factor_lab/factor_rotation/reaka_r3_condition_views.py"
    x_path = repo / "src/factor_lab/factor_rotation/reaka_r3_x_decomposition.py"
    if sha_file(timeiso_path) != EXPECTED_TIMEISO_RUNNER_SHA256:
        raise ValueError("TIMEISO runner source drift")
    if sha_file(condition_path) != EXPECTED_CONDITION_VIEWS_SHA256:
        raise ValueError("condition-view source drift")
    if _git_blob(x_path) != EXPECTED_X_DECOMP_GIT_BLOB:
        raise ValueError("X-decomposition source drift")

    from factor_lab.factor_rotation import reaka_intraday_k1_training_v1 as tr
    from factor_lab.factor_rotation import reaka_r3_time_isolated_runner as timeiso
    from factor_lab.factor_rotation.reaka_r3_transfer_inputs import TransferFeatureStore

    feature = TransferFeatureStore(Path(spec["feature_store"]))
    indices = np.asarray(np.load(feature.root / "prediction_indices.npy", allow_pickle=False), dtype=np.int64)
    candidate = read_json(Path(spec["candidate_path"]))
    receipt = read_json(Path(spec["fit_receipt"]))
    ident = _receipt_identity(receipt, spec["clock"], int(spec["seed"]), spec["arm"])
    if timeiso.jdig(candidate) != ident.get("recipe_digest"):
        raise ValueError("candidate recipe digest mismatch")
    ck_manifest = read_json(Path(spec["checkpoint_root"]) / "manifest.json")
    if ck_manifest.get("state_digest") != receipt.get("checkpoint_state_digest"):
        raise ValueError("checkpoint manifest/receipt mismatch")
    model = _build_model(candidate, int(spec["seed"]), spec["arm"])
    tr.load_state_tree(model, Path(spec["checkpoint_root"]))
    observed_state = tr.state_digest(model)
    if observed_state != ck_manifest.get("state_digest"):
        raise ValueError("loaded checkpoint state digest mismatch")
    scored = timeiso.score_no_labels(model, feature, feature.normalizer, indices, "cpu")
    out = Path(spec["output_path"])
    if out.exists() or Path(spec["receipt_path"]).exists():
        raise FileExistsError("score worker refuses overwrite")
    timeiso.save_scores(out, scored)
    r = {"schema_id": "factorlab.r3_transfer_score_receipt@1.0", "clock": spec["clock"],
         "seed": int(spec["seed"]), "arm": spec["arm"], "score_rows": int(len(scored["scores"])),
         "target_values_read": 0, "label_path_received": False, "checkpoint_state_digest": observed_state,
         "feature_manifest_sha256": sha_file(feature.root / "manifest.json"),
         "candidate_sha256": sha_file(Path(spec["candidate_path"])),
         "normalizer_sha256": sha_file(feature.root / "normalizer.json"),
         "new_model_fits": 0, "fresh_process": True}
    write_json_new(Path(spec["receipt_path"]), r)
    return r


def _load_scores(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as z:
        out = {k: np.asarray(z[k]) for k in ("indices", "scores", "rows")}
    if out["indices"].ndim != 1 or out["scores"].ndim != 1 or out["rows"].ndim != 2:
        raise ValueError("invalid score payload")
    if len(out["indices"]) != len(out["scores"]) or len(out["indices"]) != len(out["rows"]):
        raise ValueError("score payload length mismatch")
    if not np.isfinite(out["scores"]).all():
        raise ValueError("nonfinite scores")
    return out


def _sidecar(root: Path) -> dict[str, np.ndarray]:
    m = read_json(root / "manifest.json")
    if m.get("schema_id") != SIDECAR_SCHEMA or m.get("status") != "prepared_postscore_labels_not_model_input":
        raise ValueError("accepted label sidecar required")
    out = {name: np.asarray(np.load(root / (name + ".npy"), allow_pickle=False))
           for name in ("evaluation_indices", "rows", "targets")}
    for name, value in out.items():
        bind_file(root / (name + ".npy"), m["artifact_digests"][name + ".npy"])
    if not np.isfinite(out["targets"]).all():
        raise ValueError("nonfinite sidecar targets")
    return out


def _select_evaluation(score: Mapping[str, np.ndarray], side: Mapping[str, np.ndarray]) -> np.ndarray:
    idx = np.asarray(score["indices"], dtype=np.int64)
    wanted = np.asarray(side["evaluation_indices"], dtype=np.int64)
    pos = np.searchsorted(idx, wanted)
    if (pos >= len(idx)).any() or not np.array_equal(idx[pos], wanted):
        raise ValueError("label evaluation coordinates absent from score support")
    if not np.array_equal(np.asarray(score["rows"])[pos], side["rows"]):
        raise ValueError("label rows disagree with score rows")
    return pos


def _decile(score: np.ndarray, target: np.ndarray) -> float:
    order = np.argsort(score, kind="mergesort")
    n = max(1, len(order) // 10)
    return float(target[order[-n:]].mean() - target[order[:n]].mean())


def _top30(score: np.ndarray, target: np.ndarray) -> float:
    order = np.argsort(score, kind="mergesort")
    return float(target[order[-TOP_N:]].mean() - target.mean())


def daily_transfer(scores: Mapping[str, np.ndarray], targets: np.ndarray, rows: np.ndarray) -> pd.DataFrame:
    if tuple(scores) != ARMS:
        raise ValueError("four frozen arms required in fixed order")
    out = []
    for day in np.unique(rows[:, 0]):
        mask = rows[:, 0] == day
        if int(mask.sum()) < TOP_N:
            continue
        y = np.asarray(targets[mask], float)
        rankic, decile, top = {}, {}, {}
        for arm in ARMS:
            s = np.asarray(scores[arm][mask], float)
            rho = float(spearmanr(s, y).statistic)
            if not math.isfinite(rho):
                raise ValueError(f"nonfinite daily RankIC: {arm}")
            rankic[arm] = rho
            decile[arm] = _decile(s, y)
            top[arm] = _top30(s, y)
        row = {"day_position": int(day), "year": int(rows[mask, 2][0]),
               "phase": int(rows[mask, 3][0]), "n": int(mask.sum())}
        for arm in ARMS:
            row[f"rankic_{arm}"] = rankic[arm]
            row[f"decile_{arm}"] = decile[arm]
            row[f"top30_{arm}"] = top[arm]
        for name, (left, right) in ARM_PAIRS.items():
            row[name] = rankic[left] - rankic[right]
            row["decile_" + name] = decile[left] - decile[right]
            row["top30_" + name] = top[left] - top[right]
        out.append(row)
    if not out:
        raise ValueError("no paired transfer days")
    return pd.DataFrame(out)


def summarize(frame: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {"days": int(len(frame))}
    for metric in PRIMARY:
        x = frame[metric].to_numpy(float)
        out[metric] = {"mean": float(x.mean()), "median": float(np.median(x)),
                       "win_days": int((x > 0).sum()), "loss_days": int((x < 0).sum()),
                       "moving_block": {str(b): block_ci(x, b) for b in (4, 8, 12) if len(x) >= b}}
    out["by_year"] = {str(int(y)): {m: float(g[m].mean()) for m in PRIMARY}
                      for y, g in frame.groupby("year", sort=True)}
    out["by_phase"] = {str(int(p)): {m: float(g[m].mean()) for m in PRIMARY}
                       for p, g in frame.groupby("phase", sort=True)}
    for prefix in ("decile_", "top30_"):
        out[prefix.rstrip("_")] = {m: float(frame[prefix + m].mean()) for m in PRIMARY}
    return out


def _ensemble_seed_scores(items: list[Mapping[str, np.ndarray]]) -> np.ndarray:
    if len(items) != 3:
        raise ValueError("exactly three frozen seeds required")
    idx, rows = items[0]["indices"], items[0]["rows"]
    for item in items[1:]:
        if not np.array_equal(idx, item["indices"]) or not np.array_equal(rows, item["rows"]):
            raise ValueError("seed score coordinates differ")
    stack = np.stack([np.asarray(x["scores"], float) for x in items])
    result = np.zeros(len(idx), float)
    for day in np.unique(rows[:, 0]):
        mask = rows[:, 0] == day
        result[mask] = np.mean(np.stack([rankz(s[mask]) for s in stack]), axis=0)
    return result


def evaluate_clock(score_root: Path, sidecar_root: Path, clock: str, output: Path) -> dict[str, Any]:
    side = _sidecar(sidecar_root)
    raw: dict[str, list[dict[str, np.ndarray]]] = {arm: [] for arm in ARMS}
    per_seed = []
    base_idx = base_rows = None
    for seed in SEEDS:
        loaded = {}
        for arm in ARMS:
            payload = _load_scores(score_root / clock / f"seed_{seed}" / arm / "scores.npz")
            pos = _select_evaluation(payload, side)
            loaded[arm] = {**payload, "eval_scores": payload["scores"][pos]}
            raw[arm].append(payload)
            if base_idx is None:
                base_idx, base_rows = payload["indices"], payload["rows"]
            elif not np.array_equal(base_idx, payload["indices"]) or not np.array_equal(base_rows, payload["rows"]):
                raise ValueError("arm/seed score support differs")
        frame = daily_transfer({arm: loaded[arm]["eval_scores"] for arm in ARMS},
                               side["targets"], side["rows"])
        row = {"clock": clock, "seed": seed, "days": int(len(frame))}
        row.update({m: float(frame[m].mean()) for m in PRIMARY})
        per_seed.append(row)

    ensemble_eval = {}
    for arm in ARMS:
        ensemble = _ensemble_seed_scores(raw[arm])
        template = raw[arm][0]
        pos = _select_evaluation({"indices": template["indices"], "rows": template["rows"],
                                  "scores": ensemble}, side)
        ensemble_eval[arm] = ensemble[pos]
    daily = daily_transfer(ensemble_eval, side["targets"], side["rows"])
    output.mkdir(parents=True, exist_ok=True)
    daily.to_csv(output / "paired_daily.csv", index=False)
    pd.DataFrame(per_seed).to_csv(output / "per_seed.csv", index=False)
    result = {"clock": clock, "evaluation_rows": int(len(side["targets"])),
              "summary": summarize(daily), "per_seed": per_seed,
              "label_sidecar_sha256": sha_file(sidecar_root / "manifest.json")}
    write_json_new(output / "result.json", result)
    return result


def combine_clocks(results_root: Path, output: Path) -> dict[str, Any]:
    frames = {c: pd.read_csv(results_root / c / "paired_daily.csv") for c in CLOCKS}
    left, right = frames["1430"], frames["1445"]
    if not np.array_equal(left["day_position"].to_numpy(), right["day_position"].to_numpy()):
        raise ValueError("two-clock evaluated dates differ")
    combined = pd.DataFrame({"day_position": left["day_position"], "year": left["year"], "phase": left["phase"]})
    for metric in PRIMARY:
        combined[metric] = (left[metric].to_numpy(float) + right[metric].to_numpy(float)) / 2.0
        combined["decile_" + metric] = (left["decile_" + metric].to_numpy(float) + right["decile_" + metric].to_numpy(float)) / 2.0
        combined["top30_" + metric] = (left["top30_" + metric].to_numpy(float) + right["top30_" + metric].to_numpy(float)) / 2.0
    combined.to_csv(output / "combined_daily.csv", index=False)
    result = summarize(combined)
    write_json_new(output / "combined_result.json", result)
    return result


def validate_job_sources(repo_root: Path, timeiso_root: Path, feature_root: Path, accepted_environment: Path) -> None:
    if sha_file(repo_root / "src/factor_lab/factor_rotation/reaka_r3_time_isolated_runner.py") != EXPECTED_TIMEISO_RUNNER_SHA256:
        raise ValueError("TIMEISO source drift")
    if sha_file(repo_root / "src/factor_lab/factor_rotation/reaka_r3_condition_views.py") != EXPECTED_CONDITION_VIEWS_SHA256:
        raise ValueError("condition-view source drift")
    if _git_blob(repo_root / "src/factor_lab/factor_rotation/reaka_r3_x_decomposition.py") != EXPECTED_X_DECOMP_GIT_BLOB:
        raise ValueError("X-decomposition source drift")
    validate_environment(read_json(accepted_environment))
    for clock in CLOCKS:
        fm = read_json(feature_root / "stores" / clock / "manifest.json")
        if fm.get("status") != "prepared_features_only_not_scored" or fm.get("calendar_end") != "2025-12-31":
            raise ValueError("transfer feature store not accepted/bounded")
        if fm.get("new_model_fits") != 0 or fm.get("labels_read") is not False:
            raise ValueError("feature store evidence boundary drift")
        if sha_file(feature_root / "stores" / clock / "normalizer.json") != sha_file(timeiso_root / clock / "experiment/normalizer.json"):
            raise ValueError("frozen normalizer bytes changed")


def run_transfer_evaluation(spec: Mapping[str, Any], script_path: Path) -> dict[str, Any]:
    if spec.get("schema_id") != "factorlab.r3_transfer_evaluation_run@1.0":
        raise ValueError("wrong transfer evaluation run schema")
    output = Path(spec["output_root"]).resolve()
    if output.exists():
        raise FileExistsError(output)
    timeiso = Path(spec["timeiso_root"]).resolve()
    xfine = Path(spec["xfine_root"]).resolve()
    feature = Path(spec["transfer_feature_root"]).resolve()
    repo = Path(spec["repo_root"]).resolve()
    factorlab = Path(spec["factorlab_root"]).resolve()
    env = Path(spec["accepted_environment"]).resolve()
    sidecars = {c: Path(spec["label_sidecars"][c]).resolve() for c in CLOCKS}
    if set(spec.get("label_sidecars", {})) != set(CLOCKS):
        raise ValueError("both label sidecars required")
    validate_job_sources(repo, timeiso, feature, env)
    output.mkdir(parents=True)
    jobs = make_score_jobs(timeiso, xfine, feature, output, repo, factorlab)
    specs_root = output / "worker_specs"
    for i, job in enumerate(jobs):
        p = specs_root / f"job_{i:02d}.json"
        write_json_new(p, job)
        proc = subprocess.run([sys.executable, str(script_path), "--score-worker", str(p)],
                              capture_output=True, text=True)
        if proc.returncode:
            raise RuntimeError(f"score worker failed {job['clock']}/{job['seed']}/{job['arm']}: "
                               f"{proc.stderr[-500:]} {proc.stdout[-500:]}")
    result_root = output / "evaluation"
    clock_results = {c: evaluate_clock(output / "scores", sidecars[c], c, result_root / c) for c in CLOCKS}
    combined = combine_clocks(result_root, result_root)
    final = {"schema_id": RESULT_SCHEMA, "task_id": TASK,
             "status": "completed_consumed_historical_transfer",
             "score_jobs": 24, "new_model_fits": 0, "checkpoint_selection": 0,
             "labels_opened_after_all_score_jobs": True, "clocks": clock_results,
             "combined": combined, "primary_contrasts": list(PRIMARY),
             "state_mask_interpretation": "algorithm_path_transfer_not_dynamic_mask_signal",
             "fresh_oos": False, "PIT_certified": False, "production_authority": False}
    write_json_new(output / "result.json", final)
    return final
