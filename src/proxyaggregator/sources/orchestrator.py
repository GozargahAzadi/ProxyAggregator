"""Orchestrator that coordinates source collection across configured sources."""

from __future__ import annotations

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
    collected.
    """

    def __init__(self, registry: CollectorRegistry) -> None:
        self._registry = registry

    async def collect_sources(self, sources: list[SourceSchema]) -> list[SourceResult]:
        """Collect raw content from every source in order.

        Returns one ``SourceResult`` per input source, preserving the
        input ordering regardless of timing or individual failures.
        """
        results: list[SourceResult] = []
        for source in sources:
            result = await self._collect_one(source)
            results.append(result)
        return results

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
