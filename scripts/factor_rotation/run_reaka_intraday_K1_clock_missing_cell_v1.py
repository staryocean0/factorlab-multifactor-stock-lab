#!/usr/bin/env python3
"""Train one missing P6.4.1 matched cell."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from factor_lab.factor_rotation.reaka_intraday_k1_clock_attribution_v1 import (
    train_missing_cell,
)
from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    CLOCK_SUFFIX,
    read_json,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/ops/reaka_intraday_K1_clock_attribution@1.0.json"
STORE = ROOT / "output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020"
NORMALIZER = ROOT / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831/preflight"
OUTPUT = ROOT / "output/factor-rotation/reaka_intraday_K1_clock_attribution_v1_2011_2017"


def main() -> None:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--tree", choices=("formal", "isolated"), required=True)
    _ = parser.add_argument("--cell", choices=("1430_B", "1445_A"), required=True)
    args = parser.parse_args()
    tree = cast(str, args.tree)
    cell_id = cast(str, args.cell)
    contract = read_json(CONTRACT)
    cell = next(
        cast(Mapping[str, object], row)
        for row in cast(list[object], contract["cells"])
        if cast(Mapping[str, object], row)["cell_id"] == cell_id
    )
    clock = str(cell["clock"])
    result = train_missing_cell(
        contract=contract,
        cell=cell,
        store_root=STORE / tree / CLOCK_SUFFIX[clock],
        normalizer=read_json(NORMALIZER / CLOCK_SUFFIX[clock] / "normalizer.json"),
        output_root=OUTPUT / tree / cell_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
