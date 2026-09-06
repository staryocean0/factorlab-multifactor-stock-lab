#!/usr/bin/env python3
"""Check a proposed R3 plan. No market data, training or remote jobs are used."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from factor_lab.factor_rotation.reaka_r3_time_isolation import strict_json, validate_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "docs/ops/r3_time_isolated_evaluation_plan_20260906.json")
    args = parser.parse_args()
    try:
        result = validate_plan(strict_json(args.plan.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        result = {"design_consistency": "failed", "errors": [str(exc)],
                  "market_experiment_executed": False, "PIT_certified": False}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["design_consistency"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
