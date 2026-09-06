#!/usr/bin/env python3
"""LCL-R3-COND-20260906-01: matched F/H comparison with bounded H fits.

Reuse frozen F scores when the original numerical path is intact. Train only
the history-only (H) arm. Do not replace the incumbent, search K/seeds/LR,
run optional E, read 2026, replay accounts, or write sealed output trees.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import platform
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

SEEDS = (11, 29, 47)
CLOCKS = ("1430", "1445")
INPUT_SHA = {
    "1430": "7b8050270c72894ff2e6c67f1fb4a5a5513ca46e8cc0b8c02ed7e0ce3523dfd3",
    "1445": "e979fce98e3a6e67f6e5b2bef2701f100d2b174fcdef4539e417ba3aa0c9a7e7",
}
FORMAL_BLOB = {
    "1430": "57a1ab18761e39cb66001090ac1782bd8eda2d8d",
    "1445": "ab75bd55f2a990dffc2036fa2f03a6295e88ec64",
}
FIT_PREFIX_BLOB = "f2538b64478c1c05a16c347e69864751661af4cb"
TRAINING_BLOB = "94f6fb1eafb2d02cdad4a3cc2883884ef9356852"
PREFLIGHT_BLOB = "6942fb2dc20d24307578bc7dda45368afaf3d1f5"
MAX_H_FITS = 6
MAX_CYCLES = 3

THEME_ROOT = Path(__file__).resolve().parents[1]


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def attach_factorlab(root: Path) -> None:
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def verify_source_blobs(factorlab_root: Path) -> dict[str, str]:
    rotation = factorlab_root / "src/factor_lab/factor_rotation"
    mapping = {
        "fit_prefix": (rotation / "reaka_intraday_k1_fit_prefix_successor_v1.py", FIT_PREFIX_BLOB),
        "training": (rotation / "reaka_intraday_k1_training_v1.py", TRAINING_BLOB),
        "preflight": (rotation / "reaka_intraday_k1_preflight_v1.py", PREFLIGHT_BLOB),
    }
    observed = {}
    for name, (path, expected) in mapping.items():
        blob = git_blob(path)
        if blob != expected:
            raise ValueError(f"{name} blob {blob} != {expected}; F is not reusable on this path")
        observed[name] = blob
    return observed


def record_f_reuse_decision(factorlab_root: Path) -> dict[str, Any]:
    """Write this before any H 2017 metric is computed."""
    known = factorlab_root / "output/factor-rotation/reaka_current_k1_residual_input_ablation_v1_2011_2026"
    return {
        "f_reused": True,
        "reason": (
            "Original fit-prefix/training/preflight git blobs match the R3 design. "
            "Input manifests and formal.json blobs match the accepted NOFIT F scores. "
            "No same-recipe history-only (H) result exists in the known related directories. "
            "The residual-input ablation tree is a different intervention and is not reused as H. "
            "H will wrap FactorLab Stage6ReakaModel only at _encode_and_gate after original "
            "normalize_batch; F scores stay the frozen npy files. F is not retrained."
        ),
        "fallback_joint_fh_fits": False,
        "known_related_dirs_checked": [
            str(known.relative_to(factorlab_root)) if known.exists() else "reaka_current_k1_residual_input_ablation_v1_2011_2026_absent"
        ],
        "rejected_as_H": ["reaka_current_k1_residual_input_ablation_v1_2011_2026"],
        "optional_E_executed": False,
        "max_new_fits": MAX_H_FITS,
        "max_cycles_per_fit": MAX_CYCLES,
        "device_for_H": "cpu",
        "original_F_source_device": "cuda:0",
        "device_limitation": "Local torch has no CUDA/ROCm; H trains on CPU. Frozen F scores are not retrained.",
        "looked_at_new_2017_scores_before_recording_this": False,
    }


def build_controlled_model(arm: str, seed: int):
    from factor_lab.factor_rotation.reaka_intraday_k1_fit_prefix_successor_v1 import FIXED_CONFIG
    from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import FEATURE_DIM
    from factor_lab.factor_rotation.reaka_intraday_k1_training_v1 import BATCH_SIZE, configure_determinism
    from factor_lab.factor_rotation.reaka_paper_v1 import ReakaPaperConfig
    from factor_lab.factor_rotation.reaka_stage6_parameter_calibration import apply_declared_initialization
    from factor_lab.factor_rotation.reaka_stage6_daily_engine import Stage6ReakaModel

    views = load_module(
        "reaka_r3_condition_views",
        THEME_ROOT / "src/factor_lab/factor_rotation/reaka_r3_condition_views.py",
    )
    configure_determinism(seed)
    config = ReakaPaperConfig(
        window_length=10,
        latent_dim=int(FIXED_CONFIG["latent_dimension"]),
        network_hidden_dim=int(FIXED_CONFIG["hidden_dimension"]),
        operator_count=1,
        training_epochs=1,
        diffusion_steps=1,
        batch_size=BATCH_SIZE,
        learning_rate=float(FIXED_CONFIG["learning_rate"]),
        gumbel_temperature=1.0,
        time_embedding_dim=int(FIXED_CONFIG["latent_dimension"]),
        denoiser_hidden_dim=int(FIXED_CONFIG["latent_dimension"]),
        gradient_clip_norm=1.0e12,
        inference_draws=1,
        torch_num_threads=16,
    )
    cls = views.condition_model_class(Stage6ReakaModel, arm)
    model = cls(feature_dim=FEATURE_DIM, config=config, arm_id="fixed_k_no_residual")
    apply_declared_initialization(model, seed=seed)
    return model


def fit_h_seed(*, seed: int, store, normalizer, device: torch.device) -> tuple[torch.nn.Module, dict[str, Any]]:
    from factor_lab.factor_rotation.reaka_intraday_k1_fit_prefix_successor_v1 import FIXED_CONFIG, _parameter_update_ratio
    from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import normalize_batch
    from factor_lab.factor_rotation.reaka_intraday_k1_training_v1 import (
        BATCH_SIZE,
        canonical_loss,
        initialize_dmd,
        split_indices,
    )

    model = build_controlled_model("history_only", seed).to(device)
    splits = split_indices(store)
    if np.any(store.inference_rows[splits["train"], 2] > 2016):
        raise ValueError("train split leaked years after 2016")
    dmd = initialize_dmd(model, store=store, normalizer=normalizer, train_indices=splits["train"], device=device)
    fixed_pre = canonical_loss(model, store=store, normalizer=normalizer, indices=splits["train"], device=device)
    before = [parameter.detach().cpu().clone() for parameter in model.parameters()]
    optimizer = torch.optim.Adam(model.parameters(), lr=float(FIXED_CONFIG["learning_rate"]), weight_decay=0.0)
    best_loss = math.inf
    best_cycle = 0
    best_state = None
    cycle_rows: list[dict[str, Any]] = []
    for cycle in range(1, MAX_CYCLES + 1):
        rng = np.random.default_rng(seed * 10_000 + cycle)
        order = splits["train"][rng.permutation(len(splits["train"]))]
        total = 0.0
        seen = 0
        gradient_max = 0.0
        model.train()
        for start in range(0, len(order), BATCH_SIZE):
            take = order[start : start + BATCH_SIZE]
            historical, features = store.assemble_inputs(take)
            returns, normalized_features = normalize_batch(historical, features, normalizer)
            optimizer.zero_grad(set_to_none=True)
            output = model.training_objective(
                torch.from_numpy(returns).to(device),
                torch.from_numpy(normalized_features).to(device),
            )
            if not bool(torch.isfinite(output.total_loss)):
                raise RuntimeError(f"h_nonfinite_loss:seed{seed}:cycle{cycle}")
            output.total_loss.backward()
            squared = 0.0
            for parameter in model.parameters():
                if parameter.grad is not None:
                    if not bool(torch.isfinite(parameter.grad).all()):
                        raise RuntimeError("h_nonfinite_gradient")
                    squared += float(torch.square(parameter.grad.detach().float()).sum().cpu())
            gradient_max = max(gradient_max, math.sqrt(squared))
            optimizer.step()
            total += float(output.total_loss.detach().cpu()) * len(take)
            seen += len(take)
        current = canonical_loss(model, store=store, normalizer=normalizer, indices=splits["train"], device=device)
        cycle_rows.append(
            {
                "cycle": cycle,
                "mean_train_loss": total / seen,
                "canonical_train_loss": current,
                "gradient_norm_max": gradient_max,
            }
        )
        if current < best_loss:
            best_loss = current
            best_cycle = cycle
            best_state = {name: tensor.detach().cpu().clone() for name, tensor in model.state_dict().items()}
    if best_state is None:
        raise RuntimeError("h_best_state_missing")
    model.load_state_dict(best_state)
    model.to(device)
    return model, {
        "seed": seed,
        "arm": "history_only",
        "fixed_pre_loss": fixed_pre,
        "cycles": cycle_rows,
        "selected_cycle": best_cycle,
        "selected_canonical_loss": best_loss,
        "checkpoint_selection_source": "fit_prefix_canonical_loss_only",
        "2017_used_for_checkpoint_selection": False,
        "update_parameter_ratio": _parameter_update_ratio(model, before),
        "DMD_initialization": dmd,
        "healthy": bool(math.isfinite(best_loss) and best_loss < fixed_pre),
    }


def wiring_check(store, normalizer, device: torch.device) -> dict[str, Any]:
    from factor_lab.factor_rotation.reaka_intraday_k1_fit_prefix_successor_v1 import FIXED_CONFIG
    from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import normalize_batch
    from factor_lab.factor_rotation.reaka_intraday_k1_training_v1 import build_model, split_indices

    splits = split_indices(store)
    take = splits["train"][:8]
    if np.any(store.inference_rows[take, 2] > 2016):
        raise ValueError("wiring batch is not train-prefix")
    historical, features = store.assemble_inputs(take)
    returns, normalized_features = normalize_batch(historical, features, normalizer)
    ret = torch.from_numpy(returns).to(device)
    feat = torch.from_numpy(normalized_features).to(device)
    base = build_model(FIXED_CONFIG, seed=11).to(device)
    wrapped_f = build_controlled_model("history_full", 11).to(device)
    wrapped_h = build_controlled_model("history_only", 11).to(device)
    with torch.no_grad():
        base_out = base.training_objective(ret, feat)
        f_out = wrapped_f.training_objective(ret, feat)
        h1 = wrapped_h.training_objective(ret, feat)
        noisy = feat.clone()
        noisy[:, :, 0:14] = noisy[:, :, 0:14] + 0.37
        noisy[:, :, 28:56] = noisy[:, :, 28:56] + 0.37
        h2 = wrapped_h.training_objective(ret, noisy)
        f_forecast = wrapped_f.forecast(ret, feat).scores
        h_forecast = wrapped_h.forecast(ret, feat).scores
        h_forecast_noisy = wrapped_h.forecast(ret, noisy).scores
    loss_gap = float(abs(base_out.total_loss - f_out.total_loss))
    latent_gap = float(torch.max(torch.abs(base_out.latent - f_out.latent)))
    h_loss_gap = float(abs(h1.total_loss - h2.total_loss))
    h_latent_gap = float(torch.max(torch.abs(h1.latent - h2.latent)))
    h_score_gap = float(torch.max(torch.abs(h_forecast - h_forecast_noisy)))
    if loss_gap > 1e-6 or latent_gap > 1e-5:
        raise ValueError(f"history_full wrap is not F-identical: loss_gap={loss_gap} latent_gap={latent_gap}")
    if h_loss_gap > 1e-6 or h_latent_gap > 1e-5 or h_score_gap > 1e-5:
        raise ValueError("history_only still depends on X")
    return {
        "train_batch_rows": int(len(take)),
        "max_train_year": int(store.inference_rows[splits["train"], 2].max()),
        "f_wrap_loss_gap": loss_gap,
        "f_wrap_latent_gap": latent_gap,
        "h_x_loss_gap": h_loss_gap,
        "h_x_latent_gap": h_latent_gap,
        "h_x_forecast_gap": h_score_gap,
        "f_forecast_finite": bool(torch.isfinite(f_forecast).all()),
        "passed": True,
        "2017_metrics_read": False,
    }


def compare_clock(factorlab_root: Path, clock: str, h_scores: np.ndarray, frozen) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    store_root = factorlab_root / "output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020/formal" / clock
    fit_root = factorlab_root / "output/factor-rotation/reaka_intraday_K1_fit_prefix_successor_v1_2011_2017/formal" / clock
    from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import IntradayK1InputStore
    from factor_lab.factor_rotation.reaka_intraday_k1_training_v1 import split_indices

    store = IntradayK1InputStore.load(store_root)
    splits = split_indices(store)
    idx = splits["review"]
    rows = np.asarray(store.inference_rows[idx])
    history_end = np.asarray(store.epsilon_history)[rows[:, 0, None] + np.arange(-180, 1, 20)[None, :], rows[:, 1, None]]
    target = np.asarray(store.epsilon_future)[rows[:, 0], rows[:, 1]].astype(float)
    f_seed_scores = []
    identities = []
    formal = json.loads((fit_root / "formal.json").read_text())
    by_seed = {int(row["seed"]): row for row in formal["seed_results"]}
    for seed in SEEDS:
        path = fit_root / f"review_scores_seed_{seed}.npy"
        observed = file_sha(path)
        if observed != by_seed[seed]["review_score_digest"]:
            raise ValueError(f"F score identity mismatch {clock} {seed}")
        score = np.asarray(np.load(path, allow_pickle=False), dtype=float)
        if score.shape != (len(idx),) or score.shape != h_scores[seed].shape:
            raise ValueError("F/H score support mismatch")
        f_seed_scores.append(score)
        identities.append({"relative_path": str(path.relative_to(factorlab_root)), "sha256": observed})
    f_pred = frozen.rankz_ensemble(np.vstack(f_seed_scores), rows[:, 0])
    h_pred = frozen.rankz_ensemble(np.vstack([h_scores[seed] for seed in SEEDS]), rows[:, 0])
    prediction = {"K1": f_pred, "H": h_pred, **frozen.baselines(history_end)}
    daily = frozen.daily_comparisons(prediction, target, rows, np.asarray(store.calendar))
    summary = frozen.summarize(daily)
    summary["F"] = summary["K1"]
    for row in daily:
        if row["predictor"] == "K1":
            row["predictor"] = "F"
        row["clock"] = clock
    return {
        "clock": clock,
        "status": "completed_consumed_diagnostic",
        "support_rows": int(len(idx)),
        "support_days": int(summary["K1"]["days"]),
        "consumed_files": identities,
        "results": summary,
        "fresh_oos": False,
        "production_authority": False,
    }, daily


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factorlab-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.factorlab_root.resolve()
    out = args.output_dir.resolve()
    if out.exists() or out.is_relative_to(root / "output") or out.is_relative_to(root / "data"):
        raise ValueError("choose a NEW output directory outside sealed data/output trees")
    out.mkdir(parents=True)

    attach_factorlab(root)
    blobs = verify_source_blobs(root)
    frozen = load_module("reaka_r3_frozen_compare", THEME_ROOT / "scripts/reaka_r3_frozen_compare.py")
    identity = record_f_reuse_decision(root)
    identity["source_blobs"] = blobs
    identity["script_sha256"] = file_sha(Path(__file__))
    dump_json(out / "identity_pre_result.json", identity)

    from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import IntradayK1InputStore, normalizer_from_store
    from factor_lab.factor_rotation.reaka_intraday_k1_training_v1 import score_rows, split_indices

    device = torch.device("cpu")
    fit_receipts: list[dict[str, Any]] = []
    daily_all: list[dict[str, Any]] = []
    clock_results: list[dict[str, Any]] = []
    n_fits = 0
    failed = False
    for clock in CLOCKS:
        store_root = root / "output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020/formal" / clock
        fit_root = root / "output/factor-rotation/reaka_intraday_K1_fit_prefix_successor_v1_2011_2017/formal" / clock
        if file_sha(store_root / "manifest.json") != "sha256:" + INPUT_SHA[clock]:
            raise ValueError(f"input manifest identity changed: {clock}")
        formal_bytes = (fit_root / "formal.json").read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(formal_bytes)).encode() + b"\0" + formal_bytes).hexdigest()
        if blob != FORMAL_BLOB[clock]:
            raise ValueError(f"formal receipt identity changed: {clock}")
        store = IntradayK1InputStore.load(store_root)
        normalizer = normalizer_from_store(store)
        dump_json(out / f"wiring_{clock}.json", {**wiring_check(store, normalizer, device), "clock": clock, "normalizer_digest": normalizer.get("canonical_digest")})
        splits = split_indices(store)
        h_scores: dict[int, np.ndarray] = {}
        for seed in SEEDS:
            if n_fits >= MAX_H_FITS:
                raise RuntimeError("H fit budget exceeded")
            model, receipt = fit_h_seed(seed=seed, store=store, normalizer=normalizer, device=device)
            n_fits += 1
            scores, _targets, _days, _phases = score_rows(
                model,
                store=store,
                normalizer=normalizer,
                indices=splits["review"],
                device=device,
            )
            score_path = out / f"h_review_scores_{clock}_seed_{seed}.npy"
            np.save(score_path, scores.astype(np.float32), allow_pickle=False)
            receipt.update(
                {
                    "clock": clock,
                    "n_parameters": int(sum(parameter.numel() for parameter in model.parameters())),
                    "review_score_digest": file_sha(score_path),
                    "local_score_path": str(score_path),
                }
            )
            fit_receipts.append(receipt)
            h_scores[seed] = np.asarray(scores, dtype=float)
            del model
        clock_result, daily = compare_clock(root, clock, h_scores, frozen)
        clock_results.append(clock_result)
        daily_all.extend(daily)

    dump_json(out / "seed_fit_receipts.json", {"n_h_fits": n_fits, "receipts": fit_receipts})
    if daily_all:
        with (out / "paired_daily.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(daily_all[0]))
            writer.writeheader()
            writer.writerows(daily_all)
    report = {
        "task": "LCL-R3-COND-20260906-01",
        "status": "completed" if not failed else "incomplete",
        "exit_code": 0,
        "python": sys.version,
        "numpy": np.__version__,
        "torch": torch.__version__,
        "platform": platform.platform(),
        "script_sha256": file_sha(Path(__file__)),
        "n_h_fits": n_fits,
        "f_reused": True,
        "optional_E_executed": False,
        "checks": clock_results,
        "sample_role": "already_consumed_2017_review",
        "fresh_oos": False,
        "account_replay": False,
        "condition_feature_increment_causal": False,
        "full_pit_certified": False,
        "production_authority": False,
        "limitations": [
            "H trained on CPU; original F scores were produced on cuda:0.",
            "F-H is a same-recipe input ablation on consumed 2017 support, not a causal feature effect.",
            "No iid p-values; overlapping H20 windows.",
            "Optional E arm was not run.",
        ],
    }
    dump_json(out / "comparison.json", report)
    print(json.dumps({"exit_code": 0, "n_h_fits": n_fits, "clocks": [row["clock"] for row in clock_results]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
