# pyright: reportAny=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false, reportUnusedCallResult=false
# pyright: reportUnhashable=false
# pyright: reportPrivateUsage=false
# pyright: reportArgumentType=false

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from scripts.factor_rotation.build_reaka_intraday_portfolio_mapping_inputs_v1 import (
    _attach_hfq_accounting,
    _size_bucket_map,
    build_bounded_inputs,
)
from scripts.factor_rotation.prepare_reaka_intraday_portfolio_mapping_session_v1 import (
    prepare_session,
)

from factor_lab.factor_rotation.reaka_intraday_portfolio_mapping_v1 import (
    ADMISSION_SCHEMA_ID,
    CLOCKS,
    COMMON_ROOT_POLICY_ID,
    CONTRACT_DIGEST,
    INPUT_SCHEMA_ID,
    PortfolioPolicy,
    TradabilityRow,
    allocate_target_shares,
    apply_industry_cap,
    apply_rebalance_day,
    apply_size_tercile_cap,
    assert_no_future_filter,
    average_tie_ranks,
    build_execution_target,
    build_policy_grid,
    buy_cost_bps,
    common_root_policy,
    compare_tree_bytes,
    ensemble_seed_rank_z,
    evaluate_economics_gate,
    evaluate_quarterly_gate,
    file_digest,
    load_contract,
    per_decision_rank_z,
    policy_by_id,
    rank_portfolio_table,
    run_account_path,
    run_policy_family,
    sell_cost_bps,
    validate_admission,
    validate_input_manifest,
    validate_market_panel,
    validate_score_panel,
    validate_year_request,
    write_json,
)
from factor_lab.governance.canonicalization import canonical_digest

ROOT = Path(__file__).resolve().parents[2]


def _admission(phase: str) -> dict[str, object]:
    score = phase in {"score_extension", "account_execution"}
    account = phase == "account_execution"
    payload: dict[str, object] = {
        "schema_id": ADMISSION_SCHEMA_ID,
        "phase": phase,
        "contract_digest": CONTRACT_DIGEST,
        "infrastructure_implementation_allowed": True,
        "score_extension_execution_allowed": score,
        "account_mapping_execution_allowed": account,
        "post_2020_read_allowed": False,
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def _synthetic_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    symbols = [f"S{position:03d}" for position in range(60)]
    dates = pd.bdate_range("2011-01-03", periods=12)
    decisions = {dates[0], dates[5], dates[10]}
    score_rows: list[dict[str, object]] = []
    market_rows: list[dict[str, object]] = []
    for clock_index, clock in enumerate(CLOCKS):
        for day_index, day in enumerate(dates):
            for symbol_index, symbol in enumerate(symbols):
                base = 10.0 + symbol_index * 0.02
                raw_close = base * (1.0 + 0.0005 * day_index + 0.0001 * clock_index)
                factor = 1.0 + 0.1 * (day_index >= 7 and symbol_index == 3)
                raw_execution = raw_close * 0.999 if day in decisions else np.nan
                market_rows.append(
                    {
                        "date": day,
                        "decision_clock": clock,
                        "symbol": symbol,
                        "raw_execution_price": raw_execution,
                        "raw_close_price": raw_close,
                        "previous_tradable_close": raw_close,
                        "hfq_price_multiplier": factor,
                        "hfq_factor_source": "certified_adjust_factors_v9",
                        "accounting_execution_price": raw_execution * factor,
                        "accounting_close_price": raw_close * factor,
                        "buy_ok": not (day == dates[0] and symbol == "S000"),
                        "sell_ok": not (day == dates[5] and symbol == "S001"),
                        "size_bucket": ("small", "middle", "large")[symbol_index % 3],
                        "pit_industry": f"I{symbol_index % 8}",
                    }
                )
                if day in decisions:
                    score_rows.append(
                        {
                            "decision_date": day,
                            "decision_clock": clock,
                            "symbol": symbol,
                            "score": float(60 - symbol_index + 0.01 * day_index + 0.001 * clock_index),
                        }
                    )
    return pd.DataFrame(score_rows), pd.DataFrame(market_rows)


def _write_input_tree(root: Path, scores: pd.DataFrame, market: pd.DataFrame) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for clock in CLOCKS:
        suffix = clock.replace(":", "")
        score_path = root / f"bounded_score_panel_{suffix}.parquet"
        market_path = root / f"daily_market_panel_{suffix}.parquet"
        scores.loc[scores["decision_clock"].eq(clock)].reset_index(drop=True).to_parquet(score_path, index=False)
        market.loc[market["decision_clock"].eq(clock)].reset_index(drop=True).to_parquet(market_path, index=False)
        write_json(
            root / f"input_manifest_{suffix}.json",
            {
                "schema_id": INPUT_SCHEMA_ID,
                "contract_digest": CONTRACT_DIGEST,
                "decision_clock": clock,
                "decision_clocks": list(CLOCKS),
                "panel_digest": file_digest(score_path),
                "market_panel_digest": file_digest(market_path),
                "future_entry_or_target_filter_applied": False,
                "post_2020_rows": 0,
            },
        )


def test_contract_and_policy_grid_are_frozen() -> None:
    assert load_contract(ROOT)["canonical_digest"] == CONTRACT_DIGEST
    assert len(build_policy_grid()) == 24
    assert common_root_policy().policy_id == COMMON_ROOT_POLICY_ID


def test_highest_score_has_highest_rank_and_ties_are_equal() -> None:
    scores = np.asarray([1.0, 2.0, 2.0, 3.0])
    symbols = ["D", "C", "B", "A"]
    ranks = average_tie_ranks(scores, symbols)
    assert ranks[3] > ranks[1]
    assert ranks[1] == ranks[2]
    ranked = rank_portfolio_table(pd.DataFrame({"symbol": symbols, "score": scores}))
    assert ranked["symbol"].tolist() == ["A", "B", "C", "D"]


def test_rank_linear_direction_and_tie_weights() -> None:
    policy = PortfolioPolicy("test", 4, "rank_linear_capped", "backfill", "none")
    ranked = rank_portfolio_table(
        pd.DataFrame({"symbol": ["A", "B", "C", "D"], "score": [4.0, 3.0, 3.0, 1.0]})
    )
    tradability = {symbol: TradabilityRow(symbol, True, True) for symbol in ranked["symbol"]}
    ranks = dict(zip(ranked["symbol"], ranked["rank"], strict=True))
    selected, _ = cast(tuple[list[str], list[dict[str, object]]], __import__(
        "factor_lab.factor_rotation.reaka_intraday_portfolio_mapping_v1", fromlist=["select_target_symbols"]
    ).select_target_symbols(ranked, policy=policy, previous_shares={}, tradability=tradability))
    from factor_lab.factor_rotation.reaka_intraday_portfolio_mapping_v1 import target_weights_for_policy

    weights = target_weights_for_policy(policy, selected, ranks)
    assert weights["A"] > weights["D"]
    assert weights["B"] == pytest.approx(weights["C"])
    assert max(weights.values()) <= 0.5 + 1.0e-12


def test_cash_does_not_backfill_but_backfill_does() -> None:
    ranked = rank_portfolio_table(
        pd.DataFrame({"symbol": ["A", "B", "C"], "score": [3.0, 2.0, 1.0]})
    )
    gates = {
        "A": TradabilityRow("A", False, True),
        "B": TradabilityRow("B", True, True),
        "C": TradabilityRow("C", True, True),
    }
    from factor_lab.factor_rotation.reaka_intraday_portfolio_mapping_v1 import select_target_symbols

    cash = PortfolioPolicy("cash", 1, "equal", "cash", "none")
    backfill = PortfolioPolicy("backfill", 1, "equal", "backfill", "none")
    assert select_target_symbols(ranked, policy=cash, previous_shares={}, tradability=gates)[0] == []
    assert select_target_symbols(ranked, policy=backfill, previous_shares={}, tradability=gates)[0] == ["B"]


def test_cash_target_keeps_unfilled_slot_as_cash() -> None:
    symbols = [f"S{position:02d}" for position in range(12)]
    ranked = rank_portfolio_table(
        pd.DataFrame({"symbol": symbols, "score": np.arange(12, 0, -1, dtype=float)})
    )
    gates = {symbol: TradabilityRow(symbol, symbol != "S00", True) for symbol in symbols}
    size = {symbol: ("small", "middle", "large")[position % 3] for position, symbol in enumerate(symbols)}
    cash_target, _, _, _ = build_execution_target(
        ranked,
        policy=policy_by_id("N10_equal_cash_unconstrained"),
        previous_shares={},
        current_weights={},
        tradability=gates,
        size_labels=size,
    )
    backfill_target, _, _, _ = build_execution_target(
        ranked,
        policy=policy_by_id("N10_equal_backfill_unconstrained"),
        previous_shares={},
        current_weights={},
        tradability=gates,
        size_labels=size,
    )
    assert sum(cash_target.values()) == pytest.approx(0.9)
    assert sum(backfill_target.values()) == pytest.approx(1.0)
    assert "S10" not in cash_target and "S10" in backfill_target


def test_allocation_does_not_renormalize_capped_weights() -> None:
    shares, cash = allocate_target_shares(
        nav_after_cost=1_000.0,
        target_weights={"A": 0.25, "B": 0.25},
        execution_prices={"A": 10.0, "B": 20.0},
        forced_shares={},
    )
    assert shares == {"A": 25.0, "B": 12.5}
    assert cash == pytest.approx(500.0)


def test_size_cap_leaves_cash_and_missing_PIT_fails_closed() -> None:
    capped = apply_size_tercile_cap(
        {"A": 0.4, "B": 0.4, "C": 0.2},
        size_labels={"A": "small", "B": "small", "C": "large"},
    )
    assert capped["A"] + capped["B"] <= 0.5 + 1.0e-12
    assert sum(capped.values()) == pytest.approx(0.7)
    with pytest.raises(ValueError, match="PIT_size_coverage_incomplete"):
        apply_size_tercile_cap({"A": 0.5}, size_labels={})


def test_industry_cap_is_synthetic_only_and_fails_closed_on_gap() -> None:
    original = {"A": 0.5, "B": 0.5}
    assert apply_industry_cap(original, industry_labels={"A": "I1", "B": ""}) == (original, False)
    adjusted, okay = apply_industry_cap(original, industry_labels={"A": "I1", "B": "I2"})
    assert okay is True
    assert max(adjusted.values()) <= 0.25 + 1.0e-12


def test_forced_carry_preserves_exact_shares_and_has_no_sell_leg() -> None:
    result = apply_rebalance_day(
        previous_shares={"A": 10.0},
        previous_cash=100.0,
        open_prices={"B": 10.0},
        close_prices={"B": 10.0},
        previous_mark_prices={"A": 10.0},
        target_weights={"B": 0.5},
        forced_symbols=["A"],
        blocked_buy_symbols=[],
        slippage_multiplier=1.0,
    )
    assert cast(dict[str, float], result["shares"])["A"] == 10.0
    assert "A" not in cast(dict[str, float], result["sell_legs"])


def test_costs_and_drawdown_worsening_sign() -> None:
    assert buy_cost_bps(1.0) == pytest.approx(4.6)
    assert sell_cost_bps(1.0) == pytest.approx(14.6)
    assert sell_cost_bps(3.0) == pytest.approx(18.6)
    result = evaluate_economics_gate(
        challenger_metrics={"net_log_return": 0.2, "sharpe": 1.1, "maximum_drawdown": -0.2},
        root_metrics={"net_log_return": 0.1, "sharpe": 1.0, "maximum_drawdown": -0.1},
        cost_multipliers=(2.0, 3.0),
        challenger_by_cost={2.0: 0.2, 3.0: 0.15},
        root_by_cost={2.0: 0.1, 3.0: 0.08},
    )
    assert result["base_pass"] is False


def test_quarterly_gate_requires_three_distinct_years() -> None:
    two_years = [(2011 + position // 8, position % 4 + 1, 0.001) for position in range(16)]
    three_years = [(2011 + position // 4, position % 4 + 1, 0.001) for position in range(12)]
    assert evaluate_quarterly_gate(two_years)["passed"] is False
    assert evaluate_quarterly_gate(three_years)["passed"] is True


@pytest.mark.parametrize("phase", ["infrastructure", "score_extension", "account_execution"])
def test_phase_specific_admissions(phase: str) -> None:
    assert validate_admission(_admission(phase), required_phase=phase) == []


def test_account_requires_score_and_post2020_is_always_closed() -> None:
    bad = _admission("account_execution")
    bad["score_extension_execution_allowed"] = False
    bad["canonical_digest"] = canonical_digest({key: value for key, value in bad.items() if key != "canonical_digest"})
    assert "admission_account_requires_score_extension" in validate_admission(bad)
    bad = _admission("score_extension")
    bad["post_2020_read_allowed"] = True
    bad["canonical_digest"] = canonical_digest({key: value for key, value in bad.items() if key != "canonical_digest"})
    assert "admission_authority_invalid:post_2020_read_allowed" in validate_admission(bad)


def test_score_builder_rejects_stale_source_closure(tmp_path: Path) -> None:
    admission = _admission("score_extension")
    admission["source_digests"] = {}
    admission["canonical_digest"] = canonical_digest(
        {key: value for key, value in admission.items() if key != "canonical_digest"}
    )
    with pytest.raises(ValueError, match="source_closure_drift"):
        build_bounded_inputs(
            admission=admission,
            tree="formal",
            clock="14:30",
            store_root=tmp_path / "store",
            checkpoint_root=tmp_path / "checkpoint",
            normalizer_path=tmp_path / "normalizer.json",
            market_panel=tmp_path / "market.parquet",
            adjustment_factors_path=tmp_path / "factors.parquet",
            xdxr_events_path=tmp_path / "events.parquet",
            output_root=tmp_path / "output",
        )


def test_score_ensemble_is_mean_of_seed_rankz() -> None:
    symbols = ["A", "B", "C"]
    seed_scores = {
        11: np.asarray([3.0, 2.0, 1.0]),
        29: np.asarray([2.0, 3.0, 1.0]),
        47: np.asarray([1.0, 3.0, 2.0]),
    }
    expected = np.mean([per_decision_rank_z(seed_scores[seed], symbols) for seed in (11, 29, 47)], axis=0)
    assert ensemble_seed_rank_z(seed_scores, symbols) == pytest.approx(expected)


def test_future_columns_and_post2020_panels_fail_closed() -> None:
    with pytest.raises(ValueError, match="future_filter_forbidden"):
        assert_no_future_filter(["symbol", "target_ok"])
    score = pd.DataFrame(
        {"decision_date": ["2021-01-01"], "decision_clock": ["14:30"], "symbol": ["A"], "score": [1.0]}
    )
    with pytest.raises(ValueError, match="post_2020"):
        validate_score_panel(score)


def test_market_panel_schema_and_no_future_return() -> None:
    _, market = _synthetic_inputs()
    validate_market_panel(market)
    market["forward_return"] = 0.1
    with pytest.raises(ValueError, match="future_return_forbidden"):
        validate_market_panel(market)


def test_market_panel_rejects_corporate_action_identity_drift() -> None:
    _, market = _synthetic_inputs()
    market.loc[0, "accounting_close_price"] = float(market.loc[0, "accounting_close_price"]) + 0.01
    with pytest.raises(ValueError, match="accounting_close_identity_failed"):
        validate_market_panel(market)


def test_market_cap_microsecond_timestamp_is_normalized(tmp_path: Path) -> None:
    score = pd.DataFrame(
        {
            "decision_date": pd.to_datetime(["2011-01-10", "2011-01-10", "2011-01-10"]),
            "symbol": ["A", "B", "C"],
        }
    )
    table = pa.table(
        {
            "symbol": ["A", "B", "C"],
            "available_at": pa.array(
                [pd.Timestamp("2011-01-09 10:00:00", tz="Asia/Shanghai").to_pydatetime()] * 3,
                type=pa.timestamp("us", tz="Asia/Shanghai"),
            ),
            "total_market_cap": [1.0, 2.0, 3.0],
        }
    )
    path = tmp_path / "cap.parquet"
    pq.write_table(table, path)
    labels = _size_bucket_map(score, market_cap_path=path, clock="14:30")
    assert set(labels.values()) == {"small", "middle", "large"}


def test_hfq_factor_is_carried_strictly_backward_on_suspended_day(tmp_path: Path) -> None:
    raw_market = pd.DataFrame(
        {
            "date": pd.to_datetime(["2011-01-03", "2011-01-04"]),
            "decision_clock": ["14:30", "14:30"],
            "symbol": ["A", "A"],
            "raw_execution_price": [10.0, np.nan],
            "raw_close_price": [10.0, np.nan],
            "previous_tradable_close": [9.9, 10.0],
            "buy_ok": [True, False],
            "sell_ok": [True, False],
            "size_bucket": ["small", "small"],
        }
    )
    factors = pd.DataFrame(
        {
            "symbol": ["A"],
            "trading_day": ["2011-01-03"],
            "instrument_type": ["stock"],
            "factor_type": ["hfq"],
            "price_multiplier": [1.25],
        }
    )
    path = tmp_path / "factors.parquet"
    factors.to_parquet(path, index=False)
    result = _attach_hfq_accounting(
        raw_market,
        adjustment_factors_path=path,
        xdxr_events_path=tmp_path / "unused.parquet",
    )
    assert result["hfq_price_multiplier"].tolist() == [1.25, 1.25]


def test_bounded_XDXR_formula_repairs_registered_missing_symbol(tmp_path: Path) -> None:
    raw_market = pd.DataFrame(
        {
            "date": pd.to_datetime(["2011-05-24", "2011-05-25"]),
            "decision_clock": ["14:30", "14:30"],
            "symbol": ["300029", "300029"],
            "raw_execution_price": [10.0, 9.85],
            "raw_close_price": [10.0, 9.9],
            "previous_tradable_close": [9.8, 10.0],
            "buy_ok": [True, True],
            "sell_ok": [True, True],
            "size_bucket": ["small", "small"],
        }
    )
    factor_path = tmp_path / "empty_factors.parquet"
    pd.DataFrame(
        columns=["symbol", "trading_day", "instrument_type", "factor_type", "price_multiplier"]
    ).to_parquet(factor_path, index=False)
    events_path = tmp_path / "events.parquet"
    pd.DataFrame(
        {
            "date": pd.to_datetime(["2010-01-01", "2011-05-25"]),
            "code": ["300029", "300029"],
            "category": [1, 1],
            "fenhong": [0.0, 1.5],
            "peigujia": [5.0, 0.0],
            "songzhuangu": [0.0, 0.0],
            "peigu": [1.0, 0.0],
            "suogu": [0.0, 0.0],
        }
    ).to_parquet(events_path, index=False)
    result = _attach_hfq_accounting(
        raw_market,
        adjustment_factors_path=factor_path,
        xdxr_events_path=events_path,
    )
    assert result["hfq_price_multiplier"].tolist() == pytest.approx([1.0, 100.0 / 98.5])
    assert set(result["hfq_factor_source"]) == {"bounded_xdxr_event_formula_v1"}


def test_full_account_path_has_cash_for_cash_policy() -> None:
    scores, market = _synthetic_inputs()
    result = run_account_path(
        scores=scores,
        market=market,
        policy=policy_by_id("N10_equal_cash_unconstrained"),
        clock="14:30",
        slippage_multiplier=1.0,
        end_year=2011,
    )
    assert not result.daily.empty
    assert "net_log_return" in result.metrics
    assert float(result.daily.iloc[0]["cash_weight"]) > 0.0


def test_hfq_adjusted_units_remove_raw_split_jump() -> None:
    dates = pd.to_datetime(["2011-01-03", "2011-01-04"])
    scores = pd.DataFrame(
        {"decision_date": [dates[0]], "decision_clock": ["14:30"], "symbol": ["A"], "score": [1.0]}
    )
    market = pd.DataFrame(
        {
            "date": [dates[0], dates[1]],
            "decision_clock": ["14:30", "14:30"],
            "symbol": ["A", "A"],
            "raw_execution_price": [10.0, np.nan],
            "raw_close_price": [10.0, 5.0],
            "previous_tradable_close": [9.9, 10.0],
            "hfq_price_multiplier": [1.0, 2.0],
            "hfq_factor_source": ["certified_adjust_factors_v9", "certified_adjust_factors_v9"],
            "accounting_execution_price": [10.0, np.nan],
            "accounting_close_price": [10.0, 10.0],
            "buy_ok": [True, False],
            "sell_ok": [True, False],
            "size_bucket": ["small", "small"],
        }
    )
    policy = PortfolioPolicy("N1", 1, "equal", "backfill", "none")
    result = run_account_path(
        scores=scores,
        market=market,
        policy=policy,
        clock="14:30",
        slippage_multiplier=1.0,
        end_year=2011,
    )
    assert float(result.daily.iloc[1]["daily_return"]) == pytest.approx(0.0)


def test_full_24_policy_two_clock_three_cost_family_runs() -> None:
    scores, market = _synthetic_inputs()
    result = run_policy_family(scores=scores, market=market, end_year=2011)
    metrics = cast(pd.DataFrame, result["metrics"])
    assert result["attempt_count"] == 144
    assert len(metrics) == 144
    assert metrics[["policy_id", "decision_clock", "slippage_multiplier"]].drop_duplicates().shape[0] == 144
    assert result["selected_policy_id"] == COMMON_ROOT_POLICY_ID
    assert cast(dict[str, object], result["clock_nomination"])["nominated_clock"] is None


def test_input_manifest_and_year_boundaries() -> None:
    manifest: dict[str, object] = {
        "schema_id": INPUT_SCHEMA_ID,
        "contract_digest": CONTRACT_DIGEST,
        "decision_clocks": list(CLOCKS),
        "future_entry_or_target_filter_applied": False,
        "post_2020_rows": 0,
    }
    manifest["canonical_digest"] = canonical_digest(manifest)
    assert validate_input_manifest(manifest) == []
    assert "prior_receipt_missing" in validate_year_request(year=2010, prior_receipt=None)
    assert "year_out_of_range" in validate_year_request(year=2021, prior_receipt=None)


def test_one_year_session_executes_and_formal_isolated_match(tmp_path: Path) -> None:
    scores, market = _synthetic_inputs()
    formal_inputs = tmp_path / "formal_inputs"
    isolated_inputs = tmp_path / "isolated_inputs"
    _write_input_tree(formal_inputs, scores, market)
    _write_input_tree(isolated_inputs, scores, market)
    formal = prepare_session(
        year=2009,
        admission=_admission("account_execution"),
        prior_receipt_path=None,
        blind_policy_id=COMMON_ROOT_POLICY_ID,
        input_root=formal_inputs,
        output_root=tmp_path / "formal",
    )
    isolated = prepare_session(
        year=2009,
        admission=_admission("account_execution"),
        prior_receipt_path=None,
        blind_policy_id=COMMON_ROOT_POLICY_ID,
        input_root=isolated_inputs,
        output_root=tmp_path / "isolated",
    )
    assert formal["attempt_count"] == 144
    assert formal["status"] == "opportunity_absent"
    assert formal["canonical_digest"] == isolated["canonical_digest"]
    assert compare_tree_bytes(tmp_path / "formal", tmp_path / "isolated") == (True, [])


def test_receipt_chain_requires_prior_selected_policy(tmp_path: Path) -> None:
    scores, market = _synthetic_inputs()
    input_root = tmp_path / "inputs"
    _write_input_tree(input_root, scores, market)
    prior = prepare_session(
        year=2009,
        admission=_admission("account_execution"),
        prior_receipt_path=None,
        blind_policy_id=COMMON_ROOT_POLICY_ID,
        input_root=input_root,
        output_root=tmp_path / "2009",
    )
    prior_path = tmp_path / "2009" / "session_receipt.json"
    prior_path.write_text(json.dumps(prior, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    current = prepare_session(
        year=2010,
        admission=_admission("account_execution"),
        prior_receipt_path=prior_path,
        blind_policy_id=str(prior["selected_policy_id"]),
        input_root=input_root,
        output_root=tmp_path / "2010",
    )
    assert current["prior_receipt_digest"] == prior["canonical_digest"]
