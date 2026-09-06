#!/usr/bin/env python3
"""Strict delivered-data check; does not grant research or publication rights."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from factor_lab.governance.reaka_infrastructure_v1_4 import safe_path, validate_infrastructure  # noqa: E402
MAX_GIT_FILE_BYTES = 90 * 1024 * 1024
FORBIDDEN_PARTS = {".env", "credentials", "cloud_runtime", ".beads"}
IGNORED = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".venv"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    foundation = validate_infrastructure(ROOT)
    if foundation["infrastructure_consistency"] != "passed":
        raise RuntimeError(f"current infrastructure invalid: {foundation['errors']}")
    scope = json.loads((ROOT / "docs/governance/package_scope.json").read_text())
    usage = json.loads((ROOT / "docs/governance/data_usage_declaration.json").read_text())
    manifest = json.loads((ROOT / "data/manifest.json").read_text())
    assert scope["paper_redistribution_allowed"] is False
    assert scope["production_authority"] is False
    assert usage["fresh_oos"] is False
    assert manifest["post_2025_rows_included"] is False
    paper = ROOT / "research_materials/liao_residual_enhanced_adaptive_koopman_stock_prediction_2026.pdf"
    assert paper.is_file() and paper.stat().st_size > 100_000
    file_count = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in IGNORED or part.endswith(".egg-info") for part in relative.parts):
            continue
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            raise RuntimeError(f"forbidden path entered package: {relative}")
        if path.stat().st_size >= MAX_GIT_FILE_BYTES:
            raise RuntimeError(f"file exceeds declared repository packaging limit: {relative}")
        file_count += 1
    for item in manifest["products"]:
        path = safe_path(ROOT, item["path"])
        if not path.is_file() or sha256(path) != item["sha256"]:
            raise RuntimeError(f"data product drifted: {item['path']}")
        relative = str(item["path"])
        if path.suffix == ".parquet" and relative.startswith("data/development/"):
            frame = pd.read_parquet(path)
            for column in ("trading_day", "decision_date", "month_start", "date"):
                if column in frame.columns:
                    days = pd.to_datetime(frame[column], errors="coerce")
                    if days.notna().any() and str(days.max())[:10] > "2025-12-31":
                        raise RuntimeError(f"post-2025 row: {relative}")
    surface_years = list((ROOT / "data/development/nonfinancial_165f").glob("year=*/surface.parquet"))
    if len(surface_years) != 17:
        raise RuntimeError("expected 2009-2025 yearly 165f surfaces")
    sample = pq.ParquetFile(sorted(surface_years)[0])
    names = set(sample.schema_arrow.names)
    if "symbol" not in names or "amihud_illiquidity_20d_lag1" not in names:
        raise RuntimeError("165f schema drifted")
    print(json.dumps({
        "ok": True, "file_count": file_count, "products": len(manifest["products"]),
        "infrastructure_consistency": "passed", "dataset_integrity": "passed",
        "historical_reproduction": "not_evaluated", "scientific_acceptance": "not_evaluated",
        "research_permission": "not_granted_by_dataset_validation",
        "repository_visibility_verified": False, "paper_redistribution_allowed": False,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
