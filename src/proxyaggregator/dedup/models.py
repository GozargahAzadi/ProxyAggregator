"""Deduplication result models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from proxyaggregator.dedup.endpoint import EndpointIdentity  # noqa: TC001


class DedupMatchType(StrEnum):
    """Category of deduplication match."""

    NONE = "none"
    EXACT = "exact"
    ENDPOINT = "endpoint"
    FUZZY = "fuzzy"


class DedupResult(BaseModel):
    """Result of deduplicating a single parsed proxy configuration.

    Attributes:
        content_hash: SHA-256 fingerprint of the canonical form.
        endpoint: Normalized endpoint identity (protocol/host/port).
        match_type: Whether this is an exact, endpoint, or fuzzy duplicate.
        match_index: Index of the survivor item that caused the match, or None.
        match_reason: Human-readable reason for the match classification.
    """

    content_hash: str = Field(..., min_length=64, max_length=64)
    endpoint: EndpointIdentity = Field(...)
    match_type: DedupMatchType = Field(default=DedupMatchType.NONE)
    match_index: int | None = Field(default=None)
    match_reason: str | None = Field(default=None)

    model_config = {"frozen": True}
