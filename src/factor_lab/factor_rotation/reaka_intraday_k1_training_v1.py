# pyright: reportAny=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false, reportGeneralTypeIssues=false
# pyright: reportAttributeAccessIssue=false, reportIndexIssue=false
# pyright: reportArgumentType=false, reportReturnType=false
# pyright: reportUnusedCallResult=false
"""P6.4 formal K1/r0 training and operator post-sign for intraday REAKA."""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, cast

import numpy as np
import torch
from numpy.typing import NDArray
from scipy.stats import rankdata, spearmanr

from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    CLOCK_SUFFIX,
    FEATURE_DIM,
    IntradayK1InputStore,
    file_digest,
    normalize_batch,
    read_json,
    write_json,
)
from factor_lab.factor_rotation.reaka_paper_v1 import ReakaPaperConfig
from factor_lab.factor_rotation.reaka_stage6_daily_engine import Stage6ReakaModel
from factor_lab.factor_rotation.reaka_stage6_parameter_calibration import (
    apply_declared_initialization,
)

SCHEMA_ID: Final = "factorlab.reaka_intraday_K1_formal_training@1.0"
SCREEN_SCHEMA_ID: Final = "factorlab.reaka_intraday_K1_capacity_screen@1.0"
FORMAL_SCHEMA_ID: Final = "factorlab.reaka_intraday_K1_formal_fit@1.0"
CONFIRMATION_SCHEMA_ID: Final = "factorlab.reaka_intraday_K1_confirmation@1.0"
SEEDS_SCREEN: Final = (11, 29)
SEEDS_FORMAL: Final = (11, 29, 47)
SCREEN_CYCLES: Final = 4
BATCH_SIZE: Final = 4096
PERTURBATION_ROWS: Final = 16_384
MINIMUM_SEED_SCORE_SPEARMAN: Final = 0.50
MINIMUM_PERTURBATION_SPEARMAN: Final = 0.95
MAXIMUM_MEMBER_OPERATOR_RELATIVE_ERROR: Final = 0.10
MAXIMUM_SPECTRAL_RADIUS: Final = 1.05
FLOAT32_CONDITION_ERROR_BUDGET: Final = 1.0e-3
MAXIMUM_CONDITION_NUMBER: Final = float(FLOAT32_CONDITION_ERROR_BUDGET / np.finfo(np.float32).eps)
VALUE_CHANNELS: Final = tuple(range(14)) + tuple(range(28, 56))


def configure_determinism(seed: int) -> None:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.use_deterministic_algorithms(True)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
    torch.set_num_threads(16)


def split_indices(store: IntradayK1InputStore) -> dict[str, NDArray[np.int64]]:
    years = np.asarray(store.inference_rows[:, 2], dtype=np.int64)
    labelled = np.zeros(len(years), dtype=bool)
    labelled[np.asarray(store.labelled_row_indices, dtype=np.int64)] = True
    return {
        "train": np.flatnonzero(years <= 2016).astype(np.int64),
        "review": np.flatnonzero((years == 2017) & labelled).astype(np.int64),
        "confirmation": np.flatnonzero((years == 2018) & labelled).astype(np.int64),
        "outer_closed": np.flatnonzero(years >= 2019).astype(np.int64),
    }


def build_model(candidate: Mapping[str, object], *, seed: int) -> Stage6ReakaModel:
    configure_determinism(seed)
    latent = int(candidate["latent_dimension"])
    hidden = int(candidate["hidden_dimension"])
    if int(candidate["operator_count"]) != 1 or candidate["residual_identity"] != "r0_exact_zero":
        raise ValueError("intraday_K1_training_identity_invalid")
    config = ReakaPaperConfig(
        window_length=10,
        latent_dim=latent,
        network_hidden_dim=hidden,
        operator_count=1,
        training_epochs=1,
        diffusion_steps=1,
        batch_size=BATCH_SIZE,
        learning_rate=float(candidate["learning_rate"]),
        gumbel_temperature=1.0,
        time_embedding_dim=latent,
        denoiser_hidden_dim=latent,
        gradient_clip_norm=1.0e12,
        inference_draws=1,
        torch_num_threads=16,
    )
    model = Stage6ReakaModel(feature_dim=FEATURE_DIM, config=config, arm_id="fixed_k_no_residual")
    apply_declared_initialization(model, seed=seed)
    return model


def model_parameter_count(model: torch.nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters())


def state_digest(model: torch.nn.Module) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        array = tensor.detach().cpu().contiguous().numpy()
        digest.update(name.encode("utf-8"))
        digest.update(str(array.dtype).encode("ascii"))
        digest.update(str(array.shape).encode("ascii"))
        digest.update(array.tobytes(order="C"))
    return "sha256:" + digest.hexdigest()


def save_state_tree(model: torch.nn.Module, root: Path) -> dict[str, object]:
    if root.exists():
        raise FileExistsError(f"intraday_K1_checkpoint_exists:{root}")
    root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{root.name}.", dir=root.parent))
    try:
        tensors: list[dict[str, object]] = []
        for position, (name, tensor) in enumerate(sorted(model.state_dict().items())):
            filename = f"tensor_{position:03d}.npy"
            np.save(temporary / filename, tensor.detach().cpu().contiguous().numpy(), allow_pickle=False)
            tensors.append(
                {
                    "position": position,
                    "name": name,
                    "filename": filename,
                    "digest": file_digest(temporary / filename),
                }
            )
        manifest = write_json(
            temporary / "manifest.json",
            {
                "schema_id": "factorlab.reaka_intraday_K1_checkpoint@1.0",
                "state_digest": state_digest(model),
                "tensor_count": len(tensors),
                "tensors": tensors,
                "production_authority": False,
            },
        )
        temporary.rename(root)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def load_state_tree(model: torch.nn.Module, root: Path) -> None:
    manifest = read_json(root / "manifest.json")
    state: dict[str, torch.Tensor] = {}
    for row in cast(list[Mapping[str, object]], manifest["tensors"]):
        path = root / str(row["filename"])
        if file_digest(path) != row["digest"]:
            raise ValueError("intraday_K1_checkpoint_tensor_digest_invalid")
        state[str(row["name"])] = torch.from_numpy(np.load(path, allow_pickle=False))
    model.load_state_dict(state)
    if state_digest(model) != manifest["state_digest"]:
        raise ValueError("intraday_K1_checkpoint_state_digest_invalid")


def _operator_from_moments(
    gram: torch.Tensor,
    cross: torch.Tensor,
    latent_dim: int,
) -> tuple[torch.Tensor, dict[str, float]]:
    ridge = max(1.0e-6, 1.0e-4 * float(torch.trace(gram)) / latent_dim)
    operator = torch.linalg.solve(
        gram + ridge * torch.eye(latent_dim, dtype=torch.float64),
        cross.T,
    ).T
    pre_radius = float(torch.linalg.eigvals(operator).abs().max())
    if not math.isfinite(pre_radius):
        raise RuntimeError("intraday_K1_DMD_radius_nonfinite")
    if pre_radius > 1.0:
        operator /= pre_radius
    return operator, {
        "ridge": ridge,
        "pre_projection_spectral_radius": pre_radius,
        "projected_spectral_radius": float(torch.linalg.eigvals(operator).abs().max()),
        "condition_number": float(torch.linalg.cond(operator)),
    }


def dmd_moments(
    model: Stage6ReakaModel,
    *,
    store: IntradayK1InputStore,
    normalizer: Mapping[str, object],
    indices: NDArray[np.int64],
    device: torch.device,
    member_drop: bool = False,
) -> tuple[torch.Tensor, torch.Tensor, int]:
    latent_dim = model.config.latent_dim
    gram = torch.zeros((latent_dim, latent_dim), dtype=torch.float64)
    cross = torch.zeros_like(gram)
    transition_count = 0
    model.eval()
    with torch.no_grad():
        for start in range(0, len(indices), BATCH_SIZE):
            take = indices[start : start + BATCH_SIZE]
            if member_drop:
                symbols = np.asarray(store.inference_rows[take, 1], dtype=np.int64)
                take = take[symbols % 10 != 0]
            if not len(take):
                continue
            historical, features = store.assemble_inputs(take)
            returns, normalized_features = normalize_batch(historical, features, normalizer)
            output = model.training_objective(
                torch.from_numpy(returns).to(device),
                torch.from_numpy(normalized_features).to(device),
            )
            latent = output.latent[:, -1].detach().cpu().double()
            next_latent = output.next_latent[:, -1].detach().cpu().double()
            gram += latent.T @ latent
            cross += next_latent.T @ latent
            transition_count += len(take)
    return gram, cross, transition_count


def initialize_dmd(
    model: Stage6ReakaModel,
    *,
    store: IntradayK1InputStore,
    normalizer: Mapping[str, object],
    train_indices: NDArray[np.int64],
    device: torch.device,
) -> dict[str, object]:
    gram, cross, transitions = dmd_moments(
        model,
        store=store,
        normalizer=normalizer,
        indices=train_indices,
        device=device,
    )
    operator, receipt = _operator_from_moments(gram, cross, model.config.latent_dim)
    with torch.no_grad():
        model.operators[0].copy_(operator.float().to(device))
    return {
        **receipt,
        "raw_transition_count": transitions,
        "operator_digest": hashlib.sha256(operator.numpy().tobytes()).hexdigest(),
    }


def canonical_loss(
    model: Stage6ReakaModel,
    *,
    store: IntradayK1InputStore,
    normalizer: Mapping[str, object],
    indices: NDArray[np.int64],
    device: torch.device,
) -> float:
    take = indices[:BATCH_SIZE]
    historical, features = store.assemble_inputs(take)
    returns, normalized_features = normalize_batch(historical, features, normalizer)
    model.eval()
    with torch.no_grad():
        value = model.training_objective(
            torch.from_numpy(returns).to(device),
            torch.from_numpy(normalized_features).to(device),
        ).total_loss
    return float(value.detach().cpu())


def daily_metrics(
    scores: NDArray[np.float64],
    targets: NDArray[np.float64],
    days: NDArray[np.int64],
    phases: NDArray[np.int64] | None = None,
) -> dict[str, object]:
    rankics: list[float] = []
    spreads: list[float] = []
    phase_values: dict[str, list[float]] = {str(value): [] for value in range(4)}
    for day in np.unique(days):
        local = days == day
        if int(local.sum()) < 30:
            continue
        correlation = float(spearmanr(scores[local], targets[local]).statistic)
        if math.isfinite(correlation):
            rankics.append(correlation)
            if phases is not None:
                phase_values[str(int(phases[local][0]))].append(correlation)
        order = np.argsort(scores[local], kind="mergesort")
        count = max(1, len(order) // 10)
        local_target = targets[local]
        spreads.append(float(local_target[order[-count:]].mean() - local_target[order[:count]].mean()))
    values = np.asarray(rankics, dtype=np.float64)
    if not len(values):
        raise ValueError("intraday_K1_metrics_no_valid_days")
    phase_means = {key: (float(np.mean(local)) if local else None) for key, local in phase_values.items()}
    return {
        "day_count": len(values),
        "mean_daily_rankic": float(values.mean()),
        "daily_rankic_std": float(values.std(ddof=1)),
        "daily_rankic_se": float(values.std(ddof=1) / math.sqrt(len(values))),
        "mean_top_bottom_decile_spread": float(np.mean(spreads)),
        "phase_mean_rankic": phase_means,
        "positive_phase_count": sum(value is not None and value > 0.0 for value in phase_means.values()),
    }


def score_rows(
    model: Stage6ReakaModel,
    *,
    store: IntradayK1InputStore,
    normalizer: Mapping[str, object],
    indices: NDArray[np.int64],
    device: torch.device,
    perturb_seed: int | None = None,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.int64],
    NDArray[np.int64],
]:
    score_parts: list[NDArray[np.float64]] = []
    target_parts: list[NDArray[np.float64]] = []
    day_parts: list[NDArray[np.int64]] = []
    phase_parts: list[NDArray[np.int64]] = []
    rng = np.random.default_rng(perturb_seed) if perturb_seed is not None else None
    model.eval()
    with torch.no_grad():
        for start in range(0, len(indices), BATCH_SIZE):
            take = indices[start : start + BATCH_SIZE]
            historical, features, target = store.assemble_batch(take)
            returns, normalized_features = normalize_batch(historical, features, normalizer)
            if rng is not None:
                returns += rng.normal(0.0, 0.01, returns.shape).astype(np.float32)
                noise = rng.normal(0.0, 0.01, normalized_features[:, :, VALUE_CHANNELS].shape).astype(np.float32)
                normalized_features[:, :, VALUE_CHANNELS] += noise
            forecast = model.forecast(
                torch.from_numpy(returns).to(device),
                torch.from_numpy(normalized_features).to(device),
            )
            score_parts.append(forecast.scores.detach().cpu().numpy().astype(np.float64))
            target_parts.append(target.astype(np.float64))
            rows = np.asarray(store.inference_rows[take], dtype=np.int64)
            day_parts.append(rows[:, 0])
            phase_parts.append(rows[:, 3])
    return (
        np.concatenate(score_parts),
        np.concatenate(target_parts),
        np.concatenate(day_parts),
        np.concatenate(phase_parts),
    )


def _update_ratio(model: torch.nn.Module, before: Sequence[torch.Tensor]) -> float:
    left = torch.cat([value.detach().cpu().flatten() for value in before])
    right = torch.cat([value.detach().cpu().flatten() for value in model.parameters()])
    return float(torch.linalg.vector_norm(right - left) / torch.clamp(torch.linalg.vector_norm(left), min=1.0e-12))


def train_attempt(
    *,
    candidate: Mapping[str, object],
    seed: int,
    cycles: int,
    store: IntradayK1InputStore,
    normalizer: Mapping[str, object],
    device_name: str,
) -> tuple[Stage6ReakaModel, dict[str, object], NDArray[np.float64]]:
    device = torch.device("cuda:0" if device_name == "rocm" else "cpu")
    model = build_model(candidate, seed=seed).to(device)
    splits = split_indices(store)
    dmd = initialize_dmd(
        model,
        store=store,
        normalizer=normalizer,
        train_indices=splits["train"],
        device=device,
    )
    fixed_pre_loss = canonical_loss(
        model,
        store=store,
        normalizer=normalizer,
        indices=splits["train"],
        device=device,
    )
    before = [parameter.detach().cpu().clone() for parameter in model.parameters()]
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=float(candidate["learning_rate"]),
        weight_decay=0.0,
    )
    cycle_rows: list[dict[str, object]] = []
    review_scores = np.empty(0, dtype=np.float64)
    for cycle in range(1, cycles + 1):
        rng = np.random.default_rng(seed * 10_000 + cycle)
        order = splits["train"][rng.permutation(len(splits["train"]))]
        total_loss = 0.0
        seen = 0
        gradient_norm_max = 0.0
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
            loss = output.total_loss
            if not bool(torch.isfinite(loss)):
                raise RuntimeError(f"intraday_K1_nonfinite_loss:{candidate['candidate_id']}:{seed}:{cycle}")
            loss.backward()
            squared = 0.0
            for parameter in model.parameters():
                if parameter.grad is not None:
                    if not bool(torch.isfinite(parameter.grad).all()):
                        raise RuntimeError("intraday_K1_nonfinite_gradient")
                    squared += float(torch.square(parameter.grad.detach().float()).sum().cpu())
            gradient_norm_max = max(gradient_norm_max, math.sqrt(squared))
            optimizer.step()
            total_loss += float(loss.detach().cpu()) * len(take)
            seen += len(take)
        current_loss = canonical_loss(
            model,
            store=store,
            normalizer=normalizer,
            indices=splits["train"],
            device=device,
        )
        review_scores, review_targets, review_days, review_phases = score_rows(
            model,
            store=store,
            normalizer=normalizer,
            indices=splits["review"],
            device=device,
        )
        cycle_rows.append(
            {
                "cycle": cycle,
                "mean_train_loss": total_loss / seen,
                "canonical_train_loss": current_loss,
                "gradient_norm_max": gradient_norm_max,
                "review": daily_metrics(
                    review_scores,
                    review_targets,
                    review_days,
                    review_phases,
                ),
            }
        )
    losses = np.asarray([float(row["canonical_train_loss"]) for row in cycle_rows])
    slope = float(np.polyfit(np.arange(1, len(losses) + 1), losses, deg=1)[0]) if len(losses) > 1 else float(losses[0] - fixed_pre_loss)
    update_ratio = _update_ratio(model, before)
    no_sustained_explosion = bool(np.max(losses) <= 4.0 * fixed_pre_loss)
    healthy = bool(
        np.isfinite(losses).all()
        and losses[-1] < fixed_pre_loss
        and slope < 0.0
        and no_sustained_explosion
        and math.isfinite(update_ratio)
        and update_ratio < 10.0
    )
    receipt = {
        "candidate_id": candidate["candidate_id"],
        "candidate": dict(candidate),
        "seed": seed,
        "cycles": cycle_rows,
        "fixed_pre_loss": fixed_pre_loss,
        "canonical_loss_slope": slope,
        "update_parameter_ratio": update_ratio,
        "no_sustained_explosion": no_sustained_explosion,
        "DMD_initialization": dmd,
        "model_parameter_count": model_parameter_count(model),
        "healthy": healthy,
        "fit_rows": len(splits["train"]),
        "review_rows": len(splits["review"]),
        "fit_target_values_read": 0,
        "2018_rows_read": 0,
        "2019_2020_rows_read": 0,
    }
    return model, receipt, review_scores


def select_candidate(attempts: Sequence[Mapping[str, object]]) -> dict[str, object]:
    by_candidate: dict[str, list[Mapping[str, object]]] = {}
    for attempt in attempts:
        by_candidate.setdefault(str(attempt["candidate_id"]), []).append(attempt)
    rows: list[dict[str, object]] = []
    for candidate_id, local in sorted(by_candidate.items()):
        if len(local) != len(SEEDS_SCREEN) or not all(row.get("healthy") is True for row in local):
            continue
        candidate = cast(Mapping[str, object], local[0]["candidate"])
        for cycle_index in range(SCREEN_CYCLES):
            reviews = [
                cast(Mapping[str, object], cast(list[Mapping[str, object]], attempt["cycles"])[cycle_index]["review"]) for attempt in local
            ]
            means = [float(row["mean_daily_rankic"]) for row in reviews]
            ses = [float(row["daily_rankic_se"]) for row in reviews]
            spreads = [float(row["mean_top_bottom_decile_spread"]) for row in reviews]
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "cycle": cycle_index + 1,
                    "mean_daily_rankic": float(np.mean(means)),
                    "daily_rankic_se": float(math.sqrt(np.mean(np.square(ses)))),
                    "mean_top_bottom_decile_spread": float(np.mean(spreads)),
                    "latent_dimension": int(candidate["latent_dimension"]),
                    "hidden_dimension": int(candidate["hidden_dimension"]),
                    "model_parameter_count": int(local[0]["model_parameter_count"]),
                }
            )
    if not rows:
        return {"status": "blocked_no_fully_healthy_candidate", "all_rows": []}
    best = max(rows, key=lambda row: float(row["mean_daily_rankic"]))
    floor = float(best["mean_daily_rankic"]) - float(best["daily_rankic_se"])
    eligible = [row for row in rows if float(row["mean_daily_rankic"]) >= floor]
    selected = min(
        eligible,
        key=lambda row: (
            int(row["model_parameter_count"]),
            int(row["cycle"]),
            str(row["candidate_id"]),
        ),
    )
    return {
        "status": "selected_for_formal_three_seed_fit",
        "best_row": best,
        "one_standard_error_floor": floor,
        "eligible_rows": eligible,
        "selected": selected,
        "all_rows": rows,
    }


def run_screen(
    *,
    contract: Mapping[str, object],
    store_root: Path,
    normalizer: Mapping[str, object],
    decision_clock: str,
    output_path: Path,
) -> dict[str, object]:
    store = IntradayK1InputStore.load(store_root)
    candidates = cast(list[Mapping[str, object]], contract["candidate_family_by_clock"])[0 if decision_clock == "14:30" else 1]
    candidate_rows = cast(list[Mapping[str, object]], candidates["candidates"])
    attempts: list[dict[str, object]] = []
    for candidate in candidate_rows:
        for seed in SEEDS_SCREEN:
            _, receipt, _ = train_attempt(
                candidate=candidate,
                seed=seed,
                cycles=SCREEN_CYCLES,
                store=store,
                normalizer=normalizer,
                device_name=str(candidates["selected_backend"]),
            )
            attempts.append(receipt)
    selection = select_candidate(attempts)
    return write_json(
        output_path,
        {
            "schema_id": SCREEN_SCHEMA_ID,
            "status": selection["status"],
            "master_contract_digest": contract["canonical_digest"],
            "decision_clock": decision_clock,
            "attempts": attempts,
            "selection": selection,
            "scientific_candidate_count": len(candidate_rows),
            "seed_fit_count": len(attempts),
            "checkpoint_attempt_count": len(attempts) * SCREEN_CYCLES,
            "2018_rows_read": 0,
            "2019_2020_rows_read": 0,
            "account_run": False,
            "production_authority": False,
        },
    )


def _spearman(left: NDArray[np.float64], right: NDArray[np.float64]) -> float:
    return float(spearmanr(left, right).statistic)


def operator_postsign(
    model: Stage6ReakaModel,
    *,
    store: IntradayK1InputStore,
    normalizer: Mapping[str, object],
    review_indices: NDArray[np.int64],
    train_indices: NDArray[np.int64],
    device: torch.device,
    seed: int,
) -> dict[str, object]:
    trained = model.operators[0].detach().cpu().double().clone()
    spectral_radius = float(torch.linalg.eigvals(trained).abs().max())
    condition_number = float(torch.linalg.cond(trained))
    full_gram, full_cross, full_count = dmd_moments(
        model,
        store=store,
        normalizer=normalizer,
        indices=train_indices,
        device=device,
    )
    kept_gram, kept_cross, kept_count = dmd_moments(
        model,
        store=store,
        normalizer=normalizer,
        indices=train_indices,
        device=device,
        member_drop=True,
    )
    full_operator, _ = _operator_from_moments(full_gram, full_cross, model.config.latent_dim)
    kept_operator, _ = _operator_from_moments(kept_gram, kept_cross, model.config.latent_dim)
    member_relative_error = float(
        torch.linalg.vector_norm(kept_operator - full_operator) / torch.clamp(torch.linalg.vector_norm(full_operator), min=1.0e-12)
    )
    sample = review_indices[np.unique(np.linspace(0, len(review_indices) - 1, min(PERTURBATION_ROWS, len(review_indices)), dtype=np.int64))]
    base_scores, _, _, _ = score_rows(
        model,
        store=store,
        normalizer=normalizer,
        indices=sample,
        device=device,
    )
    perturbed_scores, _, _, _ = score_rows(
        model,
        store=store,
        normalizer=normalizer,
        indices=sample,
        device=device,
        perturb_seed=seed * 1000 + 73,
    )
    input_spearman = _spearman(base_scores, perturbed_scores)
    with torch.no_grad():
        model.operators[0].copy_(kept_operator.float().to(device))
    member_scores, _, _, _ = score_rows(
        model,
        store=store,
        normalizer=normalizer,
        indices=sample,
        device=device,
    )
    with torch.no_grad():
        model.operators[0].copy_(trained.float().to(device))
    member_score_spearman = _spearman(base_scores, member_scores)
    checks = {
        "condition_number_passed": condition_number <= MAXIMUM_CONDITION_NUMBER,
        "spectral_radius_passed": spectral_radius <= MAXIMUM_SPECTRAL_RADIUS,
        "member_operator_passed": member_relative_error <= MAXIMUM_MEMBER_OPERATOR_RELATIVE_ERROR,
        "member_score_passed": member_score_spearman >= MINIMUM_PERTURBATION_SPEARMAN,
        "input_score_passed": input_spearman >= MINIMUM_PERTURBATION_SPEARMAN,
    }
    support = effective_transition_support(
        store,
        train_indices,
        model.config.latent_dim,
    )
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "trained_operator_condition_number": condition_number,
        "maximum_condition_number": MAXIMUM_CONDITION_NUMBER,
        "trained_operator_spectral_radius": spectral_radius,
        "maximum_spectral_radius": MAXIMUM_SPECTRAL_RADIUS,
        "raw_K1_transition_count": full_count,
        "effective_transition_support": support,
        "member_kept_transition_count": kept_count,
        "member_drop_fraction": 1.0 - kept_count / full_count,
        "member_DMD_operator_relative_error": member_relative_error,
        "maximum_member_operator_relative_error": MAXIMUM_MEMBER_OPERATOR_RELATIVE_ERROR,
        "member_score_spearman": member_score_spearman,
        "input_noise_fraction": 0.01,
        "input_score_spearman": input_spearman,
        "minimum_perturbation_spearman": MINIMUM_PERTURBATION_SPEARMAN,
        "checks": checks,
        "operator_identifiability_claimed": all(checks.values()),
        "production_authority": False,
    }


def pairwise_score_spearman(score_by_seed: Mapping[int, NDArray[np.float64]]) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    seeds = sorted(score_by_seed)
    for left_position, left in enumerate(seeds):
        for right in seeds[left_position + 1 :]:
            rows.append(
                {
                    "left_seed": left,
                    "right_seed": right,
                    "spearman": _spearman(score_by_seed[left], score_by_seed[right]),
                }
            )
    median = float(np.median([float(row["spearman"]) for row in rows]))
    return {
        "pairs": rows,
        "median_spearman": median,
        "minimum_required": MINIMUM_SEED_SCORE_SPEARMAN,
        "passed": median >= MINIMUM_SEED_SCORE_SPEARMAN,
    }


def effective_transition_support(
    store: IntradayK1InputStore,
    indices: NDArray[np.int64],
    latent_dimension: int,
) -> dict[str, object]:
    rows = np.asarray(store.inference_rows[indices], dtype=np.int64)
    _, cross_section_counts = np.unique(rows[:, 0], return_counts=True)
    time_lower = float(len(cross_section_counts) / 4.0)
    median_cross_section = float(np.median(cross_section_counts))
    design_value = float(time_lower * math.sqrt(median_cross_section))
    upper_bound = float(len(rows) / 4.0)
    d_squared = latent_dimension**2
    time_ratio = time_lower / d_squared
    return {
        "K1_operator_occupancy": 1.0,
        "d_squared": d_squared,
        "n_k_eff_time_lower": time_lower,
        "n_k_eff_design_time_x_sqrt_cross_section": design_value,
        "n_k_eff_cross_section_upper_bound": upper_bound,
        "n_k_eff_time_lower_over_d_squared": time_ratio,
        "n_k_eff_design_over_d_squared": design_value / d_squared,
        "n_k_eff_upper_over_d_squared": upper_bound / d_squared,
        "support_diagnostic": ("comfortable" if time_ratio >= 1.0 else "thin_claim_limited"),
    }


def run_formal_fit(
    *,
    contract: Mapping[str, object],
    store_root: Path,
    normalizer: Mapping[str, object],
    decision_clock: str,
    output_root: Path,
) -> dict[str, object]:
    store = IntradayK1InputStore.load(store_root)
    selected_by_clock = cast(Mapping[str, Mapping[str, object]], contract["selected_by_clock"])
    selection = selected_by_clock[CLOCK_SUFFIX[decision_clock]]
    candidate = cast(Mapping[str, object], selection["candidate"])
    cycles = int(selection["selected_cycle_count"])
    device_name = str(selection["selected_backend"])
    device = torch.device("cuda:0" if device_name == "rocm" else "cpu")
    splits = split_indices(store)
    seed_results: list[dict[str, object]] = []
    score_by_seed: dict[int, NDArray[np.float64]] = {}
    for seed in SEEDS_FORMAL:
        model, receipt, review_scores = train_attempt(
            candidate=candidate,
            seed=seed,
            cycles=cycles,
            store=store,
            normalizer=normalizer,
            device_name=device_name,
        )
        postsign = operator_postsign(
            model,
            store=store,
            normalizer=normalizer,
            review_indices=splits["review"],
            train_indices=splits["train"],
            device=device,
            seed=seed,
        )
        checkpoint_relative = f"checkpoints/seed_{seed}"
        checkpoint = save_state_tree(model, output_root / checkpoint_relative)
        np.save(output_root / f"review_scores_seed_{seed}.npy", review_scores.astype(np.float32), allow_pickle=False)
        score_by_seed[seed] = review_scores
        final_review = cast(Mapping[str, object], cast(list[Mapping[str, object]], receipt["cycles"])[-1]["review"])
        seed_results.append(
            {
                **receipt,
                "final_review": dict(final_review),
                "operator_postsign": postsign,
                "model_state_digest": checkpoint["state_digest"],
                "checkpoint_relative": checkpoint_relative,
                "review_score_digest": file_digest(output_root / f"review_scores_seed_{seed}.npy"),
            }
        )
    rankics = [float(cast(Mapping[str, object], row["final_review"])["mean_daily_rankic"]) for row in seed_results]
    spreads = [float(cast(Mapping[str, object], row["final_review"])["mean_top_bottom_decile_spread"]) for row in seed_results]
    pairwise = pairwise_score_spearman(score_by_seed)
    checks = {
        "all_seed_numerical_health": all(row["healthy"] is True for row in seed_results),
        "all_seed_operator_postsign": all(
            cast(Mapping[str, object], row["operator_postsign"])["status"] == "passed" for row in seed_results
        ),
        "mean_review_rankic_positive": float(np.mean(rankics)) > 0.0,
        "positive_seed_count_at_least_two": sum(value > 0.0 for value in rankics) >= 2,
        "mean_review_spread_positive": float(np.mean(spreads)) > 0.0,
        "seed_score_stability": pairwise["passed"] is True,
    }
    return write_json(
        output_root / "formal_fit.json",
        {
            "schema_id": FORMAL_SCHEMA_ID,
            "status": "passed_confirmation_freeze_allowed" if all(checks.values()) else "failed_formal_gate",
            "formal_contract_digest": contract["canonical_digest"],
            "decision_clock": decision_clock,
            "selected_candidate": dict(candidate),
            "selected_cycle_count": cycles,
            "seed_results": seed_results,
            "mean_review_daily_rankic": float(np.mean(rankics)),
            "positive_seed_count": sum(value > 0.0 for value in rankics),
            "mean_review_top_bottom_spread": float(np.mean(spreads)),
            "pairwise_seed_score_stability": pairwise,
            "checks": checks,
            "2018_rows_read": 0,
            "2019_2020_rows_read": 0,
            "account_run": False,
            "production_authority": False,
        },
    )


def _rankz_by_day(scores: NDArray[np.float64], days: NDArray[np.int64]) -> NDArray[np.float64]:
    output = np.zeros_like(scores)
    for day in np.unique(days):
        local = days == day
        ranks = rankdata(scores[local], method="average")
        centered = ranks - ranks.mean()
        scale = centered.std(ddof=0)
        output[local] = centered / max(scale, 1.0e-12)
    return output


def run_confirmation(
    *,
    contract: Mapping[str, object],
    store_root: Path,
    normalizer: Mapping[str, object],
    decision_clock: str,
    output_root: Path,
) -> dict[str, object]:
    store = IntradayK1InputStore.load(store_root)
    selected_by_clock = cast(Mapping[str, Mapping[str, object]], contract["selected_by_clock"])
    selection = selected_by_clock[CLOCK_SUFFIX[decision_clock]]
    candidate = cast(Mapping[str, object], selection["candidate"])
    device_name = str(selection["selected_backend"])
    device = torch.device("cuda:0" if device_name == "rocm" else "cpu")
    confirmation = split_indices(store)["confirmation"]
    score_parts: list[NDArray[np.float64]] = []
    targets: NDArray[np.float64] | None = None
    days: NDArray[np.int64] | None = None
    phases: NDArray[np.int64] | None = None
    for seed in SEEDS_FORMAL:
        model = build_model(candidate, seed=seed).to(device)
        load_state_tree(model, output_root / f"checkpoints/seed_{seed}")
        scores, local_targets, local_days, local_phases = score_rows(
            model,
            store=store,
            normalizer=normalizer,
            indices=confirmation,
            device=device,
        )
        score_parts.append(_rankz_by_day(scores, local_days))
        targets = local_targets
        days = local_days
        phases = local_phases
    assert targets is not None and days is not None and phases is not None
    matrix = np.vstack(score_parts)
    ensemble = matrix.mean(axis=0)
    metrics = daily_metrics(ensemble, targets, days, phases)
    checks = {
        "mean_rankic_positive": float(metrics["mean_daily_rankic"]) > 0.0,
        "mean_spread_positive": float(metrics["mean_top_bottom_decile_spread"]) > 0.0,
        "positive_phase_count_at_least_three": int(metrics["positive_phase_count"]) >= 3,
    }
    np.save(output_root / "confirmation_seed_rankz.npy", matrix.astype(np.float32), allow_pickle=False)
    np.save(output_root / "confirmation_ensemble_scores.npy", ensemble.astype(np.float32), allow_pickle=False)
    np.save(output_root / "confirmation_row_indices.npy", confirmation, allow_pickle=False)
    return write_json(
        output_root / "confirmation.json",
        {
            "schema_id": CONFIRMATION_SCHEMA_ID,
            "status": "passed_P6_4_K1_baseline" if all(checks.values()) else "failed_confirmation",
            "confirmation_contract_digest": contract["canonical_digest"],
            "decision_clock": decision_clock,
            "ensemble_rule": "per_day_seed_rankz_then_equal_mean",
            "metrics": metrics,
            "checks": checks,
            "seed_score_matrix_digest": file_digest(output_root / "confirmation_seed_rankz.npy"),
            "ensemble_score_digest": file_digest(output_root / "confirmation_ensemble_scores.npy"),
            "row_indices_digest": file_digest(output_root / "confirmation_row_indices.npy"),
            "2018_rows_read": len(confirmation),
            "2019_2020_rows_read": 0,
            "account_run": False,
            "production_authority": False,
        },
    )


__all__ = [
    "BATCH_SIZE",
    "CONFIRMATION_SCHEMA_ID",
    "FORMAL_SCHEMA_ID",
    "MAXIMUM_CONDITION_NUMBER",
    "SCHEMA_ID",
    "SCREEN_CYCLES",
    "SCREEN_SCHEMA_ID",
    "SEEDS_FORMAL",
    "SEEDS_SCREEN",
    "build_model",
    "configure_determinism",
    "daily_metrics",
    "effective_transition_support",
    "load_state_tree",
    "model_parameter_count",
    "operator_postsign",
    "pairwise_score_spearman",
    "run_confirmation",
    "run_formal_fit",
    "run_screen",
    "save_state_tree",
    "select_candidate",
    "split_indices",
    "state_digest",
    "train_attempt",
]
