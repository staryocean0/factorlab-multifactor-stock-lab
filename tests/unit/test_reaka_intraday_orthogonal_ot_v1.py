# pyright: reportAny=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false, reportGeneralTypeIssues=false

from __future__ import annotations

import numpy as np
import pandas as pd

from factor_lab.factor_rotation import orthogonal_index_timing_transport_ot1_v1 as old_ot1
from factor_lab.factor_rotation.reaka_intraday_orthogonal_ot_v1 import (
    MARKET_FACTOR_ID,
    SIZE_FACTOR_ID,
    build_causal_basis_pair,
    evaluate_annual_tools,
    family_id,
    fit_intraday_stock_exposures,
    json_records,
    validate_contract,
)
from factor_lab.governance.canonicalization import canonical_digest


def _carriers() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(7)
    days = 150
    history = np.zeros((6, days, 4), dtype=np.float64)
    future = np.zeros_like(history)
    for variant in range(6):
        market = rng.normal(0, 0.01, days)
        small = 0.7 * market + rng.normal(0, 0.005, days)
        large = 0.3 * market + rng.normal(0, 0.005, days)
        industry = 0.4 * market + 0.2 * (small - large) + rng.normal(0, 0.004, days)
        history[variant] = np.column_stack((market, small, large, industry))
        future[variant] = history[variant] + rng.normal(0, 0.001, (days, 4))
    calendar = np.arange(
        np.datetime64("2010-01-01"),
        np.datetime64("2010-01-01") + days,
    ).astype("datetime64[ns]")
    return history, future, calendar


def test_future_basis_uses_history_fit_but_future_current_values() -> None:
    history, future, calendar = _carriers()
    left = build_causal_basis_pair(
        history,
        future,
        calendar,
        ["L1_FACTOR_CORE:test"],
        decision_clock="14:30",
    )
    changed = future.copy()
    changed[:, 130:, 0] += 0.02
    right = build_causal_basis_pair(
        history,
        changed,
        calendar,
        ["L1_FACTOR_CORE:test"],
        decision_clock="14:30",
    )
    np.testing.assert_array_equal(left[0], right[0])
    assert not np.array_equal(left[1], right[1], equal_nan=True)
    assert left[4]["uses_future"].eq(False).all()


def test_stock_exposure_fit_ends_strictly_before_decision() -> None:
    rng = np.random.default_rng(11)
    days, stocks = 150, 5
    calendar = np.arange(
        np.datetime64("2010-01-01"),
        np.datetime64("2010-01-01") + days,
    ).astype("datetime64[ns]")
    basis_h = rng.normal(0, 0.01, (6, days, 2))
    basis_f = basis_h + rng.normal(0, 0.001, basis_h.shape)
    history = np.zeros((days, stocks), dtype=np.float32)
    future = np.zeros_like(history)
    for stock in range(stocks):
        fold = stock % 5 + 1
        history[:, stock] = 0.001 + 0.7 * basis_h[fold, :, 0] - 0.2 * basis_h[fold, :, 1]
        future[:, stock] = 0.001 + 0.7 * basis_f[fold, :, 0] - 0.2 * basis_f[fold, :, 1]
    marks = np.ones_like(history)
    exposures, _, _, epsilon_h, epsilon_f = fit_intraday_stock_exposures(
        history_returns=history,
        future_returns=future,
        decision_marks=marks,
        history_basis=basis_h,
        future_basis=basis_f,
        calendar=calendar,
        symbols=np.asarray([f"{value:06d}" for value in range(stocks)]),
        decision_positions=np.asarray([120, 125, 130, 135, 140, 145]),
        industry_ids=[],
        industry_membership={day: {} for day in (120, 125, 130, 135, 140, 145)},
        decision_clock="14:30",
    )
    assert len(exposures) > 0
    assert pd.to_datetime(exposures["fit_end_date"]).lt(pd.to_datetime(exposures["asof_date"])).all()
    assert np.isfinite(epsilon_h).any()
    assert np.isfinite(epsilon_f).any()


def test_annual_OT2_uses_D5_future_targets_and_mean_metrics() -> None:
    dates = pd.date_range("2019-01-04", periods=40, freq="7D")
    candidate = pd.concat(
        [
            pd.DataFrame(
                {
                    "decision_clock": "14:30",
                    "variant_id": "full_reference",
                    "decision_date": dates,
                    "factor_id": MARKET_FACTOR_ID,
                    "economic_family_id": "market",
                    "tool_id": tool,
                    "timing_state": state,
                    "available": True,
                    "uses_forward_outcome": False,
                }
            )
            for tool, state in (
                ("test_tool", np.ones(len(dates))),
                ("naked_residual_level_follow_control_v1", np.zeros(len(dates))),
            )
        ],
        ignore_index=True,
    )
    future = pd.DataFrame(
        {
            "variant_id": "full_reference",
            "trading_day": dates,
            "factor_id": MARKET_FACTOR_ID,
            "orthogonal_return": 0.02,
        }
    )
    metrics = evaluate_annual_tools(
        candidate_states=candidate,
        future_basis=future,
        decision_dates=dates,
        year=2019,
    )
    selected = metrics.loc[metrics["tool_id"].eq("test_tool")].iloc[0]
    assert selected["observation_decisions"] == 39
    assert np.isclose(selected["candidate_net"], 0.02)
    assert np.isclose(selected["incremental_net_vs_naked"], 0.02)


def test_family_identity_and_contract_are_fail_closed() -> None:
    assert family_id(MARKET_FACTOR_ID) == "market"
    assert family_id(SIZE_FACTOR_ID) == "size"
    assert family_id("L1_FACTOR_CORE:test") == "industry"
    payload: dict[str, object] = {
        "schema_id": "factorlab.reaka_intraday_orthogonal_OT1_OT3@1.0",
        "decision_clocks": ["14:30", "14:45"],
        "fit_end": "strict_t_minus_1",
        "model_training_allowed": False,
        "account_execution_allowed": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    assert validate_contract(payload) == []
    payload["fit_end"] = "through_t"
    payload["canonical_digest"] = canonical_digest({key: value for key, value in payload.items() if key != "canonical_digest"})
    assert "intraday_OT_fit_end_not_t_minus_1" in validate_contract(payload)


def test_crossfit_fold_identity_is_preserved() -> None:
    positions = np.arange(15)
    assert old_ot1.stock_fold(positions).tolist() == [0, 1, 2, 3, 4] * 3


def test_selection_records_are_strict_JSON_null_not_nan() -> None:
    records = json_records(pd.DataFrame({"tool_id": ["control"], "score": [np.nan]}))
    assert records == [{"tool_id": "control", "score": None}]
