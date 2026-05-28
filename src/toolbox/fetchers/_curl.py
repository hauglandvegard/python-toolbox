import logging
from typing import TYPE_CHECKING

from curl_cffi import requests

from toolbox.fetchers._response import Response

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from types import TracebackType
    from typing import Self

    from curl_cffi.requests import BrowserTypeLiteral

    from toolbox.limiters import RateLimit


logger = logging.getLogger(__name__)


class CurlFetcher:
    """Async fetcher backed by curl_cffi with browser fingerprint impersonation."""

    def __init__(
        self,
        *,
        impersonate: BrowserTypeLiteral | None = "chrome124",
        timeout: float = 30.0,
        limiters: list[RateLimit] | None = None,
        # TODO: add -> follow_redirects: bool = True
        # TODO: add -> max_redirects: int = 10
        # TODO: add -> verify_tls: bool = True,
        # TODO: add -> user_agent: str | None = None,
        # TODO: add -> raise_for_status: bool = True,
    ) -> None:
        if timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout}")

        self._impersonate: BrowserTypeLiteral | None = impersonate
        self._session: requests.AsyncSession | None = None
        self._timeout = timeout

        self._limiters: list[RateLimit] = list(limiters) if limiters else []

    @property
    def limiters(self) -> Sequence[RateLimit]:
        return self._limiters

    async def fetch(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response:
        if self._session is None:
            raise RuntimeError(
                "CurlFetcher must be used as an async context manager: "
                "`async with CurlFetcher() as f: await f.fetch(...)`"
            )

        logger.debug("fetch start", extra={"url": url, "backend": "curl"})
        result = await self._session.request(
            "GET",
            url,
            headers=dict(headers) if headers is not None else None,
            timeout=timeout if timeout is not None else self._timeout,
        )

        return Response(
            url=str(result.url),
            status_code=result.status_code,
            headers={k: v or "" for k, v in result.headers.items()},
            content=result.content,
        )

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> Self:
        if self._session is None:
            self._session = requests.AsyncSession(impersonate=self._impersonate)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    def __repr__(self) -> str:
        state = "open" if self._session is not None else "closed"
        return (
            f"CurlFetcher(impersonate={self._impersonate!r}, "
            f"timeout={self._timeout}, limiters={len(self._limiters)}, session={state})"
        )
