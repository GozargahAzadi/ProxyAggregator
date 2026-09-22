"""Pydantic schema for health check results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthCheckSchema(BaseModel):
    """Domain model for a proxy health check result.

    Exposed as the public record type for health checks. Mirrors the result
    shape used by the Phase 6 runner and the ORM persistence model.
    """

    proxy_config_id: int = Field(..., gt=0, description="Reference to ProxyConfig")
    is_alive: bool = Field(..., description="Check result")
    latency_ms: float | None = Field(default=None, ge=0.0, description="Latency in milliseconds")
    error_message: str | None = Field(default=None, description="Error message if check failed")

    status: str | None = Field(
        default=None, description="Stable status token, e.g. 'ok', 'timeout'"
    )
    checked_ip: str | None = Field(default=None, description="Working IP used for the check")
    attempted_ips: list[str] = Field(
        default_factory=list, description="All IPs considered for this check"
    )
    connect_ms: float | None = Field(default=None, ge=0.0, description="TCP connect duration")
    tls_ms: float | None = Field(default=None, ge=0.0, description="TLS handshake duration")
    proxy_ms: float | None = Field(default=None, ge=0.0, description="Protocol handshake duration")
    tls_used: bool = Field(default=False, description="Whether TLS was attempted")
    protocol_checked: bool = Field(
        default=False, description="Whether the protocol was truly verified"
    )

    model_config = {"frozen": True}
