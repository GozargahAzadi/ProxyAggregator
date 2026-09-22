"""Scoring input and result models for Phase 7.

The score is the only quality signal: a pure, deterministic conversion of the
latest observed latency into a ranked order. Status, latency, and identity
fields below are the complete scoring contract — no protocol, country, or
GeoIP metadata influences the score.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from proxyaggregator.health.models import HealthStatus  # noqa: TC001


class RankCandidate(BaseModel):
    """One proxy endpoint together with its latest health outcome.

    Producers (e.g. the pipeline) attach the already-selected ``latest`` health
    check; the scorer never re-defines "latest" or performs database access.
    """

    proxy_config_id: int = Field(..., gt=0, description="Reference to ProxyConfig")
    content_hash: str = Field(
        ..., min_length=64, max_length=64, description="Canonical dedup fingerprint"
    )
    status: HealthStatus = Field(..., description="Latest health outcome")
    latency_ms: float | None = Field(
        default=None, ge=0.0, description="Latest measured latency (None = no usable measure)"
    )

    model_config = {"frozen": True}


class ProxyScore(BaseModel):
    """Result of scoring one proxy endpoint.

    ``score`` and ``latency_ms`` are present only when ``eligible`` is True.
    Ineligible results carry no score and are excluded from ranking.
    """

    proxy_config_id: int = Field(..., gt=0, description="Reference to ProxyConfig")
    content_hash: str = Field(..., min_length=64, max_length=64)
    status: HealthStatus = Field(..., description="Latest health outcome")
    eligible: bool = Field(..., description="Whether the proxy qualifies for ranking")
    score: float | None = Field(
        default=None, ge=0.0, description="Latency score (None when ineligible)"
    )
    latency_ms: float | None = Field(
        default=None, ge=0.0, description="Latest measured latency (None when ineligible)"
    )

    model_config = {"frozen": True}
