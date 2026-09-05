from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_paper_is_present_and_private_only() -> None:
    paper = ROOT / "research_materials/liao_residual_enhanced_adaptive_koopman_stock_prediction_2026.pdf"
    notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
    scope = json.loads((ROOT / "docs/governance/package_scope.json").read_text())
    assert paper.is_file()
    assert "IEEE" in notice
    assert scope["paper_redistribution_allowed"] is False
    assert scope["private_repository_required"] is True


def test_current_authority_remains_closed() -> None:
    current = json.loads((ROOT / "docs/ops/reaka_multifactor_current_manifest@1.2.json").read_text())
    assert current["stage5_execution_allowed"] is False
    assert current["model_training_allowed"] is False
    assert current["production_authority"] is False
    assert current["semantic_invariants"]["user_supplies_operator_count"] is False


def test_no_2026_qfq_year() -> None:
    years = sorted(path.parent.name for path in (ROOT / "data/development/cn_a_qfq_daily").glob("year=*/bars.parquet"))
    assert "year=2026" not in years
    assert "year=2007" in years
    assert "year=2025" in years


def test_stage4_review_is_unsigned() -> None:
    summary = pd.read_csv(
        ROOT / "output/factor-rotation/reaka_v2_stage4_observable_factor_pairing_v1_2011_2025/formal/hypothesis_summary.csv"
    )
    assert set(summary["financial_verdict"]) == {"waiting_user_review"}
