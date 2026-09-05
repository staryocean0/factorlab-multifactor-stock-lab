#!/usr/bin/env python3
"""Strict five-in-one consistency check, independent of market-data uploads."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from factor_lab.governance.reaka_foundation_contract import validate_foundation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    report = validate_foundation(args.root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["infrastructure_consistency"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
