# pyright: reportAny=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false, reportPrivateUsage=false
# pyright: reportPrivateLocalImportUsage=false

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import factor_lab.factor_rotation.reaka_intraday_target_fill_v1 as intraday


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["000001"] * 6 + ["000002"] * 3,
            "trading_day": ["2020-01-02"] * 9,
            "timestamp": [
                "2020-01-02T14:29:00Z",
                "2020-01-02T14:30:00Z",
                "2020-01-02T14:31:00Z",
                "2020-01-02T14:45:00Z",
                "2020-01-02T14:46:00Z",
                "2020-01-02T15:00:00Z",
                "2020-01-02T14:28:00Z",
                "2020-01-02T14:40:00Z",
                "2020-01-02T14:55:00Z",
            ],
            "open": [9.0, 10.0, 12.0, 13.0, 14.0, 15.0, 20.0, 21.0, 22.0],
            "close": [9.5, 11.0, 12.5, 13.5, 14.5, 15.5, 20.5, 21.5, 22.5],
        }
    )


def test_clock_coordinates_separate_known_mark_from_future_fill() -> None:
    result = intraday.select_clock_coordinates(_bars())
    first = result.loc[result["symbol"].eq("000001") & result["decision_clock"].eq("14:30")].iloc[0]
    assert first["decision_timestamp"] == "2020-01-02T14:30:00Z"
    assert first["decision_close"] == 11.0
    assert first["entry_timestamp"] == "2020-01-02T14:31:00Z"
    assert first["entry_open"] == 12.0
    second = result.loc[result["symbol"].eq("000001") & result["decision_clock"].eq("14:45")].iloc[0]
    assert second["decision_timestamp"] == "2020-01-02T14:45:00Z"
    assert second["entry_timestamp"] == "2020-01-02T14:46:00Z"
    assert second["entry_open"] == 14.0


def test_sparse_symbol_uses_last_known_mark_and_first_later_trade() -> None:
    result = intraday.select_clock_coordinates(_bars())
    row = result.loc[result["symbol"].eq("000002") & result["decision_clock"].eq("14:45")].iloc[0]
    assert row["decision_timestamp"] == "2020-01-02T14:40:00Z"
    assert row["decision_close"] == 21.5
    assert row["entry_timestamp"] == "2020-01-02T14:55:00Z"
    assert row["entry_open"] == 22.0


def test_h20_history_uses_decision_marks_but_target_uses_post_clock_fills() -> None:
    decision = np.full((25, 1), np.nan, dtype=np.float32)
    entry = np.full((25, 1), np.nan, dtype=np.float32)
    decision[0, 0], decision[20, 0] = 10.0, 12.0
    entry[0, 0], entry[20, 0] = 11.0, 15.0
    history, future = intraday._h20_surfaces(decision, entry)  # noqa: SLF001
    assert np.isclose(history[20, 0], 0.2)
    assert np.isclose(future[0, 0], (15.0 / 11.0) - 1.0)
    assert not np.isclose(history[20, 0], future[0, 0])


def test_inference_rows_exist_even_when_every_future_label_is_missing() -> None:
    calendar = np.arange(
        np.datetime64("2008-01-01"),
        np.datetime64("2010-01-01"),
        dtype="datetime64[D]",
    ).astype("datetime64[ns]")
    history = np.ones((len(calendar), 2), dtype=np.float32)
    future = np.full_like(history, np.nan)
    support = np.ones_like(history, dtype=bool)
    anchor = int(np.flatnonzero(calendar.astype("datetime64[D]") == intraday.ANCHOR_DAY)[0])
    positions = np.arange(anchor, len(calendar), 5, dtype=np.int64)
    positions = positions[positions + 1 < len(calendar)]
    rows, evaluation = intraday._inference_rows(  # noqa: SLF001
        calendar=calendar,
        history=history,
        feature_support=support,
        future=future,
        decision_positions=positions,
    )
    assert len(rows) > 0
    assert len(evaluation) == 0


def test_contract_rejects_next_open_and_scientific_execution() -> None:
    payload: dict[str, object] = {
        "schema_id": intraday.INTRADAY_TARGET_FILL_SCHEMA_ID,
        "decision_clocks": ["14:30", "14:45"],
        "execution_window": "next_tradable_after_bar_close",
        "next_open_allowed": False,
        "model_training_allowed": False,
        "score_materialization_allowed": False,
        "account_execution_allowed": False,
    }
    payload["canonical_digest"] = intraday.canonical_digest(payload)
    assert intraday.validate_contract(payload) == []
    payload["execution_window"] = "next_open"
    payload["next_open_allowed"] = True
    payload["canonical_digest"] = intraday.canonical_digest({key: value for key, value in payload.items() if key != "canonical_digest"})
    blockers = intraday.validate_contract(payload)
    assert "intraday_contract_execution_invalid" in blockers
    assert "intraday_contract_next_open_not_forbidden" in blockers


def test_month_range_and_artifact_inventory_are_frozen() -> None:
    months = intraday.month_range()
    assert months[0] == "2007-01"
    assert months[-1] == "2020-12"
    assert len(months) == 168
    assert "future_h20_raw_1430.npy" in intraday.ARTIFACT_NAMES
    assert "future_h20_raw_1445.npy" in intraday.ARTIFACT_NAMES


def test_current_datahub_root_is_a_versioned_immutable_path() -> None:
    assert intraday.DEFAULT_DATASET_ROOT.name == (f"dataset_version={intraday.DEFAULT_DATASET_VERSION}")
    assert Path(intraday.DEFAULT_DATASET_ROOT).is_absolute()
