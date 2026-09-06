#!/usr/bin/env python3
# pyright: reportAny=false, reportUnusedCallResult=false
"""Materialize one frozen P6.1 intraday target/fill tree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from factor_lab.factor_rotation.reaka_intraday_target_fill_v1 import (
    DEFAULT_DATASET_ROOT,
    materialize_intraday_target_fill,
    read_json,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/ops/reaka_intraday_target_fill@1.0.json"
REFERENCE = ROOT / "output/factor-rotation/orthogonal_index_timing_transport_OT1_v1_1_2009_2020" / "daily_stock_idiosyncratic_returns.npz"
OT3 = ROOT / "output/factor-rotation/orthogonal_timing_stock_transport_OT3_v1_1_2009_2020" / "weekly_stock_timing_transport.parquet"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    contract = read_json(CONTRACT)
    if contract.get("materialization_allowed") is not True:
        raise RuntimeError("reaka_intraday_materialization_not_authorized")
    result = materialize_intraday_target_fill(
        output_root=args.output_root,
        dataset_root=args.dataset_root,
        reference_path=REFERENCE,
        ot3_path=OT3,
        contract_digest=str(contract["canonical_digest"]),
        workers=args.workers,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
