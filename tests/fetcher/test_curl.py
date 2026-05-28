"""Tests for CurlFetcher against a fake AsyncSession."""

import logging
from collections.abc import Sequence

import pytest

from tests.fetcher._fakes import FakeAsyncSession, FakeCurlResponse
from toolbox.fetcher import CurlFetcher, Response
from toolbox.limiters import rate_limit

_HTTP_OK = 200
_INSTANCE_TIMEOUT = 42.0
_PER_CALL_TIMEOUT = 5.0


@pytest.fixture
def fake_session(monkeypatch: pytest.MonkeyPatch) -> FakeAsyncSession:
    s = FakeAsyncSession()
    monkeypatch.setattr(
        "toolbox.fetcher._curl.requests.AsyncSession",
        lambda **_: s,
    )
    return s


# ── init ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("timeout", [0, -1, -0.5])
def test_init_rejects_non_positive_timeout(timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout must be positive"):
        CurlFetcher(timeout=timeout)


def test_init_copies_limiters_list() -> None:
    limiters = [rate_limit(10)]
    f = CurlFetcher(limiters=limiters)
    limiters.clear()
    assert len(list(f.limiters)) == 1


def test_limiters_property_returns_sequence() -> None:
    f = CurlFetcher()
    assert isinstance(f.limiters, Sequence)
    assert len(f.limiters) == 0


# ── lifecycle ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aenter_creates_session(fake_session: FakeAsyncSession) -> None:
    f = CurlFetcher()
    assert f._session is None
    async with f:
        assert f._session is fake_session


@pytest.mark.asyncio
async def test_aexit_closes_and_resets(fake_session: FakeAsyncSession) -> None:
    f = CurlFetcher()
    async with f:
        pass
    assert fake_session.closed is True
    assert f._session is None


@pytest.mark.asyncio
async def test_reentry_works_after_close(fake_session: FakeAsyncSession) -> None:
    f = CurlFetcher()
    async with f:
        pass
    async with f:
        assert f._session is fake_session  # type: ignore[comparison-overlap]


# ── fetch ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_without_aenter_raises() -> None:
    f = CurlFetcher()
    with pytest.raises(RuntimeError, match="async context manager"):
        await f.fetch("https://example.com")


@pytest.mark.asyncio
async def test_fetch_returns_response_dataclass(fake_session: FakeAsyncSession) -> None:
    fake_session.response = FakeCurlResponse(
        url="https://example.com/final",
        status_code=_HTTP_OK,
        headers={"content-type": "text/html"},
        content=b"<html></html>",
    )
    async with CurlFetcher() as f:
        result = await f.fetch("https://example.com")
    assert isinstance(result, Response)
    assert result.url == "https://example.com/final"
    assert result.status_code == _HTTP_OK
    assert result.headers == {"content-type": "text/html"}
    assert result.content == b"<html></html>"


@pytest.mark.asyncio
async def test_fetch_passes_headers_as_dict(fake_session: FakeAsyncSession) -> None:
    async with CurlFetcher() as f:
        await f.fetch("https://example.com", headers={"X-Foo": "bar"})
    assert fake_session.requests[0]["headers"] == {"X-Foo": "bar"}


@pytest.mark.asyncio
async def test_fetch_uses_instance_timeout(fake_session: FakeAsyncSession) -> None:
    async with CurlFetcher(timeout=_INSTANCE_TIMEOUT) as f:
        await f.fetch("https://example.com")
    assert fake_session.requests[0]["timeout"] == _INSTANCE_TIMEOUT


@pytest.mark.asyncio
async def test_fetch_per_call_timeout_overrides_instance(
    fake_session: FakeAsyncSession,
) -> None:
    async with CurlFetcher(timeout=_INSTANCE_TIMEOUT) as f:
        await f.fetch("https://example.com", timeout=_PER_CALL_TIMEOUT)
    assert fake_session.requests[0]["timeout"] == _PER_CALL_TIMEOUT


@pytest.mark.asyncio
async def test_fetch_logs_debug_start(
    fake_session: FakeAsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="toolbox.fetcher._curl")
    async with CurlFetcher() as f:
        await f.fetch("https://example.com")
    matches = [r for r in caplog.records if r.message == "fetch start"]
    assert len(matches) == 1
    assert getattr(matches[0], "url", None) == "https://example.com"
    assert getattr(matches[0], "backend", None) == "curl"


# ── repr ────────────────────────────────────────────────────────────────


def test_repr_closed_state() -> None:
    f = CurlFetcher()
    text = repr(f)
    assert "session=closed" in text
    assert "limiters=0" in text


@pytest.mark.asyncio
async def test_repr_open_state(fake_session: FakeAsyncSession) -> None:
    async with CurlFetcher() as f:
        assert "session=open" in repr(f)
