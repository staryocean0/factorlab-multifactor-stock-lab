from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from factor_lab.factor_rotation.reaka_current_k1_account_ledgers_v1 import (
    annual_pnl_summary,
    annual_selection_summary,
    standardize_account_path,
)
from factor_lab.factor_rotation.reaka_intraday_portfolio_mapping_v1 import (
    AccountPath,
    buy_cost_bps,
)
from factor_lab.governance.canonicalization import canonical_digest


def test_standardize_account_path_builds_additive_trade_cost() -> None:
    dates = pd.to_datetime(["2020-01-02", "2020-01-03"])
    execution_price = 100.0
    transaction_cost = execution_price * buy_cost_bps(1.0) / 10_000.0
    path = AccountPath(
        daily=pd.DataFrame(
            {
                "date": dates,
                "nav": [1_000_001.0 - transaction_cost, 1_000_002.0 - transaction_cost],
                "daily_return": [1.0e-6 - transaction_cost / 1_000_000.0, 1.0 / (1_000_001.0 - transaction_cost)],
                "cash": [999_900.0 - transaction_cost, 999_900.0 - transaction_cost],
                "cash_weight": [0.999, 0.999],
                "holding_count": [1, 1],
                "is_rebalance": [True, False],
            }
        ),
        holdings=pd.DataFrame(
            {
                "date": dates,
                "symbol": ["000001", "000001"],
                "shares": [1.0, 1.0],
                "mark_price": [101.0, 102.0],
                "market_value": [101.0, 102.0],
            }
        ),
        trades=pd.DataFrame(
            {
                "date": [dates[0]],
                "symbol": ["000001"],
                "direction": ["buy"],
                "daily_total_cost": [transaction_cost],
            }
        ),
        events=pd.DataFrame(columns=["date", "symbol", "event_type", "reason"]),
        metrics={},
    )
    _, holdings, trades, events = standardize_account_path(
        path=path,
        clock="14:30",
        replay_segment_id="fixture",
        execution_price={(dates[0], "000001"): execution_price},
    )
    assert holdings["asset_id"].tolist() == ["000001", "000001"]
    assert trades.iloc[0]["trade_value"] == pytest.approx(100.0)
    assert trades.iloc[0]["transaction_cost"] == pytest.approx(transaction_cost)
    assert events.empty


def test_annual_selection_and_pnl_summaries_keep_two_ledger_questions_separate() -> None:
    selection = pd.DataFrame(
        [
            {
                "year": 2020,
                "decision_clock": "14:30",
                "replay_segment_id": "fixture",
                "decision_id": "d1",
                "eligible_count": 100,
                "selected_oracle_overlap_share": 0.2,
                "selected_mean_h20_return": 0.03,
                "oracle_mean_h20_return": 0.10,
                "selection_gap_mean_h20_return": -0.07,
                "selected_median_opportunity_rank": 55.0,
            }
        ]
    )
    selection_annual = annual_selection_summary(selection)
    assert selection_annual.iloc[0]["mean_selection_gap_h20_return"] == pytest.approx(-0.07)

    pnl = pd.DataFrame(
        [
            {
                "year": 2020,
                "decision_clock": "14:30",
                "replay_segment_id": "fixture",
                "component_id": "index",
                "simple_contribution": 0.02,
                "linked_log_contribution": 0.019,
            },
            {
                "year": 2020,
                "decision_clock": "14:30",
                "replay_segment_id": "fixture",
                "component_id": "transaction_cost",
                "simple_contribution": -0.001,
                "linked_log_contribution": -0.001,
            },
        ]
    )
    pnl_annual = annual_pnl_summary(pnl)
    assert set(pnl_annual["component_group"]) == {"index", "other"}


def test_current_ledger_contract_is_canonical_and_has_no_parameter_authority() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "docs/ops/reaka_current_k1_account_ledgers@1.5.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = payload.pop("canonical_digest")
    assert stored == canonical_digest(payload)
    assert payload["strategy_identity"]["model"] == "d8-h8-K1-r0_fit_prefix_successor_incumbent"
    assert payload["predecessor"]["canonical_digest"] == (
        "sha256:55f859f16ddabff4192b260d0c8445d061f48ad3c33aa87439fbf7c34b10f9db"
    )
    assert payload["authority"]["parameter_selection"] is False
    assert payload["authority"]["production_authority"] is False
