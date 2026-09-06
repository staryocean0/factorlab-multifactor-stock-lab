#!/usr/bin/env python3
"""Run one fit-prefix successor tree/clock."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from factor_lab.factor_rotation.reaka_intraday_k1_fit_prefix_successor_v1 import (
    run_formal,
)
from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    CLOCK_SUFFIX,
    read_json,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/ops/reaka_intraday_K1_fit_prefix_successor@1.0.json"
STORE = ROOT / "output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020"
NORMALIZER = ROOT / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831/preflight"
OUTPUT = ROOT / "output/factor-rotation/reaka_intraday_K1_fit_prefix_successor_v1_2011_2017"


def main() -> None:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--tree", choices=("formal", "isolated"), required=True)
    _ = parser.add_argument("--clock", choices=("14:30", "14:45"), required=True)
    args = parser.parse_args()
    tree = cast(str, args.tree)
    clock = cast(str, args.clock)
    suffix = CLOCK_SUFFIX[clock]
    result = run_formal(
        contract=read_json(CONTRACT),
        tree=tree,
        clock=clock,
        store_root=STORE / tree / suffix,
        normalizer=read_json(NORMALIZER / suffix / "normalizer.json"),
        output_root=OUTPUT / tree / suffix,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
