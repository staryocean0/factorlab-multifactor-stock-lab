from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from factor_lab.governance.reaka_infrastructure_v1_4 import validate_infrastructure

ROOT = Path(__file__).resolve().parents[1]


def test_paper_license_declaration_is_not_repository_visibility_proof() -> None:
    paper = ROOT / "research_materials/liao_residual_enhanced_adaptive_koopman_stock_prediction_2026.pdf"
    notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
    scope = json.loads((ROOT / "docs/governance/package_scope.json").read_text())
    assert paper.is_file()
    assert "IEEE" in notice
    assert scope["paper_redistribution_allowed"] is False
    # The original private_repository_required declaration is a requirement,
    # not proof of the repository's actual current visibility.
    assert scope["private_repository_required"] is True


def test_infrastructure_does_not_grant_research_or_production_authority() -> None:
    report = validate_infrastructure(ROOT)
    assert report["infrastructure_consistency"] == "passed", report["errors"]
    assert report["production_authority"] is False
    assert report["research_permission"] == "not_granted_by_infrastructure_validation"


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
    summary = pd.read_csv(ROOT / "output/factor-rotation/reaka_v2_stage4_observable_factor_pairing_v1_2011_2025/formal/hypothesis_summary.csv")
    assert set(summary["financial_verdict"]) == {"waiting_user_review"}
