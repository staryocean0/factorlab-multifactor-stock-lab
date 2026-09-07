#!/usr/bin/env python3
"""Run the pre-registered Stage-B fine X decomposition after read-only preflight."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACTORLAB_ROOT = Path(os.environ.get("FACTORLAB_ROOT", "/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab"))


def _bootstrap() -> None:
    src = str(FACTORLAB_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    import factor_lab.factor_rotation as pkg
    theme = ROOT / "src/factor_lab/factor_rotation"
    for name in (
        "reaka_r3_condition_views", "reaka_r3_time_isolation", "reaka_r3_time_isolated_runner",
        "reaka_r3_x_decomposition", "reaka_r3_x_coarse_runner", "reaka_r3_x_fine_runner",
        "reaka_r3_x_fine_preflight",
    ):
        dest = f"factor_lab.factor_rotation.{name}"
        spec = importlib.util.spec_from_file_location(dest, theme / f"{name}.py")
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load {name}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[dest] = mod
        spec.loader.exec_module(mod)
        setattr(pkg, name, mod)


_bootstrap()
from factor_lab.factor_rotation import reaka_r3_x_fine_preflight as preflight
from factor_lab.factor_rotation import reaka_r3_x_fine_runner as fine


def read_spec(path: Path) -> dict:
    body = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise ValueError("spec must be object")
    return body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--reload-fine-worker", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.reload_fine_worker:
            s = read_spec(args.reload_fine_worker)
            out = fine.reload_arm_worker(
                Path(s["store_root"]), Path(s["checkpoint_root"]), Path(s["normalizer_path"]),
                Path(s["candidate_path"]), str(s["arm"]), int(s["seed"]), Path(s["indices_path"]),
                Path(s["output_path"]), str(s.get("device_name", "cpu")),
            )
            print(json.dumps(out, ensure_ascii=False)); return 0
        if not args.spec:
            raise ValueError("--spec required")
        s = read_spec(args.spec)
        if s.get("schema_id") != "factorlab.r3_x_fine_run_spec@1.0":
            raise ValueError("wrong schema")
        timeiso_root = Path(s["accepted_timeiso_run_root"]).resolve()
        xcoarse_root = Path(s["accepted_xcoarse_run_root"]).resolve()
        output_root = Path(s["output_root"]).resolve()
        expected_factorlab_commit = str(s["expected_factorlab_commit"])

        # Mandatory zero-fit, zero-inference reference preflight before any new model fit.
        pre = preflight.run(
            timeiso_root, xcoarse_root, ROOT / "src/factor_lab/factor_rotation",
            FACTORLAB_ROOT, expected_factorlab_commit,
        )
        preflight_path = output_root.parent / f"{output_root.name}.preflight.json"
        fine.write_json(preflight_path, pre)
        if args.preflight_only:
            print(json.dumps({
                "status": pre["status"], "reference_seed_pairs_checked": pre["reference_seed_pairs_checked"],
                "new_fits": 0, "new_inference": 0, "preflight_receipt": str(preflight_path),
            }, ensure_ascii=False)); return 0

        result = fine.run(
            timeiso_root, xcoarse_root, output_root, Path(__file__).resolve(),
            ROOT / "src/factor_lab/factor_rotation", FACTORLAB_ROOT, expected_factorlab_commit,
        )
        result["preflight_receipt"] = str(preflight_path)
        fine.write_json(output_root / "result.json", result)
        print(json.dumps({
            "status": result["status"], "new_fits": result["new_fits"], "new_arms": result["new_arms"],
            "preflight_receipt": str(preflight_path),
        }, ensure_ascii=False)); return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)); return 1


if __name__ == "__main__":
    raise SystemExit(main())
