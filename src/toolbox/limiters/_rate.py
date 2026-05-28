from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class RateLimit:
    calls: int
    seconds: int

    def __post__init__(self) -> None:
        assert self.calls > 0
        assert self.seconds > 0


_UNIT_SECONDS = {
    "sec": 1,
    "min": 60,
    "hour": 3_600,
    "day": 86_400,
    "week": 604_800,
    "month": 2_592_000,
}

Unit = Literal["sec", "min", "hour", "day", "week", "month"]


def rate_limit(calls: int, *, per: Unit = "sec", every: int = 1) -> RateLimit:
    return RateLimit(calls, _UNIT_SECONDS[per] * every)
