#!/usr/bin/env python3
"""Assemble bound 2021--2025 feature bundles; never train or score a model."""
from __future__ import annotations
import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "src/factor_lab/factor_rotation/reaka_r3_transfer_inputs.py"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args()
    try:
        spec = importlib.util.spec_from_file_location("r3_transfer_inputs_cli", PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load the transfer adapter")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        result = module.run(module.read_json(args.spec))
        print(json.dumps({"status": result["status"], "task_id": result["task_id"],
                          "new_model_fits": 0, "new_inference": 0}))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
