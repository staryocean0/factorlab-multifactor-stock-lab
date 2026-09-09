#!/usr/bin/env python3
"""Validate live infrastructure, or explicitly check a restored historical V1.3."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--inventory", action="store_true", help="Also report repository Markdown navigation")
    parser.add_argument("--historical-v1-3", action="store_true", help="Check V1.3 original bytes, not live guidance")
    args = parser.parse_args()
    if args.historical_v1_3:
        from factor_lab.governance.reaka_foundation_contract import validate_foundation
        report = validate_foundation(args.root)
    else:
        from factor_lab.governance.reaka_infrastructure_v1_4 import validate_infrastructure
        report = validate_infrastructure(args.root, inventory=args.inventory)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["infrastructure_consistency"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
