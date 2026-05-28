"""Tests for justfile recipe presence and correctness."""

from pathlib import Path

JUSTFILE = Path(__file__).resolve().parents[1] / "justfile"


def test_coverage_recipe_present() -> None:
    content = JUSTFILE.read_text()
    lines = content.splitlines()
    recipe_line_found = any(line.strip() == "coverage:" for line in lines)
    assert recipe_line_found, "justfile must contain a 'coverage:' recipe line"
    assert "pytest --cov=toolbox --cov-report=term-missing" in content, (
        "coverage recipe must invoke pytest --cov=toolbox --cov-report=term-missing"
    )
