#!/usr/bin/env python3
# pyright: reportAny=false
# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportMissingTypeStubs=false
# pyright: reportOperatorIssue=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnusedCallResult=false
"""Validate both current-strategy REAKA ledgers and account snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for value in (ROOT, ROOT / "src"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from factor_lab.factor_rotation.reaka_current_k1_account_ledgers_v1 import (  # noqa: E402
    MODEL_IDENTITY,
    STRATEGY_ID,
    source_closure,
)
from factor_lab.factor_rotation.reaka_current_k1_factor_attribution_v1 import (  # noqa: E402
    write_json,
)
from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import read_json  # noqa: E402
from factor_lab.governance.canonicalization import canonical_digest  # noqa: E402
from factor_lab.portfolio.account_research_bundle import (  # noqa: E402
    load_account_snapshot,
    validate_factor_return_surface,
    validate_realized_pnl_ledger,
    validate_selection_opportunity_ledger,
)

CONTRACT_PATH = ROOT / "docs/ops/reaka_current_k1_account_ledgers@1.5.json"
SCIENTIFIC_FILES = (
    "account_snapshot/portfolio_daily.parquet",
    "account_snapshot/holdings.parquet",
    "account_snapshot/trades.parquet",
    "account_snapshot/events.parquet",
    "selection_opportunity_ledger.parquet",
    "selection_opportunity_decision_summary.csv",
    "selection_opportunity_annual.csv",
    "factor_return_surface.parquet",
    "realized_pnl_ledger.parquet",
    "realized_pnl_annual.csv",
    "result.json",
)
ALLOWED_FILES = {
    *SCIENTIFIC_FILES,
    "account_snapshot/snapshot_manifest.json",
    "execution_receipt.json",
}


def _canonical_valid(payload: Mapping[str, object]) -> bool:
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    return stored == canonical_digest(body)


def validate(*, formal_root: Path, isolated_root: Path, evidence_root: Path) -> dict[str, object]:
    if evidence_root.exists():
        raise FileExistsError(evidence_root)
    contract = read_json(CONTRACT_PATH)
    blockers: list[str] = []
    if not _canonical_valid(contract):
        blockers.append("contract_digest_invalid")
    if contract.get("source_closure") != source_closure():
        blockers.append("source_closure_drift")
    results: dict[str, dict[str, object]] = {}
    receipts: dict[str, dict[str, object]] = {}
    diagnostics: dict[str, object] = {}
    for tree, root in (("formal", formal_root), ("isolated", isolated_root)):
        files = {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}
        if files != ALLOWED_FILES:
            blockers.append(f"{tree}_file_allowlist_invalid")
        result = read_json(root / "result.json")
        receipt = read_json(root / "execution_receipt.json")
        results[tree] = result
        receipts[tree] = receipt
        if not _canonical_valid(result) or not _canonical_valid(receipt):
            blockers.append(f"{tree}_canonical_invalid")
        if receipt.get("contract_digest") != contract.get("canonical_digest"):
            blockers.append(f"{tree}_contract_binding_invalid")
        if receipt.get("source_closure") != source_closure():
            blockers.append(f"{tree}_receipt_source_closure_drift")
        if result.get("strategy_id") != STRATEGY_ID or result.get("model_identity") != MODEL_IDENTITY:
            blockers.append(f"{tree}_strategy_identity_invalid")
        if result.get("model_or_parameter_change") is not False:
            blockers.append(f"{tree}_model_or_parameter_changed")
        if result.get("fresh_oos") is not False or result.get("production_authority") is not False:
            blockers.append(f"{tree}_authority_invalid")
        prefix = cast(dict[str, dict[str, bool]], result.get("prefix_checks", {}))
        if not prefix or any(not value for section in prefix.values() for value in section.values()):
            blockers.append(f"{tree}_prefix_checks_failed")
        fit_diagnostics = cast(dict[str, dict[str, object]], result.get("factor_fit_diagnostics", {}))
        if not fit_diagnostics:
            blockers.append(f"{tree}_factor_fit_diagnostics_missing")
        else:
            for clock, local in fit_diagnostics.items():
                if local.get("backend") != "pytorch_rocm_float64_batched_lstsq":
                    blockers.append(f"{tree}_{clock}_factor_backend_invalid")
                if float(local.get("coefficient_max_abs_parity_error", np.inf)) > 1.0e-10:
                    blockers.append(f"{tree}_{clock}_factor_parity_failed")
        replay = cast(dict[str, float], result.get("sealed_annual_replay_checks", {}))
        if not replay or any(float(value) > 1.0e-8 for value in replay.values()):
            blockers.append(f"{tree}_sealed_annual_replay_failed")
        snapshot = load_account_snapshot(root / "account_snapshot")
        opportunity = pd.read_parquet(root / "selection_opportunity_ledger.parquet")
        factor_surface = pd.read_parquet(root / "factor_return_surface.parquet")
        pnl = pd.read_parquet(root / "realized_pnl_ledger.parquet")
        opportunity_check = validate_selection_opportunity_ledger(opportunity)
        factor_check = validate_factor_return_surface(factor_surface)
        pnl_check = validate_realized_pnl_ledger(pnl, account_daily=snapshot.daily)
        decision_summary = pd.read_csv(root / "selection_opportunity_decision_summary.csv")
        if (pd.to_numeric(decision_summary["selection_gap_mean_h20_return"]) > 1.0e-12).any():
            blockers.append(f"{tree}_opportunity_ceiling_violated")
        if set(decision_summary["selected_count"].astype(int)) != {30}:
            blockers.append(f"{tree}_selection_count_invalid")
        annual_selection = pd.read_csv(root / "selection_opportunity_annual.csv")
        annual_pnl = pd.read_csv(root / "realized_pnl_annual.csv")
        if set(annual_selection["year"].astype(int)) != set(range(2011, 2027)):
            blockers.append(f"{tree}_selection_year_coverage_invalid")
        if set(annual_pnl["year"].astype(int)) != set(range(2011, 2027)):
            blockers.append(f"{tree}_pnl_year_coverage_invalid")
        if set(annual_pnl["component_group"].astype(str)) != {"index", "size", "industry", "other"}:
            blockers.append(f"{tree}_pnl_group_inventory_invalid")
        diagnostics[tree] = {
            "snapshot_manifest_digest": snapshot.manifest["canonical_digest"],
            "selection_opportunity": opportunity_check,
            "factor_return_surface": factor_check,
            "realized_pnl": pnl_check,
            "elapsed_seconds": receipt.get("elapsed_seconds"),
        }
    byte_pairs = 0
    for name in SCIENTIFIC_FILES:
        left = formal_root / name
        right = isolated_root / name
        if not left.is_file() or not right.is_file():
            blockers.append(f"scientific_file_missing:{name}")
            continue
        byte_pairs += 1
        if left.read_bytes() != right.read_bytes():
            blockers.append(f"formal_isolated_bytes_differ:{name}")
    report = write_json(
        evidence_root / "validation_report.json",
        {
            "schema_id": "factorlab.reaka_current_K1_account_ledgers_validation@1.0",
            "status": "passed" if not blockers else "blocked",
            "contract_digest": contract.get("canonical_digest"),
            "strategy_id": STRATEGY_ID,
            "model_identity": MODEL_IDENTITY,
            "formal_result_digest": results.get("formal", {}).get("canonical_digest"),
            "isolated_result_digest": results.get("isolated", {}).get("canonical_digest"),
            "formal_receipt_digest": receipts.get("formal", {}).get("canonical_digest"),
            "isolated_receipt_digest": receipts.get("isolated", {}).get("canonical_digest"),
            "scientific_byte_identical_pairs": byte_pairs,
            "tree_diagnostics": diagnostics,
            "old_d8_K2_opportunity_ledger_reused_as_current": False,
            "old_sealed_ledgers_rewritten": False,
            "result_backflow_allowed": False,
            "fresh_oos": False,
            "production_authority": False,
            "blockers": blockers,
        },
    )
    write_json(
        evidence_root / "controller_acceptance.json",
        {
            "schema_id": "factorlab.reaka_current_K1_account_ledgers_acceptance@1.0",
            "status": "accepted_current_strategy_two_ledgers" if not blockers else "rejected",
            "validation_report_digest": report["canonical_digest"],
            "result_digest": results.get("formal", {}).get("canonical_digest"),
            "account_snapshot_manifest_digest": diagnostics.get("formal", {}).get(
                "snapshot_manifest_digest"
            ),
            "strategy_or_parameter_mutation": False,
            "result_backflow_allowed": False,
            "fresh_oos": False,
            "production_authority": False,
            "blockers": blockers,
        },
    )
    if blockers:
        raise ValueError("current_K1_account_ledgers_validation_failed:" + ",".join(blockers))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--isolated-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    report = validate(
        formal_root=Path(args.formal_root),
        isolated_root=Path(args.isolated_root),
        evidence_root=Path(args.evidence_root),
    )
    print(json.dumps({"status": report["status"], "digest": report["canonical_digest"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
