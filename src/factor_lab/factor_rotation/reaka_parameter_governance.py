"""Govern every fixed, derived, project-owned, and unresolved REAKA parameter."""

# pyright: reportArgumentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportUnnecessaryComparison=false
# pyright: reportUnnecessaryContains=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnreachable=false

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum

from factor_lab.governance.canonicalization import canonical_digest


class PaperStatus(StrEnum):
    FIXED = "paper_fixed"
    EQUATION_ONLY = "paper_equation_only"
    UNSPECIFIED = "paper_unspecified"
    INCONSISTENT = "paper_internally_inconsistent"
    NOT_APPLICABLE = "not_applicable_to_paper"


class DecisionClass(StrEnum):
    PAPER_FIXED = "paper_fixed"
    MATHEMATICAL_DERIVED = "mathematical_derived"
    MEASURED_ROUTE = "measured_route"
    PROJECT_POLICY = "project_policy"
    UNRESOLVED = "unresolved"


class FreedomClass(StrEnum):
    FORMULA_FORCED = "formula_forced"
    PRODUCT_CONTRACT = "product_contract"
    CONDITIONAL_DERIVED = "conditional_derived"
    MEASURED_NUISANCE = "measured_nuisance"
    GENUINE_DESIGN_DOF = "genuine_design_dof"


INITIAL_FACTORLAB_TRAINING_BLOCKERS = (
    "data.stock_universe",
    "encoder.layer_count",
    "network.hidden_dimension",
    "koopman.initialization",
    "selector.gumbel_temperature",
    "selector.gumbel_schedule",
    "selector.straight_through",
    "residual.target_gradient_attachment",
    "residual.denoiser_architecture",
    "residual.time_embedding_dimension",
    "residual.x0_mapping",
    "decoder.architecture",
    "loss.scale_normalization",
    "optimizer.family",
    "optimizer.learning_rate",
    "optimizer.weight_decay",
    "training.coverage_budget",
    "training.early_stopping",
    "training.gradient_clip_norm",
    "training.general_initialization",
    "portfolio.rebalance_frequency",
    "portfolio.weighting",
)

GENUINE_FACTORLAB_DOF_ROOTS = (
    "network.hidden_dimension",
    "selector.gumbel_temperature",
    "residual.denoiser_architecture",
)

EXTERNAL_GOVERNING_VARIABLES = (
    "execution.fill_clock",
    "execution.pit_tradability",
    "latent.gauge",
    "portfolio.execution_contract",
    "product.target_universe",
    "residual.snr",
    "selector.logit_normalization",
    "time.latent_transition_step",
    "training.effective_sample_size",
    "training.gradient_scale",
)


def _audit(
    parameter_id: str,
    freedom_class: FreedomClass,
    *,
    constraint: str,
    resolution: str,
    governing_parameters: Sequence[str] = (),
    root_dof_id: str | None = None,
    required_evidence: Sequence[str] = (),
) -> dict[str, object]:
    genuine = freedom_class == FreedomClass.GENUINE_DESIGN_DOF
    return {
        "parameter_id": parameter_id,
        "freedom_class": freedom_class.value,
        "constraint": constraint,
        "resolution": resolution,
        "governing_parameters": list(governing_parameters),
        "root_dof_id": root_dof_id,
        "required_evidence": list(required_evidence),
        "decision_class": (
            DecisionClass.UNRESOLVED.value
            if genuine
            else (
                DecisionClass.MEASURED_ROUTE.value
                if freedom_class == FreedomClass.MEASURED_NUISANCE
                else DecisionClass.MATHEMATICAL_DERIVED.value
            )
        ),
        "blocks_new_factorlab_training": genuine,
    }


def build_training_degree_of_freedom_audit() -> list[dict[str, object]]:
    """Collapse the apparent 22 choices into independent mathematical roots."""

    formula = FreedomClass.FORMULA_FORCED
    product = FreedomClass.PRODUCT_CONTRACT
    dependent = FreedomClass.CONDITIONAL_DERIVED
    nuisance = FreedomClass.MEASURED_NUISANCE
    genuine = FreedomClass.GENUINE_DESIGN_DOF
    deterministic_root = "network.hidden_dimension"
    selector_root = "selector.gumbel_temperature"
    residual_root = "residual.denoiser_architecture"
    return [
        _audit(
            "data.stock_universe",
            product,
            constraint="model support must equal the frozen product's PIT-observable execution universe",
            resolution="full A-share effective-dated universe with execution-time tradability gate",
            governing_parameters=("product.target_universe", "execution.pit_tradability"),
            required_evidence=("effective_dated_universe", "prefix_invariance"),
        ),
        _audit(
            "encoder.layer_count",
            dependent,
            constraint="depth and width are coordinates of one deterministic capacity family, not independent searches",
            resolution=(
                "use one recurrent layer in the minimal nested family; depth may change only through the deterministic capacity root"
            ),
            governing_parameters=("encoder.return_type", deterministic_root),
            root_dof_id=deterministic_root,
        ),
        _audit(
            deterministic_root,
            genuine,
            constraint="deterministic depth/width capacity is not identified by dimensions or Koopman invariance",
            resolution="choose one preregistered nested deterministic capacity family anchored by h/d",
            governing_parameters=("encoder.latent_dimension", "training.effective_sample_size"),
            root_dof_id=deterministic_root,
            required_evidence=("capacity_ablation", "effective_rank", "multiplicity_receipt"),
        ),
        _audit(
            "koopman.initialization",
            dependent,
            constraint="K is a one-physical-step linear propagator in the frozen latent gauge",
            resolution="training-prefix regularized DMD warm start, projected to the declared stability class",
            governing_parameters=("koopman.parameterization", "time.latent_transition_step", "latent.gauge"),
            required_evidence=("dmd_initialization_receipt", "spectral_stability"),
        ),
        _audit(
            selector_root,
            genuine,
            constraint="tau is the sole continuous bias-variance coordinate of the paper's categorical relaxation",
            resolution="preregister one dimensionless selector entropy target after logit-scale normalization",
            governing_parameters=("koopman.operator_count", "selector.logit_normalization"),
            root_dof_id=selector_root,
            required_evidence=("selector_entropy_gradient_surface", "multiplicity_receipt"),
        ),
        _audit(
            "selector.gumbel_schedule",
            dependent,
            constraint="the temperature path is downstream of the single selector-relaxation design root",
            resolution="use a constant path in the minimal family; annealing may enter only as part of a new selector-root decision",
            governing_parameters=(selector_root,),
            root_dof_id=selector_root,
        ),
        _audit(
            "selector.straight_through",
            formula,
            constraint="Equations 13-15 advance with the soft alpha-weighted operator during training",
            resolution="false; hard straight-through would replace the stated forward map",
            governing_parameters=("selector.architecture",),
        ),
        _audit(
            "residual.target_gradient_attachment",
            formula,
            constraint="DDPM noise prediction treats R as a sample from the target data distribution",
            resolution="stop-gradient on R in Ldiff; otherwise the target can move to reduce its own scoring loss",
            governing_parameters=("residual.target_definition", "loss.formula"),
            required_evidence=("residual_target_gradient_test",),
        ),
        _audit(
            residual_root,
            genuine,
            constraint="the conditional score function class is not identified by the DDPM equations",
            resolution="choose one preregistered conditional denoiser capacity family",
            governing_parameters=("encoder.latent_dimension", "residual.snr", "training.effective_sample_size"),
            root_dof_id=residual_root,
            required_evidence=("residual_capacity_ablation", "cross_fitted_residual_predictability"),
        ),
        _audit(
            "residual.time_embedding_dimension",
            dependent,
            constraint="diffusion time is a condition of the same score network, not an independent state space",
            resolution="tie time-embedding dimension to latent dimension d inside the selected denoiser family",
            governing_parameters=("encoder.latent_dimension", residual_root),
            root_dof_id=residual_root,
        ),
        _audit(
            "residual.x0_mapping",
            formula,
            constraint="Equation 16 diffuses R directly, so x0 and R occupy the same coordinates and dimension",
            resolution="identity map x0 to residual; any learned map is an extra unregistered decoder",
            governing_parameters=("residual.target_definition", "latent.gauge"),
        ),
        _audit(
            "decoder.architecture",
            dependent,
            constraint="one shared pointwise map D:R^d->R must decode every time step in Equations 22-27",
            resolution="minimal shared one-hidden-layer decoder; width equals the deterministic capacity root",
            governing_parameters=("encoder.latent_dimension", deterministic_root),
            root_dof_id=deterministic_root,
            required_evidence=("decoder_reconstruction_noise_floor",),
        ),
        _audit(
            "loss.scale_normalization",
            formula,
            constraint="Equation 28 has unit coefficients and Equations 29-31 are expectations/MSEs",
            resolution="per-observation per-element means, Lrec as two means, then coefficients exactly 1:1:1",
            governing_parameters=("loss.formula", "latent.gauge"),
            required_evidence=("gradient_scale_audit", "latent_gauge_receipt"),
        ),
        _audit(
            "optimizer.family",
            nuisance,
            constraint="the optimizer is a numerical solver for the frozen objective, not a term in that objective",
            resolution="select fastest solver passing stationary-point and multi-start solution-equivalence gates",
            governing_parameters=("loss.formula", "training.numeric_precision"),
            required_evidence=("solver_equivalence_preflight",),
        ),
        _audit(
            "optimizer.learning_rate",
            nuisance,
            constraint="stable step size is bounded by local curvature for the selected solver",
            resolution="largest dimensionless stable step from a training-prefix range test",
            governing_parameters=("optimizer.family", "training.gradient_scale"),
            required_evidence=("learning_rate_range_test",),
        ),
        _audit(
            "optimizer.weight_decay",
            formula,
            constraint="positive weight decay adds a regularizer absent from Lrec+Lkoop+Ldiff",
            resolution="zero for formula-faithful training; positive decay is a new objective identity",
            governing_parameters=("loss.formula",),
        ),
        _audit(
            "training.coverage_budget",
            nuisance,
            constraint="epochs only discretize convergence of the frozen empirical objective",
            resolution="full no-replacement coverage cycles until preregistered convergence tolerance or maximum budget",
            governing_parameters=("training.effective_sample_size", "optimizer.family", "optimizer.learning_rate"),
            required_evidence=("coverage_convergence_receipt",),
        ),
        _audit(
            "training.early_stopping",
            nuisance,
            constraint="stopping must select a healthy stationary approximation without consulting an outer year",
            resolution="health gates first, then inner-validation RankIC/spread plateau within the fixed coverage budget",
            governing_parameters=("training.checkpoint_selection", "training.coverage_budget"),
            required_evidence=("checkpoint_attempt_receipt",),
        ),
        _audit(
            "training.gradient_clip_norm",
            nuisance,
            constraint="clipping is a numerical stability guard and must not define the learned objective",
            resolution="disabled when finite; otherwise set from the preregistered unclipped gradient tail quantile",
            governing_parameters=("optimizer.family", "training.gradient_scale"),
            required_evidence=("unclipped_gradient_distribution",),
        ),
        _audit(
            "training.general_initialization",
            dependent,
            constraint="initial variance and memory scale must match activation fan-in and sequence length T",
            resolution="activation-aware variance preservation, orthogonal recurrence, chrono forget bias from T; K uses its DMD rule",
            governing_parameters=("time.window_points", deterministic_root, "koopman.initialization"),
            required_evidence=("initialization_variance_receipt",),
        ),
        _audit(
            "portfolio.rebalance_frequency",
            product,
            constraint="a new score exists only on the frozen decision grid and execution occurs at its paired fill time",
            resolution="rebalance on each 5-trading-day H20 launch at next-session open; carry between launches",
            governing_parameters=("time.decision_cadence", "execution.fill_clock"),
            required_evidence=("portfolio_execution_contract",),
        ),
        _audit(
            "portfolio.weighting",
            product,
            constraint="the Stage6 execution contract already fixes the score-to-account map",
            resolution="equal-weight target subject to forced carry, deterministic rank tie and buyability backfill",
            governing_parameters=("portfolio.execution_contract", "portfolio.topk"),
            required_evidence=("portfolio_execution_contract",),
        ),
    ]


def _training_instantiation_contract(
    audit: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    by_class: dict[str, list[str]] = {freedom.value: [] for freedom in FreedomClass}
    evidence_ids: set[str] = set()
    for row in audit:
        by_class[str(row["freedom_class"])].append(str(row["parameter_id"]))
        evidence_ids.update(str(value) for value in row["required_evidence"])
    return {
        "schema_id": "factorlab.reaka_training_parameter_instantiation_contract@1.0",
        "catalog_dof_gate_must_pass": True,
        "all_22_values_must_be_explicit": True,
        "historical_defaults_forbidden": True,
        "required_parameter_ids": list(INITIAL_FACTORLAB_TRAINING_BLOCKERS),
        "required_evidence_ids": sorted(evidence_ids),
        "resolution_order": [
            *by_class[FreedomClass.FORMULA_FORCED],
            *by_class[FreedomClass.PRODUCT_CONTRACT],
            *by_class[FreedomClass.GENUINE_DESIGN_DOF],
            *by_class[FreedomClass.CONDITIONAL_DERIVED],
            *by_class[FreedomClass.MEASURED_NUISANCE],
        ],
    }


def _entry(
    parameter_id: str,
    layer: str,
    paper_status: PaperStatus,
    decision_class: DecisionClass,
    *,
    paper_value: object | None = None,
    current_h20_value: object | None = None,
    selection_rule: str,
    required_evidence: Sequence[str] = (),
    blocks_author_replication: bool = False,
    blocks_new_factorlab_training: bool = False,
    note: str = "",
) -> dict[str, object]:
    return {
        "parameter_id": parameter_id,
        "layer": layer,
        "paper_status": paper_status.value,
        "decision_class": decision_class.value,
        "paper_value": paper_value,
        "current_h20_value": current_h20_value,
        "selection_rule": selection_rule,
        "required_evidence": list(required_evidence),
        "blocks_author_replication": blocks_author_replication,
        "blocks_new_factorlab_training": blocks_new_factorlab_training,
        "note": note,
    }


def reaka_parameter_entries() -> list[dict[str, object]]:
    """Return the complete current catalog; no class default is authoritative."""

    fixed = PaperStatus.FIXED
    equation = PaperStatus.EQUATION_ONLY
    unspecified = PaperStatus.UNSPECIFIED
    inconsistent = PaperStatus.INCONSISTENT
    na = PaperStatus.NOT_APPLICABLE
    paper = DecisionClass.PAPER_FIXED
    derived = DecisionClass.MATHEMATICAL_DERIVED
    measured = DecisionClass.MEASURED_ROUTE
    policy = DecisionClass.PROJECT_POLICY
    unresolved = DecisionClass.UNRESOLVED
    return [
        _entry(
            "data.frequency",
            "data",
            fixed,
            paper,
            paper_value="daily",
            current_h20_value="20_trading_day_physical_step_launched_every_5_days",
            selection_rule="paper daily for numeric reproduction; FactorLab frequency comes from the frozen product target",
        ),
        _entry(
            "data.feature_family",
            "data",
            fixed,
            paper,
            paper_value="Qlib Alpha158",
            current_h20_value="CORE_SPATIAL_H20_48_factor_identities",
            selection_rule="exact paper reproduction requires Alpha158; project adapter must freeze an independent feature identity",
        ),
        _entry(
            "data.qlib_version",
            "data",
            unspecified,
            unresolved,
            selection_rule="obtain author environment or freeze a named Qlib release and label it an adaptation",
            blocks_author_replication=True,
            blocks_new_factorlab_training=False,
        ),
        _entry(
            "data.stock_universe",
            "data",
            equation,
            unresolved,
            paper_value="CSI300_and_SP500",
            selection_rule="need constituent schedule, survivorship policy, listing filters and date-effective membership",
            required_evidence=("effective_dated_universe",),
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "data.feature_preprocessing",
            "data",
            unspecified,
            unresolved,
            current_h20_value="daily_cross_sectional_average_percentile_centered_train_prefix_independent",
            selection_rule="freeze scaling, winsorization, normalization axis and fit prefix before training",
            required_evidence=("prefix_invariance", "normalization_receipt"),
            blocks_author_replication=True,
            blocks_new_factorlab_training=False,
        ),
        _entry(
            "data.missing_value_policy",
            "data",
            unspecified,
            policy,
            current_h20_value="explicit_availability_mask_then_zero_only_after_mask",
            selection_rule="missingness must remain an explicit channel; no unmasked zero fill",
            required_evidence=("availability_ablation",),
        ),
        _entry(
            "data.historical_return_definition",
            "time",
            equation,
            derived,
            paper_value="historical_return_sequence_y_1_to_T",
            current_h20_value="matured_nonoverlapping_H20_period_return",
            selection_rule="historical return period must equal feature, latent, decoder, residual and forecast step",
            required_evidence=("temporal_coordinate_certificate",),
        ),
        _entry(
            "data.target_definition",
            "time",
            fixed,
            derived,
            paper_value="next_step_return",
            current_h20_value="next_nonoverlapping_H20_period_return",
            selection_rule="freeze entry, exit, availability and horizon as one target identity",
            required_evidence=("label_spec_digest",),
        ),
        _entry(
            "time.decision_cadence",
            "time",
            unspecified,
            derived,
            current_h20_value=5,
            selection_rule="decision launch cadence may divide the physical transition step; overlapping phases are dependent views",
            required_evidence=("phase_overlap_report",),
        ),
        _entry(
            "time.window_points",
            "time",
            fixed,
            paper,
            paper_value=10,
            current_h20_value=10,
            selection_rule="paper T=10; an adapted T requires new identity and window-neighborhood evidence",
        ),
        _entry(
            "time.physical_lookback",
            "time",
            na,
            derived,
            current_h20_value=200,
            selection_rule="required_history=T*physical_step; endpoint span=(T-1)*step",
            required_evidence=("temporal_coordinate_certificate",),
        ),
        _entry(
            "time.split_protocol",
            "evidence",
            fixed,
            policy,
            paper_value={"train": "2010_2017", "validation": "2018", "test": "2019_2020"},
            current_h20_value="chronological_prefix_and_consumed_history_receipts",
            selection_rule="never random split; paper dates reproduce only its experiment, project runs use declared evidence roles",
        ),
        _entry(
            "encoder.return_type",
            "architecture",
            fixed,
            paper,
            paper_value="LSTM",
            current_h20_value="one_layer_LSTM",
            selection_rule="paper fixes LSTM family but not layers or hidden size",
        ),
        _entry(
            "encoder.feature_type",
            "architecture",
            fixed,
            paper,
            paper_value="separate_LSTM",
            current_h20_value="one_layer_LSTM",
            selection_rule="paper fixes a separate feature LSTM; depth remains unresolved",
        ),
        _entry(
            "encoder.layer_count",
            "architecture",
            unspecified,
            unresolved,
            current_h20_value=1,
            selection_rule="bounded architecture preregistration required; current one-layer value is historical, not authoritative",
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "encoder.latent_dimension",
            "capacity",
            unspecified,
            measured,
            current_h20_value=8,
            selection_rule=(
                "measure training-prefix effective rank and bracket it with the "
                "smallest supported dimensions; require reconstruction, rank and "
                "perturbation evidence"
            ),
            required_evidence=("effective_rank", "latent_participation", "capacity_ablation"),
            blocks_author_replication=True,
        ),
        _entry(
            "network.hidden_dimension",
            "capacity",
            unspecified,
            unresolved,
            current_h20_value=32,
            selection_rule="must be a bounded candidate tied to d and sample size; 32 is historical only",
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "gate.architecture",
            "architecture",
            fixed,
            paper,
            paper_value="MLP_sigmoid_on_feature_hidden",
            current_h20_value="MLP_sigmoid_on_feature_hidden",
            selection_rule="G weights return path and 1-G weights feature path exactly as equations 7-10",
        ),
        _entry(
            "gate.regularization",
            "architecture",
            unspecified,
            unresolved,
            current_h20_value=None,
            selection_rule="do not force balanced occupancy; first require context dependency counterfactual and shortcut audit",
            required_evidence=("context_dependency_certificate",),
            blocks_author_replication=True,
            blocks_new_factorlab_training=False,
        ),
        _entry(
            "gate.context_dependency_certificate",
            "governance",
            na,
            derived,
            current_h20_value={"minimum_median_feature_share": 0.10, "maximum_full_neutral_rank_correlation": 0.995},
            selection_rule="a model claiming context use must show material feature path and counterfactual prediction dependence",
            required_evidence=("gate_by_seed", "full_vs_neutral_counterfactual"),
        ),
        _entry(
            "adapter.external_state_representation",
            "architecture",
            na,
            derived,
            current_h20_value="transparent_context_spine_plus_bounded_modulation",
            selection_rule=(
                "paper has latent states, not user-named external states; explicit "
                "states require a separate adapter identity and cannot be hidden "
                "amplitude defaults"
            ),
            required_evidence=("state_learnability_certificate", "financial_review_receipt"),
        ),
        _entry(
            "koopman.operator_count",
            "capacity",
            unspecified,
            measured,
            current_h20_value=1,
            selection_rule=(
                "K1 is mandatory baseline; K>1 requires independent episodes, n_k_eff per degree, stable occupancy and distinct operators"
            ),
            required_evidence=("episode_atlas", "operator_identifiability"),
            blocks_author_replication=True,
        ),
        _entry(
            "koopman.parameterization",
            "capacity",
            equation,
            measured,
            current_h20_value="full_matrix_K1",
            selection_rule="choose full, diagonal or low-rank from effective transitions per degree; full dxd is not automatic",
            required_evidence=("n_eff_per_degree", "condition_number"),
        ),
        _entry(
            "koopman.initialization",
            "architecture",
            unspecified,
            unresolved,
            current_h20_value="identity_plus_0p01_gaussian",
            selection_rule=(
                "scale perturbation to the expected physical-step transition and compare identity/orthogonal/stable initialization"
            ),
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "selector.architecture",
            "architecture",
            fixed,
            paper,
            paper_value="single_layer_MLP_LeakyReLU_on_Z_and_Hy",
            current_h20_value="not_applicable_K1",
            selection_rule="use exact selector only after K>1 learnability gate",
        ),
        _entry(
            "selector.granularity",
            "architecture",
            equation,
            paper,
            paper_value="per_time_step",
            current_h20_value="not_applicable_K1",
            selection_rule="paper text supports per-step selection; other granularity is a new adapter",
        ),
        _entry(
            "selector.gumbel_temperature",
            "training",
            equation,
            unresolved,
            paper_value="tau_positive",
            current_h20_value=0.75,
            selection_rule="calibrate from selector entropy and gradient variance on training prefix; 0.75 is historical only",
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "selector.gumbel_schedule",
            "training",
            unspecified,
            unresolved,
            current_h20_value="fixed_no_annealing",
            selection_rule="freeze fixed or annealed schedule and straight-through policy before K>1 training",
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "selector.straight_through",
            "training",
            unspecified,
            unresolved,
            current_h20_value=False,
            selection_rule="author behavior unknown; any choice creates a separate implementation identity",
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "residual.target_definition",
            "residual",
            fixed,
            paper,
            paper_value="Z_plus_minus_K_selected_Z",
            current_h20_value="not_opened",
            selection_rule="latent residual only; never price residual or omitted factor bucket",
        ),
        _entry(
            "residual.target_gradient_attachment",
            "residual",
            unspecified,
            unresolved,
            current_h20_value="attached",
            selection_rule="freeze attached vs detached target and retrain ablation; current attached value is an assumption",
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "residual.denoiser_architecture",
            "residual",
            equation,
            unresolved,
            paper_value="conditional_diffusion_given_Z",
            current_h20_value="two_hidden_layer_SiLU_MLP",
            selection_rule="paper fixes conditioning concept, not depth/width/time embedding",
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "residual.diffusion_steps",
            "residual",
            unspecified,
            measured,
            current_h20_value=None,
            selection_rule="choose smallest step count meeting residual distribution and score Monte Carlo convergence",
            required_evidence=("residual_scale_certificate", "draw_convergence"),
            blocks_author_replication=True,
        ),
        _entry(
            "residual.beta_schedule_family",
            "residual",
            equation,
            measured,
            paper_value="noise_schedule",
            current_h20_value=None,
            selection_rule="calibrate schedule to training-prefix residual SNR; image DDPM defaults forbidden",
            required_evidence=("residual_snr",),
            blocks_author_replication=True,
        ),
        _entry(
            "residual.beta_endpoints",
            "residual",
            unspecified,
            measured,
            current_h20_value=None,
            selection_rule="derive endpoints from residual variance and terminal-noise target, then freeze",
            required_evidence=("residual_scale_certificate",),
            blocks_author_replication=True,
        ),
        _entry(
            "residual.time_embedding_dimension",
            "residual",
            unspecified,
            unresolved,
            current_h20_value=8,
            selection_rule="bounded architecture choice after diffusion is authorized; 8 is historical only",
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "residual.inference_draws",
            "residual",
            unspecified,
            measured,
            current_h20_value=None,
            selection_rule="increase draws until score rank, TopK membership and Monte Carlo error converge",
            required_evidence=("draw_convergence",),
            blocks_author_replication=True,
        ),
        _entry(
            "residual.x0_mapping",
            "residual",
            unspecified,
            unresolved,
            current_h20_value="identity",
            selection_rule=(
                "author mapping from final diffusion state to residual is unknown; identity is an explicit implementation assumption"
            ),
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "decoder.architecture",
            "architecture",
            equation,
            unresolved,
            paper_value="latent_to_return_decoder",
            current_h20_value="two_layer_SiLU_MLP",
            selection_rule="paper fixes role and last-element forecast, not decoder depth/width",
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "loss.formula",
            "training",
            fixed,
            paper,
            paper_value="Lrec_plus_Lkoop_plus_Ldiff",
            current_h20_value="same_when_applicable",
            selection_rule="paper-exact arm uses all coefficients one; adapter losses require new fingerprint",
        ),
        _entry(
            "loss.scale_normalization",
            "training",
            unspecified,
            measured,
            current_h20_value="diagnostic_only",
            selection_rule="report loss magnitudes, shared-gradient norms and angles; equal symbols do not imply equal influence",
            required_evidence=("gradient_scale_audit",),
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "loss.ranking_objective",
            "training",
            unspecified,
            policy,
            current_h20_value="not_in_paper_objective",
            selection_rule="FactorLab ranking extensions require a new adapter and ablation; never call them paper exact",
        ),
        _entry(
            "optimizer.family",
            "training",
            unspecified,
            unresolved,
            current_h20_value="Adam",
            selection_rule="freeze a bounded optimizer family after gradient/noise preflight; Adam is historical only",
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "optimizer.learning_rate",
            "training",
            unspecified,
            measured,
            current_h20_value=0.001,
            selection_rule="choose from a preregistered log-scale stability bracket using training-prefix loss and gradient diagnostics",
            required_evidence=("learning_rate_range_test",),
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "optimizer.weight_decay",
            "training",
            unspecified,
            unresolved,
            current_h20_value=0.0,
            selection_rule="explicitly freeze zero or positive value; absence from constructor is not authority",
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "optimizer.batch_size",
            "performance",
            unspecified,
            measured,
            current_h20_value=4096,
            selection_rule="select fastest integrity-equivalent batch fitting memory and numerical parity; not a scientific search",
            required_evidence=("performance_preflight",),
            blocks_author_replication=True,
        ),
        _entry(
            "training.coverage_budget",
            "training",
            unspecified,
            measured,
            current_h20_value="historical_12_epochs_current_successor_requires_full_coverage_cycles",
            selection_rule="count full no-replacement coverage cycles; freeze max budget before results and select by full validation",
            required_evidence=("coverage_receipt",),
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "training.early_stopping",
            "training",
            unspecified,
            unresolved,
            current_h20_value="validation_total_loss_checkpoint",
            selection_rule=(
                "final checkpoint criterion must match declared product metric after "
                "health gates; reconstruction-only selection cannot govern RankIC"
            ),
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "training.checkpoint_selection",
            "training",
            unspecified,
            derived,
            current_h20_value="future_successor_health_then_rank_metric",
            selection_rule=(
                "first pass numerical/causal health, then use preregistered inner "
                "validation RankIC and spread; outer year never selects checkpoint"
            ),
            required_evidence=("loss_rank_alignment", "checkpoint_attempt_receipt"),
        ),
        _entry(
            "training.gradient_clip_norm",
            "training",
            unspecified,
            measured,
            current_h20_value=5.0,
            selection_rule="set only after unclipped gradient distribution is measured; 5 is historical",
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "training.random_seeds",
            "training",
            unspecified,
            policy,
            current_h20_value=[11, 29, 47],
            selection_rule=(
                "seed values are reproducibility labels; seed count must expose assignment/gate stability and all attempts count"
            ),
            required_evidence=("multi_seed_stability",),
            blocks_author_replication=True,
        ),
        _entry(
            "training.numeric_precision",
            "performance",
            unspecified,
            measured,
            current_h20_value="ROCm_autocast_float16",
            selection_rule="choose fastest precision within preregistered loss and score parity tolerance",
            required_evidence=("precision_parity",),
            blocks_author_replication=True,
        ),
        _entry(
            "training.general_initialization",
            "training",
            unspecified,
            unresolved,
            current_h20_value="PyTorch_defaults",
            selection_rule="freeze initializer family and scale for each module; framework defaults are version-dependent",
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "evaluation.rankic",
            "evaluation",
            fixed,
            paper,
            paper_value="daily_Spearman_predicted_vs_realized_return",
            current_h20_value="day_equal_Spearman",
            selection_rule="use decision-day equal weighting and exact common support",
        ),
        _entry(
            "evaluation.rankicir",
            "evaluation",
            inconsistent,
            policy,
            paper_value="printed_mean_divided_by_mean_typo",
            current_h20_value="mean_daily_rankic_over_std_daily_rankic",
            selection_rule="FactorLab uses the standard mean/std definition and labels it a documented correction",
            required_evidence=("metric_definition_receipt",),
        ),
        _entry(
            "evaluation.annual_reporting",
            "evaluation",
            unspecified,
            derived,
            current_h20_value=True,
            selection_rule="combined multi-year test can hide failure; natural-year and phase breakdown are mandatory",
            required_evidence=("annual_dispersion", "phase_dispersion"),
        ),
        _entry(
            "portfolio.topk",
            "portfolio",
            fixed,
            paper,
            paper_value=30,
            current_h20_value="not_model_parameter",
            selection_rule="Top30 reproduces paper simulation only; project TopK is an outer strategy identity",
        ),
        _entry(
            "portfolio.rebalance_frequency",
            "portfolio",
            unspecified,
            unresolved,
            selection_rule="freeze signal time, rebalance schedule and overlapping holdings",
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "portfolio.weighting",
            "portfolio",
            unspecified,
            unresolved,
            selection_rule="freeze equal/value/risk weights and tie behavior",
            blocks_author_replication=True,
            blocks_new_factorlab_training=True,
        ),
        _entry(
            "portfolio.transaction_cost",
            "portfolio",
            unspecified,
            policy,
            current_h20_value={"buy_bps": 4.6, "sell_bps": 9.6},
            selection_rule="paper numeric reproduction lacks cost authority; project uses its execution contract",
            blocks_author_replication=True,
        ),
        _entry(
            "portfolio.slippage_capacity",
            "portfolio",
            unspecified,
            measured,
            current_h20_value="project_cost_and_capacity_stress",
            selection_rule="derive from tradability, capital tier and execution data, never from paper return chart",
            blocks_author_replication=True,
        ),
        _entry(
            "adapter.transparent_context_anchor",
            "governance",
            na,
            derived,
            current_h20_value={
                "baseline_coefficient": 1.0,
                "residual_weight_nonnegative": True,
                "residual_weight_cap": 0.25,
            },
            selection_rule=(
                "known transparent logic cannot be overwritten; model enters only as "
                "training-prefix orthogonal residual with exact zero fallback"
            ),
            required_evidence=("context_anchor_fit", "no_harm_replay"),
        ),
        _entry(
            "adapter.temporal_residual_role",
            "governance",
            na,
            derived,
            current_h20_value="independent_temporal_residual_expert_not_state_model",
            selection_rule=(
                "when context dependency fails, model may contribute only "
                "independently validated residual information and cannot claim state "
                "effects"
            ),
            required_evidence=("context_dependency_certificate", "anchored_residual_replay"),
        ),
    ]


def build_parameter_catalog() -> dict[str, object]:
    audit = build_training_degree_of_freedom_audit()
    audit_by_id = {str(row["parameter_id"]): row for row in audit}
    entries: list[dict[str, object]] = []
    for original in reaka_parameter_entries():
        entry = dict(original)
        parameter_id = str(entry["parameter_id"])
        if parameter_id in audit_by_id:
            row = audit_by_id[parameter_id]
            entry["pre_dof_audit_decision_class"] = entry["decision_class"]
            entry["decision_class"] = row["decision_class"]
            entry["freedom_class"] = row["freedom_class"]
            entry["dof_constraint"] = row["constraint"]
            entry["selection_rule"] = row["resolution"]
            entry["governing_parameters"] = row["governing_parameters"]
            entry["root_dof_id"] = row["root_dof_id"]
            entry["required_evidence"] = sorted(set(entry["required_evidence"]) | set(row["required_evidence"]))
            entry["blocks_new_factorlab_training"] = row["blocks_new_factorlab_training"]
        entries.append(entry)
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_paper_parameter_catalog@1.1",
        "supersedes": "factorlab.reaka_paper_parameter_catalog@1.0",
        "status": "implemented_dof_compressed_fail_closed_parameter_governance",
        "parameter_count": len(entries),
        "entries": entries,
        "factorlab_training_dof_audit": audit,
        "factorlab_training_dof_summary": {
            "apparent_parameter_count_before_audit": len(INITIAL_FACTORLAB_TRAINING_BLOCKERS),
            "formula_forced_count": 5,
            "product_contract_count": 3,
            "conditional_derived_count": 6,
            "measured_nuisance_count": 5,
            "genuine_design_dof_count": len(GENUINE_FACTORLAB_DOF_ROOTS),
            "genuine_design_dof_ids": list(GENUINE_FACTORLAB_DOF_ROOTS),
            "resolved_or_dependent_count": (len(INITIAL_FACTORLAB_TRAINING_BLOCKERS) - len(GENUINE_FACTORLAB_DOF_ROOTS)),
        },
        "training_instantiation_contract": _training_instantiation_contract(audit),
        "factorlab_training_constraint_graph": {
            "external_governing_variables": list(EXTERNAL_GOVERNING_VARIABLES),
            "edges": [{"source": source, "target": row["parameter_id"]} for row in audit for source in row["governing_parameters"]],
        },
        "scope_gates": {
            "author_numeric_replication": [entry["parameter_id"] for entry in entries if entry["blocks_author_replication"]],
            "new_factorlab_neural_training": [entry["parameter_id"] for entry in entries if entry["blocks_new_factorlab_training"]],
        },
        "class_defaults_have_parameter_authority": False,
        "unresolved_values_may_not_fall_back_silently": True,
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def validate_parameter_catalog(payload: Mapping[str, object]) -> dict[str, object]:
    blockers: list[str] = []
    if payload.get("schema_id") != "factorlab.reaka_paper_parameter_catalog@1.1":
        blockers.append("parameter_catalog_schema_invalid")
    entries = list(payload.get("entries", []))
    ids = [str(entry.get("parameter_id", "")) for entry in entries]
    if not ids or len(ids) != len(set(ids)):
        blockers.append("parameter_catalog_identity_missing_or_duplicate")
    for entry in entries:
        paper_status = str(entry.get("paper_status", ""))
        decision_class = str(entry.get("decision_class", ""))
        if paper_status == PaperStatus.UNSPECIFIED and decision_class == DecisionClass.PAPER_FIXED:
            blockers.append(f"unspecified_parameter_falsely_paper_fixed:{entry.get('parameter_id')}")
        if decision_class == DecisionClass.UNRESOLVED and not (
            entry.get("blocks_author_replication") or entry.get("blocks_new_factorlab_training")
        ):
            blockers.append(f"unresolved_parameter_has_no_blocker:{entry.get('parameter_id')}")
        if not str(entry.get("selection_rule", "")):
            blockers.append(f"parameter_selection_rule_missing:{entry.get('parameter_id')}")
    if int(payload.get("parameter_count", -1)) != len(entries):
        blockers.append("parameter_count_mismatch")
    audit = list(payload.get("factorlab_training_dof_audit", []))
    audit_ids = [str(row.get("parameter_id", "")) for row in audit]
    if tuple(audit_ids) != INITIAL_FACTORLAB_TRAINING_BLOCKERS:
        blockers.append("factorlab_training_dof_audit_identity_drift")
    genuine_ids = [str(row.get("parameter_id", "")) for row in audit if row.get("freedom_class") == FreedomClass.GENUINE_DESIGN_DOF]
    if tuple(genuine_ids) != GENUINE_FACTORLAB_DOF_ROOTS:
        blockers.append("factorlab_genuine_dof_root_drift")
    for row in audit:
        parameter_id = str(row.get("parameter_id", ""))
        genuine = row.get("freedom_class") == FreedomClass.GENUINE_DESIGN_DOF
        if bool(row.get("blocks_new_factorlab_training")) != genuine:
            blockers.append(f"factorlab_dof_blocker_mismatch:{parameter_id}")
        root_dof_id = row.get("root_dof_id")
        if root_dof_id is not None and str(root_dof_id) not in GENUINE_FACTORLAB_DOF_ROOTS:
            blockers.append(f"factorlab_dof_root_unknown:{parameter_id}")
        if not str(row.get("constraint", "")) or not str(row.get("resolution", "")):
            blockers.append(f"factorlab_dof_rule_missing:{parameter_id}")
    entry_by_id = {str(entry.get("parameter_id", "")): entry for entry in entries}
    for row in audit:
        parameter_id = str(row.get("parameter_id", ""))
        entry = entry_by_id.get(parameter_id, {})
        for field in (
            "freedom_class",
            "decision_class",
            "blocks_new_factorlab_training",
        ):
            if entry.get(field) != row.get(field):
                blockers.append(f"factorlab_dof_overlay_drift:{parameter_id}:{field}")
    if payload.get("training_instantiation_contract") != _training_instantiation_contract(audit):
        blockers.append("training_instantiation_contract_drift")
    graph = dict(payload.get("factorlab_training_constraint_graph", {}))
    if graph.get("external_governing_variables") != list(EXTERNAL_GOVERNING_VARIABLES):
        blockers.append("factorlab_constraint_graph_external_identity_drift")
    known_sources = set(ids) | set(EXTERNAL_GOVERNING_VARIABLES)
    expected_edges = [{"source": source, "target": row["parameter_id"]} for row in audit for source in row["governing_parameters"]]
    if graph.get("edges") != expected_edges:
        blockers.append("factorlab_constraint_graph_edge_drift")
    for edge in expected_edges:
        if str(edge["source"]) not in known_sources:
            blockers.append(f"factorlab_constraint_graph_source_unknown:{edge['source']}")
    scope_gates = dict(payload.get("scope_gates", {}))
    expected_scopes = {
        "author_numeric_replication": [str(entry.get("parameter_id", "")) for entry in entries if entry.get("blocks_author_replication")],
        "new_factorlab_neural_training": [
            str(entry.get("parameter_id", "")) for entry in entries if entry.get("blocks_new_factorlab_training")
        ],
    }
    for scope, expected_ids in expected_scopes.items():
        actual_ids = [str(value) for value in scope_gates.get(scope, [])]
        if actual_ids != expected_ids:
            blockers.append(f"parameter_scope_gate_drift:{scope}")
    digest_payload = dict(payload)
    actual_digest = str(digest_payload.pop("canonical_digest", ""))
    if actual_digest != canonical_digest(digest_payload):
        blockers.append("parameter_catalog_digest_mismatch")
    result: dict[str, object] = {
        "schema_id": "factorlab.reaka_paper_parameter_catalog_validation@1.1",
        "status": "passed" if not blockers else "blocked",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "parameter_count": len(entries),
        "production_authority": False,
    }
    result["canonical_digest"] = canonical_digest(result)
    return result


def parameter_scope_gate(
    payload: Mapping[str, object],
    *,
    scope: str,
    root_resolution_receipt: Mapping[str, object] | None = None,
) -> dict[str, object]:
    gates = dict(payload.get("scope_gates", {}))
    if scope not in gates:
        raise ValueError("reaka_parameter_scope_unknown")
    # The scope lists are explicit fail-closed declarations.  A later catalog
    # version removes an id only after author evidence or a project decision
    # receipt resolves it; a convenient current value never clears the gate.
    unresolved = [str(parameter_id) for parameter_id in gates[scope]]
    catalog_validation = validate_parameter_catalog(payload)
    resolution_status = "not_applicable"
    if root_resolution_receipt is not None:
        resolved_ids = [str(value) for value in root_resolution_receipt.get("resolved_root_ids", [])]
        receipt_valid = (
            scope == "new_factorlab_neural_training"
            and root_resolution_receipt.get("status") == "approved_mathematical_root_routes"
            and root_resolution_receipt.get("catalog_digest") == payload.get("canonical_digest")
            and resolved_ids == unresolved
            and all(str(row.get("selection_policy", "")) for row in root_resolution_receipt.get("root_resolutions", []))
        )
        resolution_status = "passed" if receipt_valid else "blocked"
        if receipt_valid:
            unresolved = []
    result: dict[str, object] = {
        "schema_id": "factorlab.reaka_parameter_scope_gate@1.1",
        "scope": scope,
        "status": ("passed" if not unresolved and catalog_validation["status"] == "passed" else "blocked"),
        "catalog_validation_status": catalog_validation["status"],
        "root_resolution_receipt_status": resolution_status,
        "unresolved_parameter_ids": unresolved,
        "unresolved_count": len(unresolved),
        "production_authority": False,
    }
    result["canonical_digest"] = canonical_digest(result)
    return result


def validate_training_parameter_instantiation(
    catalog: Mapping[str, object],
    instantiation: Mapping[str, object],
    *,
    root_resolution_receipt: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Require explicit values and receipts after the root DOFs are fixed."""

    blockers: list[str] = []
    catalog_validation = validate_parameter_catalog(catalog)
    catalog_gate = parameter_scope_gate(
        catalog,
        scope="new_factorlab_neural_training",
        root_resolution_receipt=root_resolution_receipt,
    )
    if catalog_validation["status"] != "passed":
        blockers.append("catalog_validation_blocked")
    if catalog_gate["status"] != "passed":
        blockers.append("genuine_design_dof_gate_blocked")
    if instantiation.get("catalog_digest") != catalog.get("canonical_digest"):
        blockers.append("instantiation_catalog_digest_mismatch")
    contract = dict(catalog.get("training_instantiation_contract", {}))
    values: dict[str, object | None] = {str(key): value for key, value in dict(instantiation.get("parameter_values", {})).items()}
    receipts = {str(key): value for key, value in dict(instantiation.get("evidence_receipts", {})).items()}
    for parameter_id in contract.get("required_parameter_ids", []):
        parameter_key = str(parameter_id)
        if parameter_key not in values or values[parameter_key] is None:
            blockers.append(f"instantiation_parameter_missing:{parameter_id}")
    for evidence_id in contract.get("required_evidence_ids", []):
        if not str(receipts.get(evidence_id, "")):
            blockers.append(f"instantiation_evidence_missing:{evidence_id}")
    result: dict[str, object] = {
        "schema_id": "factorlab.reaka_training_parameter_instantiation_validation@1.0",
        "status": "passed" if not blockers else "blocked",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "catalog_validation_status": catalog_validation["status"],
        "genuine_design_dof_gate_status": catalog_gate["status"],
        "production_authority": False,
    }
    result["canonical_digest"] = canonical_digest(result)
    return result


__all__ = [
    "DecisionClass",
    "EXTERNAL_GOVERNING_VARIABLES",
    "FreedomClass",
    "GENUINE_FACTORLAB_DOF_ROOTS",
    "INITIAL_FACTORLAB_TRAINING_BLOCKERS",
    "PaperStatus",
    "build_parameter_catalog",
    "build_training_degree_of_freedom_audit",
    "parameter_scope_gate",
    "reaka_parameter_entries",
    "validate_parameter_catalog",
    "validate_training_parameter_instantiation",
]
