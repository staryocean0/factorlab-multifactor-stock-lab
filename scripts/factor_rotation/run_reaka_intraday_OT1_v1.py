#!/usr/bin/env python3
# pyright: reportAny=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false, reportArgumentType=false
# pyright: reportUnusedCallResult=false
# pyright: reportGeneralTypeIssues=false
"""Materialize one clock/tree of the P6.2 intraday OT1 layer."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from factor_lab.factor_rotation import orthogonal_index_timing_transport_ot1_v1 as old_ot1
from factor_lab.factor_rotation.reaka_intraday_orthogonal_ot_v1 import (
    CLOCK_SUFFIX,
    LARGE_TARGET_ID,
    MARKET_FACTOR_ID,
    SMALL_TARGET_ID,
    build_causal_basis_pair,
    file_digest,
    fit_intraday_stock_exposures,
    load_memberships,
    membership_for_decisions,
    read_json,
    validate_contract,
    write_deterministic_npz,
    write_json,
    write_parquet,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/ops/reaka_intraday_orthogonal_OT1_OT3@1.0.json"
P6_ROOT = ROOT / "output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020"
OUTPUT_ROOT = ROOT / "output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020"
EVIDENCE_ROOT = ROOT / "docs/ops/evidence/reaka_intraday_orthogonal_OT_v1_20260831"
CLOUDRIDGE = (
    ROOT / "output/factor-rotation/reaka_opportunity_ledger_v9_inputs_2008_2020" / "cloudridge_beta_weekly_2008_2020.constituents.csv"
)
CORE = ROOT / "output/factor-rotation/reaka_condensation_B7_admission_v1_2009_2020" / "extended_weekly_membership.parquet"
REGISTRY = ROOT / "docs/ops/factor_condensation_index_registry@1.0.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", choices=("formal", "isolated"), required=True)
    parser.add_argument("--clock", choices=("14:30", "14:45"), required=True)
    args = parser.parse_args()
    suffix = CLOCK_SUFFIX[args.clock]
    contract = read_json(CONTRACT)
    blockers = validate_contract(contract)
    if blockers:
        raise RuntimeError(f"reaka_intraday_OT_contract_blocked:{blockers}")
    p6 = P6_ROOT / args.tree
    output = OUTPUT_ROOT / args.tree / suffix / "ot1"
    evidence = EVIDENCE_ROOT / args.tree / suffix / "ot1"
    if output.exists():
        raise FileExistsError(f"reaka_intraday_OT1_output_exists:{output}")
    started = time.perf_counter()
    calendar = np.load(p6 / "calendar.npy", mmap_mode="r")
    symbols = np.load(p6 / "symbols.npy", mmap_mode="r").astype(str)
    decisions = np.load(p6 / "decision_positions.npy", mmap_mode="r")
    history_raw = np.load(p6 / f"history_h20_raw_{suffix}.npy", mmap_mode="r")
    future_raw = np.load(p6 / f"future_h20_raw_{suffix}.npy", mmap_mode="r")
    decision_marks = np.load(p6 / f"decision_close_{suffix}.npy", mmap_mode="r")
    cloudridge, core, industry_ids = load_memberships(
        cloudridge_path=CLOUDRIDGE,
        core_path=CORE,
        registry_path=REGISTRY,
        symbols=symbols,
    )
    market_h, market_counts = old_ot1.materialize_equal_weight_carriers(
        history_raw,
        calendar,
        cloudridge,
        [MARKET_FACTOR_ID],
        minimum_members=12,
    )
    market_f, _ = old_ot1.materialize_equal_weight_carriers(
        future_raw,
        calendar,
        cloudridge,
        [MARKET_FACTOR_ID],
        minimum_members=12,
    )
    target_order = [SMALL_TARGET_ID, LARGE_TARGET_ID, *industry_ids]
    core_h, core_counts = old_ot1.materialize_equal_weight_carriers(
        history_raw,
        calendar,
        core,
        target_order,
        minimum_members=5,
    )
    core_f, _ = old_ot1.materialize_equal_weight_carriers(
        future_raw,
        calendar,
        core,
        target_order,
        minimum_members=5,
    )
    raw_h = np.concatenate([market_h, core_h], axis=2)
    raw_f = np.concatenate([market_f, core_f], axis=2)
    basis_h, basis_f, basis_history, basis_future, receipts = build_causal_basis_pair(
        raw_h,
        raw_f,
        calendar,
        industry_ids,
        decision_clock=args.clock,
    )
    industry_membership = membership_for_decisions(
        core,
        industry_ids,
        calendar,
        decisions,
    )
    exposures, industry_exposures, summary, epsilon_h, epsilon_f = fit_intraday_stock_exposures(
        history_returns=history_raw,
        future_returns=future_raw,
        decision_marks=decision_marks,
        history_basis=basis_h,
        future_basis=basis_f,
        calendar=calendar,
        symbols=symbols,
        decision_positions=decisions,
        industry_ids=industry_ids,
        industry_membership=industry_membership,
        decision_clock=args.clock,
    )
    output.mkdir(parents=True)
    evidence.mkdir(parents=True, exist_ok=True)
    write_parquet(
        basis_history,
        output / "factor_basis_history.parquet",
        ["variant_id", "trading_day", "factor_id"],
    )
    write_parquet(
        basis_future,
        output / "factor_basis_future.parquet",
        ["variant_id", "trading_day", "factor_id"],
    )
    write_parquet(
        receipts,
        output / "basis_projection_receipts.parquet",
        ["variant_id", "trading_day", "projection_id"],
    )
    write_parquet(
        exposures,
        output / "d5_stock_exposures.parquet",
        ["asof_date", "symbol"],
    )
    write_parquet(
        industry_exposures,
        output / "d5_stock_industry_exposures.parquet",
        ["asof_date", "symbol", "industry_factor_id"],
    )
    write_parquet(
        summary,
        output / "exposure_decision_summary.parquet",
        ["asof_date"],
    )
    write_deterministic_npz(
        output / "stock_residual_surfaces.npz",
        {
            "calendar": np.asarray(calendar),
            "symbols": np.asarray(symbols),
            "epsilon_history": epsilon_h,
            "epsilon_future": epsilon_f,
        },
    )
    output_names = (
        "factor_basis_history.parquet",
        "factor_basis_future.parquet",
        "basis_projection_receipts.parquet",
        "d5_stock_exposures.parquet",
        "d5_stock_industry_exposures.parquet",
        "exposure_decision_summary.parquet",
        "stock_residual_surfaces.npz",
    )
    manifest = write_json(
        output / "manifest.json",
        {
            "schema_id": "factorlab.reaka_intraday_OT1_manifest@1.0",
            "contract_digest": contract["canonical_digest"],
            "decision_clock": args.clock,
            "files": {name: file_digest(output / name) for name in output_names},
            "factor_variant_count": len(old_ot1.variant_ids()),
            "industry_factor_count": len(industry_ids),
            "basis_history_rows": len(basis_history),
            "basis_future_rows": len(basis_future),
            "projection_receipt_rows": len(receipts),
            "stock_exposure_rows": len(exposures),
            "industry_exposure_rows": len(industry_exposures),
            "decision_count": len(summary),
            "epsilon_history_finite_count": int(np.isfinite(epsilon_h).sum()),
            "epsilon_future_finite_count": int(np.isfinite(epsilon_f).sum()),
            "raw_carrier_minimum_member_count": int(
                min(
                    np.min(market_counts[market_counts > 0]),
                    np.min(core_counts[core_counts > 0]),
                )
            ),
            "post_2020_rows_read": 0,
            "uses_future_in_fit": False,
            "model_training_run": False,
            "score_run": False,
            "account_run": False,
            "production_authority": False,
        },
    )
    validation_blockers: list[str] = []
    if receipts.empty:
        validation_blockers.append("intraday_OT1_projection_receipts_empty")
    elif float(receipts["reconstruction_max_abs_error"].max()) > 1.0e-10:
        validation_blockers.append("intraday_OT1_projection_reconstruction_failed")
    if len(exposures) == 0 or len(summary) == 0:
        validation_blockers.append("intraday_OT1_exposures_empty")
    if len(exposures) and pd.to_datetime(exposures["fit_end_date"]).ge(pd.to_datetime(exposures["asof_date"])).any():
        validation_blockers.append("intraday_OT1_fit_not_strict_t_minus_1")
    if len(exposures) and exposures["uses_future"].any():
        validation_blockers.append("intraday_OT1_exposure_reads_future")
    if not np.isfinite(epsilon_h).any() or not np.isfinite(epsilon_f).any():
        validation_blockers.append("intraday_OT1_epsilon_empty")
    validation = write_json(
        evidence / "validation_report.json",
        {
            "schema_id": "factorlab.reaka_intraday_OT1_validation@1.0",
            "status": "passed" if not validation_blockers else "blocked",
            "blockers": validation_blockers,
            "contract_digest": contract["canonical_digest"],
            "manifest_digest": manifest["canonical_digest"],
            "decision_clock": args.clock,
            "projection_max_reconstruction_error": (float(receipts["reconstruction_max_abs_error"].max()) if len(receipts) else None),
            "projection_max_orthogonality_error": (float(receipts["orthogonality_max_abs"].max()) if len(receipts) else None),
            "mean_exposure_coverage": float(summary["coverage"].mean()),
            "minimum_exposure_coverage": float(summary["coverage"].min()),
            "elapsed_seconds": time.perf_counter() - started,
            "post_2020_rows_read": 0,
            "model_training_run": False,
            "score_run": False,
            "account_run": False,
            "production_authority": False,
        },
    )
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    if validation_blockers:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
