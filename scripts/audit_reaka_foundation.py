#!/usr/bin/env python3
"""Print a read-only foundation audit: exit 0 complete, 1 errors, 2 gaps."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from factor_lab.governance.reaka_foundation_audit import audit_foundation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--report-only", action="store_true",
        help="Return zero after report generation; report status and foundation_ready still express all failures.",
    )
    args = parser.parse_args()
    report = audit_foundation(args.root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report_only:
        return 0
    return {"passed": 0, "failed": 1, "incomplete": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
