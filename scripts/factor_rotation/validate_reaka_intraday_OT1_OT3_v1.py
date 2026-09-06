#!/usr/bin/env python3
# pyright: reportAny=false, reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnusedCallResult=false
# pyright: reportGeneralTypeIssues=false
"""Validate the complete formal/isolated P6.2 OT1--OT3 tree."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

from factor_lab.factor_rotation.reaka_intraday_orthogonal_ot_v1 import (
    CLOCK_SUFFIX,
    OT1_FILES,
    OT2_FILES,
    OT3_FILES,
    VALIDATION_SCHEMA_ID,
    canonical_valid,
    file_digest,
    read_json,
    validate_contract,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/ops/reaka_intraday_orthogonal_OT1_OT3@1.0.json"
OUTPUT = ROOT / "output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020"
EVIDENCE = ROOT / "docs/ops/evidence/reaka_intraday_orthogonal_OT_v1_20260831"
REPORT = EVIDENCE / "validation_report.json"


def main() -> None:
    contract = read_json(CONTRACT)
    blockers = validate_contract(contract)
    closure = cast(dict[str, str], contract.get("source_closure", {}))
    source_drift = [
        relative for relative, expected in closure.items() if not (ROOT / relative).is_file() or file_digest(ROOT / relative) != expected
    ]
    if source_drift:
        blockers.append("intraday_OT_source_closure_drift")
    replay_mismatches: list[str] = []
    clock_reports: dict[str, object] = {}
    for clock, suffix in CLOCK_SUFFIX.items():
        formal = OUTPUT / "formal" / suffix
        isolated = OUTPUT / "isolated" / suffix
        for layer, names in (
            ("ot1", OT1_FILES),
            ("ot2", OT2_FILES),
            ("ot3", OT3_FILES),
        ):
            for name in names:
                left = formal / layer / name
                right = isolated / layer / name
                if not left.is_file() or not right.is_file():
                    replay_mismatches.append(f"{clock}:{layer}:{name}:missing")
                elif file_digest(left) != file_digest(right):
                    replay_mismatches.append(f"{clock}:{layer}:{name}")
                elif name.endswith(".json"):
                    payload = read_json(left)
                    if not canonical_valid(payload):
                        blockers.append(f"{clock}_{layer}_{name}_canonical_invalid")
                    if "contract_digest" in payload and payload["contract_digest"] != contract["canonical_digest"]:
                        blockers.append(f"{clock}_{layer}_{name}_contract_drift")
        ot1_validation = read_json(EVIDENCE / "formal" / suffix / "ot1/validation_report.json")
        final_validation = read_json(EVIDENCE / "formal" / suffix / "ot2_ot3_validation.json")
        if ot1_validation.get("status") != "passed":
            blockers.append(f"{clock}_OT1_not_passed")
        if final_validation.get("status") != "passed":
            blockers.append(f"{clock}_OT2_OT3_not_passed")
        exposures = pd.read_parquet(formal / "ot1/d5_stock_exposures.parquet")
        ot1_manifest = read_json(formal / "ot1/manifest.json")
        if ot1_manifest.get("post_2020_rows_read") != 0:
            blockers.append(f"{clock}_OT1_post2020_read")
        if pd.to_datetime(exposures["fit_end_date"]).ge(pd.to_datetime(exposures["asof_date"])).any():
            blockers.append(f"{clock}_fit_not_strict_t_minus_1")
        if exposures["uses_future"].any():
            blockers.append(f"{clock}_exposure_future_read")
        selections = read_json(formal / "ot2/selected_family_tools.json")
        selection_rows = cast(list[dict[str, object]], selections["selections"])
        if len(selection_rows) != 3:
            blockers.append(f"{clock}_selection_count_invalid")
        transport = pd.read_parquet(formal / "ot3/d5_stock_timing_transport.parquet")
        if transport.duplicated(["asof_date", "symbol"]).any():
            blockers.append(f"{clock}_transport_duplicate")
        if any(column in transport for column in ("combined_score", "total_score", "tool_vote_sum")):
            blockers.append(f"{clock}_transport_presum")
        with np.load(formal / "ot1/stock_residual_surfaces.npz", allow_pickle=False) as payload:
            epsilon_h = payload["epsilon_history"]
            epsilon_f = payload["epsilon_future"]
        clock_reports[clock] = {
            "OT1_validation_digest": ot1_validation["canonical_digest"],
            "OT2_OT3_validation_digest": final_validation["canonical_digest"],
            "stock_exposure_rows": len(exposures),
            "epsilon_history_finite": int(np.isfinite(epsilon_h).sum()),
            "epsilon_future_finite": int(np.isfinite(epsilon_f).sum()),
            "selections": selection_rows,
            "transport_rows": len(transport),
        }
    if replay_mismatches:
        blockers.append("intraday_OT_formal_isolated_byte_mismatch")
    predecessor = str(contract["canonical_digest"])
    annual_receipts: dict[str, str] = {}
    for year in range(2009, 2021):
        receipt = read_json(EVIDENCE / "annual_sessions" / str(year) / "receipt.json")
        if receipt.get("predecessor_digest") != predecessor:
            blockers.append(f"intraday_OT2_annual_chain_invalid:{year}")
        if receipt.get("post_year_rows_read") != 0:
            blockers.append(f"intraday_OT2_post_year_read:{year}")
        if receipt.get("status") != "completed":
            blockers.append(f"intraday_OT2_annual_not_completed:{year}")
        if receipt.get("formal_isolated_mismatches") != []:
            blockers.append(f"intraday_OT2_annual_replay_mismatch:{year}")
        predecessor = str(receipt["canonical_digest"])
        annual_receipts[str(year)] = predecessor
    report = write_json(
        REPORT,
        {
            "schema_id": VALIDATION_SCHEMA_ID,
            "status": "passed" if not blockers else "blocked",
            "issue_ref": "bd://fl-eginj.2",
            "blockers": blockers,
            "contract_digest": contract["canonical_digest"],
            "source_closure_drift": source_drift,
            "formal_isolated_mismatches": replay_mismatches,
            "annual_receipt_digests": annual_receipts,
            "clock_reports": clock_reports,
            "post_2020_rows_read": 0,
            "model_training_run": False,
            "score_run": False,
            "account_run": False,
            "production_authority": False,
        },
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if blockers:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
