import asyncio
import logging
from typing import NamedTuple

from toolbox.fetchers import CurlFetcher
from toolbox.schedulers._exceptions import (
    AddUrlError,
    AddQueueError,
    RemoveQueueError
)

logger = logging.getLogger(__name__)


class QueueItem(NamedTuple):
    """Item enqueued for fetching.

    ``priority`` is stored negated so that ``asyncio.PriorityQueue`` (a
    min-heap) pops the highest-priority URL first.
    """

    priority: int
    url: str


class FetchingQueue:
    """Priority queue of URLs bound to a single fetcher.

    One instance per logical grouping (e.g. per domain), so per-queue
    concerns like rate limiting or connection reuse stay isolated.
    """

    def __init__(self, queue_id: str, fetcher: CurlFetcher | None = None):
        """Initialize queue.

        Args:
            queue_id: Identifier used by ``FetchingScheduler`` for lookup.
            fetcher: Fetcher to use. A new ``CurlFetcher`` is created when
                omitted; pass a shared instance to pool connections across
                queues.
        """
        self._id = queue_id
        self._queue: asyncio.PriorityQueue[QueueItem] = asyncio.PriorityQueue()
        self._fetcher: CurlFetcher = CurlFetcher() if fetcher is None else fetcher

    async def add_url(self, url: str, priority: int) -> None:
        """Enqueue ``url``. Higher ``priority`` pops sooner."""
        await self._queue.put(QueueItem(-priority, url))


class FetchingScheduler:
    """Routes URLs to registered ``FetchingQueue`` instances by ``queue_id``."""

    def __init__(self) -> None:
        self._fetching_queues: dict[str, FetchingQueue] = {}

    async def add_url(self, url: str, queue_id: str, priority: int = 0) -> None:
        """Enqueue ``url`` on queue ``queue_id``.

        Raises:
            AddUrlError: ``queue_id`` not registered.
        """
        if queue_id not in self._fetching_queues:
            extra = {"url": url, "queue_id": queue_id, "priority": priority, "queue_ids": self._get_queue_ids()}
            logger.warning("add_url failed due to queue_id not existing", extra=extra)
            raise AddUrlError(f"no queue with id <{queue_id}>")

        await self._fetching_queues[queue_id].add_url(url=url, priority=priority)

    def add_queue(self, queue_id: str, fetcher: CurlFetcher | None = None) -> None:
        """Register a new queue under ``queue_id``.

        Raises:
            AddQueueError: ``queue_id`` already registered.
        """
        if queue_id in self._fetching_queues:
            extra = {"queue_id": queue_id, "queue_ids": self._get_queue_ids()}
            logger.warning("queue id already registered" , extra=extra)
            raise AddQueueError(f"queue with id <{queue_id}> exists")

        self._fetching_queues[queue_id] = FetchingQueue(queue_id=queue_id, fetcher=fetcher)

    def remove_queue(self, queue_id: str) -> None:
        """Unregister queue ``queue_id``.

        Raises:
            RemoveQueueError: ``queue_id`` not registered.
        """
        if queue_id not in self._fetching_queues:
            extra = {"queue_id": queue_id, "queue_ids": self._get_queue_ids()}
            logger.warning("unable to remove queue" , extra=extra)
            raise RemoveQueueError(f"queue with id <{queue_id}> does not exists")

        self._fetching_queues.pop(queue_id)

    def _get_queue_ids(self) -> list[str]:
        """Return registered queue ids (snapshot)."""
        return list(self._fetching_queues.keys())
