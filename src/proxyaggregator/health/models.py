"""Health check result models.

Results are immutable and intentionally never contain credentials:
no username, password, or raw proxy URI is stored. Errors carry only
stable, sanitized reason codes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field


class HealthStatus(StrEnum):
    """Outcome of a full health check for a proxy endpoint."""

    OK = "ok"
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"
    DNS_FAILURE = "dns_failure"
    TLS_FAILURE = "tls_failure"
    PROTOCOL_FAILURE = "protocol_failure"
    UNSUPPORTED = "unsupported"
    DECLINED = "declined"
    SKIPPED = "skipped"


class CheckStage(StrEnum):
    """Deepest check stage that was reached for an endpoint."""

    TCP = "tcp"
    TLS = "tls"
    PROTOCOL = "protocol"


class HealthCheckResult(BaseModel):
    """Immutable result of a single proxy health check.

    All identifier fields (protocol/host/port) are non-credential identity
    data. Credential material such as username, password, and raw URI are
    deliberately absent from this model.
    """

    proxy_config_id: int | None = Field(default=None, description="Reference to ProxyConfig")
    protocol: str = Field(..., min_length=1, description="Protocol of the checked proxy")
    host: str = Field(..., min_length=1, description="Original proxy hostname or IP")
    port: int = Field(..., ge=1, le=65535, description="Proxy port")

    status: HealthStatus = Field(..., description="Overall check outcome")
    checked_ip: str | None = Field(
        default=None, description="Working IP actually used (if transport succeeded)"
    )
    attempted_ips: list[str] = Field(
        default_factory=list, description="All IPs considered during this check"
    )
    stage: CheckStage = Field(default=CheckStage.TCP, description="Deepest stage reached")

    connect_ms: float | None = Field(default=None, ge=0.0, description="TCP connect duration")
    tls_ms: float | None = Field(default=None, ge=0.0, description="TLS handshake duration")
    proxy_ms: float | None = Field(default=None, ge=0.0, description="Protocol handshake duration")
    latency_ms: float | None = Field(
        default=None, ge=0.0, description="Total time to deepest successful check"
    )

    tls_used: bool = Field(default=False, description="Whether TLS stage was attempted")
    protocol_checked: bool = Field(
        default=False, description="Whether a real protocol handshake was validated"
    )
    tls_verified: bool = Field(
        default=False, description="Whether the TLS certificate chain was verified"
    )

    error: str | None = Field(
        default=None, max_length=1024, description="Sanitized stable error code"
    )
    checked_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC),
        description="When the check was performed",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_alive(self) -> bool:
        """A proxy is only ever alive when the full applicable check succeeded."""
        return self.status == HealthStatus.OK

    model_config = {"frozen": True}
