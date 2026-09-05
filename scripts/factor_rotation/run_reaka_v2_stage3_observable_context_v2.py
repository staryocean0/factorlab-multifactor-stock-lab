#!/usr/bin/env python3
from __future__ import annotations

import argparse

from factor_lab.factor_rotation.reaka_v2_stage3_observable_context_v2 import (
    execute_tree,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", choices=("formal", "isolated"), required=True)
    args = parser.parse_args()
    execute_tree(tree=str(args.tree))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
