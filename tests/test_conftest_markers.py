"""Tests for root conftest.py: --live and --slow marker registration and auto-skip."""

import tomllib
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Marker registration (pyproject.toml)
# ---------------------------------------------------------------------------


def _load_markers() -> list[str]:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    markers: list[str] = (
        data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", [])
    )
    return markers


def test_live_marker_registered() -> None:
    markers = _load_markers()
    assert any(m.startswith("live:") for m in markers), (
        "'live' marker not found in [tool.pytest.ini_options].markers"
    )


def test_slow_marker_registered() -> None:
    markers = _load_markers()
    assert any(m.startswith("slow:") for m in markers), (
        "'slow' marker not found in [tool.pytest.ini_options].markers"
    )
