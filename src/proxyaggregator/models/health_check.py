"""Pydantic schema for health check results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthCheckSchema(BaseModel):
    """Domain model for a proxy health check result."""

    proxy_config_id: int = Field(..., gt=0, description="Reference to ProxyConfig")
    is_alive: bool = Field(..., description="Check result")
    latency_ms: float | None = Field(
        default=None, ge=0.0, description="Latency in milliseconds"
    )
    error_message: str | None = Field(
        default=None, description="Error message if check failed"
    )

    model_config = {"frozen": True}
