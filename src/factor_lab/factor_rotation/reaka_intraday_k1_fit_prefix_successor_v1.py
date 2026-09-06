# pyright: reportAny=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false, reportGeneralTypeIssues=false
# pyright: reportAttributeAccessIssue=false, reportIndexIssue=false
# pyright: reportArgumentType=false, reportReturnType=false
# pyright: reportUnusedCallResult=false
"""P6.4.4 fixed K1 successor with per-seed fit-prefix checkpoint selection."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, cast

import numpy as np
import torch

from factor_lab.factor_rotation.reaka_intraday_k1_clock_attribution_v1 import (
    diagnose_cell,
)
from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    CLOCK_SUFFIX,
    IntradayK1InputStore,
    file_digest,
    normalize_batch,
    write_json,
)
from factor_lab.factor_rotation.reaka_intraday_k1_training_v1 import (
    BATCH_SIZE,
    MAXIMUM_CONDITION_NUMBER,
    SEEDS_FORMAL,
    build_model,
    canonical_loss,
    initialize_dmd,
    save_state_tree,
    score_rows,
    split_indices,
)

SCHEMA_ID: Final = "factorlab.reaka_intraday_K1_fit_prefix_successor@1.0"
FIXED_CONFIG: Final = {
    "candidate_id": "d8_h8_lr0p03_max3_fit_prefix_K1_r0",
    "capacity_id": "d8_h8",
    "latent_dimension": 8,
    "hidden_dimension": 8,
    "learning_rate": 0.03,
    "max_cycles": 3,
    "operator_count": 1,
    "residual_identity": "r0_exact_zero",
}


def _parameter_update_ratio(
    model: torch.nn.Module,
    before: Sequence[torch.Tensor],
) -> float:
    left = torch.cat([value.detach().cpu().flatten() for value in before])
    right = torch.cat([value.detach().cpu().flatten() for value in model.parameters()])
    return float(torch.linalg.vector_norm(right - left) / torch.clamp(torch.linalg.vector_norm(left), min=1.0e-12))


def fit_seed(
    *,
    seed: int,
    store: IntradayK1InputStore,
    normalizer: Mapping[str, object],
    device: torch.device,
) -> tuple[torch.nn.Module, dict[str, object], np.ndarray]:
    model = build_model(FIXED_CONFIG, seed=seed).to(device)
    splits = split_indices(store)
    dmd = initialize_dmd(
        model,
        store=store,
        normalizer=normalizer,
        train_indices=splits["train"],
        device=device,
    )
    fixed_pre = canonical_loss(
        model,
        store=store,
        normalizer=normalizer,
        indices=splits["train"],
        device=device,
    )
    before = [parameter.detach().cpu().clone() for parameter in model.parameters()]
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=float(FIXED_CONFIG["learning_rate"]),
        weight_decay=0.0,
    )
    best_loss = math.inf
    best_cycle = 0
    best_state: dict[str, torch.Tensor] | None = None
    cycle_rows: list[dict[str, object]] = []
    for cycle in range(1, int(FIXED_CONFIG["max_cycles"]) + 1):
        rng = np.random.default_rng(seed * 10_000 + cycle)
        order = splits["train"][rng.permutation(len(splits["train"]))]
        total = 0.0
        seen = 0
        gradient_max = 0.0
        model.train()
        for start in range(0, len(order), BATCH_SIZE):
            take = order[start : start + BATCH_SIZE]
            historical, features = store.assemble_inputs(take)
            returns, normalized_features = normalize_batch(
                historical,
                features,
                normalizer,
            )
            optimizer.zero_grad(set_to_none=True)
            output = model.training_objective(
                torch.from_numpy(returns).to(device),
                torch.from_numpy(normalized_features).to(device),
            )
            if not bool(torch.isfinite(output.total_loss)):
                raise RuntimeError(f"fit_prefix_nonfinite_loss:seed{seed}:cycle{cycle}")
            output.total_loss.backward()
            squared = 0.0
            for parameter in model.parameters():
                if parameter.grad is not None:
                    if not bool(torch.isfinite(parameter.grad).all()):
                        raise RuntimeError("fit_prefix_nonfinite_gradient")
                    squared += float(torch.square(parameter.grad.detach().float()).sum().cpu())
            gradient_max = max(gradient_max, math.sqrt(squared))
            optimizer.step()
            total += float(output.total_loss.detach().cpu()) * len(take)
            seen += len(take)
        current = canonical_loss(
            model,
            store=store,
            normalizer=normalizer,
            indices=splits["train"],
            device=device,
        )
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
        raise RuntimeError("fit_prefix_best_state_missing")
    model.load_state_dict(best_state)
    model.to(device)
    update_ratio = _parameter_update_ratio(model, before)
    scores, targets, days, phases = score_rows(
        model,
        store=store,
        normalizer=normalizer,
        indices=splits["review"],
        device=device,
    )
    from factor_lab.factor_rotation.reaka_intraday_k1_training_v1 import daily_metrics

    review = daily_metrics(scores, targets, days, phases)
    healthy = bool(math.isfinite(best_loss) and best_loss < fixed_pre and math.isfinite(update_ratio) and update_ratio < 10.0)
    return (
        model,
        {
            "seed": seed,
            "fixed_pre_loss": fixed_pre,
            "cycles": cycle_rows,
            "selected_cycle": best_cycle,
            "selected_canonical_loss": best_loss,
            "checkpoint_selection_source": "fit_prefix_canonical_loss_only",
            "2017_used_for_checkpoint_selection": False,
            "update_parameter_ratio": update_ratio,
            "DMD_initialization": dmd,
            "review": review,
            "healthy": healthy,
            "2018_rows_read": 0,
            "2019_2020_rows_read": 0,
        },
        scores,
    )


def run_formal(
    *,
    contract: Mapping[str, object],
    tree: str,
    clock: str,
    store_root: Path,
    normalizer: Mapping[str, object],
    output_root: Path,
) -> dict[str, object]:
    store = IntradayK1InputStore.load(store_root)
    device = torch.device("cuda:0")
    seed_results: list[dict[str, object]] = []
    for seed in SEEDS_FORMAL:
        model, receipt, scores = fit_seed(
            seed=seed,
            store=store,
            normalizer=normalizer,
            device=device,
        )
        relative = f"checkpoints/seed_{seed}"
        checkpoint = save_state_tree(model, output_root / relative)
        np.save(
            output_root / f"review_scores_seed_{seed}.npy",
            scores.astype(np.float32),
            allow_pickle=False,
        )
        seed_results.append(
            {
                **receipt,
                "state_digest": checkpoint["state_digest"],
                "checkpoint_relative": relative,
                "review_score_digest": file_digest(output_root / f"review_scores_seed_{seed}.npy"),
            }
        )
    cell = {
        "cell_id": CLOCK_SUFFIX[clock],
        "clock": clock,
        "config": FIXED_CONFIG,
        "source": "P6_4_1_missing",
    }
    diagnostic = diagnose_cell(
        tree=tree,
        cell=cell,
        store_root=store_root,
        normalizer=normalizer,
        p64_root=output_root,
        attribution_root=output_root.parents[1],
    )
    conditions = [float(row["condition_number"]) for row in cast(Sequence[Mapping[str, object]], diagnostic["seed_dynamics"])]
    checks = {
        "all_seed_fit_prefix_health": all(row["healthy"] is True for row in seed_results),
        "all_seed_checkpoint_selection_target_free": all(row["2017_used_for_checkpoint_selection"] is False for row in seed_results),
        "all_seed_condition_number": all(value <= MAXIMUM_CONDITION_NUMBER for value in conditions),
        "ensemble_member_robustness": float(diagnostic["ensemble_member_score_spearman"]) >= 0.95,
        "ensemble_input_robustness": float(diagnostic["ensemble_input_score_spearman"]) >= 0.95,
        "ensemble_rankic_positive": float(cast(Mapping[str, object], diagnostic["ensemble_review_metrics"])["mean_daily_rankic"]) > 0.0,
        "ensemble_spread_positive": float(
            cast(Mapping[str, object], diagnostic["ensemble_review_metrics"])["mean_top_bottom_decile_spread"]
        )
        > 0.0,
    }
    return write_json(
        output_root / "formal.json",
        {
            "schema_id": SCHEMA_ID,
            "status": "passed_retrospective_K1_candidate" if all(checks.values()) else "failed_formal_gate",
            "contract_digest": contract["canonical_digest"],
            "tree_neutral": True,
            "clock": clock,
            "config": FIXED_CONFIG,
            "seed_results": seed_results,
            "diagnostic": diagnostic,
            "checks": checks,
            "2018_rows_read": 0,
            "2019_2020_rows_read": 0,
            "account_run": False,
            "P6_5_execution_allowed": False,
            "production_authority": False,
        },
    )


__all__ = ["FIXED_CONFIG", "SCHEMA_ID", "fit_seed", "run_formal"]
