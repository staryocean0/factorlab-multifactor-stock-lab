#!/usr/bin/env python3
# pyright: reportAny=false, reportUnusedCallResult=false
"""Build both current-strategy REAKA account ledgers for one evidence tree."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for value in (ROOT, ROOT / "src"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from factor_lab.factor_rotation.reaka_current_k1_account_ledgers_v1 import (  # noqa: E402
    execute_tree,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", choices=("formal", "isolated"), required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--factor-batch-size", type=int, default=32)
    args = parser.parse_args()
    receipt = execute_tree(
        tree=str(args.tree),
        output_root=Path(args.output_root),
        factor_batch_size=int(args.factor_batch_size),
    )
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "elapsed_seconds": receipt["elapsed_seconds"],
                "receipt_digest": receipt["canonical_digest"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
