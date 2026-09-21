"""HTTP/HTTPS source collector using httpx."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

from proxyaggregator.sources.base import BaseSourceCollector
from proxyaggregator.sources.result import SourceResult, SourceResultStatus

if TYPE_CHECKING:
    from proxyaggregator.models.source import SourceSchema


class HttpSourceCollector(BaseSourceCollector):
    """Fetches raw proxy content from HTTP/HTTPS URLs.

    Security notes:
    - URLs are treated as untrusted.
    - Responses are bounded by ``max_response_bytes``.
    - Timeouts are explicit and enforced.
    - Redirects are followed but bounded by httpx defaults (20 hops).
    """

    def __init__(self, *, timeout: int = 30, max_response_bytes: int = 10 * 1024 * 1024) -> None:
        self._timeout = timeout
        self._max_response_bytes = max_response_bytes

    @property
    def supported_type(self) -> str:
        return "http"

    async def collect(self, source: SourceSchema) -> SourceResult:
        now = datetime.now(tz=UTC)
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                follow_redirects=True,
                max_redirects=20,
            ) as client:
                response = await client.get(source.url)
                response.raise_for_status()

                raw_text = response.text
                if len(raw_text) > self._max_response_bytes:
                    raw_text = raw_text[: self._max_response_bytes]

                return SourceResult(
                    source_name=source.name,
                    source_type=self.supported_type,
                    source_url=source.url,
                    status=SourceResultStatus.SUCCESS,
                    content=raw_text,
                    status_code=response.status_code,
                    fetched_at=now,
                    content_length=len(raw_text),
                )

        except httpx.TimeoutException as exc:
            return SourceResult(
                source_name=source.name,
                source_type=self.supported_type,
                source_url=source.url,
                status=SourceResultStatus.TIMEOUT,
                content="",
                fetched_at=now,
                error=f"Connection timed out: {exc}",
            )
        except httpx.HTTPStatusError as exc:
            return SourceResult(
                source_name=source.name,
                source_type=self.supported_type,
                source_url=source.url,
                status=SourceResultStatus.ERROR,
                content="",
                fetched_at=now,
                status_code=exc.response.status_code,
                error=f"HTTP {exc.response.status_code}: {exc.response.reason_phrase}",
            )
        except httpx.RequestError as exc:
            return SourceResult(
                source_name=source.name,
                source_type=self.supported_type,
                source_url=source.url,
                status=SourceResultStatus.ERROR,
                content="",
                fetched_at=now,
                error=f"Request error: {exc}",
            )
        except Exception as exc:
            return SourceResult(
                source_name=source.name,
                source_type=self.supported_type,
                source_url=source.url,
                status=SourceResultStatus.ERROR,
                content="",
                fetched_at=now,
                error=f"Unexpected error: {exc}",
            )
