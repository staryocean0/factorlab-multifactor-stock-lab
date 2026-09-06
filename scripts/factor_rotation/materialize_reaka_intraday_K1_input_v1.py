#!/usr/bin/env python3
"""Materialize one frozen P6.3 intraday K1/r0 input tree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    CLOCK_SUFFIX,
    materialize_store,
    read_json,
    validate_contract,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/ops/reaka_intraday_K1_preflight@1.0.json"
P61 = ROOT / "output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020"
P62 = ROOT / "output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020"
OUTPUT = ROOT / "output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020"


def main() -> None:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--tree", choices=("formal", "isolated"), required=True)
    _ = parser.add_argument("--clock", choices=("14:30", "14:45"), required=True)
    args = parser.parse_args()
    tree = cast(str, args.tree)
    clock = cast(str, args.clock)
    contract = read_json(CONTRACT)
    blockers = validate_contract(contract)
    if blockers:
        raise RuntimeError(";".join(blockers))
    suffix = CLOCK_SUFFIX[clock]
    result = materialize_store(
        output_root=OUTPUT / tree / suffix,
        ot_root=P62 / tree / suffix,
        p6_root=P61 / tree,
        contract_digest=str(contract["canonical_digest"]),
        decision_clock=clock,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
