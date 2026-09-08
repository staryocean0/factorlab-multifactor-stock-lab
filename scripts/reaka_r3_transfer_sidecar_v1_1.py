#!/usr/bin/env python3
"""Build a transfer label sidecar from the repaired @1.1 entry-open bundle.

This is a narrow compatibility successor. It first binds and validates the
@1.1 bundle (including entry-open raw-future identity and structural-anchor
checks), then feeds an ephemeral schema-only compatibility view into the
existing sidecar builder. No target array bytes are changed and no model score,
checkpoint, or training path is available here.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "src/factor_lab/factor_rotation/reaka_r3_transfer_evaluation.py"
LABEL_SCHEMA_V11 = "factorlab.r3_transfer_label_bundle@1.1"
ANCHOR_SCHEMA_V11 = "factorlab.r3_transfer_target_anchor_checks@1.1"
RAW_FUTURE = "entry_open_t_plus_20_div_entry_open_t_minus_1"
SOURCE_TASK = "LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01"
ANCHOR_RULE = "five_equal_index_quantiles_of_structurally_mature_2018_2020_old_D5_blind_to_target_values"
REQUIRED = (
    "calendar.npy", "symbols.npy", "factor_ids.json", "symbol_fold_ids.npy",
    "epsilon_future.npy", "producer_sources.json", "target_anchor_checks.json",
)


def load_base():
    spec = importlib.util.spec_from_file_location("r3_transfer_eval_sidecar_v11_base", BASE)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load transfer evaluation module")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read(path: Path) -> dict[str, Any]:
    body = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise ValueError(f"JSON object required: {path}")
    return body


def validate_v11(base, label_bundle: Path, expected_bundle_sha256: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    bundle_path = label_bundle / "bundle.json"
    observed = base.bind_file(bundle_path, expected_bundle_sha256)
    bm = base.read_json(bundle_path)
    if bm.get("schema_id") != LABEL_SCHEMA_V11:
        raise ValueError("repaired label bundle @1.1 required; legacy @1.0 is rejected")
    if bm.get("raw_future_definition") != RAW_FUTURE:
        raise ValueError("entry-open raw future definition required")
    if bm.get("target_source_task") != SOURCE_TASK:
        raise ValueError("repaired target-source task identity required")
    source_sha = bm.get("target_source_bundle_sha256")
    if not isinstance(source_sha, str) or not source_sha.startswith("sha256:") or len(source_sha) != 71:
        raise ValueError("target-source bundle SHA256 required")
    if bm.get("calendar_end") != "2025-12-31" or bm.get("contains_2026") is not False:
        raise ValueError("bounded 2025 repaired label bundle required")
    if bm.get("target_definition") != "H20_financial_residual_epsilon_future_K1_v1":
        raise ValueError("target definition drift")
    if bm.get("horizon_trading_positions") != 20 or bm.get("labels_used_for_features") is not False:
        raise ValueError("label separation/horizon drift")
    if bm.get("fold_policy") != "explicit_incumbent_symbol_position_mod5":
        raise ValueError("fold identity drift")
    artifacts = bm.get("artifact_digests")
    if not isinstance(artifacts, dict):
        raise ValueError("artifact digests required")
    for name in REQUIRED:
        base.bind_file(label_bundle / name, artifacts.get(name))

    anchors = base.read_json(label_bundle / "target_anchor_checks.json")
    if anchors.get("schema_id") != ANCHOR_SCHEMA_V11 or anchors.get("passed") is not True:
        raise ValueError("repaired structural anchor checks required")
    if anchors.get("selection_rule") != ANCHOR_RULE:
        raise ValueError("structural anchor selection rule drift")
    if int(anchors.get("anchors_checked", 0)) != 5:
        raise ValueError("exactly five repaired anchors required")
    if int(anchors.get("support_mismatches", -1)) != 0:
        raise ValueError("repaired anchor support drift")
    if float(anchors.get("max_abs_error", float("inf"))) > 1e-7:
        raise ValueError("repaired anchor values drift")
    rows = anchors.get("anchors")
    if not isinstance(rows, list) or len(rows) != 5 or any(r.get("structurally_mature") is not True for r in rows):
        raise ValueError("all repaired anchors must be structurally mature")
    return bm, anchors, observed


def build(spec: dict[str, Any]) -> dict[str, Any]:
    base = load_base()
    feature = Path(spec["feature_store"]).resolve()
    label = Path(spec["label_bundle"]).resolve()
    reference = Path(spec["reference_label_store"]).resolve()
    output = Path(spec["output_root"]).resolve()
    bm, anchors, bundle_sha = validate_v11(base, label, str(spec["label_bundle_sha256"]))

    # The existing builder has stronger coordinate/prefix/maturity checks but is
    # frozen to @1.0 metadata. Create a temporary metadata-only compatibility
    # view. Arrays stay byte-identical through symlinks.
    with tempfile.TemporaryDirectory(prefix="r3_sidecar_v11_") as td:
        compat = Path(td)
        for name in REQUIRED:
            if name == "target_anchor_checks.json":
                continue
            os.symlink((label / name).resolve(), compat / name)
        compat_anchor = dict(anchors)
        compat_anchor["schema_id"] = "factorlab.r3_transfer_target_anchor_checks@1.0"
        (compat / "target_anchor_checks.json").write_text(
            json.dumps(compat_anchor, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        compat_bundle = dict(bm)
        compat_bundle["schema_id"] = base.LABEL_SCHEMA
        compat_artifacts = dict(bm["artifact_digests"])
        compat_artifacts["target_anchor_checks.json"] = base.sha_file(compat / "target_anchor_checks.json")
        compat_bundle["artifact_digests"] = compat_artifacts
        (compat / "bundle.json").write_text(
            json.dumps(compat_bundle, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        result = base.build_label_sidecar(
            feature, compat, reference, output,
            expected_bundle_sha256=base.sha_file(compat / "bundle.json"),
            expected_reference_manifest_sha256=str(spec["reference_manifest_sha256"]),
        )

    binding = {
        "schema_id": "factorlab.r3_transfer_sidecar_v11_binding@1.0",
        "source_label_bundle_schema": LABEL_SCHEMA_V11,
        "source_label_bundle_sha256": bundle_sha,
        "target_source_bundle_sha256": bm["target_source_bundle_sha256"],
        "raw_future_definition": RAW_FUTURE,
        "anchor_schema": ANCHOR_SCHEMA_V11,
        "anchors_checked": 5,
        "anchor_support_mismatches": 0,
        "anchor_max_abs_error": float(anchors["max_abs_error"]),
        "compatibility_transform": "metadata_schema_only_arrays_symlinked_byte_identical",
        "target_array_rewritten": False,
        "model_scores_read": 0,
        "checkpoint_reload": 0,
        "new_model_fits": 0,
        "fresh_oos": False,
        "PIT_certified": False,
    }
    base.write_json_new(output / "label_source_binding_v1_1.json", binding)
    return {**result, "source_label_bundle_sha256": bundle_sha,
            "target_source_bundle_sha256": bm["target_source_bundle_sha256"]}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spec", type=Path, required=True)
    args = p.parse_args()
    try:
        body = _read(args.spec)
        result = build(body)
        print(json.dumps({"status": result["status"],
                          "finite_evaluation_rows": result["finite_evaluation_rows"]}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
