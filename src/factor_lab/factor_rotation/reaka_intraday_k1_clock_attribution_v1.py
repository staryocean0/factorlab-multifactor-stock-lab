# pyright: reportAny=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false, reportGeneralTypeIssues=false
# pyright: reportAttributeAccessIssue=false, reportIndexIssue=false
# pyright: reportArgumentType=false, reportReturnType=false
# pyright: reportUnusedCallResult=false
"""P6.4.1 paired clock/config attribution and gate-semantics diagnostics."""

from __future__ import annotations

import ast
import inspect
import math
import textwrap
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, cast

import numpy as np
import torch
from numpy.typing import NDArray
from scipy.stats import rankdata, spearmanr

from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    CLOCK_SUFFIX,
    IntradayK1InputStore,
    file_digest,
    normalize_batch,
    read_json,
    write_json,
)
from factor_lab.factor_rotation.reaka_intraday_k1_training_v1 import (
    BATCH_SIZE,
    SEEDS_FORMAL,
    build_model,
    daily_metrics,
    dmd_moments,
    load_state_tree,
    save_state_tree,
    score_rows,
    split_indices,
    train_attempt,
)
from factor_lab.factor_rotation.reaka_paper_v1 import ReakaPaperModel
from factor_lab.factor_rotation.reaka_stage6_daily_engine import Stage6ReakaModel

SCHEMA_ID: Final = "factorlab.reaka_intraday_K1_clock_attribution@1.0"
CONFIG_A: Final = {
    "config_id": "A_d8_h8_lr0p1_c4",
    "candidate_id": "d8_h8_K1_r0",
    "latent_dimension": 8,
    "hidden_dimension": 8,
    "operator_count": 1,
    "residual_identity": "r0_exact_zero",
    "learning_rate": 0.1,
    "cycles": 4,
}
CONFIG_B: Final = {
    "config_id": "B_d16_h16_lr0p03_c3",
    "candidate_id": "d16_h16_K1_r0",
    "latent_dimension": 16,
    "hidden_dimension": 16,
    "operator_count": 1,
    "residual_identity": "r0_exact_zero",
    "learning_rate": 0.03,
    "cycles": 3,
}
CELL_SPECS: Final = (
    {"cell_id": "1430_A", "clock": "14:30", "config": CONFIG_A, "source": "P6_4_control"},
    {"cell_id": "1430_B", "clock": "14:30", "config": CONFIG_B, "source": "P6_4_1_missing"},
    {"cell_id": "1445_A", "clock": "14:45", "config": CONFIG_A, "source": "P6_4_1_missing"},
    {"cell_id": "1445_B", "clock": "14:45", "config": CONFIG_B, "source": "P6_4_control"},
)
DIAGNOSTIC_SAMPLE_ROWS: Final = 32_768


def train_missing_cell(
    *,
    contract: Mapping[str, object],
    cell: Mapping[str, object],
    store_root: Path,
    normalizer: Mapping[str, object],
    output_root: Path,
) -> dict[str, object]:
    if cell.get("source") != "P6_4_1_missing":
        raise ValueError("clock_attribution_control_cell_must_not_retrain")
    store = IntradayK1InputStore.load(store_root)
    config = cast(Mapping[str, object], cell["config"])
    seed_results: list[dict[str, object]] = []
    for seed in SEEDS_FORMAL:
        model, receipt, review_scores = train_attempt(
            candidate=config,
            seed=seed,
            cycles=int(config["cycles"]),
            store=store,
            normalizer=normalizer,
            device_name="rocm",
        )
        checkpoint_relative = f"checkpoints/seed_{seed}"
        checkpoint = save_state_tree(model, output_root / checkpoint_relative)
        np.save(
            output_root / f"review_scores_seed_{seed}.npy",
            review_scores.astype(np.float32),
            allow_pickle=False,
        )
        seed_results.append(
            {
                **receipt,
                "model_state_digest": checkpoint["state_digest"],
                "checkpoint_relative": checkpoint_relative,
                "review_score_digest": file_digest(output_root / f"review_scores_seed_{seed}.npy"),
            }
        )
    return write_json(
        output_root / "fit.json",
        {
            "schema_id": "factorlab.reaka_intraday_K1_clock_attribution_missing_fit@1.0",
            "status": ("passed_diagnostic_fit" if all(row["healthy"] is True for row in seed_results) else "failed_diagnostic_fit"),
            "contract_digest": contract["canonical_digest"],
            "cell_id": cell["cell_id"],
            "clock": cell["clock"],
            "config": dict(config),
            "seed_results": seed_results,
            "2018_rows_read": 0,
            "2019_2020_rows_read": 0,
            "account_run": False,
            "production_authority": False,
        },
    )


def forecast_semantics_audit() -> dict[str, object]:
    source = inspect.getsource(ReakaPaperModel.forecast)
    tree = ast.parse(textwrap.dedent(source))
    transition_calls = sum(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_transition" for node in ast.walk(tree)
    )
    operator_loops = sum(
        isinstance(node, (ast.For, ast.While))
        and any(isinstance(child, ast.Attribute) and child.attr == "_transition" for child in ast.walk(node))
        for node in ast.walk(tree)
    )
    return {
        "forecast_transition_call_count": transition_calls,
        "forecast_recursive_transition_loop_count": operator_loops,
        "current_financial_score_operator_usage": "one_step_full_window_last_decoder_score",
        "recursive_spectral_radius_scope": "future_recursive_rollout_diagnostic_not_current_one_step_hard_gate",
        "passed": transition_calls == 1 and operator_loops == 0,
    }


def _operator_from_moments(
    gram: torch.Tensor,
    cross: torch.Tensor,
    latent_dimension: int,
) -> torch.Tensor:
    ridge = max(1.0e-6, 1.0e-4 * float(torch.trace(gram)) / latent_dimension)
    operator = torch.linalg.solve(
        gram + ridge * torch.eye(latent_dimension, dtype=torch.float64),
        cross.T,
    ).T
    radius = float(torch.linalg.eigvals(operator).abs().max())
    if radius > 1.0:
        operator /= radius
    return operator


def _rankz_by_day(
    scores: NDArray[np.float64],
    days: NDArray[np.int64],
) -> NDArray[np.float64]:
    output = np.zeros_like(scores)
    for day in np.unique(days):
        local = days == day
        ranks = rankdata(scores[local], method="average")
        centered = ranks - ranks.mean()
        output[local] = centered / max(centered.std(ddof=0), 1.0e-12)
    return output


def _quantiles(values: NDArray[np.float64]) -> dict[str, float]:
    return {
        "q50": float(np.quantile(values, 0.50)),
        "q95": float(np.quantile(values, 0.95)),
        "q99": float(np.quantile(values, 0.99)),
    }


def one_step_and_recursive_metrics(
    model: Stage6ReakaModel,
    *,
    store: IntradayK1InputStore,
    normalizer: Mapping[str, object],
    review_indices: NDArray[np.int64],
    device: torch.device,
) -> dict[str, object]:
    sample = review_indices[
        np.unique(
            np.linspace(
                0,
                len(review_indices) - 1,
                min(DIAGNOSTIC_SAMPLE_ROWS, len(review_indices)),
                dtype=np.int64,
            )
        )
    ]
    latent_parts: list[NDArray[np.float64]] = []
    next_parts: list[NDArray[np.float64]] = []
    advanced_parts: list[NDArray[np.float64]] = []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(sample), BATCH_SIZE):
            take = sample[start : start + BATCH_SIZE]
            historical, features = store.assemble_inputs(take)
            returns, normalized_features = normalize_batch(
                historical,
                features,
                normalizer,
            )
            output = model.training_objective(
                torch.from_numpy(returns).to(device),
                torch.from_numpy(normalized_features).to(device),
            )
            latent_parts.append(output.latent[:, -1].detach().cpu().numpy())
            next_parts.append(output.next_latent[:, -1].detach().cpu().numpy())
            advanced_parts.append(output.advanced_latent[:, -1].detach().cpu().numpy())
    latent = np.concatenate(latent_parts).astype(np.float64)
    next_latent = np.concatenate(next_parts).astype(np.float64)
    advanced = np.concatenate(advanced_parts).astype(np.float64)
    one_step_error = float(np.mean(np.square(advanced - next_latent)))
    next_energy = float(np.mean(np.square(next_latent)))
    gain = np.linalg.norm(advanced, axis=1) / np.maximum(
        np.linalg.norm(latent, axis=1),
        1.0e-12,
    )
    operator = model.operators[0].detach().cpu().double().numpy()
    recursive: dict[str, object] = {}
    current = latent.copy()
    initial_norm = np.maximum(np.linalg.norm(latent, axis=1), 1.0e-12)
    for step in range(1, 5):
        current = current @ operator.T
        if step in (1, 2, 4):
            recursive[str(step)] = _quantiles(np.linalg.norm(current, axis=1) / initial_norm)
    return {
        "sample_rows": len(sample),
        "spectral_radius": float(np.max(np.abs(np.linalg.eigvals(operator)))),
        "condition_number": float(np.linalg.cond(operator)),
        "one_step_latent_mse": one_step_error,
        "one_step_latent_relative_mse": one_step_error / max(next_energy, 1.0e-12),
        "one_step_advanced_to_next_rms_ratio": math.sqrt(float(np.mean(np.square(advanced))) / max(next_energy, 1.0e-12)),
        "observed_one_step_gain": _quantiles(gain),
        "recursive_observed_gain": recursive,
    }


def _cell_checkpoint_root(
    *,
    tree: str,
    cell: Mapping[str, object],
    p64_root: Path,
    attribution_root: Path,
) -> Path:
    if cell["source"] == "P6_4_control":
        return p64_root / tree / CLOCK_SUFFIX[str(cell["clock"])]
    return attribution_root / tree / str(cell["cell_id"])


def diagnose_cell(
    *,
    tree: str,
    cell: Mapping[str, object],
    store_root: Path,
    normalizer: Mapping[str, object],
    p64_root: Path,
    attribution_root: Path,
) -> dict[str, object]:
    store = IntradayK1InputStore.load(store_root)
    splits = split_indices(store)
    config = cast(Mapping[str, object], cell["config"])
    root = _cell_checkpoint_root(
        tree=tree,
        cell=cell,
        p64_root=p64_root,
        attribution_root=attribution_root,
    )
    device = torch.device("cuda:0")
    seed_dynamics: list[dict[str, object]] = []
    base_rankz: list[NDArray[np.float64]] = []
    member_rankz: list[NDArray[np.float64]] = []
    input_rankz: list[NDArray[np.float64]] = []
    targets: NDArray[np.float64] | None = None
    days: NDArray[np.int64] | None = None
    phases: NDArray[np.int64] | None = None
    for seed in SEEDS_FORMAL:
        model = build_model(config, seed=seed).to(device)
        load_state_tree(model, root / f"checkpoints/seed_{seed}")
        dynamics = one_step_and_recursive_metrics(
            model,
            store=store,
            normalizer=normalizer,
            review_indices=splits["review"],
            device=device,
        )
        trained_operator = model.operators[0].detach().cpu().double().clone()
        kept_gram, kept_cross, _ = dmd_moments(
            model,
            store=store,
            normalizer=normalizer,
            indices=splits["train"],
            device=device,
            member_drop=True,
        )
        kept_operator = _operator_from_moments(
            kept_gram,
            kept_cross,
            model.config.latent_dim,
        )
        scores, local_targets, local_days, local_phases = score_rows(
            model,
            store=store,
            normalizer=normalizer,
            indices=splits["review"],
            device=device,
        )
        perturbed, _, _, _ = score_rows(
            model,
            store=store,
            normalizer=normalizer,
            indices=splits["review"],
            device=device,
            perturb_seed=9917,
        )
        with torch.no_grad():
            model.operators[0].copy_(kept_operator.float().to(device))
        member, _, _, _ = score_rows(
            model,
            store=store,
            normalizer=normalizer,
            indices=splits["review"],
            device=device,
        )
        with torch.no_grad():
            model.operators[0].copy_(trained_operator.float().to(device))
        base_rankz.append(_rankz_by_day(scores, local_days))
        member_rankz.append(_rankz_by_day(member, local_days))
        input_rankz.append(_rankz_by_day(perturbed, local_days))
        targets = local_targets
        days = local_days
        phases = local_phases
        seed_dynamics.append({"seed": seed, **dynamics})
    assert targets is not None and days is not None and phases is not None
    base = np.vstack(base_rankz).mean(axis=0)
    member = np.vstack(member_rankz).mean(axis=0)
    perturbed = np.vstack(input_rankz).mean(axis=0)
    ensemble_metrics = daily_metrics(base, targets, days, phases)
    return {
        "cell_id": cell["cell_id"],
        "clock": cell["clock"],
        "config": dict(config),
        "source": cell["source"],
        "seed_dynamics": seed_dynamics,
        "mean_spectral_radius": float(np.mean([float(row["spectral_radius"]) for row in seed_dynamics])),
        "mean_one_step_relative_mse": float(np.mean([float(row["one_step_latent_relative_mse"]) for row in seed_dynamics])),
        "mean_recursive_q99_gain_step4": float(
            np.mean(
                [
                    float(cast(Mapping[str, object], cast(Mapping[str, object], row["recursive_observed_gain"])["4"])["q99"])
                    for row in seed_dynamics
                ]
            )
        ),
        "ensemble_review_metrics": ensemble_metrics,
        "ensemble_member_score_spearman": float(spearmanr(base, member).statistic),
        "ensemble_input_score_spearman": float(spearmanr(base, perturbed).statistic),
        "2018_rows_read": 0,
        "2019_2020_rows_read": 0,
        "account_run": False,
        "production_authority": False,
    }


def factorial_effects(
    cells: Mapping[str, Mapping[str, object]],
    metric: str,
) -> dict[str, float]:
    a = float(cells["1430_A"][metric])
    b = float(cells["1430_B"][metric])
    c = float(cells["1445_A"][metric])
    d = float(cells["1445_B"][metric])
    clock_effect = ((c + d) - (a + b)) / 2.0
    config_effect = ((b + d) - (a + c)) / 2.0
    interaction = (d - c) - (b - a)
    total = abs(clock_effect) + abs(config_effect) + abs(interaction)
    return {
        "grand_mean": (a + b + c + d) / 4.0,
        "clock_1445_minus_1430": clock_effect,
        "config_B_minus_A": config_effect,
        "difference_in_differences_interaction": interaction,
        "absolute_clock_share": abs(clock_effect) / max(total, 1.0e-12),
        "absolute_config_share": abs(config_effect) / max(total, 1.0e-12),
        "absolute_interaction_share": abs(interaction) / max(total, 1.0e-12),
    }


def run_attribution(
    *,
    contract: Mapping[str, object],
    tree: str,
    store_base: Path,
    normalizer_base: Path,
    p64_root: Path,
    output_root: Path,
) -> dict[str, object]:
    cells: dict[str, Mapping[str, object]] = {}
    for cell in cast(Sequence[Mapping[str, object]], contract["cells"]):
        clock = str(cell["clock"])
        result = diagnose_cell(
            tree=tree,
            cell=cell,
            store_root=store_base / tree / CLOCK_SUFFIX[clock],
            normalizer=read_json(normalizer_base / CLOCK_SUFFIX[clock] / "normalizer.json"),
            p64_root=p64_root,
            attribution_root=output_root,
        )
        cells[str(cell["cell_id"])] = result
    effects = {
        metric: factorial_effects(cells, metric)
        for metric in (
            "mean_spectral_radius",
            "mean_one_step_relative_mse",
            "mean_recursive_q99_gain_step4",
            "ensemble_member_score_spearman",
            "ensemble_input_score_spearman",
        )
    }
    rankic_cells = {
        key: {
            **value,
            "ensemble_rankic": cast(Mapping[str, object], value["ensemble_review_metrics"])["mean_daily_rankic"],
        }
        for key, value in cells.items()
    }
    effects["ensemble_rankic"] = factorial_effects(
        rankic_cells,
        "ensemble_rankic",
    )
    return write_json(
        output_root / tree / "attribution.json",
        {
            "schema_id": SCHEMA_ID,
            "status": "completed_paired_diagnostic_no_admission_authority",
            "contract_digest": contract["canonical_digest"],
            "forecast_semantics": forecast_semantics_audit(),
            "cells": cells,
            "factorial_effects": effects,
            "2018_rows_read": 0,
            "2019_2020_rows_read": 0,
            "account_run": False,
            "P6_5_execution_allowed": False,
            "production_authority": False,
        },
    )


__all__ = [
    "CELL_SPECS",
    "CONFIG_A",
    "CONFIG_B",
    "SCHEMA_ID",
    "diagnose_cell",
    "factorial_effects",
    "forecast_semantics_audit",
    "one_step_and_recursive_metrics",
    "run_attribution",
    "train_missing_cell",
]
