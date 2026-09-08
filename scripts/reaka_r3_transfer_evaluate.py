#!/usr/bin/env python3
"""Build transfer label sidecars or run frozen 2021--2025 transfer evaluation."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACTORLAB_ROOT = Path(os.environ.get("FACTORLAB_ROOT", "/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab"))
MOD_PATH = ROOT / "src/factor_lab/factor_rotation/reaka_r3_transfer_evaluation.py"


def load_module():
    spec = importlib.util.spec_from_file_location("factor_lab.factor_rotation.reaka_r3_transfer_evaluation", MOD_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load transfer evaluation module")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def bootstrap_theme():
    src = str(FACTORLAB_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    import factor_lab.factor_rotation as pkg
    theme = ROOT / "src/factor_lab/factor_rotation"
    for name in ("reaka_r3_condition_views", "reaka_r3_time_isolated_runner",
                 "reaka_r3_x_decomposition", "reaka_r3_transfer_inputs",
                 "reaka_r3_transfer_evaluation"):
        dest = f"factor_lab.factor_rotation.{name}"
        path = theme / f"{name}.py"
        spec = importlib.util.spec_from_file_location(dest, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load {name}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[dest] = mod
        spec.loader.exec_module(mod)
        setattr(pkg, name, mod)


def read(path: Path):
    body = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise ValueError("spec object required")
    return body


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build-label-sidecar", type=Path)
    p.add_argument("--score-worker", type=Path)
    p.add_argument("--run", type=Path)
    args = p.parse_args()
    modes = sum(x is not None for x in (args.build_label_sidecar, args.score_worker, args.run))
    if modes != 1:
        p.error("choose exactly one mode")
    try:
        if args.build_label_sidecar:
            m = load_module()
            s = read(args.build_label_sidecar)
            result = m.build_label_sidecar(
                Path(s["feature_store"]), Path(s["label_bundle"]), Path(s["reference_label_store"]),
                Path(s["output_root"]), expected_bundle_sha256=str(s["label_bundle_sha256"]),
                expected_reference_manifest_sha256=str(s["reference_manifest_sha256"]))
            print(json.dumps({"status": result["status"], "finite_evaluation_rows": result["finite_evaluation_rows"]}))
            return 0
        bootstrap_theme()
        from factor_lab.factor_rotation import reaka_r3_transfer_evaluation as m
        if args.score_worker:
            result = m.run_score_worker(read(args.score_worker))
            print(json.dumps({"status": "scored_no_labels", "clock": result["clock"],
                              "seed": result["seed"], "arm": result["arm"],
                              "target_values_read": result["target_values_read"]}))
            return 0
        result = m.run_transfer_evaluation(read(args.run), Path(__file__).resolve())
        print(json.dumps({"status": result["status"], "score_jobs": result["score_jobs"],
                          "new_model_fits": result["new_model_fits"]}))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
