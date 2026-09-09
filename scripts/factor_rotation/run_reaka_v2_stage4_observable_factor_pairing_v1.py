#!/usr/bin/env python3
from __future__ import annotations

# ruff: noqa: E402
# Retired materializers cannot recreate historical current/evidence authority.
# Keep this check before legacy imports, including optional project dependencies.
import sys as _foundation_sys
from pathlib import Path as _FoundationPath

_FOUNDATION_ROOT = _FoundationPath(__file__).resolve().parents[2]
if str(_FOUNDATION_ROOT / "src") not in _foundation_sys.path:
    _foundation_sys.path.insert(0, str(_FOUNDATION_ROOT / "src"))
from factor_lab.governance.reaka_foundation_contract import (  # noqa: E402
    reject_legacy_entrypoint as _reject_legacy_entrypoint,
)

if __name__ == "__main__":
    _reject_legacy_entrypoint(__file__)

import argparse

from factor_lab.factor_rotation.reaka_v2_stage4_observable_factor_pairing_v1 import execute_tree


def main() -> int:
    _reject_legacy_entrypoint(__file__)
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", choices=("formal", "isolated"), required=True)
    args = parser.parse_args()
    execute_tree(tree=str(args.tree))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
