"""Exposure-first factor rotation infrastructure.

Public conveniences load on use. Importing a bounded REAKA submodule must not
require unrelated services from the full local FactorLab distribution.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {'CANDIDATE_USAGE_SCHEMA_VERSION': 'factor_lab.factor_rotation.candidate_profile_workflow', 'build_candidate_profile_artifacts': 'factor_lab.factor_rotation.candidate_profile_workflow', 'build_factor_candidate_usage_report': 'factor_lab.factor_rotation.candidate_profile_workflow', 'FACTOR_ROTATION_FRAMEWORK_VERSION': 'factor_lab.factor_rotation.constants', 'LEGACY_BASELINE_STATUS': 'factor_lab.factor_rotation.constants', 'FACTOR_EFFECTIVENESS_PROFILE_SCHEMA_VERSION': 'factor_lab.factor_rotation.effectiveness_profile', 'build_factor_effectiveness_profile': 'factor_lab.factor_rotation.effectiveness_profile', 'build_factor_profile_cards': 'factor_lab.factor_rotation.effectiveness_profile', 'FactorSpec': 'factor_lab.factor_rotation.factor_specs', 'builtin_factor_registry': 'factor_lab.factor_rotation.factor_specs', 'FACTOR_USAGE_METHOD_STATE_SCHEMA_VERSION': 'factor_lab.factor_rotation.factor_usage_method_state', 'FactorUsageMethodEvidence': 'factor_lab.factor_rotation.factor_usage_method_state', 'FactorUsageMethodSpec': 'factor_lab.factor_rotation.factor_usage_method_state', 'build_factor_usage_method_production_gate_report': 'factor_lab.factor_rotation.factor_usage_method_state', 'build_factor_usage_method_state_report': 'factor_lab.factor_rotation.factor_usage_method_state', 'build_p3_fallback_method_spec': 'factor_lab.factor_rotation.factor_usage_method_state', 'build_v6_narrow_method_spec': 'factor_lab.factor_rotation.factor_usage_method_state', 'classify_factor_usage_method': 'factor_lab.factor_rotation.factor_usage_method_state'}
__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
