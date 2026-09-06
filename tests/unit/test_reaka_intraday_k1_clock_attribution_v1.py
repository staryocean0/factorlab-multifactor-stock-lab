from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from factor_lab.factor_rotation.reaka_intraday_k1_clock_attribution_v1 import (
    CELL_SPECS,
    factorial_effects,
    forecast_semantics_audit,
)


def test_cells_form_exact_two_by_two_without_new_configuration() -> None:
    identities = {
        (
            str(row["clock"]),
            str(cast(Mapping[str, object], row["config"])["config_id"]),
        )
        for row in CELL_SPECS
    }
    assert len(identities) == 4
    assert {str(row["source"]) for row in CELL_SPECS} == {
        "P6_4_control",
        "P6_4_1_missing",
    }


def test_factorial_effects_separate_clock_config_and_interaction() -> None:
    cells = {
        "1430_A": {"value": 1.0},
        "1430_B": {"value": 3.0},
        "1445_A": {"value": 2.0},
        "1445_B": {"value": 6.0},
    }
    effects = factorial_effects(cells, "value")
    assert effects["clock_1445_minus_1430"] == 2.0
    assert effects["config_B_minus_A"] == 3.0
    assert effects["difference_in_differences_interaction"] == 2.0


def test_current_forecast_uses_one_nonrecursive_transition() -> None:
    audit = forecast_semantics_audit()
    assert audit["forecast_transition_call_count"] == 1
    assert audit["forecast_recursive_transition_loop_count"] == 0
    assert audit["passed"] is True
