"""Navigation counters must not invent defects from mathematical brackets."""
from pathlib import Path

from factor_lab.governance.reaka_infrastructure_v1_4 import link_issues, markdown_links


def test_matrix_brackets_are_not_unresolved_markdown_references() -> None:
    assert markdown_links("matrix[i][j] and [0][1]") == []


def test_undefined_reference_is_plain_text_not_a_fabricated_missing_file() -> None:
    assert markdown_links("[title][undefined]") == []


def test_defined_reference_is_checked(tmp_path: Path) -> None:
    (tmp_path / "entry.md").write_text("[title][ref]\n[ref]: missing.md\n")
    result = link_issues(tmp_path, "entry.md")
    assert result == [{"source": "entry.md", "target": "missing.md", "reason": "missing_target"}]


def test_external_link_does_not_get_a_false_offline_acceptance(tmp_path: Path) -> None:
    (tmp_path / "entry.md").write_text("[external](https://example.invalid/no-verification)\n")
    assert markdown_links((tmp_path / "entry.md").read_text()) == ["https://example.invalid/no-verification"]
    assert link_issues(tmp_path, "entry.md") == []  # Deliberately unverified, not fetched.
