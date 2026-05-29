import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from toolbox.schedulers._exceptions import (
    AddQueueError,
    AddUrlError,
    RemoveQueueError,
)

if TYPE_CHECKING:
    from toolbox.fetchers import CurlFetcher
    from toolbox.fetchers._response import Response

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, order=False)
class QueueItem:
    """Item enqueued for fetching.

    Custom ``__lt__`` implementation ensures higher priority items sort
    "less than" others, allowing ``asyncio.PriorityQueue`` (a min-heap)
    to act as a max-priority queue.
    """

    priority: int
    url: str

    def __lt__(self, other: QueueItem) -> bool:
        if self.priority != other.priority:
            return self.priority > other.priority
        return self.url < other.url


class FetchingQueue:
    """Priority queue of URLs bound to a single fetcher.

    One instance per logical grouping (e.g. per domain), so per-queue
    concerns like rate limiting or connection reuse stay isolated.
    """

    def __init__(
        self,
        queue_id: str,
        fetcher: CurlFetcher,
        output: asyncio.Queue[Response],
    ):
        """Initialize queue.

        Args:
            queue_id: Identifier used by ``FetchingScheduler`` for lookup.
            fetcher: Fetcher to use. Caller owns its lifecycle (e.g. via
                ``async with``).
            output: Shared sink for ``Response`` objects produced by this
                queue's worker loop.
        """
        self._id = queue_id
        self._queue: asyncio.PriorityQueue[QueueItem] = asyncio.PriorityQueue()
        self._fetcher = fetcher
        self._output = output

    @property
    def id(self) -> str:
        return self._id

    async def add_url(self, url: str, priority: int) -> None:
        """Enqueue ``url``. Higher ``priority`` pops sooner."""
        await self._queue.put(QueueItem(priority, url))

    async def run(self) -> None:
        """Pull items, fetch, push ``Response`` to output. Run until cancelled."""
        while True:
            item = await self._queue.get()
            try:
                resp = await self._fetcher.fetch(item.url)
                await self._output.put(resp)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "fetch failed",
                    extra={"url": item.url, "queue_id": self._id},
                )
            finally:
                self._queue.task_done()


class FetchingScheduler:
    """Owns registered queues and their worker tasks.

    Caller drains results via ``await scheduler.responses.get()``.
    Caller owns ``CurlFetcher`` lifecycle.
    """

    def __init__(self) -> None:
        self._fetching_queues: dict[str, FetchingQueue] = {}
        self._workers: dict[str, asyncio.Task[None]] = {}
        self._responses: asyncio.Queue[Response] = asyncio.Queue()
        self._running = False

    @property
    def responses(self) -> asyncio.Queue[Response]:
        """Output queue. Drain with ``await scheduler.responses.get()``."""
        return self._responses

    async def start(self) -> None:
        """Spawn one worker task per registered queue. Idempotent."""
        if self._running:
            return
        self._running = True
        for qid, queue in self._fetching_queues.items():
            self._workers[qid] = asyncio.create_task(queue.run(), name=f"fetch-worker-{qid}")

    async def stop(self) -> None:
        """Cancel all workers and await their teardown. Idempotent."""
        if not self._running:
            return
        self._running = False
        for task in self._workers.values():
            task.cancel()
        await asyncio.gather(*self._workers.values(), return_exceptions=True)
        self._workers.clear()

    async def add_url(self, url: str, queue_id: str, priority: int = 0) -> None:
        """Enqueue ``url`` on queue ``queue_id``.

        Raises:
            AddUrlError: ``queue_id`` not registered.
        """
        if queue_id not in self._fetching_queues:
            extra = {
                "url": url,
                "queue_id": queue_id,
                "priority": priority,
                "queue_ids": self._get_queue_ids(),
            }
            logger.warning("add_url failed due to queue_id not existing", extra=extra)
            raise AddUrlError(f"no queue with id <{queue_id}>")

        await self._fetching_queues[queue_id].add_url(url=url, priority=priority)

    def add_queue(self, queue_id: str, fetcher: CurlFetcher) -> None:
        """Register a new queue under ``queue_id``.

        If the scheduler is already running, the queue's worker starts
        immediately. Otherwise it starts on the next ``start()``.

        Raises:
            AddQueueError: ``queue_id`` already registered.
        """
        if queue_id in self._fetching_queues:
            extra = {"queue_id": queue_id, "queue_ids": self._get_queue_ids()}
            logger.warning("queue id already registered", extra=extra)
            raise AddQueueError(f"queue with id <{queue_id}> exists")

        queue = FetchingQueue(queue_id=queue_id, fetcher=fetcher, output=self._responses)
        self._fetching_queues[queue_id] = queue
        if self._running:
            self._workers[queue_id] = asyncio.create_task(
                queue.run(), name=f"fetch-worker-{queue_id}"
            )

    def remove_queue(self, queue_id: str) -> None:
        """Unregister queue ``queue_id``. Cancels its worker if running.

        Raises:
            RemoveQueueError: ``queue_id`` not registered.
        """
        if queue_id not in self._fetching_queues:
            extra = {"queue_id": queue_id, "queue_ids": self._get_queue_ids()}
            logger.warning("unable to remove queue", extra=extra)
            raise RemoveQueueError(f"queue with id <{queue_id}> does not exists")

        worker = self._workers.pop(queue_id, None)
        if worker is not None:
            worker.cancel()
        self._fetching_queues.pop(queue_id)

    def _get_queue_ids(self) -> list[str]:
        """Return registered queue ids (snapshot)."""
        return list(self._fetching_queues.keys())
