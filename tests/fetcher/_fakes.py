"""Test fakes for the fetcher subpackage."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeCurlResponse:
    """Stand-in for curl_cffi.requests.Response — only the fields CurlFetcher reads."""

    url: str = "https://example.com"
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict[str, str])
    content: bytes = b""


class FakeAsyncSession:
    """Stand-in for curl_cffi.requests.AsyncSession.

    Captures every .request() call into ``self.requests`` (list of kwargs dicts).
    Returns the canned ``self.response`` for each call.
    """

    def __init__(self, response: FakeCurlResponse | None = None) -> None:
        self.response = response or FakeCurlResponse()
        self.requests: list[dict[str, Any]] = []
        self.closed = False

    async def request(self, method: str, url: str, **kwargs: Any) -> FakeCurlResponse:
        self.requests.append({"method": method, "url": url, **kwargs})
        return self.response

    async def close(self) -> None:
        self.closed = True
