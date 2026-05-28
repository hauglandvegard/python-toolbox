from typing import get_args

import pytest

from toolbox.limiters._rate import _UNIT_SECONDS, Unit, rate_limit

# ---------------------------------------------------------------------------
# _UNIT_SECONDS table test
# ---------------------------------------------------------------------------

SEC = 1
MIN = 60
HOUR = MIN * 60
DAY = HOUR * 24
WEEK = DAY * 7
MONTH = DAY * 30


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        ("sec", SEC),
        ("min", MIN),
        ("hour", HOUR),
        ("day", DAY),
        ("week", WEEK),
        ("month", MONTH),
    ],
)
def test_unit_seconds(unit: Unit, expected: int) -> None:
    assert _UNIT_SECONDS[unit] == expected


def test_unit_literal_matches_table() -> None:
    """Literal `Unit` and `_UNIT_SECONDS` must stay in sync."""
    assert set(get_args(Unit)) == set(_UNIT_SECONDS)


# ---------------------------------------------------------------------------
# RateLimit dataclass invariants
# ---------------------------------------------------------------------------


def test_ratelimit_is_frozen() -> None:
    rl = rate_limit(10)
    with pytest.raises(AttributeError):
        rl.calls = 999  # type: ignore[misc]


def test_ratelimit_equality() -> None:
    assert rate_limit(10, per="min") == rate_limit(10, per="min")
    assert rate_limit(10, per="min") != rate_limit(10, per="sec")


def test_ratelimit_hashable() -> None:
    {rate_limit(10), rate_limit(10, per="min")}  # no raise


# ---------------------------------------------------------------------------
# Robustness (decide policy)
# ---------------------------------------------------------------------------


def test_invalid_unit_raises_at_runtime() -> None:
    with pytest.raises(KeyError):
        rate_limit(10, per="century")  # type: ignore[arg-type]


@pytest.mark.parametrize("calls", [-1, 0])
def test_non_positive_calls(calls: int) -> None:
    """Document current behavior: no validation. If you add __post_init__,
    flip this to `with pytest.raises(ValueError):`."""
    rl = rate_limit(calls)
    assert rl.calls == calls
