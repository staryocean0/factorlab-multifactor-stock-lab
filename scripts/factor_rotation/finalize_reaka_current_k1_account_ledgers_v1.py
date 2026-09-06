#!/usr/bin/env python3
# pyright: reportAny=false, reportUnknownVariableType=false, reportUnusedCallResult=false
"""Apply the v1.5 metadata-only packaging repair to completed v1.4 ledgers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
for value in (ROOT, ROOT / "src"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from factor_lab.factor_rotation.reaka_current_k1_account_ledgers_v1 import (  # noqa: E402
    CONTRACT_PATH,
    file_digest,
    source_closure,
    write_json,
)
from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import read_json  # noqa: E402
from factor_lab.governance.canonicalization import canonical_digest  # noqa: E402

DATA_FILES = (
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
)


def _canonical_valid(payload: dict[str, object]) -> bool:
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    return stored == canonical_digest(body)


def finalize(*, formal_root: Path, isolated_root: Path) -> dict[str, object]:
    contract = read_json(CONTRACT_PATH)
    if not _canonical_valid(contract) or contract.get("source_closure") != source_closure():
        raise ValueError("current_K1_ledger_v1_5_contract_invalid")
    common_digests: dict[str, str] = {}
    for name in DATA_FILES:
        left = formal_root / name
        right = isolated_root / name
        if left.read_bytes() != right.read_bytes():
            raise ValueError(f"current_K1_ledger_v1_5_scientific_data_mismatch:{name}")
        common_digests[name] = file_digest(left)
    common_tree_digest = canonical_digest(common_digests)
    if common_tree_digest != "sha256:7c260339176e4aa20b3c98d0d9719246b9fc5fb77f5bdba853d527e082a9b625":
        raise ValueError("current_K1_ledger_v1_5_scientific_data_tree_drift")
    snapshot_digest = canonical_digest(
        {
            name.removeprefix("account_snapshot/"): digest
            for name, digest in common_digests.items()
            if name.startswith("account_snapshot/")
        }
    )
    result_digest = ""
    receipt_digests: dict[str, str] = {}
    for tree, root in (("formal", formal_root), ("isolated", isolated_root)):
        old_result = read_json(root / "result.json")
        old_receipt = read_json(root / "execution_receipt.json")
        if not _canonical_valid(old_result) or not _canonical_valid(old_receipt):
            raise ValueError(f"current_K1_ledger_v1_4_metadata_invalid:{tree}")
        fit = cast(dict[str, dict[str, object]], old_result["factor_fit_diagnostics"])
        scientific_fit = {
            clock: {key: value for key, value in local.items() if key != "elapsed_seconds"}
            for clock, local in fit.items()
        }
        new_result = dict(old_result)
        new_result.pop("canonical_digest", None)
        new_result.pop("account_snapshot_manifest_digest", None)
        new_result["factor_fit_diagnostics"] = scientific_fit
        new_result["account_snapshot_scientific_digest"] = snapshot_digest
        new_result["packaging_repair_contract_digest"] = contract["canonical_digest"]
        result = write_json(root / "result.json", new_result)
        if result_digest and result["canonical_digest"] != result_digest:
            raise RuntimeError("current_K1_ledger_v1_5_result_digest_differ")
        result_digest = str(result["canonical_digest"])
        scientific = dict(common_digests)
        scientific["result.json"] = file_digest(root / "result.json")
        receipt = write_json(
            root / "execution_receipt.json",
            {
                "schema_id": "factorlab.reaka_current_K1_account_ledgers_execution@1.1",
                "status": "completed_packaging_only_v1_5",
                "tree": tree,
                "contract_digest": contract["canonical_digest"],
                "backend": old_receipt["backend"],
                "elapsed_seconds": old_receipt["elapsed_seconds"],
                "original_v1_4_receipt_digest": old_receipt["canonical_digest"],
                "result_digest": result["canonical_digest"],
                "account_snapshot_manifest_digest": old_receipt["account_snapshot_manifest_digest"],
                "account_snapshot_scientific_digest": snapshot_digest,
                "factor_fit_runtime_diagnostics": fit,
                "scientific_file_digests": scientific,
                "input_digests": old_receipt["input_digests"],
                "source_closure": source_closure(),
                "scientific_data_recomputation_count": 0,
                "model_score_market_account_factor_fit_opportunity_or_pnl_recomputation_count": 0,
                "model_or_parameter_change": False,
                "result_backflow_allowed": False,
                "fresh_oos": False,
                "production_authority": False,
            },
        )
        receipt_digests[tree] = str(receipt["canonical_digest"])
    return {
        "status": "completed_packaging_only_v1_5",
        "contract_digest": contract["canonical_digest"],
        "scientific_data_tree_digest": common_tree_digest,
        "account_snapshot_scientific_digest": snapshot_digest,
        "result_digest": result_digest,
        "receipt_digests": receipt_digests,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--isolated-root", type=Path, required=True)
    args = parser.parse_args()
    result = finalize(
        formal_root=Path(args.formal_root),
        isolated_root=Path(args.isolated_root),
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
