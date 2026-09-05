"""Archived launchers must refuse before dependencies, data, or evidence writes."""

from __future__ import annotations

import ast
import copy
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

from factor_lab.governance.reaka_foundation_contract import (
    reject_legacy_entrypoint,
    require_research_action,
)

ROOT = Path(__file__).resolve().parents[2]
LEGACY_LAUNCHERS = tuple(
    f"scripts/factor_rotation/{name}.py"
    for name in (
        "build_reaka_multifactor_infrastructure_v1",
        "build_reaka_v2_stage3_observable_context_v2",
        "build_reaka_v2_stage4_observable_factor_pairing_v1",
        "close_reaka_multifactor_infrastructure_v1",
        "close_reaka_v2_stage3_observable_context_v2",
        "close_reaka_v2_stage3_state_episode_atlas_v1",
        "close_reaka_v2_stage4_observable_factor_pairing_v1",
        "freeze_reaka_v2_stage3_state_episode_atlas_v1",
        "run_reaka_v2_stage3_observable_context_v2",
        "run_reaka_v2_stage3_state_episode_atlas_v1",
        "run_reaka_v2_stage4_observable_factor_pairing_v1",
        "validate_reaka_multifactor_infrastructure_v1",
        "validate_reaka_v2_stage3_observable_context_v2",
        "validate_reaka_v2_stage3_state_episode_atlas_v1",
        "validate_reaka_v2_stage4_observable_factor_pairing_v1",
    )
) + (
    "scripts/build_strategy_slice_rebuild_workflow.py",
    "scripts/build_strategy_progressive_development_workflow.py",
)
LEGACY_FUNCTIONS = (
    ("reaka_paper_v1", "fit_reaka_paper_challenger", "train"),
    ("reaka_paper_v1_runtime", "run_reaka_paper_round3a_diagnostic", "train"),
    ("reaka_stage6_parameter_calibration", "run_declared_fit", "train"),
    ("reaka_stage6_parameter_calibration", "execute", "train"),
    ("reaka_v2_stage3_state_episode_atlas_v1", "execute_tree", "stage3_execute"),
    ("reaka_v2_stage3_observable_context_v2", "execute_tree", "stage3_execute"),
    ("reaka_k1_only_index_regime_atlas_v1", "execute_tree", "stage3_execute"),
)


@pytest.mark.parametrize("relative", LEGACY_LAUNCHERS)
def test_direct_legacy_cli_refuses_without_site_packages(relative: str, tmp_path: Path) -> None:
    # -I -S removes PYTHONPATH and installed dependencies. The real CLI must
    # still explain its retirement instead of importing pandas/torch first.
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(ROOT / relative), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert "RuntimeError: REAKA archived entrypoint" in result.stderr
    assert "scripts/validate_reaka_foundation.py" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr
    assert result.stdout == ""
    assert list(tmp_path.iterdir()) == []


def _source_function(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return copy.deepcopy(next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name))


def _compile_source_function(node: ast.FunctionDef, path: Path, namespace: dict[str, object]) -> object:
    # Compile the complete, unmodified function body without importing the old
    # module's unavailable project dependencies. Defaults are irrelevant to
    # the first-action guard, so avoid evaluating their historical constants.
    node.args.defaults = [ast.Constant(None) for _ in node.args.defaults]
    node.args.kw_defaults = [ast.Constant(None) if value is not None else None for value in node.args.kw_defaults]
    module = ast.Module(
        body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), node],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[node.name]


@pytest.mark.parametrize("relative", LEGACY_LAUNCHERS)
def test_imported_legacy_main_cannot_bypass_cli_guard(relative: str) -> None:
    path = ROOT / relative
    node = _source_function(path, "main")
    main = _compile_source_function(
        node,
        path,
        {"__file__": str(path), "_reject_legacy_entrypoint": reject_legacy_entrypoint},
    )
    # No argparse or output helpers exist in this namespace: any attempt to
    # reach the retired body before the real guard fails this assertion.
    with pytest.raises(RuntimeError, match="REAKA archived entrypoint"):
        main()


@pytest.mark.parametrize(("module_name", "function_name", "action"), LEGACY_FUNCTIONS)
def test_public_legacy_execution_checks_authority_before_body(
    module_name: str, function_name: str, action: str
) -> None:
    path = ROOT / "src/factor_lab/factor_rotation" / f"{module_name}.py"
    node = _source_function(path, function_name)
    body = node.body
    if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    first_call = body[0]
    assert isinstance(first_call, ast.Expr) and isinstance(first_call.value, ast.Call)
    assert isinstance(first_call.value.func, ast.Name)
    assert first_call.value.func.id == "require_research_action"
    assert isinstance(first_call.value.args[1], ast.Constant)
    assert first_call.value.args[1].value == action
    function = _compile_source_function(
        node,
        path,
        {"__file__": str(path), "Path": Path, "require_research_action": require_research_action},
    )
    arguments = {argument.arg: None for argument in (*node.args.args, *node.args.kwonlyargs)}
    with pytest.raises(PermissionError):
        function(**arguments)


def test_imported_stage3_runner_refuses_before_frozen_data_is_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("factor_lab.factor_rotation.reaka_v2_stage3_observable_context_v2")

    def unexpected_data_read(*args: object, **kwargs: object) -> None:
        pytest.fail("retired runner read historical data before checking current authority")

    monkeypatch.setattr(module.pd, "read_csv", unexpected_data_read)
    with pytest.raises(PermissionError):
        module.execute_tree(tree="formal")


def test_imported_paper_fit_refuses_before_optimizer_or_tensor_work(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("factor_lab.factor_rotation.reaka_paper_v1")

    def unexpected_training(*args: object, **kwargs: object) -> None:
        pytest.fail("retired fit initialized training before checking current authority")

    monkeypatch.setattr(module, "_seed_everything", unexpected_training)
    with pytest.raises(PermissionError):
        module.fit_reaka_paper_challenger(panel=None, train_indices=None, test_indices=None, seed=1)
