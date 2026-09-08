from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/reaka_r3_transfer_sidecar_v1_1.py"


def load():
    spec = importlib.util.spec_from_file_location("r3_transfer_sidecar_v11_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def writej(path: Path, body):
    path.write_text(json.dumps(body), encoding="utf-8")


def make_bundle(root: Path):
    m = load(); base = m.load_base(); root.mkdir()
    for name in m.REQUIRED:
        if name == "target_anchor_checks.json":
            continue
        (root / name).write_bytes(("payload:" + name).encode())
    anchors = {
        "schema_id": m.ANCHOR_SCHEMA_V11,
        "selection_rule": m.ANCHOR_RULE,
        "passed": True,
        "anchors_checked": 5,
        "support_mismatches": 0,
        "max_abs_error": 0.0,
        "anchors": [{"structurally_mature": True, "day_position": i, "date": f"2020-01-{i+1:02d}"} for i in range(5)],
    }
    writej(root / "target_anchor_checks.json", anchors)
    artifacts = {name: base.sha_file(root / name) for name in m.REQUIRED}
    bundle = {
        "schema_id": m.LABEL_SCHEMA_V11,
        "raw_future_definition": m.RAW_FUTURE,
        "target_source_task": m.SOURCE_TASK,
        "target_source_bundle_sha256": "sha256:" + "1" * 64,
        "calendar_end": "2025-12-31",
        "contains_2026": False,
        "target_definition": "H20_financial_residual_epsilon_future_K1_v1",
        "horizon_trading_positions": 20,
        "labels_used_for_features": False,
        "fold_policy": "explicit_incumbent_symbol_position_mod5",
        "artifact_digests": artifacts,
    }
    writej(root / "bundle.json", bundle)
    return m, base, bundle, anchors


def test_repaired_v11_bundle_is_accepted(tmp_path):
    m, base, _, _ = make_bundle(tmp_path / "b")
    bm, anchors, observed = m.validate_v11(base, tmp_path / "b", base.sha_file(tmp_path / "b/bundle.json"))
    assert bm["raw_future_definition"] == m.RAW_FUTURE
    assert anchors["passed"] is True
    assert observed.startswith("sha256:")


def test_legacy_v10_bundle_is_rejected(tmp_path):
    m, base, bundle, _ = make_bundle(tmp_path / "b")
    bundle["schema_id"] = "factorlab.r3_transfer_label_bundle@1.0"
    writej(tmp_path / "b/bundle.json", bundle)
    with pytest.raises(ValueError, match="legacy"):
        m.validate_v11(base, tmp_path / "b", base.sha_file(tmp_path / "b/bundle.json"))


def test_wrong_raw_future_definition_is_rejected(tmp_path):
    m, base, bundle, _ = make_bundle(tmp_path / "b")
    bundle["raw_future_definition"] = "decision_close_t_plus_20_div_decision_close_t_minus_1"
    writej(tmp_path / "b/bundle.json", bundle)
    with pytest.raises(ValueError, match="entry-open"):
        m.validate_v11(base, tmp_path / "b", base.sha_file(tmp_path / "b/bundle.json"))


def test_anchor_schema_and_structure_are_strict(tmp_path):
    m, base, bundle, anchors = make_bundle(tmp_path / "b")
    anchors["anchors"][4]["structurally_mature"] = False
    writej(tmp_path / "b/target_anchor_checks.json", anchors)
    bundle["artifact_digests"]["target_anchor_checks.json"] = base.sha_file(tmp_path / "b/target_anchor_checks.json")
    writej(tmp_path / "b/bundle.json", bundle)
    with pytest.raises(ValueError, match="structurally mature"):
        m.validate_v11(base, tmp_path / "b", base.sha_file(tmp_path / "b/bundle.json"))


def test_adapter_has_no_model_execution_entrypoints():
    text = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("score_no_labels(", "forecast(", "load_state_tree(", "run_score_worker(", "checkpoint_root"):
        assert forbidden not in text
    assert "metadata_schema_only_arrays_symlinked_byte_identical" in text
    assert "entry_open_t_plus_20_div_entry_open_t_minus_1" in text
