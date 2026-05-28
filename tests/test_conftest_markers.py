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


# ---------------------------------------------------------------------------
# Auto-skip behaviour (pytester)
# ---------------------------------------------------------------------------

pytest_plugins = ["pytester"]


def test_live_tests_skipped_without_flag(pytester: pytest.Pytester) -> None:
    """A @pytest.mark.live test is skipped when --live is NOT passed."""
    pytester.makepyprojecttoml(
        """
        [tool.pytest.ini_options]
        markers = [
            "live: real network / browser; opt-in via --live",
            "slow: takes >1s wall-clock; skipped without --slow",
        ]
        """
    )
    pytester.makeconftest(
        """
        import pytest

        def pytest_addoption(parser: pytest.Parser) -> None:
            parser.addoption("--live", action="store_true", default=False)
            parser.addoption("--slow", action="store_true", default=False)

        def pytest_collection_modifyitems(
            config: pytest.Config,
            items: list[pytest.Item],
        ) -> None:
            if not config.getoption("--live"):
                skip = pytest.mark.skip(reason="pass --live to run")
                for item in items:
                    if item.get_closest_marker("live"):
                        item.add_marker(skip)
            if not config.getoption("--slow"):
                skip = pytest.mark.skip(reason="pass --slow to run")
                for item in items:
                    if item.get_closest_marker("slow"):
                        item.add_marker(skip)
        """
    )
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.live
        def test_live_example():
            pass
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(skipped=1)


def test_live_tests_run_with_flag(pytester: pytest.Pytester) -> None:
    """A @pytest.mark.live test runs when --live IS passed."""
    pytester.makepyprojecttoml(
        """
        [tool.pytest.ini_options]
        markers = [
            "live: real network / browser; opt-in via --live",
            "slow: takes >1s wall-clock; skipped without --slow",
        ]
        """
    )
    pytester.makeconftest(
        """
        import pytest

        def pytest_addoption(parser: pytest.Parser) -> None:
            parser.addoption("--live", action="store_true", default=False)
            parser.addoption("--slow", action="store_true", default=False)

        def pytest_collection_modifyitems(
            config: pytest.Config,
            items: list[pytest.Item],
        ) -> None:
            if not config.getoption("--live"):
                skip = pytest.mark.skip(reason="pass --live to run")
                for item in items:
                    if item.get_closest_marker("live"):
                        item.add_marker(skip)
            if not config.getoption("--slow"):
                skip = pytest.mark.skip(reason="pass --slow to run")
                for item in items:
                    if item.get_closest_marker("slow"):
                        item.add_marker(skip)
        """
    )
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.live
        def test_live_example():
            pass
        """
    )
    result = pytester.runpytest("--live")
    result.assert_outcomes(passed=1)


def test_slow_tests_skipped_without_flag(pytester: pytest.Pytester) -> None:
    """A @pytest.mark.slow test is skipped when --slow is NOT passed."""
    pytester.makepyprojecttoml(
        """
        [tool.pytest.ini_options]
        markers = [
            "live: real network / browser; opt-in via --live",
            "slow: takes >1s wall-clock; skipped without --slow",
        ]
        """
    )
    pytester.makeconftest(
        """
        import pytest

        def pytest_addoption(parser: pytest.Parser) -> None:
            parser.addoption("--live", action="store_true", default=False)
            parser.addoption("--slow", action="store_true", default=False)

        def pytest_collection_modifyitems(
            config: pytest.Config,
            items: list[pytest.Item],
        ) -> None:
            if not config.getoption("--live"):
                skip = pytest.mark.skip(reason="pass --live to run")
                for item in items:
                    if item.get_closest_marker("live"):
                        item.add_marker(skip)
            if not config.getoption("--slow"):
                skip = pytest.mark.skip(reason="pass --slow to run")
                for item in items:
                    if item.get_closest_marker("slow"):
                        item.add_marker(skip)
        """
    )
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.slow
        def test_slow_example():
            pass
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(skipped=1)


def test_slow_tests_run_with_flag(pytester: pytest.Pytester) -> None:
    """A @pytest.mark.slow test runs when --slow IS passed."""
    pytester.makepyprojecttoml(
        """
        [tool.pytest.ini_options]
        markers = [
            "live: real network / browser; opt-in via --live",
            "slow: takes >1s wall-clock; skipped without --slow",
        ]
        """
    )
    pytester.makeconftest(
        """
        import pytest

        def pytest_addoption(parser: pytest.Parser) -> None:
            parser.addoption("--live", action="store_true", default=False)
            parser.addoption("--slow", action="store_true", default=False)

        def pytest_collection_modifyitems(
            config: pytest.Config,
            items: list[pytest.Item],
        ) -> None:
            if not config.getoption("--live"):
                skip = pytest.mark.skip(reason="pass --live to run")
                for item in items:
                    if item.get_closest_marker("live"):
                        item.add_marker(skip)
            if not config.getoption("--slow"):
                skip = pytest.mark.skip(reason="pass --slow to run")
                for item in items:
                    if item.get_closest_marker("slow"):
                        item.add_marker(skip)
        """
    )
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.slow
        def test_slow_example():
            pass
        """
    )
    result = pytester.runpytest("--slow")
    result.assert_outcomes(passed=1)
