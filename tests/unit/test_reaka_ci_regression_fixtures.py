"""Sparse CI retains real small counterexamples without downloading the lake."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ci_keeps_the_three_existing_small_regression_fixtures() -> None:
    workflow = (ROOT / '.github/workflows/ci.yml').read_text()
    foundation = workflow.split('  dataset-integrity:', 1)[0]
    for name in ('state_learnability_certificate.json', 'state_months.csv', 'monthly_selector_panel.csv'):
        assert name in foundation
    assert "['git', 'show', 'HEAD:' + relative]" in foundation
    assert 'regression_fixtures.json' in foundation
    assert 'git sparse-checkout disable' not in foundation


def test_research_state_gives_directions_not_a_mandatory_stage_sequence() -> None:
    import json
    state = json.loads((ROOT / 'docs/ops/research_state.json').read_text())
    directions = state['research_directions_not_a_mandatory_sequence']
    assert directions
    assert all(set(item) == {'question', 'independent_prework', 'empirical_dependency'} for item in directions)
    assert state['production_authority'] is False
