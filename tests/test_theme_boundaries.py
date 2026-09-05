from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from factor_lab.governance.reaka_foundation_contract import CURRENT_MANIFEST, CLOSED_ACTIONS, validate_foundation

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
    current = json.loads((ROOT / CURRENT_MANIFEST).read_text())
    assert all(current["research_actions"][action] is False for action in CLOSED_ACTIONS)
    assert current["user_financial_receipt_signed"] is False
    assert validate_foundation(ROOT)["infrastructure_consistency"] == "passed"


def test_no_2026_qfq_year() -> None:
    years = sorted(path.name for path in (ROOT / "data/development/cn_a_qfq_daily").glob("year=*") if path.is_dir())
    assert "year=2026" not in years
    assert "year=2007" in years
    assert "year=2023" in years
    assert "year=2024" in years
    assert "year=2025" in years
    for year in ("2023", "2024"):
        names = sorted(path.name for path in (ROOT / "data/development/cn_a_qfq_daily" / f"year={year}").glob("*.parquet"))
        assert names == [f"{m:02d}.parquet" for m in range(1, 13)]


def test_historical_stage4_review_is_unsigned() -> None:
    summary = pd.read_csv(
        ROOT / "output/factor-rotation/reaka_v2_stage4_observable_factor_pairing_v1_2011_2025/formal/hypothesis_summary.csv"
    )
    assert set(summary["financial_verdict"]) == {"waiting_user_review"}
