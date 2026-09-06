#!/usr/bin/env python3
"""Freeze the result-free P6.1 intraday target/fill contract."""

from __future__ import annotations

import json
from pathlib import Path

from factor_lab.factor_rotation.reaka_intraday_target_fill_v1 import (
    CLOCKS,
    DEFAULT_DATASET_ROOT,
    DEFAULT_DATASET_VERSION,
    INTRADAY_TARGET_FILL_SCHEMA_ID,
    file_digest,
    read_json,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
ISSUE_REF = "bd://fl-eginj.1"
ADAPTER = ROOT / "docs/ops/reaka_framework_content_adapter@1.0.json"
ACCEPTANCE = ROOT / "docs/ops/evidence/reaka_framework_content_adapter_infrastructure_v1_20260831" / "controller_acceptance.json"
REFERENCE = ROOT / "output/factor-rotation/orthogonal_index_timing_transport_OT1_v1_1_2009_2020" / "daily_stock_idiosyncratic_returns.npz"
OT3 = ROOT / "output/factor-rotation/orthogonal_timing_stock_transport_OT3_v1_1_2009_2020" / "weekly_stock_timing_transport.parquet"
CONTRACT = ROOT / "docs/ops/reaka_intraday_target_fill@1.0.json"
SUCCESSION = ROOT / "docs/ops/reaka_controller_succession_audit@144.0.json"
INCIDENT = ROOT / "docs/ops/evidence/reaka_intraday_target_fill_v1_20260831" / "pre_result_performance_incident.json"
SOURCE_PATHS = (
    "docs/ops/reaka_intraday_target_fill_whitepaper.md",
    "docs/user/reaka_intraday_target_fill_workflow.md",
    "src/factor_lab/factor_rotation/reaka_intraday_target_fill_v1.py",
    "scripts/factor_rotation/freeze_reaka_intraday_target_fill_v1.py",
    "scripts/factor_rotation/materialize_reaka_intraday_target_fill_v1.py",
    "scripts/factor_rotation/validate_reaka_intraday_target_fill_v1.py",
    "scripts/factor_rotation/close_reaka_intraday_target_fill_v1.py",
    "tests/unit/test_reaka_intraday_target_fill_v1.py",
)


def main() -> None:
    adapter = read_json(ADAPTER)
    acceptance = read_json(ACCEPTANCE)
    source_closure = {relative: file_digest(ROOT / relative) for relative in SOURCE_PATHS}
    payload = write_json(
        CONTRACT,
        {
            "schema_id": INTRADAY_TARGET_FILL_SCHEMA_ID,
            "status": "frozen_materialization_authorized",
            "issue_ref": ISSUE_REF,
            "framework_content_adapter_digest": adapter["canonical_digest"],
            "P0_P5_acceptance_digest": acceptance["canonical_digest"],
            "pre_result_performance_incident_digest": read_json(INCIDENT)["canonical_digest"],
            "dataset": {
                "dataset_version": DEFAULT_DATASET_VERSION,
                "dataset_root": str(DEFAULT_DATASET_ROOT),
                "manifest_digest": file_digest(DEFAULT_DATASET_ROOT / "manifest.json"),
                "quality_report_digest": file_digest(DEFAULT_DATASET_ROOT / "quality_report.json"),
                "instrument_type": "stock",
                "frequency": "1m",
                "price_space": "raw",
            },
            "axis": {
                "reference_digest": file_digest(REFERENCE),
                "OT3_digest": file_digest(OT3),
                "calendar_start": "2007-01-04",
                "calendar_end": "2020-12-31",
                "symbol_count": 3982,
            },
            "decision_clocks": list(CLOCKS),
            "decision_price": ("last_raw_trade_close_between_1300_and_decision_clock_same_day"),
            "execution_window": "next_tradable_after_bar_close",
            "entry_fill": "first_raw_1m_bar_open_after_decision_clock_same_day",
            "exit_fill": ("same_clock_first_raw_1m_bar_open_after_clock_on_t_plus_20"),
            "history_return": ("decision_close_t_div_decision_close_t_minus_20_minus_1"),
            "future_target": "entry_open_t_plus_20_div_entry_open_t_minus_1",
            "H_days": 20,
            "L_points": 10,
            "W_days": 200,
            "decision_interval_days": 5,
            "phase_count": 4,
            "portfolio_horizon_semantics": "rolling_h20_reforecast_r5",
            "inference_support": [
                "historical_window_complete_at_decision",
                "strictly_prior_OT3_feature_support",
            ],
            "decision_mark_freshness": ("must_have_same_day_afternoon_trade_at_or_after_1300"),
            "forbidden_inference_support": [
                "future_target_available",
                "post_decision_entry_available",
            ],
            "labels_joined_after_scoring": True,
            "execution_eligibility_applied_after_scoring": True,
            "residual_target_status": ("not_materialized_requires_intraday_OT1_successor_before_model_training"),
            "data_usage": {
                "2007_2008": "warmup_only",
                "2009_2020": "consumed_development_material",
                "post_2020_rows_allowed": 0,
                "fresh_oos": False,
            },
            "output_root": ("output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020"),
            "source_closure": source_closure,
            "next_open_allowed": False,
            "materialization_allowed": True,
            "model_training_allowed": False,
            "score_materialization_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    succession = write_json(
        SUCCESSION,
        {
            "schema_id": "factorlab.reaka_controller_succession_audit@144.0",
            "status": "P6_1_intraday_target_fill_materialization_open",
            "issue_ref": ISSUE_REF,
            "contract_digest": payload["canonical_digest"],
            "next_legal_action": "formal_then_isolated_intraday_materialization",
            "model_training_allowed": False,
            "score_materialization_allowed": False,
            "account_execution_allowed": False,
            "production_authority": False,
        },
    )
    print(
        json.dumps(
            {
                "contract_digest": payload["canonical_digest"],
                "succession_digest": succession["canonical_digest"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
