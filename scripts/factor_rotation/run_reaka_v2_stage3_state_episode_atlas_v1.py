#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from factor_lab.factor_rotation.reaka_v2_stage3_state_episode_atlas_v1 import (
    execute_tree,
)

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", choices=("formal", "isolated"), required=True)
    args = parser.parse_args()
    execute_tree(
        tree=args.tree,
        output_root=(ROOT / "output/factor-rotation/reaka_v2_stage3_state_episode_atlas_v1_2011_2025" / args.tree),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
