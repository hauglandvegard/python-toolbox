# pyright: reportPrivateUsage=false
import asyncio

import pytest
from tests.fetcher._fakes import FakeAsyncSession, FakeCurlResponse

from toolbox.fetchers import CurlFetcher, Response
from toolbox.schedulers._exceptions import (
    AddQueueError,
    AddUrlError,
    RemoveQueueError,
)
from toolbox.schedulers._fetching_scheduler import (
    FetchingQueue,
    FetchingScheduler,
    QueueItem,
)

HTTP_OK = 200


# ── fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def fake_session(monkeypatch: pytest.MonkeyPatch) -> FakeAsyncSession:
    s = FakeAsyncSession()

    def _factory(**_: object) -> FakeAsyncSession:
        return s

    monkeypatch.setattr("toolbox.fetchers._curl.requests.AsyncSession", _factory)
    return s


async def _drain(q: asyncio.Queue[Response], n: int, timeout: float = 1.0) -> list[Response]:
    out: list[Response] = []
    for _ in range(n):
        out.append(await asyncio.wait_for(q.get(), timeout=timeout))
    return out


# ── QueueItem priority ordering ─────────────────────────────────────────


def test_queue_item_higher_priority_sorts_first() -> None:
    high = QueueItem(10, "https://a")
    low = QueueItem(1, "https://b")
    assert high < low


def test_queue_item_breaks_ties_by_url() -> None:
    a = QueueItem(5, "https://a")
    b = QueueItem(5, "https://b")
    assert a < b


# ── FetchingQueue.add_url ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_queue_add_url_stores_priority(fake_session: FakeAsyncSession) -> None:
    out: asyncio.Queue[Response] = asyncio.Queue()
    async with CurlFetcher() as fetcher:
        q = FetchingQueue("q", fetcher, out)
        await q.add_url("https://x", priority=5)
        item = await q._queue.get()
        assert item == QueueItem(5, "https://x")


@pytest.mark.asyncio
async def test_queue_pops_higher_priority_first(
    fake_session: FakeAsyncSession,
) -> None:
    out: asyncio.Queue[Response] = asyncio.Queue()
    async with CurlFetcher() as fetcher:
        q = FetchingQueue("q", fetcher, out)
        await q.add_url("https://low", priority=1)
        await q.add_url("https://high", priority=10)
        await q.add_url("https://mid", priority=5)
        first = await q._queue.get()
        second = await q._queue.get()
        third = await q._queue.get()
    assert [first.url, second.url, third.url] == [
        "https://high",
        "https://mid",
        "https://low",
    ]


# ── start/stop lifecycle ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_stop_idempotent_without_queues() -> None:
    sched = FetchingScheduler()
    await sched.start()
    await sched.start()  # second call is no-op
    await sched.stop()
    await sched.stop()  # second call is no-op


@pytest.mark.asyncio
async def test_start_spawns_one_worker_per_queue(
    fake_session: FakeAsyncSession,
) -> None:
    sched = FetchingScheduler()
    async with CurlFetcher() as fetcher:
        sched.add_queue("a", fetcher)
        sched.add_queue("b", fetcher)
        await sched.start()
        try:
            assert set(sched._workers.keys()) == {"a", "b"}
            assert all(not t.done() for t in sched._workers.values())
        finally:
            await sched.stop()
    assert sched._workers == {}


@pytest.mark.asyncio
async def test_stop_cancels_workers(fake_session: FakeAsyncSession) -> None:
    sched = FetchingScheduler()
    async with CurlFetcher() as fetcher:
        sched.add_queue("a", fetcher)
        await sched.start()
        worker = sched._workers["a"]
        await sched.stop()
    assert worker.cancelled() or worker.done()


# ── enqueue → fetch → response ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_enqueued_url_produces_response(
    fake_session: FakeAsyncSession,
) -> None:
    fake_session.response = FakeCurlResponse(
        url="https://example.com", status_code=200, content=b"ok"
    )
    sched = FetchingScheduler()
    async with CurlFetcher() as fetcher:
        sched.add_queue("default", fetcher)
        await sched.start()
        try:
            await sched.add_url("https://example.com", queue_id="default")
            [resp] = await _drain(sched.responses, 1)
        finally:
            await sched.stop()

    assert resp.url == "https://example.com"
    assert resp.status_code == HTTP_OK
    assert resp.content == b"ok"
    assert fake_session.requests[0]["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_multiple_queues_fetch_concurrently(
    fake_session: FakeAsyncSession,
) -> None:
    sched = FetchingScheduler()
    async with CurlFetcher() as fetcher:
        sched.add_queue("a", fetcher)
        sched.add_queue("b", fetcher)
        await sched.start()
        try:
            await sched.add_url("https://a", queue_id="a")
            await sched.add_url("https://b", queue_id="b")
            responses = await _drain(sched.responses, 2)
        finally:
            await sched.stop()

    urls = {r.url for r in responses}
    # FakeAsyncSession returns the canned response.url for both. Assert by request log.
    fetched = {r["url"] for r in fake_session.requests}
    assert fetched == {"https://a", "https://b"}
    assert len(urls) >= 1


@pytest.mark.asyncio
async def test_worker_survives_fetch_exception(
    monkeypatch: pytest.MonkeyPatch,
    fake_session: FakeAsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls = {"n": 0}

    async def flaky_request(method: str, url: str, **kwargs: object) -> FakeCurlResponse:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return FakeCurlResponse(url=url, status_code=HTTP_OK)

    monkeypatch.setattr(fake_session, "request", flaky_request)

    sched = FetchingScheduler()
    async with CurlFetcher() as fetcher:
        sched.add_queue("q", fetcher)
        await sched.start()
        try:
            await sched.add_url("https://first", queue_id="q")
            await sched.add_url("https://second", queue_id="q")
            [resp] = await _drain(sched.responses, 1, timeout=2.0)
        finally:
            await sched.stop()

    assert resp.url == "https://second"
    assert calls["n"] == 2  # noqa: PLR2004
    assert any("fetch failed" in rec.message for rec in caplog.records)


# ── add_url errors ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_url_unknown_queue_raises() -> None:
    sched = FetchingScheduler()
    with pytest.raises(AddUrlError, match="no queue with id <missing>"):
        await sched.add_url("https://x", queue_id="missing")


# ── add_queue errors ────────────────────────────────────────────────────


def test_add_queue_duplicate_raises(fake_session: FakeAsyncSession) -> None:
    sched = FetchingScheduler()
    fetcher = CurlFetcher()
    sched.add_queue("dup", fetcher)
    with pytest.raises(AddQueueError, match="queue with id <dup> exists"):
        sched.add_queue("dup", fetcher)


@pytest.mark.asyncio
async def test_add_queue_while_running_spawns_worker(
    fake_session: FakeAsyncSession,
) -> None:
    sched = FetchingScheduler()
    async with CurlFetcher() as fetcher:
        await sched.start()
        try:
            sched.add_queue("late", fetcher)
            assert "late" in sched._workers
            await sched.add_url("https://late", queue_id="late")
            [resp] = await _drain(sched.responses, 1)
        finally:
            await sched.stop()
    assert resp.status_code == HTTP_OK


# ── remove_queue ────────────────────────────────────────────────────────


def test_remove_queue_unknown_raises() -> None:
    sched = FetchingScheduler()
    with pytest.raises(RemoveQueueError, match="<gone> does not exists"):
        sched.remove_queue("gone")


@pytest.mark.asyncio
async def test_remove_queue_while_running_cancels_worker(
    fake_session: FakeAsyncSession,
) -> None:
    sched = FetchingScheduler()
    async with CurlFetcher() as fetcher:
        sched.add_queue("q", fetcher)
        await sched.start()
        worker = sched._workers["q"]
        sched.remove_queue("q")
        # Yield once so cancellation propagates.
        await asyncio.sleep(0)
        assert "q" not in sched._fetching_queues
        assert "q" not in sched._workers
        assert worker.cancelled() or worker.done()
        await sched.stop()


def test_get_queue_ids_returns_snapshot(fake_session: FakeAsyncSession) -> None:
    sched = FetchingScheduler()
    sched.add_queue("a", CurlFetcher())
    sched.add_queue("b", CurlFetcher())
    ids = sched._get_queue_ids()
    assert sorted(ids) == ["a", "b"]
    sched._fetching_queues.clear()
    assert sorted(ids) == ["a", "b"]  # snapshot, not a live view
