"""Abstract base class for source collectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from proxyaggregator.models.source import SourceSchema
    from proxyaggregator.sources.result import SourceResult


class BaseSourceCollector(ABC):
    """Contract that every source collector must satisfy.

    Subclasses declare which ``source_type`` they handle via the
    ``supported_type`` property and implement the ``collect`` method
    that performs the actual fetch.
    """

    @property
    @abstractmethod
    def supported_type(self) -> str:
        """Return the source_type string this collector handles."""

    @abstractmethod
    async def collect(self, source: SourceSchema) -> SourceResult:
        """Fetch raw content from *source* and return a ``SourceResult``."""
