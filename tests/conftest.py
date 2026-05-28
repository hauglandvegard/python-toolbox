"""Root pytest configuration: CLI flags and auto-skip for opt-in markers."""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register --live and --slow command-line options."""
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run tests marked with @pytest.mark.live (real network / browser).",
    )
    parser.addoption(
        "--slow",
        action="store_true",
        default=False,
        help="Run tests marked with @pytest.mark.slow (takes >1 s wall-clock).",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Auto-skip live and slow tests unless the corresponding flag is passed."""
    if not config.getoption("--live"):
        skip_live = pytest.mark.skip(reason="pass --live to run")
        for item in items:
            if item.get_closest_marker("live"):
                item.add_marker(skip_live)

    if not config.getoption("--slow"):
        skip_slow = pytest.mark.skip(reason="pass --slow to run")
        for item in items:
            if item.get_closest_marker("slow"):
                item.add_marker(skip_slow)
