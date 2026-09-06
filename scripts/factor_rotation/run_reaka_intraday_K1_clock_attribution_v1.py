#!/usr/bin/env python3
"""Materialize one P6.4.1 paired attribution tree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from factor_lab.factor_rotation.reaka_intraday_k1_clock_attribution_v1 import (
    run_attribution,
)
from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import read_json

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/ops/reaka_intraday_K1_clock_attribution@1.0.json"
STORE = ROOT / "output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020"
NORMALIZER = ROOT / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831/preflight"
P64 = ROOT / "output/factor-rotation/reaka_intraday_K1_formal_v1_2011_2018"
OUTPUT = ROOT / "output/factor-rotation/reaka_intraday_K1_clock_attribution_v1_2011_2017"


def main() -> None:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--tree", choices=("formal", "isolated"), required=True)
    args = parser.parse_args()
    tree = cast(str, args.tree)
    result = run_attribution(
        contract=read_json(CONTRACT),
        tree=tree,
        store_base=STORE,
        normalizer_base=NORMALIZER,
        p64_root=P64,
        output_root=OUTPUT,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
