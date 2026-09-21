"""Collector registry for source type → collector mapping."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from proxyaggregator.sources.base import BaseSourceCollector


class CollectorRegistry:
    """Maps source_type strings to their collector instances."""

    def __init__(self) -> None:
        self._collectors: dict[str, BaseSourceCollector] = {}

    def register(self, collector: BaseSourceCollector) -> None:
        """Register a collector.  Overwrites any previous collector for the same type."""
        self._collectors[collector.supported_type] = collector

    def get(self, source_type: str) -> BaseSourceCollector | None:
        """Return the collector for *source_type*, or ``None``."""
        return self._collectors.get(source_type)

    @property
    def supported_types(self) -> list[str]:
        """Return all registered source types."""
        return list(self._collectors)


_default_registry: CollectorRegistry | None = None


def get_registry() -> CollectorRegistry:
    """Return (and lazily create) the default collector registry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = CollectorRegistry()
        from proxyaggregator.sources.http import HttpSourceCollector

        _default_registry.register(HttpSourceCollector())
    return _default_registry
