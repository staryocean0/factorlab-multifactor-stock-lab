"""Spec registry repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from factor_lab.core.settings import get_data_home
from factor_lab.factor_engine.advanced_factors import list_advanced_factor_specs
from factor_lab.factor_engine.models.factor_spec import (
    EvaluationProtocol,
    FactorSpec,
    LabelSpec,
)
from factor_lab.factor_engine.standard_factors import list_standard_factor_specs


class SpecRegistry:
    """Registry for factor, label, and protocol specifications."""

    def __init__(self):
        self._factor_specs: dict[str, FactorSpec] = {}
        self._label_specs: dict[str, LabelSpec] = {}
        self._protocols: dict[str, EvaluationProtocol] = {}

        # Version indexes
        self._factor_versions: dict[str, list[str]] = {}  # name -> list of version ids
        self._label_versions: dict[str, list[str]] = {}
        self._loaded_custom_path: Path | None = None
        self._load_standard_factor_specs()
        self._load_advanced_factor_specs()

    @staticmethod
    def _custom_spec_path() -> Path:
        directory = get_data_home() / "spec_registry"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / "factor_specs.json"

    @staticmethod
    def _factor_spec_from_dict(payload: dict[str, object]) -> FactorSpec:
        return FactorSpec(
            spec_id=str(payload.get("spec_id", payload.get("spec_version", ""))),
            spec_version=str(payload.get("spec_version", "")),
            name=str(payload.get("name", "")),
            description=str(payload.get("description", "")),
            factor_type=str(payload.get("factor_type", "python_callable")),
            callable_ref=str(payload.get("callable_ref", "")),
            dsl_expression=(
                str(payload["dsl_expression"])
                if payload.get("dsl_expression") is not None
                else None
            ),
            materialized_frame_ref=str(payload.get("materialized_frame_ref", "")),
            value_column=str(payload.get("value_column", "factor_value")),
            preprocess_spec_version=str(payload.get("preprocess_spec_version", "")),
            input_schema=(
                cast(dict[str, object], payload.get("input_schema"))
                if isinstance(payload.get("input_schema"), dict)
                else {}
            ),
            output_schema=(
                cast(dict[str, object], payload.get("output_schema"))
                if isinstance(payload.get("output_schema"), dict)
                else {}
            ),
            parameters=(
                cast(dict[str, object], payload.get("parameters"))
                if isinstance(payload.get("parameters"), dict)
                else {}
            ),
            source_family=str(payload.get("source_family", "price_volume")),
            source_refs=(
                [str(item) for item in cast(list[object], payload.get("source_refs"))]
                if isinstance(payload.get("source_refs"), list)
                else []
            ),
            input_field_lineage=(
                {
                    str(key): str(value)
                    for key, value in cast(
                        dict[object, object], payload.get("input_field_lineage")
                    ).items()
                }
                if isinstance(payload.get("input_field_lineage"), dict)
                else {}
            ),
            dsl_ast_version=str(payload.get("dsl_ast_version", "")),
            operator_set_version=str(payload.get("operator_set_version", "")),
            expression_hash=str(payload.get("expression_hash", "")),
            complexity_score=(
                float(str(payload.get("complexity_score", 0.0)))
                if payload.get("complexity_score") is not None
                else 0.0
            ),
            field_refs=(
                [str(item) for item in cast(list[object], payload.get("field_refs"))]
                if isinstance(payload.get("field_refs"), list)
                else []
            ),
            window_refs=(
                [
                    int(str(item))
                    for item in cast(list[object], payload.get("window_refs"))
                ]
                if isinstance(payload.get("window_refs"), list)
                else []
            ),
            nan_policy=str(payload.get("nan_policy", "")),
            normalized_ast=(
                cast(dict[str, object], payload.get("normalized_ast"))
                if isinstance(payload.get("normalized_ast"), dict)
                else {}
            ),
            operator_list=(
                [str(item) for item in cast(list[object], payload.get("operator_list"))]
                if isinstance(payload.get("operator_list"), list)
                else []
            ),
            tags=(
                {
                    str(key): str(value)
                    for key, value in cast(
                        dict[object, object], payload.get("tags")
                    ).items()
                }
                if isinstance(payload.get("tags"), dict)
                else {}
            ),
            feature_refs=(
                [
                    str(item)
                    for item in cast(list[object], payload.get("feature_refs"))
                ]
                if isinstance(payload.get("feature_refs"), list)
                else []
            ),
        )

    def _index_factor_spec(self, spec: FactorSpec) -> None:
        self._factor_specs[spec.spec_version] = spec
        _ = self._factor_versions.setdefault(spec.name, [])
        if spec.spec_version not in self._factor_versions[spec.name]:
            self._factor_versions[spec.name].append(spec.spec_version)

    def _load_standard_factor_specs(self) -> None:
        """Seed the registry with the built-in REQ-001 standard factors."""
        for spec in list_standard_factor_specs():
            self._index_factor_spec(spec)

    def _load_advanced_factor_specs(self) -> None:
        """Seed the registry with built-in advanced REQ-001 factors."""
        for spec in list_advanced_factor_specs():
            self._index_factor_spec(spec)

    def _load_custom_factor_specs(self) -> None:
        """Load runtime-registered specs from FACTOR_LAB_HOME."""
        path = self._custom_spec_path()
        if self._loaded_custom_path == path:
            return
        self._loaded_custom_path = path
        if not path.exists():
            return
        payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
        if not isinstance(payload, list):
            return
        for item in cast(list[object], payload):
            if isinstance(item, dict):
                spec = self._factor_spec_from_dict(cast(dict[str, object], item))
                if spec.spec_version:
                    self._index_factor_spec(spec)

    def _persist_custom_factor_specs(self) -> None:
        """Persist non-built-in specs so DSL/API-created specs survive restart."""
        path = self._custom_spec_path()
        built_in_tags = {"standard_price_volume", "advanced_standardized_market"}
        payload = [
            spec.to_dict()
            for spec in self._factor_specs.values()
            if spec.tags.get("library") not in built_in_tags
        ]
        _ = path.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )

    # Factor Specs
    async def register_factor_spec(self, spec: FactorSpec) -> FactorSpec:
        """Register a factor spec."""
        return self.register_factor_spec_sync(spec)

    def register_factor_spec_sync(self, spec: FactorSpec) -> FactorSpec:
        """Register a factor spec from deterministic non-async build workflows."""

        self._load_custom_factor_specs()
        self._index_factor_spec(spec)
        self._persist_custom_factor_specs()
        return spec

    def get_factor_spec_sync(self, spec_version: str) -> FactorSpec | None:
        """Synchronously get factor spec by version string."""
        self._load_custom_factor_specs()
        return self._factor_specs.get(spec_version)

    async def get_factor_spec(self, spec_version: str) -> FactorSpec | None:
        """Get factor spec by version string."""
        return self.get_factor_spec_sync(spec_version)

    async def list_factor_specs(self, name: str | None = None) -> list[FactorSpec]:
        """List factor specs, optionally filtered by name."""
        self._load_custom_factor_specs()
        if name:
            versions = self._factor_versions.get(name, [])
            return [self._factor_specs[v] for v in versions if v in self._factor_specs]
        return list(self._factor_specs.values())

    def list_factor_specs_sync(self, name: str | None = None) -> list[FactorSpec]:
        """Synchronously list factor specs for runtime inventory services."""
        self._load_custom_factor_specs()
        if name:
            versions = self._factor_versions.get(name, [])
            return [self._factor_specs[v] for v in versions if v in self._factor_specs]
        return list(self._factor_specs.values())

    # Label Specs
    async def register_label_spec(self, spec: LabelSpec) -> LabelSpec:
        """Register a label spec."""
        self._label_specs[spec.spec_version] = spec

        if spec.name not in self._label_versions:
            self._label_versions[spec.name] = []
        if spec.spec_version not in self._label_versions[spec.name]:
            self._label_versions[spec.name].append(spec.spec_version)

        return spec

    async def get_label_spec(self, spec_version: str) -> LabelSpec | None:
        """Get label spec by version."""
        return self._label_specs.get(spec_version)

    # Protocols
    async def register_protocol(
        self, protocol: EvaluationProtocol
    ) -> EvaluationProtocol:
        """Register an evaluation protocol."""
        self._protocols[protocol.protocol_version] = protocol
        return protocol

    async def get_protocol(self, protocol_version: str) -> EvaluationProtocol | None:
        """Get protocol by version."""
        return self._protocols.get(protocol_version)


# Global registry instance
spec_registry = SpecRegistry()
