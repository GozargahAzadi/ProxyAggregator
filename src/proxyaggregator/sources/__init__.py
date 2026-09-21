"""Source collectors for fetching proxy configurations from public sources."""

from proxyaggregator.sources.base import BaseSourceCollector
from proxyaggregator.sources.http import HttpSourceCollector
from proxyaggregator.sources.orchestrator import SourceOrchestrator
from proxyaggregator.sources.registry import CollectorRegistry, get_registry
from proxyaggregator.sources.result import SourceResult, SourceResultStatus

__all__ = [
    "BaseSourceCollector",
    "CollectorRegistry",
    "HttpSourceCollector",
    "SourceOrchestrator",
    "SourceResult",
    "SourceResultStatus",
    "get_registry",
]
