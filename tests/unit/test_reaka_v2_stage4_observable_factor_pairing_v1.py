from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import factor_lab.factor_rotation.reaka_v2_stage4_observable_factor_pairing_v1 as pairing


def _inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Independent finite fixture: no observed strategy results enter the tests."""
    states: list[dict[str, object]] = []
    factors: list[dict[str, object]] = []
    for year in (2015, 2017, 2018):
        for number, month in enumerate(pd.period_range(f"{year}-01", f"{year}-12", freq="M")):
            source = month - 1
            role = (
                "development_selection" if year < 2017 else "development_listing" if year == 2017 else "consumed_blackbox_diagnostic"
            )
            state_role = "development_material_state_certificate" if year < 2017 else pairing.data_role(role)
            trend = ("up", "down", "sideways")[number % 3]
            states.append(
                {
                    "decision_period": str(month),
                    "source_period": str(source),
                    "trend": trend,
                    "data_role": state_role,
                    "pit_available_at": source.end_time.strftime("%Y-%m-%d"),
                    "source_last_date": source.end_time.strftime("%Y-%m-%d"),
                }
            )
            for clock in ("14:30", "14:45"):
                factors.append(
                    {
                        "period": str(month),
                        "decision_clock": clock,
                        "year": year,
                        "index": (0.02, -0.02, 0.0)[number % 3],
                        "industry": (0.01, -0.01, 0.005)[number % 3],
                        "data_role": role,
                    }
                )
    return pd.DataFrame(states), pd.DataFrame(factors)


def _panel() -> pd.DataFrame:
    return pairing.build_pairing_panel(*_inputs())


def test_sealed_contract_retains_five_hypotheses_but_is_not_live_execution_authority() -> None:
    contract = json.loads(pairing.CONTRACT.read_text(encoding="utf-8"))
    assert contract["multiplicity_family_size"] == 5
    assert contract["legacy_same_month_trend_column_allowed"] is False
    assert contract["authority"]["stage5_execution_allowed"] is False
    # A legitimate live-source repair cannot silently rewrite or rebind the old seal.
    with pytest.raises(PermissionError, match="contract_or_source_invalid"):
        pairing.load_contract()


def test_pairing_uses_previous_calendar_month_state_and_preserves_every_row() -> None:
    panel = _panel()
    source = pd.PeriodIndex(panel["source_period"], freq="M")
    decision = pd.PeriodIndex(panel["period"], freq="M")
    assert (source + 1 == decision).all()
    assert len(panel) == 72
    assert not panel.duplicated(["data_role", "decision_clock", "period"]).any()


def test_stage4_scope_is_descriptive_index_and_industry_only() -> None:
    annual, episodes, summary = pairing.evaluate(_panel())
    assert not annual.empty and not episodes.empty
    assert set(summary["factor"]) == {"index", "industry"}
    assert len(summary) == 30
    assert set(summary["financial_verdict"]) == {"waiting_user_review"}


def test_existing_duplicate_months_are_rejected_without_deduplication() -> None:
    states = pd.read_csv(pairing.STATE_ROOT / "formal/state_months.csv")
    factors = pd.read_csv(pairing.FACTOR_ROOT / "formal/monthly_selector_panel.csv")
    assert factors.duplicated(["period", "decision_clock"]).any()
    with pytest.raises(ValueError, match="duplicate_monthly_key"):
        pairing.build_pairing_panel(states, factors)


@pytest.mark.parametrize("different_role", [False, True])
def test_duplicate_monthly_key_cannot_hide_behind_role(different_role: bool) -> None:
    states, factors = _inputs()
    duplicate = factors.iloc[[0]].copy()
    if different_role:
        duplicate["data_role"] = "consumed_blackbox_diagnostic"
    factors = pd.concat([factors, duplicate], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate_monthly_key"):
        pairing.build_pairing_panel(states, factors)


def test_duplicate_state_month_is_rejected() -> None:
    states, factors = _inputs()
    with pytest.raises(ValueError, match="duplicate_state_month"):
        pairing.build_pairing_panel(pd.concat([states, states.iloc[[0]]], ignore_index=True), factors)


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf, "invalid"])
def test_nonfinite_or_nonnumeric_attribution_is_rejected(value: object) -> None:
    states, factors = _inputs()
    factors["index"] = factors["index"].astype(object)
    factors.loc[0, "index"] = value
    with pytest.raises(ValueError, match="factor_(missing_values|values_nonfinite|values_invalid)"):
        pairing.build_pairing_panel(states, factors)


@pytest.mark.parametrize("source_period", ["2015-01", "2014-11", "2014-12-01", "2014-13"])
def test_same_month_stale_or_noncanonical_state_is_rejected(source_period: str) -> None:
    states, factors = _inputs()
    states.loc[0, "source_period"] = source_period
    with pytest.raises(ValueError, match="previous_calendar_month|month_invalid"):
        pairing.build_pairing_panel(states, factors)


@pytest.mark.parametrize("available", ["2015-01-01", "2015-01-20", "2014-12-01", "NaT", "2015-01-01T01:00:00+08:00"])
def test_state_publication_must_follow_source_and_precede_decision_month(available: str) -> None:
    states, factors = _inputs()
    states.loc[0, "pit_available_at"] = available
    with pytest.raises(ValueError, match="state_not_pit"):
        pairing.build_pairing_panel(states, factors)


def test_year_must_match_month_exactly() -> None:
    states, factors = _inputs()
    factors.loc[0, "year"] = 2016
    with pytest.raises(ValueError, match="year_mismatch"):
        pairing.build_pairing_panel(states, factors)


def test_consumed_year_cannot_be_relabelled_as_development_in_both_inputs() -> None:
    states, factors = _inputs()
    factors.loc[factors["year"].eq(2018), "data_role"] = "development_selection"
    states.loc[states["decision_period"].str.startswith("2018"), "data_role"] = "development_material_state_certificate"
    with pytest.raises(ValueError, match="calendar_role_mismatch"):
        pairing.build_pairing_panel(states, factors)


def test_both_clocks_require_identical_month_support() -> None:
    states, factors = _inputs()
    with pytest.raises(ValueError, match="clock_support_mismatch"):
        pairing.build_pairing_panel(states, factors.iloc[1:])


def test_missing_month_breaks_an_episode_even_if_trend_is_unchanged() -> None:
    states, factors = _inputs()
    months = ["2015-01", "2015-03"]
    states = states.loc[states["decision_period"].isin(months)].copy()
    states["trend"] = "up"
    factors = factors.loc[factors["period"].isin(months)]
    panel = pairing.build_pairing_panel(states, factors)
    assert panel["episode_id"].nunique() == 2


@pytest.mark.parametrize("column", ["pit_available_at", "source_last_date"])
def test_missing_pit_evidence_is_rejected(column: str) -> None:
    states, factors = _inputs()
    with pytest.raises(ValueError, match="state_columns_invalid"):
        pairing.build_pairing_panel(states.drop(columns=column), factors)


def test_direct_evaluation_cannot_bypass_monthly_key_validation() -> None:
    panel = _panel()
    with pytest.raises(ValueError, match="duplicate_monthly_key"):
        pairing.evaluate(pd.concat([panel, panel.iloc[[0]]], ignore_index=True))


def test_zero_effect_is_no_direction_and_never_opposed_or_positive() -> None:
    panel = _panel()
    panel[["index", "industry"]] = 0.0
    _, _, summary = pairing.evaluate(panel)
    assert set(summary["machine_directional_evidence"]) == {"no_direction"}
    assert set(summary["financial_verdict"]) == {"waiting_user_review"}


def _bound_input_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    states, factors = _inputs()
    root = tmp_path / "inputs"
    (root / "formal").mkdir(parents=True)
    monkeypatch.setattr(pairing, "STATE_ROOT", root)
    monkeypatch.setattr(pairing, "FACTOR_ROOT", root)
    digests = {}
    for name, frame in (("state_months.csv", states), ("monthly_selector_panel.csv", factors)):
        path = root / "formal" / name
        frame.to_csv(path, index=False)
        digests[name] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return {"input_digests": {"formal": digests}, "canonical_digest": "synthetic"}


def test_loader_reads_exact_hash_bound_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _bound_input_files(tmp_path, monkeypatch)
    states, factors = pairing._load_bound_inputs(contract, tree="formal")
    assert len(pairing.build_pairing_panel(states, factors)) == 72


@pytest.mark.parametrize("name", ["state_months.csv", "monthly_selector_panel.csv"])
def test_tampered_bound_input_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    contract = _bound_input_files(tmp_path, monkeypatch)
    path = pairing.STATE_ROOT / "formal" / name
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(PermissionError, match="input_digest_mismatch"):
        pairing._load_bound_inputs(contract, tree="formal")


def test_missing_digest_inventory_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _bound_input_files(tmp_path, monkeypatch)
    with pytest.raises(PermissionError, match="input_digest_inventory_invalid"):
        pairing._load_bound_inputs({}, tree="formal")


def test_old_executor_is_closed_before_input_reads_or_output_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pairing, "OUTPUT_ROOT", tmp_path / "output")

    def must_not_load() -> dict[str, object]:
        pytest.fail("historical contract was loaded before current authority check")

    monkeypatch.setattr(pairing, "load_contract", must_not_load)
    with pytest.raises(PermissionError):
        pairing.execute_tree(tree="formal")
    assert not (tmp_path / "output").exists()
