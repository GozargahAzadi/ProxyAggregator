"""Orchestrator that coordinates source collection across configured sources."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from proxyaggregator.sources.result import SourceResult, SourceResultStatus

if TYPE_CHECKING:
    from proxyaggregator.models.source import SourceSchema
    from proxyaggregator.sources.registry import CollectorRegistry


class SourceOrchestrator:
    """Drives the collection of raw content from a list of sources.

    For each source the orchestrator looks up the appropriate collector
    from the registry, calls ``collect``, and aggregates results.  A
    failure in one source does NOT prevent other sources from being
    collected.  Fetches run with bounded asyncio concurrency while
    results are always returned in input order.
    """

    DEFAULT_CONCURRENCY = 10

    def __init__(
        self, registry: CollectorRegistry, *, concurrency: int = DEFAULT_CONCURRENCY
    ) -> None:
        self._registry = registry
        self._concurrency = max(1, concurrency)

    async def collect_sources(self, sources: list[SourceSchema]) -> list[SourceResult]:
        """Collect raw content from every source with bounded concurrency.

        Returns one ``SourceResult`` per input source, preserving the
        input ordering regardless of timing or individual failures.
        """
        if not sources:
            return []
        semaphore = asyncio.Semaphore(self._concurrency)

        async def _collect_bounded(source: SourceSchema) -> SourceResult:
            async with semaphore:
                return await self._collect_one(source)

        return list(await asyncio.gather(*(_collect_bounded(source) for source in sources)))

    async def _collect_one(self, source: SourceSchema) -> SourceResult:
        collector = self._registry.get(source.source_type)
        if collector is None:
            return SourceResult(
                source_name=source.name,
                source_type=source.source_type,
                source_url=source.url,
                status=SourceResultStatus.ERROR,
                content="",
                fetched_at=datetime.now(tz=UTC),
                error=f"Unsupported source type: {source.source_type}",
            )
        return await collector.collect(source)
