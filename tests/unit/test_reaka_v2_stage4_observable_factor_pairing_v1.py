from __future__ import annotations

import pandas as pd

from factor_lab.factor_rotation.reaka_v2_stage4_observable_factor_pairing_v1 import (
    FACTOR_ROOT,
    STATE_ROOT,
    build_pairing_panel,
    evaluate,
    load_contract,
)


def _panel() -> pd.DataFrame:
    states = pd.read_csv(STATE_ROOT / "formal/state_months.csv")
    factors = pd.read_csv(FACTOR_ROOT / "formal/monthly_selector_panel.csv")
    return build_pairing_panel(states, factors)


def test_contract_freezes_five_hypotheses_and_closes_stage5() -> None:
    contract = load_contract()
    assert contract["multiplicity_family_size"] == 5
    assert contract["legacy_same_month_trend_column_allowed"] is False
    authority = contract["authority"]
    assert isinstance(authority, dict)
    assert authority["stage4_execution_allowed"] is True
    assert authority["stage5_execution_allowed"] is False


def test_pairing_uses_previous_calendar_month_state() -> None:
    panel = _panel()
    source = pd.PeriodIndex(panel["source_period"], freq="M")
    decision = pd.PeriodIndex(panel["period"], freq="M")
    assert all(left + 1 == right for left, right in zip(source, decision, strict=True))
    assert len(panel.loc[panel["data_role"].eq("development_material_pairing")]) == 136


def test_stage4_scope_is_index_and_industry_only() -> None:
    annual, episodes, summary = evaluate(_panel())
    assert not annual.empty and not episodes.empty
    assert set(summary["factor"]) == {"index", "industry"}
    assert "size" not in set(summary["factor"])
    assert len(summary) == 30


def test_machine_does_not_sign_financial_verdict() -> None:
    _, _, summary = evaluate(_panel())
    assert set(summary["financial_verdict"]) == {"waiting_user_review"}
