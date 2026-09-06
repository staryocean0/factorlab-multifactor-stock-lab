from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import scripts.factor_rotation.build_reaka_intraday_portfolio_mapping_market_rebuild_v2 as rebuild

from factor_lab.factor_rotation.reaka_intraday_portfolio_mapping_v1 import write_json


def _metadata() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trading_day": "2011-01-04",
                "symbol": "000638",
                "exchange": "SZSE",
                "board": "main",
                "listing_phase": "seasoned",
                "risk_warning_state": "normal",
                "historical_name": "万方地产",
                "suspension_status": "not_suspended",
            },
            {
                "trading_day": "2011-01-05",
                "symbol": "000638",
                "exchange": "SZSE",
                "board": "main",
                "listing_phase": "seasoned",
                "risk_warning_state": "normal",
                "historical_name": "万方地产",
                "suspension_status": "not_full_day_suspended",
            },
            {
                "trading_day": "2020-12-31",
                "symbol": "000638",
                "exchange": "SZSE",
                "board": "main",
                "listing_phase": "seasoned",
                "risk_warning_state": "normal",
                "historical_name": "万方发展",
                "suspension_status": "not_suspended",
            },
        ]
    )


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trading_day": "2010-12-31",
                "symbol": "000638",
                "open": 9.8,
                "close": 10.0,
                "volume": 100.0,
                "amount": 1000.0,
            },
            {
                "trading_day": "2011-01-04",
                "symbol": "000638",
                "open": 10.2,
                "close": 10.5,
                "volume": 100.0,
                "amount": 1000.0,
            },
            {
                "trading_day": "2011-01-05",
                "symbol": "000638",
                "open": 10.6,
                "close": 10.7,
                "volume": 100.0,
                "amount": 1000.0,
            },
            {
                "trading_day": "2020-12-31",
                "symbol": "000638",
                "open": 11.0,
                "close": 11.2,
                "volume": 100.0,
                "amount": 1000.0,
            },
        ]
    )


def _fake_rules(tmp_path: Path):
    rules = tmp_path / "rules.json"
    rules.write_text("{}\n", encoding="utf-8")

    class Query:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def resolve(_profile, _query):
        return SimpleNamespace(
            status="resolved",
            rule_id="main_normal_10pct",
            gap_id="",
            params={"has_limit": True, "upper_ratio": 0.10, "lower_ratio": 0.10},
            detail="",
        )

    return object(), Query, resolve, rules


def test_repair_tradeability_uses_previous_raw_close_and_not_full_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata_path = tmp_path / "metadata.parquet"
    bars_path = tmp_path / "bars.parquet"
    _metadata().to_parquet(metadata_path, index=False)
    _bars().to_parquet(bars_path, index=False)
    monkeypatch.setattr(rebuild, "_load_rules", lambda: _fake_rules(tmp_path))
    panel, report = rebuild._repair_tradeability_panel(
        metadata_path=metadata_path,
        raw_bars_path=bars_path,
    )
    assert panel["previous_tradable_close"].tolist() == [10.0, 10.5, 10.7]
    assert panel["paused"].tolist() == [False, False, False]
    assert panel["suspension_status"].tolist() == [
        "not_suspended",
        "not_full_day_suspended",
        "not_suspended",
    ]
    assert report["unresolved_rule_rows"] == 0


def test_repair_tradeability_rejects_positive_bar_full_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata = _metadata()
    metadata.loc[0, "suspension_status"] = "full_day"
    metadata_path = tmp_path / "metadata.parquet"
    bars_path = tmp_path / "bars.parquet"
    metadata.to_parquet(metadata_path, index=False)
    _bars().to_parquet(bars_path, index=False)
    monkeypatch.setattr(rebuild, "_load_rules", lambda: _fake_rules(tmp_path))
    with pytest.raises(ValueError, match="positive_bar_marked_full_day"):
        rebuild._repair_tradeability_panel(
            metadata_path=metadata_path,
            raw_bars_path=bars_path,
        )


def test_score_market_join_requires_all_143_target_coordinates() -> None:
    dates = pd.date_range("2011-01-04", periods=143, freq="B")
    score = pd.DataFrame(
        {
            "decision_date": dates,
            "decision_clock": "14:30",
            "symbol": "000638",
        }
    )
    market = pd.DataFrame(
        {"date": dates, "decision_clock": "14:30", "symbol": "000638"}
    )
    report = rebuild._score_market_join_report(score, market, clock="14:30")
    assert report["target_joined_coordinate_count"] == 143
    assert report["missing_score_market_coordinates"] == 0


def test_score_market_join_fails_one_missing_target_coordinate() -> None:
    dates = pd.date_range("2011-01-04", periods=143, freq="B")
    score = pd.DataFrame(
        {
            "decision_date": dates,
            "decision_clock": "14:45",
            "symbol": "000638",
        }
    )
    market = pd.DataFrame(
        {"date": dates[:-1], "decision_clock": "14:45", "symbol": "000638"}
    )
    with pytest.raises(ValueError, match="score_market_join_invalid"):
        rebuild._score_market_join_report(score, market, clock="14:45")


def _target_raw_market() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2013-04-09", "2013-05-16"]),
            "decision_clock": ["14:30", "14:30"],
            "symbol": ["000638", "000638"],
            "raw_execution_price": [10.0, 11.0],
            "raw_close_price": [10.0, 11.5],
            "previous_tradable_close": [9.5, 10.0],
            "buy_ok": [True, True],
            "sell_ok": [True, True],
            "size_bucket": ["small", "small"],
        }
    )


def _empty_primary_factors(path: Path) -> None:
    pd.DataFrame(
        {
            "symbol": pd.Series(dtype=str),
            "instrument_type": pd.Series(dtype=str),
            "factor_type": pd.Series(dtype=str),
        }
    ).to_parquet(path, index=False)


def test_target_hfq_applies_exact_category1_event(tmp_path: Path) -> None:
    primary = tmp_path / "factors.parquet"
    events = tmp_path / "events.parquet"
    _empty_primary_factors(primary)
    pd.DataFrame(
        [
            {
                "date": "2013-04-10",
                "code": "000638",
                "category": 1,
                "fenhong": 0.0,
                "peigujia": 0.0,
                "songzhuangu": 10.0,
                "peigu": 0.0,
                "suogu": 0.0,
            }
        ]
    ).to_parquet(events, index=False)
    result = rebuild._attach_repair_symbol_hfq(
        _target_raw_market(),
        adjustment_factors_path=primary,
        xdxr_events_path=events,
        expected_category1_events=1,
        factor_source_label="bounded_xdxr_event_formula_v1",
    )
    assert result["hfq_price_multiplier"].tolist() == [1.0, 2.0]
    assert result["accounting_execution_price"].tolist() == [10.0, 22.0]
    assert set(result["hfq_factor_source"]) == {"bounded_xdxr_event_formula_v1"}


def test_target_hfq_rejects_nonzero_peigu(tmp_path: Path) -> None:
    primary = tmp_path / "factors.parquet"
    events = tmp_path / "events.parquet"
    _empty_primary_factors(primary)
    pd.DataFrame(
        [
            {
                "date": "2013-04-10",
                "code": "000638",
                "category": 1,
                "fenhong": 0.0,
                "peigujia": 5.0,
                "songzhuangu": 0.0,
                "peigu": 1.0,
                "suogu": 0.0,
            }
        ]
    ).to_parquet(events, index=False)
    with pytest.raises(ValueError, match="peigu_not_preregistered"):
        rebuild._attach_repair_symbol_hfq(
            _target_raw_market(),
            adjustment_factors_path=primary,
            xdxr_events_path=events,
            expected_category1_events=1,
            factor_source_label="bounded_xdxr_event_formula_v1",
        )


def test_contract_keeps_account_execution_closed(tmp_path: Path) -> None:
    path = tmp_path / "contract.json"
    write_json(
        path,
        {
            "schema_id": rebuild.CONTRACT_SCHEMA_ID,
            "status": "result_free_DataHub_repair_bound_market_rebuild_authorized",
            "account_mapping_execution_allowed": False,
            "post_2020_read_allowed": False,
        },
    )
    assert rebuild.load_rebuild_contract(path)["account_mapping_execution_allowed"] is False


def test_contract_rejects_account_authority(tmp_path: Path) -> None:
    path = tmp_path / "contract.json"
    write_json(
        path,
        {
            "schema_id": rebuild.CONTRACT_SCHEMA_ID,
            "status": "result_free_DataHub_repair_bound_market_rebuild_authorized",
            "account_mapping_execution_allowed": True,
            "post_2020_read_allowed": False,
        },
    )
    with pytest.raises(ValueError, match="account_boundary_invalid"):
        rebuild.load_rebuild_contract(path)


def test_compare_trees_accepts_exact_bytes(tmp_path: Path) -> None:
    formal = tmp_path / "formal"
    isolated = tmp_path / "isolated"
    formal.mkdir()
    isolated.mkdir()
    for root in (formal, isolated):
        (root / "a.json").write_bytes(b"same\n")
        (root / "b.parquet").write_bytes(b"same-payload")
    assert rebuild.compare_trees(formal, isolated)["byte_identical"] is True


def test_compare_trees_rejects_drift(tmp_path: Path) -> None:
    formal = tmp_path / "formal"
    isolated = tmp_path / "isolated"
    formal.mkdir()
    isolated.mkdir()
    (formal / "a.json").write_text("formal", encoding="utf-8")
    (isolated / "a.json").write_text("isolated", encoding="utf-8")
    with pytest.raises(ValueError, match="formal_isolated_drift"):
        rebuild.compare_trees(formal, isolated)


def test_script_entrypoint_imports_from_outside_repo(tmp_path: Path) -> None:
    script = Path(rebuild.__file__).resolve()
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Rebuild REAKA P7 market inputs" in result.stdout
