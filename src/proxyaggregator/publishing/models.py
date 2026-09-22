"""Subscription generation input/result models (Phase 8).

Phase 8 accepts the already-ranked, eligible proxies produced by Phase 7 and
the canonical proxy configuration data persisted by earlier phases. The
generator never re-reads health state, never consults ``ProxyConfig.is_alive``,
and never recalculates a score.

Only the canonical URI plus non-credential identity fields (`protocol`, `host`,
`port`, `content_hash`) are released into feeds. Scores, ranks, and internal
database ids are input-provenance data and are never serialized.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SubscriptionFormat(StrEnum):
    """Output encodings supported by the Phase 8 generator."""

    PLAIN = "plain"
    BASE64 = "base64"
    JSON = "json"


class RankedProxy(BaseModel):
    """One proxy endpoint in Phase 7 rank order.

    The producer is expected to pass the eligible results of Phase 7 ranking
    in authoritative rank order (best first). ``raw_uri`` is the persisted
    canonical source string; it is the only carrier of fields that the database
    does not persist (UUID, password, TLS/SNI/network options, ...).
    """

    proxy_config_id: int = Field(..., gt=0, description="Reference to ProxyConfig")
    protocol: str = Field(..., min_length=1, description="Protocol identifier")
    host: str = Field(..., min_length=1, description="Server hostname or IP")
    port: int = Field(..., ge=1, le=65535, description="Server port")
    raw_uri: str = Field(..., min_length=1, description="Persisted canonical source URI")
    content_hash: str = Field(
        ..., min_length=64, max_length=64, description="Canonical dedup fingerprint"
    )
    score: float = Field(..., ge=0.0, description="Phase 7 latency score")
    rank: int = Field(..., ge=1, description="1-based rank position")

    model_config = {"frozen": True}


class SubscriptionRequest(BaseModel):
    """Parameters for a single subscription generation call."""

    max_items: int | None = Field(
        default=None, ge=1, description="Max number of unique proxies to emit (None = all)"
    )

    model_config = {"frozen": True}


class Subscription(BaseModel):
    """A generated, byte-deterministic subscription feed.

    ``content`` is UTF-8 text: newline-delimited canonical URIs for PLAIN, a
    single ASCII token for BASE64, and compact JSON for the JSON format.
    ``count`` is the number of unique proxies represented.
    """

    format: SubscriptionFormat = Field(..., description="Feed encoding")
    content: str = Field(..., description="UTF-8 feed content")
    count: int = Field(..., ge=0, description="Number of unique proxies emitted")

    model_config = {"frozen": True}
