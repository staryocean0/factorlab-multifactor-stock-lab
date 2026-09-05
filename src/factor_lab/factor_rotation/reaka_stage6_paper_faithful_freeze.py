"""Stage 6 paper-faithful REAKA controller freeze and one-shot handoff.

This module freezes every scientific and architectural choice before an
external execution AI is allowed to implement the heavy engineering block.
The external block may build and qualify an engine, but it may not open or
adjudicate the twelve annual strategy sessions.
"""

# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportGeneralTypeIssues=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportIndexIssue=false
# pyright: reportCallIssue=false

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Final

import pandas as pd

STAGE6_SCHEMA_ID: Final = "factorlab.reaka_stage6_paper_faithful_freeze@1.0"
STAGE6_STRATEGY_ID: Final = "reaka_stage6_paper_faithful_daily_v1"
PAPER_SHA256: Final = "e47b342414508a2d1ab7859c6e6a7df1ceb99141e0561a3598e866645f14d21e"
YEARS: Final = tuple(range(2009, 2021))
SEEDS: Final = (11, 29, 47)
LATENT_DIMENSIONS: Final = (4, 8, 16, 32)
OPERATOR_COUNTS: Final = (1, 2, 4)
STATE_DURATION_DAYS: Final = (5, 10, 20, 40)
MODEL_ARM_IDS: Final = (
    "transparent_rank",
    "vanilla_autoencoder",
    "fixed_k_no_residual",
    "without_aks",
    "without_drc",
    "residual_mlp",
    "without_gate",
    "reaka",
)


def canonical_digest(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class Stage6FreezePolicy:
    """Controller-owned choices that an execution AI may not change."""

    strategy_id: str = STAGE6_STRATEGY_ID
    minimum_training_years: int = 3
    validation_years: int = 1
    maximum_epochs: int = 24
    minimum_epochs: int = 12
    early_stopping_patience: int = 4
    learning_rate: float = 1e-3
    batch_size: int = 4096
    gradient_clip_norm: float = 5.0
    gumbel_temperature: float = 0.75
    diffusion_steps: int = 8
    diffusion_beta_start: float = 1e-4
    diffusion_beta_end: float = 2e-2
    buy_cost_bps: float = 4.6
    sell_cost_bps: float = 9.6
    portfolio_size_candidates: tuple[int, ...] = (30, 50, 100)
    slippage_stress_multipliers: tuple[int, ...] = (1, 2, 3)
    capital_primary_cny: int = 1_000_000

    def validate(self) -> None:
        if self.strategy_id != STAGE6_STRATEGY_ID:
            raise ValueError("stage6_strategy_identity_drift")
        if self.minimum_training_years < 3 or self.validation_years != 1:
            raise ValueError("stage6_annual_prefix_policy_invalid")
        if not 1 <= self.minimum_epochs <= self.maximum_epochs:
            raise ValueError("stage6_epoch_policy_invalid")
        if self.early_stopping_patience < 1:
            raise ValueError("stage6_early_stopping_policy_invalid")
        if self.learning_rate <= 0 or self.batch_size < 1:
            raise ValueError("stage6_optimizer_policy_invalid")
        if self.gradient_clip_norm <= 0 or self.gumbel_temperature <= 0:
            raise ValueError("stage6_gradient_or_gumbel_policy_invalid")
        if not 0 < self.diffusion_beta_start < self.diffusion_beta_end < 1:
            raise ValueError("stage6_diffusion_schedule_invalid")
        if self.diffusion_steps < 2:
            raise ValueError("stage6_diffusion_steps_invalid")
        if tuple(sorted(set(self.portfolio_size_candidates))) != self.portfolio_size_candidates:
            raise ValueError("stage6_portfolio_candidates_invalid")
        if self.capital_primary_cny != 1_000_000:
            raise ValueError("stage6_primary_capital_must_match_c1")

    def as_dict(self) -> dict[str, object]:
        self.validate()
        return asdict(self)


def paper_equation_mapping() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_stage6_paper_equation_mapping@1.0",
        "paper_title": "Residual-Enhanced Adaptive Koopman Autoencoder: A Deep Latent Dynamics Model for Stock Prediction",
        "paper_pages": "2696-2700",
        "paper_sha256": PAPER_SHA256,
        "paper_exact": [
            "eq_1_2_overlapping_return_windows",
            "eq_3_6_return_and_feature_lstm_delay_embeddings",
            "eq_7_10_feature_controlled_elementwise_gate",
            "eq_11_15_selector_on_Z_and_Hy_gumbel_train_operator_mix",
            "eq_16_21_conditional_ddpm_latent_residual",
            "eq_22_27_return_decoder_last_element_forecast",
            "eq_28_31_equal_sum_Lrec_Lkoop_Ldiff",
            "inference_argmax_operator_selection",
        ],
        "paper_fixed_experiment": {
            "frequency": "daily",
            "feature_family": "Qlib Alpha158",
            "window_trading_days": 10,
            "train": "2010-01-01/2017-12-31",
            "validation": "2018-01-01/2018-12-31",
            "test": "2019-01-01/2020-12-31",
            "portfolio": "Top30",
        },
        "paper_unspecified": [
            "latent_dimension",
            "operator_count",
            "optimizer_and_learning_rate",
            "epochs_and_batch_size",
            "gumbel_temperature_schedule",
            "diffusion_steps_and_beta_schedule",
            "random_seed_distribution",
            "transaction_cost_and_A_share_execution",
        ],
        "factorlab_adaptations": [
            "98_frozen_base_factor_exposures_compiled_by_1183_usage_tickets",
            "task_isolation_by_cadence_and_horizon",
            "ticket_specific_sequence_lengths_from_stage5",
            "explicit_missingness_masks_after_train_only_rank_normalization",
            "A_share_T_plus_1_asymmetric_costs_capacity_and_full_investment",
            "sequential_annual_controller_adjudication_2009_2020",
        ],
        "claims_forbidden": [
            "author_code_bit_exact_replication",
            "paper_metric_replication",
            "latent_operator_as_named_macro_state",
            "post2020_fresh_oos",
            "production_authority",
        ],
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def model_arm_registry() -> pd.DataFrame:
    rows = [
        ("transparent_rank", 0, False, False, False, "none", "project_common_root", "always"),
        ("vanilla_autoencoder", 1, True, False, False, "none", "paper_table2_autoencoder", "transparent_core_accepted"),
        ("fixed_k_no_residual", 2, True, False, True, "none", "project_identifiability_prerequisite", "neural_carrier_health_passed"),
        ("without_aks", 3, True, False, True, "diffusion", "paper_table2_without_aks", "full_engine_implemented_diagnostic_only"),
        ("without_drc", 4, True, True, True, "none", "paper_table2_without_drc", "fixed_k_and_neural_health_passed"),
        ("residual_mlp", 5, True, True, True, "mlp", "paper_table2_residual_mlp", "adaptive_koopman_health_passed"),
        ("without_gate", 6, False, True, True, "diffusion", "paper_table2_without_gate", "full_engine_implemented_diagnostic_only"),
        ("reaka", 7, True, True, True, "diffusion", "paper_full", "residual_mlp_health_passed"),
    ]
    frame = pd.DataFrame(
        rows,
        columns=[
            "arm_id",
            "layer_order",
            "feature_gate",
            "adaptive_selector",
            "koopman_transition",
            "residual_mode",
            "paper_relation",
            "scientific_activation_prerequisite",
        ],
    )
    frame["external_ai_must_implement"] = frame["arm_id"].ne("transparent_rank")
    frame["external_ai_may_run_real_scientific_results"] = False
    frame["production_authority"] = False
    return frame


def build_task_registry(
    tickets: pd.DataFrame,
    ticket_support: pd.DataFrame,
    time_grid: pd.DataFrame,
) -> pd.DataFrame:
    required_ticket = {
        "usage_ticket_id",
        "factor_id",
        "pathway_id",
        "cadence_id",
        "horizon_days",
        "mechanism_vote_weight",
    }
    if missing := required_ticket - set(tickets):
        raise ValueError(f"stage6_ticket_columns_missing:{sorted(missing)}")
    if tickets["usage_ticket_id"].duplicated().any():
        raise ValueError("stage6_usage_ticket_duplicate")
    ticket_ids = set(tickets["usage_ticket_id"].astype(str))
    if set(ticket_support["usage_ticket_id"].astype(str)) != ticket_ids:
        raise ValueError("stage6_ticket_support_coverage_mismatch")
    if set(time_grid["usage_ticket_id"].astype(str)) != ticket_ids:
        raise ValueError("stage6_time_grid_coverage_mismatch")

    support = ticket_support[["usage_ticket_id", "capital_tier", "physical_future_rows_read"]]
    merged = tickets.merge(support, on="usage_ticket_id", how="left", validate="one_to_one")
    if bool(merged["physical_future_rows_read"].any()):
        raise ValueError("stage6_future_rows_were_read")
    sequence_map = (
        time_grid.groupby("usage_ticket_id", sort=True)["sequence_length_points"]
        .agg(lambda values: tuple(sorted(set(map(int, values)))))
        .to_dict()
    )
    state_map = (
        time_grid.groupby("usage_ticket_id", sort=True)["state_duration_candidate_days"]
        .agg(lambda values: tuple(sorted(set(map(int, values)))))
        .to_dict()
    )
    merged["sequence_lengths"] = merged["usage_ticket_id"].map(sequence_map)
    merged["state_duration_candidates"] = merged["usage_ticket_id"].map(state_map)

    rows: list[dict[str, object]] = []
    for (cadence, horizon), group in merged.groupby(["cadence_id", "horizon_days"], sort=True, observed=True):
        pathway_counts = {str(key): int(value) for key, value in sorted(group["pathway_id"].value_counts().to_dict().items())}
        sequences = sorted({item for values in group["sequence_lengths"] for item in values})
        durations = sorted({item for values in group["state_duration_candidates"] for item in values})
        rows.append(
            {
                "task_id": f"{cadence}::h{int(horizon)}",
                "cadence_id": str(cadence),
                "horizon_days": int(horizon),
                "usage_ticket_count": len(group),
                "base_factor_count": int(group["factor_id"].nunique()),
                "pathway_counts_json": json.dumps(pathway_counts, sort_keys=True),
                "sequence_length_candidates": ",".join(map(str, sequences)),
                "state_duration_candidates_days": ",".join(map(str, durations)),
                "c1_only_ticket_count": int(group["capital_tier"].eq("c1_1m_only").sum()),
                "ticket_weight_sum": float(group["mechanism_vote_weight"].sum()),
                "input_formula": ("rank_centered_base_factor*observable_spatial_mask*matured_follow_weight*mechanism_vote_weight"),
                "external_ai_scientific_execution_allowed": False,
                "production_authority": False,
            }
        )
    result = pd.DataFrame(rows).sort_values(["horizon_days", "cadence_id"], kind="mergesort")
    if int(result["usage_ticket_count"].sum()) != len(tickets):
        raise RuntimeError("stage6_task_ticket_conservation_failed")
    return result.reset_index(drop=True)


def loss_contract(policy: Stage6FreezePolicy) -> dict[str, object]:
    policy.validate()
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_stage6_loss_contract@1.0",
        "paper_full_objective": "L_total=L_rec+L_koop+L_diff",
        "paper_loss_weights": {"L_rec": 1.0, "L_koop": 1.0, "L_diff": 1.0},
        "return_ranking_loss_added": False,
        "postfit_residual_training_allowed": False,
        "residual_targets": {
            "true": "Z_plus-K_selected_Z",
            "linear": "zero_residual_control",
            "mlp": "deterministic_MSE_residual",
            "diffusion": "conditional_DDPM_noise_prediction_given_Z",
        },
        "training": {
            "optimizer": "Adam",
            "learning_rate": policy.learning_rate,
            "batch_size": policy.batch_size,
            "maximum_epochs": policy.maximum_epochs,
            "minimum_epochs": policy.minimum_epochs,
            "early_stopping_patience": policy.early_stopping_patience,
            "gradient_clip_norm": policy.gradient_clip_norm,
            "gumbel_temperature": policy.gumbel_temperature,
            "gumbel_annealing": False,
            "diffusion_steps": policy.diffusion_steps,
            "beta_schedule": "linear",
            "beta_start": policy.diffusion_beta_start,
            "beta_end": policy.diffusion_beta_end,
        },
        "selection_rule": "inner_training_prefix_only_no_outer_year_return_selection",
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def health_contract() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_stage6_training_health_contract@1.0",
        "fail_closed_required_evidence": [
            "active_module_gradient_norms_and_shared_encoder_gradient_angles",
            "first_and_last_epoch_losses",
            "soft_operator_occupancy_and_n_k_eff",
            "n_k_eff_over_d_squared",
            "operator_condition_numbers",
            "one_percent_parameter_perturbation_stability",
            "true_linear_mlp_diffusion_residual_energy_and_tail_ratios",
            "input_ood_fraction",
            "same_seed_deterministic_replay",
            "cpu_gpu_numerical_parity",
        ],
        "hard_sanity_limits": {
            "maximum_operator_occupancy_exclusive_for_K_gt_1": 0.99,
            "gate_mean_inclusive": [0.05, 0.95],
            "maximum_residual_to_advanced_energy_ratio": 2.0,
            "predicted_to_true_residual_median_energy_ratio": [0.5, 2.0],
            "predicted_to_true_residual_q95_ratio": [0.5, 2.0],
            "maximum_input_ood_fraction": 0.05,
            "minimum_loss_improvement_fraction": 0.05,
            "maximum_operator_condition_number": 1000000.0,
            "minimum_perturbed_score_rank_correlation": 0.95,
            "minimum_perturbed_operator_assignment_agreement": 0.80,
            "minimum_cpu_gpu_score_correlation": 0.999,
            "minimum_cpu_gpu_top20_member_overlap": 0.98,
        },
        "capacity_diagnostic": {
            "comfortable": "n_k_eff/d_squared>=5",
            "thin": "1<=n_k_eff/d_squared<5",
            "very_thin": "n_k_eff/d_squared<1",
            "permanent_threshold_claimed": False,
            "missing_measurement_blocks_claim": True,
        },
        "economic_improvement_cannot_override_health_failure": True,
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def annual_controller_protocol(policy: Stage6FreezePolicy) -> dict[str, object]:
    policy.validate()
    sessions = []
    for year in YEARS:
        train_end = year - 2
        validation_year = year - 1
        enough = train_end >= 2009 + policy.minimum_training_years - 1
        sessions.append(
            {
                "year": year,
                "training_interval": f"2009/{train_end}" if enough else None,
                "validation_year": validation_year if enough else None,
                "scientific_neural_run_allowed": enough,
                "otherwise": "insufficient_training_prefix_inconclusive",
                "main_controller_review_required_before_next_year": True,
            }
        )
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_stage6_annual_controller_protocol@1.0",
        "evidence_role": "retrospective_development_material_only",
        "input_selection_already_used_2009_2020": True,
        "fresh_oos": False,
        "sessions": sessions,
        "one_year_preparer_only": True,
        "shell_loop_or_batch_year_driver_forbidden": True,
        "external_ai_may_author_analysis_or_seal_receipts": False,
        "main_controller_must_rebuild_complete_active_arm_each_year": True,
        "final_status_if_candidate_survives": ("frozen_research_candidate_waiting_for_new_unseen_challenge"),
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def one_shot_handoff_contract() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_stage6_one_shot_handoff@1.0",
        "handoff_count": 1,
        "external_phase_name": "stage6_engineering_execution_only",
        "external_allowed": [
            "implement_daily_ticket_task_compiler",
            "implement_paper_equations_1_31_engine_by_wrapping_reaka_paper_v1",
            "implement_all_frozen_model_arms",
            "materialize_immutable_2009_2020_task_tensors_without_performance_ranking",
            "implement_one_year_runner_that_refuses_missing_prior_controller_receipt",
            "implement_training_health_and_posttraining_certificate_generators",
            "run_synthetic_equation_gradient_determinism_cpu_gpu_and_performance_preflight",
            "run_tests_lint_typecheck_and_static_analysis",
            "write_one_final_handoff_to_controller",
        ],
        "external_forbidden": [
            "run_or_open_real_annual_strategy_results",
            "run_multiple_years_or_batch_year_driver",
            "read_2021_2026_rows_or_results",
            "change_frozen_inputs_candidates_losses_health_gates_or_costs",
            "select_horizon_cadence_factor_operator_or_arm_by_returns",
            "lower_a_gate_or_add_a_rescue_rule_after_failure",
            "modify_existing_sealed_stage4_stage5_or_v2_4_evidence",
            "claim_scientific_strategy_or_production_authority",
        ],
        "external_code_scope": [
            "src/factor_lab/factor_rotation/reaka_stage6_daily_engine.py",
            "scripts/factor_rotation/materialize_reaka_stage6_daily_inputs.py",
            "scripts/factor_rotation/run_reaka_stage6_engineering_preflight.py",
            "scripts/factor_rotation/prepare_reaka_stage6_one_year.py",
            "scripts/factor_rotation/validate_reaka_stage6_engineering_handoff.py",
            "tests/unit/test_reaka_stage6_daily_engine.py",
            "output/factor-rotation/reaka_stage6_engineering_handoff_v1_20260817/**",
        ],
        "required_return_artifacts": [
            "engine_implementation_receipt.json",
            "task_tensor_manifest.json",
            "paper_equation_parity.json",
            "synthetic_gradient_receipt.json",
            "deterministic_replay.json",
            "cpu_gpu_parity.json",
            "gpu_performance_receipt.json",
            "test_and_static_gate_report.json",
            "handoff_to_controller.md",
        ],
        "controller_after_return": [
            "validate_once",
            "repair_ordinary_code_defects_locally_without_returning_to_external_ai",
            "run_and_review_2009_2020_sessions_sequentially",
            "adjudicate_layers_and_complete_posttraining_certificate",
        ],
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def render_external_prompt(
    *,
    output_root: str,
    handoff: dict[str, object],
) -> str:
    allowed = "\n".join(f"- {item}" for item in handoff["external_allowed"])
    forbidden = "\n".join(f"- {item}" for item in handoff["external_forbidden"])
    code_scope = "\n".join(f"- `{item}`" for item in handoff["external_code_scope"])
    artifacts = "\n".join(f"- `{item}`" for item in handoff["required_return_artifacts"])
    return f"""# 外部AI唯一任务：Stage 6论文忠实日频工程引擎一次性交付

## 角色与停止点

你是执行AI，不是科学主控。主控已经冻结全部架构、候选、损失、健康门、数据边界和年度纪律。你必须一次性完成下述工程工作，最后只交回一次；不得运行真实年度科学结果，不得要求主控中途裁决。

工作目录：`/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab`

冻结证据根：`{output_root}`

## 必读（按顺序）

1. `AGENTS.md`
2. `ai-readme.md`
3. `.codex/skills/strategy-slice-rebuild/SKILL.md`及其`references/project-contract.md`
4. `docs/user/reaka_stage6_paper_faithful_training_workflow.md`
5. `docs/ops/reaka_stage6_paper_faithful_training_whitepaper.md`
6. `docs/ops/reaka_stage6_paper_faithful_training@1.0.json`
7. `{output_root}/paper_equation_mapping.json`
8. `{output_root}/frozen_input_identity.json`
9. `{output_root}/task_registry.csv`
10. `{output_root}/model_arm_registry.csv`
11. `{output_root}/loss_contract.json`
12. `{output_root}/training_health_contract.json`
13. `{output_root}/annual_controller_protocol.json`
14. `{output_root}/single_handoff_contract.json`

## 允许执行

{allowed}

## 禁止执行

{forbidden}

## 唯一写入范围

{code_scope}

不得编辑Stage 4、Stage 5、V2.4封存证据、共享索引或本冻结包。
若确需修改范围外文件，停止并把原因写入`handoff_to_controller.md`，不要自行扩大范围。

## 必须实现的工程合同

1. 输入编译器按`cadence_id × horizon_days`形成12个隔离任务；底层因子值只物化一次，使用票只生成合法的长期、空间或滞后跟随交互。
2. 标签、T+1和可交易性必须复用Stage 2封存口径，不得新发明收益期限或价格口径。
标签可存入2009-2020封闭张量，但禁止计算、排名或展示任何真实策略指标。
3. 特征按训练前缀做日内截面秩归一；缺失值填0前必须附带可见性掩码。禁止全样本scaler。
4. 收益/特征重叠窗口、双LSTM、特征门控、selector、Gumbel训练、argmax推理、多Koopman、条件DDPM、decoder和三损失必须对应论文方程1-31。
5. 实现全部冻结模型臂，但只在合成数据或无收益工程样本上做前向、反向、确定性、CPU/GPU和性能预检。
6. 单年runner必须显式接收一个年份；若缺少上一个主控封条必须失败。禁止提供多年份循环入口。
7. 每个训练收据预留Stage 5要求的算子占用、`n_k_eff/d²`、矩阵条件数/扰动、真实/MLP/扩散残差尺度/尾部、损失/梯度/夹角和共同支持集字段。
8. GPU通过项目`run_factor_lab_rocm_gpu.sh`启动；CPU只做对照和小型测试。

## 必须返回

将工程证据写到`output/factor-rotation/reaka_stage6_engineering_handoff_v1_20260817/`，至少包括：

{artifacts}

`handoff_to_controller.md`必须列出：完成项、未完成项、代码路径、命令、运行时间、峰值内存、所有测试结果、任何阻断。禁止写收益结论、最佳参数或下一步科学建议。

## 最终停止条件

只有当工程验收器通过、所有返回文件齐全、2021-2026读取为0、真实年度科学运行次数为0时才结束。结束后停止，等待主控验收；不要进入2009年度，更不要批量运行2009-2020。
"""


def build_summary(*, task_registry: pd.DataFrame, arm_registry: pd.DataFrame) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_stage6_controller_freeze_summary@1.0",
        "strategy_id": STAGE6_STRATEGY_ID,
        "status": "controller_freeze_complete_external_execution_ready",
        "task_count": len(task_registry),
        "usage_ticket_count": int(task_registry["usage_ticket_count"].sum()),
        "base_factor_count_max_per_task": int(task_registry["base_factor_count"].max()),
        "model_arm_count": len(arm_registry),
        "latent_dimension_candidates": list(LATENT_DIMENSIONS),
        "operator_count_candidates": list(OPERATOR_COUNTS),
        "seed_count": len(SEEDS),
        "annual_session_count": len(YEARS),
        "external_handoff_count": 1,
        "external_real_scientific_run_count_allowed": 0,
        "stage6_training_executed": False,
        "closed_2021_2026_rows_read": False,
        "fresh_oos": False,
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


__all__ = [
    "LATENT_DIMENSIONS",
    "MODEL_ARM_IDS",
    "OPERATOR_COUNTS",
    "PAPER_SHA256",
    "SEEDS",
    "STAGE6_SCHEMA_ID",
    "STAGE6_STRATEGY_ID",
    "Stage6FreezePolicy",
    "annual_controller_protocol",
    "build_summary",
    "build_task_registry",
    "canonical_digest",
    "health_contract",
    "loss_contract",
    "model_arm_registry",
    "one_shot_handoff_contract",
    "paper_equation_mapping",
    "render_external_prompt",
]
