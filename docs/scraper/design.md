# `toolbox.fetcher` — Design

Status: approved 2026-05-27
Scope: v1 (with v2 backlog explicitly marked)
Branch: `fetcher`

---

## 1. Problem statement

`toolbox.fetcher` is a fetch-only subpackage of `python-toolbox` providing two async, swappable backends behind a single `Fetcher` Protocol:

- **Primary** — `curl_cffi` + `asyncio`. Lightweight. Browser TLS/HTTP-2 fingerprint impersonation to slip past Cloudflare-class passive fingerprint blocks.
- **Heavy fallback** — `playwright` + `playwright-stealth`. For sites requiring real JS execution or stronger anti-detection.

Both expose the same `.fetch()` signature. Call sites switch backends by construction line only. Composable via `FallbackFetcher(primary, fallback)` — itself a `Fetcher` — so callers write `await fetcher.fetch(url)` everywhere; fallback logic lives in one place.

### Four pains solved

1. Fingerprint-blocked sites → `curl_cffi` impersonation.
2. JS-rendered / anti-bot sites → Playwright fallback.
3. Per-host rate-limit code duplicated across projects → `rate_limit.py` with pluggable, composable strategies parametrized in calls per sec/min/hour/day/week/month, injected into fetcher by caller.
4. Inconsistent error semantics across HTTP and browser stacks → unified `FetcherError` hierarchy.

### Strict scope: fetch only

URL in → response out. No parsing, no link extraction, no pagination, no job queues, no response caching. Caller's job.

### In scope (v1)

- Two backends + `FallbackFetcher` composition.
- `rate_limit.py` strategies (budgets + human-behavior simulation).
- Unified exception hierarchy.
- Opt-in `robots.txt` enforcement (off by default; stdlib `urllib.robotparser`; refuses disallowed paths with `RobotsBlockedError`).
- `PlaywrightFetcher.fetch_with_actions` for must-drive-browser content loading.

### Out / deferred

- HTML parsing — out.
- Distributed scraping / job queues — out (caller's responsibility).
- Response caching — out (caller's responsibility).
- CAPTCHA solving — out (brittle, expensive arms race).
- Proxy rotation — deferred to v2 (`proxy: str | None` placeholder accepted in v1; v2 swaps to pool).
- `toolbox.pagination` — deferred to v2 as separate subpackage. Will compose against any `Fetcher`.
- Out-of-process shared rate-limit state — deferred to v2 (single-process asyncio only in v1).

### Audience

Author's downstream apps only. No third-party API stability promises; opinionated defaults welcome.

### v1 quality bar

Python 3.14+, strict mypy, no `Any` in public API.

---

## 2. Module layout + public API surface

### Directory structure

```
src/toolbox/fetcher/
    __init__.py          # re-exports public API
    _protocol.py         # Fetcher Protocol, Response dataclass
    _curl.py             # CurlFetcher
    _playwright.py       # PlaywrightFetcher, BrowserAction types
    _fallback.py         # FallbackFetcher
    _robots.py           # RobotsChecker (opt-in)
    _exceptions.py       # FetcherError hierarchy
    rate_limit.py        # public — strategies injected by caller
```

`rate_limit.py` lives **inside** the fetcher subpackage (decided 2.1b). Symmetric promotion to top-level `toolbox.rate_limit` is a future refactor if another subpackage needs the same primitive.

Internal modules use underscore prefix (`_curl.py`, etc.); `rate_limit.py` is public (no underscore).

### `Fetcher` Protocol

```python
# _protocol.py
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

@runtime_checkable
class Fetcher(Protocol):
    async def fetch(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> "Response": ...

    async def close(self) -> None: ...

    async def __aenter__(self) -> "Fetcher": ...
    async def __aexit__(self, *args: object) -> None: ...
```

### `Response`

```python
# _protocol.py
from dataclasses import dataclass
from collections.abc import Mapping

@dataclass(frozen=True, slots=True)
class Response:
    url: str                       # final URL after redirects
    status_code: int
    headers: Mapping[str, str]     # case-insensitive view (impl detail)
    body: bytes
    elapsed: float                 # seconds, wall-clock
    backend: str                   # "curl" | "playwright" — for debug/logging

    @property
    def text(self) -> str:
        """Decoded using charset from Content-Type; fallback utf-8."""

    def json(self) -> object:
        """json.loads(self.body)."""
```

### Public re-exports

```python
# fetcher/__init__.py
from ._protocol import Fetcher, Response
from ._curl import CurlFetcher
from ._playwright import (
    PlaywrightFetcher,
    BrowserAction, Scroll, ScrollLoop, ClickSelector, WaitForSelector, Sleep,
)
from ._fallback import FallbackFetcher
from ._exceptions import (
    FetcherError, NetworkError, FetchTimeoutError, HTTPStatusError,
    BlockedError, RobotsBlockedError, BrowserError, RateLimitError,
)

__all__ = [
    "Fetcher", "Response",
    "CurlFetcher", "PlaywrightFetcher", "FallbackFetcher",
    "BrowserAction", "Scroll", "ScrollLoop", "ClickSelector", "WaitForSelector", "Sleep",
    "FetcherError", "NetworkError", "FetchTimeoutError", "HTTPStatusError",
    "BlockedError", "RobotsBlockedError", "BrowserError", "RateLimitError",
]
```

No re-export at `toolbox` root — caller imports from `toolbox.fetcher` (decision 9.6a).

---

## 3. `rate_limit.py` — strategies + composition

### Protocol

```python
class RateLimitStrategy(Protocol):
    async def acquire(self, *, max_wait: float | None = None) -> None:
        """Block until next call is permitted. If max_wait elapses, raise RateLimitError."""
```

### Algorithm: sliding window

Internal `_SlidingWindow` class. Tracks call timestamps in a `deque`, evicts entries older than the window, blocks if window is full until oldest entry expires.

```python
class _SlidingWindow:
    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self._max = max_calls
        self._window = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self, *, max_wait: float | None = None) -> None:
        deadline = time.monotonic() + max_wait if max_wait is not None else None
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._timestamps and self._timestamps[0] <= now - self._window:
                    self._timestamps.popleft()
                if len(self._timestamps) < self._max:
                    self._timestamps.append(now)
                    return
                wait = self._timestamps[0] + self._window - now
                if deadline is not None and now + wait > deadline:
                    raise RateLimitError(
                        f"rate-limit wait exceeded max_wait={max_wait}s",
                        waited_seconds=now - (deadline - max_wait),
                    )
                await asyncio.sleep(max(wait, 0))
```

Public factories (no exposed `_SlidingWindow` constructor):

```python
def PerSecond(n: int) -> RateLimitStrategy: return _SlidingWindow(n, 1.0)
def PerMinute(n: int) -> RateLimitStrategy: return _SlidingWindow(n, 60.0)
def PerHour(n: int)   -> RateLimitStrategy: return _SlidingWindow(n, 3600.0)
def PerDay(n: int)    -> RateLimitStrategy: return _SlidingWindow(n, 86_400.0)
def PerWeek(n: int)   -> RateLimitStrategy: return _SlidingWindow(n, 604_800.0)
def PerMonth(n: int)  -> RateLimitStrategy: return _SlidingWindow(n, 2_592_000.0)  # rolling 30d
```

### Composition

```python
class Compose:
    def __init__(self, *strategies: RateLimitStrategy) -> None:
        self._strategies = strategies

    async def acquire(self, *, max_wait: float | None = None) -> None:
        for s in self._strategies:
            await s.acquire(max_wait=max_wait)
```

Sequential `acquire` — each must be satisfied.

### Human-behavior strategies

All implement `RateLimitStrategy`. All composable under `Compose`.

```python
class Jitter:
    """Sleeps random delay every call. Per-call independent randomness — never shared semantics."""
    def __init__(self, min_seconds: float = 0.0, max_seconds: float = 0.5) -> None: ...

class Distraction:
    """With probability p, pauses min..max seconds. Per-call independent randomness."""
    def __init__(self, probability: float = 0.05,
                 min_seconds: float = 60, max_seconds: float = 120) -> None: ...

class CoffeeBreak:
    """Every random interval, pause min..max seconds. asyncio.Lock-serialized for shared-instance semantics."""
    def __init__(self, every_min_s: float = 1800, every_max_s: float = 3600,
                 duration_min_s: float = 240, duration_max_s: float = 360) -> None: ...

class AwakeHours:
    """Wall-clock gate. Pauses while outside awake window. Lock-serialized to dedupe log spam."""
    def __init__(self, start: dt.time = dt.time(7, 0), end: dt.time = dt.time(23, 0),
                 tz: dt.tzinfo | None = None) -> None: ...
```

`CoffeeBreak` and `AwakeHours` use `asyncio.Lock` so concurrent callers sharing the same instance experience one synchronized break / one log line per gate trigger. `Jitter` and `Distraction` do NOT lock — they're per-call independent.

### Convenience helper

```python
def human_profile(
    per_second: int = 2,
    per_hour: int = 500,
    with_coffee: bool = True,
    with_sleep: bool = True,
    tz: dt.tzinfo | None = None,
) -> RateLimitStrategy:
    parts: list[RateLimitStrategy] = [PerSecond(per_second), PerHour(per_hour), Jitter(0.1, 1.0)]
    if with_coffee: parts.append(CoffeeBreak())
    if with_sleep:  parts.append(AwakeHours(tz=tz))
    return Compose(*parts)
```

### Sharing model (no library magic)

Caller shares state by passing the same strategy instance to multiple fetchers. Instance identity = shared state. Example:

```python
# downstream/fetching_setup.py
SHARED_COFFEE = CoffeeBreak()
SHARED_AWAKE  = AwakeHours(start=dt.time(7), end=dt.time(23))

def site_profile(*, per_sec: int, per_hour: int) -> RateLimitStrategy:
    return Compose(
        PerSecond(per_sec), PerHour(per_hour),        # per-site
        Jitter(0.1, 1.2), Distraction(probability=0.05),
        SHARED_COFFEE, SHARED_AWAKE,                  # shared across sites
    )

site_a = CurlFetcher(rate_limit=site_profile(per_sec=2, per_hour=500))
site_b = CurlFetcher(rate_limit=site_profile(per_sec=1, per_hour=200))
site_c = PlaywrightFetcher(rate_limit=site_profile(per_sec=1, per_hour=100))
```

Result: per-site budgets and jitter; shared coffee schedule; shared awake hours.

### Properties

| | Behavior |
|---|---|
| Algorithm | sliding window |
| Burst tolerance | none — strict N-per-window |
| Cancellation-safe | timestamps appended only on grant |
| Concurrent acquires | asyncio.Lock-serialized per instance |
| Persistence | in-memory only; process restart resets |
| Per-host | caller composes manually; library helper deferred |
| `PerMonth` | rolling 30 days, not calendar month |
| Imports | stdlib only |

---

## 4. Backend details

### `CurlFetcher`

```python
class CurlFetcher:
    def __init__(
        self,
        *,
        rate_limit: RateLimitStrategy | None = None,
        impersonate: str = "chrome124",
        timeout: float = 30.0,
        follow_redirects: bool = True,
        max_redirects: int = 10,
        verify_tls: bool = True,
        proxy: str | None = None,                # v2 placeholder (single proxy URL)
        respect_robots: bool = False,
        robots_user_agent: str | None = None,
        user_agent: str | None = None,           # overrides impersonate UA if set
        raise_for_status: bool = True,
        max_concurrent: int | None = None,       # opt-in semaphore
    ) -> None: ...
```

Notes:
- One persistent `curl_cffi.requests.AsyncSession` per instance — cookies + connection pool reused.
- Default `impersonate="chrome124"`; default UA inherited from impersonation (no override).
- Built-in block heuristics on response → raise `BlockedError`.
- `raise_for_status=True` by default; non-2xx without block-match → `HTTPStatusError`.
- `max_concurrent`: if set, internal `asyncio.Semaphore` caps in-flight requests.
- `.close()` closes session. Async context manager covers init + close.

### `PlaywrightFetcher`

```python
class PlaywrightFetcher:
    def __init__(
        self,
        *,
        rate_limit: RateLimitStrategy | None = None,
        browser: Literal["chromium", "firefox", "webkit"] = "chromium",
        headless: bool = True,
        stealth: bool = True,
        timeout: float = 60.0,
        viewport: tuple[int, int] = (1280, 800),
        user_agent: str | None = None,
        locale: str = "en-US",
        proxy: str | None = None,
        respect_robots: bool = False,
        robots_user_agent: str | None = None,
        raise_for_status: bool = True,
    ) -> None: ...

    async def fetch(self, url, *, headers=None, timeout=None) -> Response: ...

    async def fetch_with_actions(
        self,
        url: str,
        actions: Sequence[BrowserAction],
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response: ...
```

Lifecycle:
- One `Browser` per `PlaywrightFetcher` instance, reused across fetches.
- Fresh `BrowserContext` per fetch — clean cookies, fresh fingerprint.
- `playwright-stealth` applied to each context when `stealth=True`.
- `fetch_with_actions` runs actions sequentially on a `Page`, returns final DOM snapshot as `Response`.

### `BrowserAction` types

```python
class BrowserAction(Protocol):
    async def apply(self, page: "playwright.async_api.Page") -> None: ...

@dataclass(frozen=True, slots=True)
class Scroll:
    to_bottom: bool = True
    wait_after_ms: int = 500

@dataclass(frozen=True, slots=True)
class ScrollLoop:
    max_iterations: int = 20
    stop_when_selector_stable: str | None = None
    wait_after_ms: int = 800

@dataclass(frozen=True, slots=True)
class ClickSelector:
    selector: str
    times: int = 1
    wait_after_ms: int = 500

@dataclass(frozen=True, slots=True)
class WaitForSelector:
    selector: str
    timeout_ms: int = 10_000

@dataclass(frozen=True, slots=True)
class Sleep:
    seconds: float
```

`fetch_with_actions` is **NOT** part of the `Fetcher` Protocol — callers using it accept they're bound to `PlaywrightFetcher` and lose backend swap-ability for that call.

### `FallbackFetcher`

```python
class FallbackFetcher:
    def __init__(
        self,
        primary: Fetcher,
        fallback: Fetcher,
        *,
        rate_limit: RateLimitStrategy | None = None,
        should_fallback: Callable[[Exception], bool] = is_blocked_or_throttled,
    ) -> None: ...
```

Default trigger predicate:

```python
def is_blocked_or_throttled(e: Exception) -> bool:
    return (
        isinstance(e, BlockedError)
        or (isinstance(e, HTTPStatusError) and e.status_code in {403, 429, 503})
    )
```

Rate limit on composite = single shared budget across primary + fallback.

---

## 5. Exception hierarchy

```
FetcherError                  (base)
├── NetworkError              (DNS, conn refused, reset, TLS handshake)
├── FetchTimeoutError         (also subclasses builtin TimeoutError)
├── HTTPStatusError           (non-2xx; carries Response)
├── BlockedError              (anti-bot heuristic; carries Response + reason)
├── RobotsBlockedError        (only when respect_robots=True)
├── BrowserError              (Playwright page crash, nav fail, action fail)
└── RateLimitError            (acquire(max_wait=...) exceeded)
```

### Translation rule

**Backend-specific exceptions never leak.** Every `curl_cffi.*` and `playwright.async_api.*` exception is caught in `_curl.py` / `_playwright.py` and re-raised as a `FetcherError` subclass, using `raise ... from underlying` to preserve `__cause__`.

| Underlying | Re-raised as |
|---|---|
| `curl_cffi.requests.RequestsError` (DNS, conn) | `NetworkError` |
| `curl_cffi.requests.Timeout` | `FetchTimeoutError` |
| `curl_cffi` SSL/TLS error | `NetworkError` |
| non-2xx + no block detected | `HTTPStatusError` |
| any response + block heuristic match | `BlockedError` |
| `playwright.async_api.TimeoutError` | `FetchTimeoutError` |
| `playwright.async_api.Error` (nav, crash, action) | `BrowserError` |
| robots check denial | `RobotsBlockedError` |
| `acquire(max_wait=N)` exceeded | `RateLimitError` |

### Naming notes

- `FetchTimeoutError` (not `TimeoutError`) — avoids namespace shadow. Inherits builtin `TimeoutError` so `except TimeoutError` still catches.
- `HTTPStatusError` (not `HttpError`) — matches httpx convention.
- `BlockedError` separate from `HTTPStatusError` — block can present as 200 + challenge HTML.

### `BlockedError.reason` values

| Reason | Trigger |
|---|---|
| `"cloudflare-challenge"` | CF challenge page HTML signature |
| `"waf"` | Common WAF interstitial signatures (Akamai, Imperva, etc.) |
| `"captcha-page"` | Captcha-page HTML signature |

Heuristics ship as a single internal `is_blocked_response(response) -> str | None` function. Extensible by adding signatures.

---

## 6. `robots.txt` enforcement (opt-in)

### Behavior

Opt-in via `respect_robots=True`. Default off. When on:

1. Before fetching a URL, check cached `RobotsChecker` for that host.
2. If not cached, fetch `<scheme>://<host>/robots.txt` using the **same fetcher** (same fingerprint + rate-limit budget).
3. Parse via stdlib `urllib.robotparser.RobotFileParser`.
4. If `can_fetch(user_agent, url)` is False → raise `RobotsBlockedError`.

### Class shape

```python
class RobotsChecker:
    """Per-host robots.txt cache + lookup. Library-internal."""
    def __init__(self, user_agent: str) -> None: ...
    async def allows(self, url: str, fetch_text: Callable[[str], Awaitable[str]]) -> bool: ...
    async def crawl_delay(self, url: str) -> float | None: ...
```

### Defaults

| | Value |
|---|---|
| User-Agent for matching | `"*"` (matches generic disallow rules) |
| Cache scope | per-fetcher instance |
| Cache TTL | process lifetime (no expiration in v1) |
| Fail mode (robots.txt unreachable) | **fail-open** — assume allow all, emit WARN log |
| `Crawl-delay` | exposed via `crawl_delay()`; caller plugs into rate_limit manually (no auto-application) |

### Logging

- DEBUG on cache miss.
- WARNING on robots.txt fetch failure (fail-open).
- INFO when `RobotsBlockedError` raised.

---

## 7. Logging conventions

### Per-module loggers

```
toolbox                            (NullHandler attached in root __init__)
└── toolbox.fetcher
    ├── toolbox.fetcher._curl
    ├── toolbox.fetcher._playwright
    ├── toolbox.fetcher._fallback
    ├── toolbox.fetcher._robots
    └── toolbox.fetcher.rate_limit
```

Every module: `logger = logging.getLogger(__name__)`.

### Level matrix

| Event | Level |
|---|---|
| fetch start | DEBUG |
| fetch success (status, elapsed, bytes) | DEBUG |
| fetch failure → typed `FetcherError` | INFO |
| fallback triggered | INFO |
| rate-limit wait | DEBUG |
| `RateLimitError` (max_wait exceeded) | WARNING |
| coffee break / distraction / awake-hours gate | INFO |
| robots.txt cache miss | DEBUG |
| robots.txt fetch failure (fail-open) | WARNING |
| `RobotsBlockedError` | INFO |
| Playwright browser launch | DEBUG |
| Playwright action sequence start/end | DEBUG |
| `BrowserError` | WARNING |
| `BlockedError` | INFO |

Never ERROR or CRITICAL from library code — escapes belong to caller.

### Structured fields via stdlib `extra=`

Required on every fetch-path log:
- `url`
- `backend` — `"curl"` | `"playwright"` | `"fallback"`

Per-event additions per the matrix above.

Consumable by `structlog.stdlib.ExtraAdder` in host app. Library stays stdlib-only.

### Never logged

- Full response body. Log byte length only.
- `Authorization`, `Cookie`, `Set-Cookie` headers.
- Full headers dict. Use internal `safe_headers()` allowlist:
  - `Content-Type`, `Content-Length`, `Server`, `Cache-Control`, `X-Cache`.
- Request body. Length only.

---

## 8. Testing approach

### Layout

```
tests/
    conftest.py
    fetcher/
        test_protocol.py
        test_response.py
        test_curl.py
        test_playwright.py
        test_fallback.py
        test_robots.py
        test_exceptions.py
        test_rate_limit.py
        fixtures/
            blocked/        # canned block HTML samples
        integration/
            test_curl_live.py        # @pytest.mark.live
            test_playwright_live.py  # @pytest.mark.live
    typing/
        test_protocol.py    # mypy-checked Protocol satisfaction
```

### Layers

**Layer 1 — Pure unit (default `just test`):**
- `rate_limit.py` strategies (time + random monkeypatched).
- `Response` dataclass.
- Exception classes + translation table.
- `FallbackFetcher` orchestration (with fake `Fetcher` impls).
- `RobotsChecker` parser logic (in-memory robots.txt strings).
- No network, no browser, no sleep.

**Layer 2 — Backend with stubbed transport:**
- `CurlFetcher` with `curl_cffi` session monkeypatched.
- `PlaywrightFetcher` with fake `Page` satisfying action API.

**Layer 3 — Live integration (opt-in via `--live`):**
- Local HTTP server: stdlib `http.server` in a thread (no new dev dep).
- Playwright: real chromium against the local server.
- Skipped by default.

### Time / randomness control

Monkeypatch `time.monotonic` + `asyncio.sleep` for deterministic rate-limit tests. Monkeypatch `random.uniform` / `random.random` for jitter / distraction tests.

```python
@pytest.fixture
def frozen_time(monkeypatch):
    class Clock: now: float = 0.0
    clock = Clock()
    monkeypatch.setattr("time.monotonic", lambda: clock.now)
    async def fake_sleep(s: float) -> None: clock.now += s
    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    return clock
```

### Block detection fixtures

Real-world Cloudflare / WAF / captcha HTML samples committed in `tests/fetcher/fixtures/blocked/`. Each fixture asserts `BlockedError(reason=...)` with the expected slug.

### `FakeFetcher` for `FallbackFetcher` tests

```python
class FakeFetcher:
    def __init__(self, *, raises: Exception | None = None, response: Response | None = None) -> None: ...
    async def fetch(self, url, *, headers=None, timeout=None) -> Response: ...
    async def close(self) -> None: ...
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
```

Covers: primary blocks → fallback runs; primary NetworkError → propagates; both fail → fallback error propagates; custom predicate honored.

### Markers

```toml
[tool.pytest.ini_options]
markers = [
    "live: real network / browser; opt-in via --live",
    "slow: takes >1s wall-clock; skipped without --slow",
]
```

`conftest.py` adds both flags and auto-skips when not passed.

### Coverage

`pytest-cov` already in dev deps. Separate `just coverage` recipe (keeps default `just test` fast):

```
coverage:
    uv run pytest --cov=toolbox.fetcher --cov-report=term-missing
```

### Protocol-satisfaction type test

`tests/typing/test_protocol.py` contains assertions like:

```python
from toolbox.fetcher import Fetcher, CurlFetcher, PlaywrightFetcher, FallbackFetcher

def _proves_protocol_satisfaction() -> None:
    _curl: Fetcher = CurlFetcher()
    _pw:   Fetcher = PlaywrightFetcher()
    _fb:   Fetcher = FallbackFetcher(primary=CurlFetcher(), fallback=PlaywrightFetcher())
```

Strict mypy fails on any Protocol mismatch.

---

## 9. Dependencies + deferred items

### Runtime deps (v1)

```toml
[project]
dependencies = [
    "curl_cffi>=0.15",
]

[project.optional-dependencies]
browser = [
    "playwright>=1.60",
    "playwright-stealth",
]
dev = [
    "python-toolbox[browser]",
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "ruff>=0.6",
    "mypy>=1.10",
]
```

Core install (`pip install python-toolbox`) brings `curl_cffi` only — saves install size for callers who only need the primary backend. Browser support is opt-in via `pip install python-toolbox[browser]`. Dev install includes `[browser]` so the full test suite runs.

### Deferred to v2 (explicit backlog)

| Feature | Reason | Constraint on v1 |
|---|---|---|
| `toolbox.pagination` | Independent module; design after fetcher API stabilizes | Response must support body-cursor extraction by callers |
| Proxy rotation | Operational complexity (sourcing, session affinity, per-context proxies) | `proxy: str \| None` placeholder accepted in v1 |
| Out-of-process shared rate-limit state | Needs backing store (Redis / file lock) | All v1 state is in-memory + asyncio-only |
| CAPTCHA solver hook | Not needed yet | Out of scope entirely |
| Auto-application of `Crawl-delay` | Caller decides via `crawl_delay()` lookup | Public method available |
| Response cache | Caller-owned | Response is frozen — safe to memoize externally |
| Per-host built-in rate-limit helper | Caller composes manually | No constraint |
| `PlaywrightFetcher` persistent storage state (login flows) | YAGNI | Add `storage_state_path: Path \| None` later |
| Top-level `toolbox.rate_limit` (promotion from subpackage) | Only relevant once another subpackage needs it | Refactor when triggered |

### Defaults log (single-source-of-truth)

| | Value |
|---|---|
| `curl_cffi` impersonate | `chrome124` |
| `CurlFetcher.timeout` | `30.0s` |
| `CurlFetcher.follow_redirects` | `True` |
| `CurlFetcher.max_redirects` | `10` |
| `CurlFetcher.raise_for_status` | `True` |
| `CurlFetcher.max_concurrent` | `None` (unlimited) |
| `PlaywrightFetcher.browser` | `"chromium"` |
| `PlaywrightFetcher.headless` | `True` |
| `PlaywrightFetcher.stealth` | `True` |
| `PlaywrightFetcher.timeout` | `60.0s` |
| `PlaywrightFetcher.viewport` | `(1280, 800)` |
| `PlaywrightFetcher.locale` | `"en-US"` |
| `PlaywrightFetcher` context lifetime | fresh per fetch |
| `PlaywrightFetcher` browser lifetime | per instance, reused |
| `FallbackFetcher.should_fallback` | `is_blocked_or_throttled` (BlockedError or HTTP 403/429/503) |
| `RobotsChecker` user-agent | `"*"` |
| `RobotsChecker` fail-mode | fail-open + WARN log |
| `RobotsChecker` cache TTL | process lifetime |
| `PerMonth` window | rolling 30 days |
| `RateLimit.acquire` `max_wait` | `None` (wait forever) |
| `Jitter` default | `(0.0, 0.5)` seconds |
| `Distraction` default | probability `0.05`, pause `60..120s` |
| `CoffeeBreak` default | every `1800..3600s`, duration `240..360s` |
| `AwakeHours` default | `07:00 – 23:00` |
| Logging — fetch success | DEBUG |
| Logging — fetch failure (typed) | INFO |
| Logging — fallback trigger | INFO |
| Logging — rate-limit wait | DEBUG |
| Logging — coffee / distraction / awake | INFO |

---

## 10. Housekeeping (post-rename)

- `docs/scraper/diagram.md` is a stale placeholder from the previous `scraper` naming. Either delete or repurpose under `docs/fetcher/`.
- Commit history references "scraper module" — left as-is; renaming history not worth it.
