"""Factor, label, and evaluation protocol specification models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from factor_lab.core.source_universe import PRICE_VOLUME_SOURCE_FAMILY


@dataclass
class FactorSpec:
    """Versioned factor specification.

    `spec_version` remains the public identifier used by legacy fixtures.  REQ-001
    lineage fields make the spec self-describing when it is served through the API
    or embedded in factor-frame artifacts.
    """

    spec_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    spec_version: str = ""

    # Metadata
    name: str = ""
    description: str = ""

    # Implementation
    # python_callable, template, formulaic_dsl, materialized_frame
    factor_type: str = "python_callable"
    callable_ref: str = ""  # e.g., "factor_lab.factor_engine.factors.momentum_20d"
    dsl_expression: str | None = None
    materialized_frame_ref: str = ""
    value_column: str = "factor_value"

    # Preprocessing spec reference
    preprocess_spec_version: str = ""

    # Input/output schema
    input_schema: dict[str, object] = field(default_factory=dict)
    output_schema: dict[str, object] = field(default_factory=dict)

    # Parameters
    parameters: dict[str, object] = field(default_factory=dict)

    # REQ-001 lineage
    source_family: str = PRICE_VOLUME_SOURCE_FAMILY
    source_refs: list[str] = field(default_factory=list)
    input_field_lineage: dict[str, str] = field(default_factory=dict)

    # Formulaic DSL governance metadata
    dsl_ast_version: str = ""
    operator_set_version: str = ""
    expression_hash: str = ""
    complexity_score: float = 0.0
    field_refs: list[str] = field(default_factory=list)
    window_refs: list[int] = field(default_factory=list)
    nan_policy: str = ""
    normalized_ast: dict[str, object] = field(default_factory=dict)
    operator_list: list[str] = field(default_factory=list)

    # Tags
    tags: dict[str, str] = field(default_factory=dict)

    # Feature-library bridge.  Empty by default for backward compatibility with
    # legacy FactorSpec fixtures and DSL-created specs.
    feature_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "spec_id": self.spec_id,
            "spec_version": self.spec_version,
            "factor_spec_version": self.spec_version,
            "name": self.name,
            "description": self.description,
            "factor_type": self.factor_type,
            "callable_ref": self.callable_ref,
            "dsl_expression": self.dsl_expression,
            "materialized_frame_ref": self.materialized_frame_ref,
            "value_column": self.value_column,
            "preprocess_spec_version": self.preprocess_spec_version,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "parameters": self.parameters,
            "source_family": self.source_family,
            "source_refs": self.source_refs,
            "input_field_lineage": self.input_field_lineage,
            "dsl_ast_version": self.dsl_ast_version,
            "operator_set_version": self.operator_set_version,
            "expression_hash": self.expression_hash,
            "complexity_score": self.complexity_score,
            "field_refs": self.field_refs,
            "window_refs": self.window_refs,
            "nan_policy": self.nan_policy,
            "normalized_ast": self.normalized_ast,
            "operator_list": self.operator_list,
            "tags": self.tags,
            "feature_refs": self.feature_refs,
        }


@dataclass
class LabelSpec:
    """Label specification."""

    spec_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    spec_version: str = ""

    name: str = ""
    description: str = ""

    label_type: str = "forward_return"
    horizon: str = "5d"  # 1d, 5d, 10d, etc.

    # Calculation
    calculation: str = ""  # e.g., "(close[t+5] / close[t+1]) - 1"
    exclude_current_bar: bool = True
    use_adjusted_prices: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "spec_id": self.spec_id,
            "spec_version": self.spec_version,
            "name": self.name,
            "description": self.description,
            "label_type": self.label_type,
            "horizon": self.horizon,
            "calculation": self.calculation,
            "exclude_current_bar": self.exclude_current_bar,
            "use_adjusted_prices": self.use_adjusted_prices,
        }


@dataclass
class EvaluationProtocol:
    """Evaluation protocol specification."""

    protocol_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    protocol_version: str = ""

    name: str = ""
    description: str = ""

    # Configuration
    horizon: str = "1d"
    groups: list[str] = field(default_factory=lambda: ["quantile_5"])
    metrics: list[str] = field(default_factory=lambda: ["ic", "rank_ic", "turnover"])

    cost_model: str = "none"  # none, basic, advanced
    neutralization: list[str] = field(default_factory=list)  # market, industry, size

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "name": self.name,
            "description": self.description,
            "horizon": self.horizon,
            "groups": self.groups,
            "metrics": self.metrics,
            "cost_model": self.cost_model,
            "neutralization": self.neutralization,
        }
