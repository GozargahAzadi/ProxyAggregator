"""Pydantic schema for proxy configurations."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ProxyConfigSchema(BaseModel):
    """Domain model for a parsed proxy configuration."""

    protocol: str = Field(..., min_length=1, description="Protocol type (vless, vmess, etc.)")
    host: str = Field(..., min_length=1, description="Server hostname or IP")
    port: int = Field(..., ge=1, le=65535, description="Server port")
    raw_uri: str = Field(..., min_length=1, description="Original URI string")
    content_hash: str = Field(
        ..., min_length=64, max_length=64, description="SHA-256 hash for deduplication"
    )

    country_code: str | None = Field(
        default=None, min_length=2, max_length=2, description="ISO 3166-1 alpha-2"
    )
    city: str | None = Field(default=None, description="City name")
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)

    is_alive: bool = Field(default=False, description="Last health check result")
    latency_ms: float | None = Field(
        default=None, ge=0.0, description="Last measured latency in ms"
    )

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, v: str | None) -> str | None:
        if v is not None and len(v) != 2:
            raise ValueError("country_code must be exactly 2 characters")
        return v

    model_config = {"frozen": True}
