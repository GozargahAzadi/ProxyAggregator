"""GeoIP data models for enrichment results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GeoIpRecord(BaseModel):
    """Structured result of a GeoIP lookup for a single IP."""

    ip: str = Field(..., description="Queried IP address")
    country_code: str | None = Field(default=None, description="ISO 3166-1 alpha-2")
    country_name: str | None = Field(default=None)
    city: str | None = Field(default=None)
    latitude: float | None = Field(default=None)
    longitude: float | None = Field(default=None)

    model_config = {"frozen": True}


class EnrichmentResult(BaseModel):
    """Result of enriching a single proxy endpoint with DNS + GeoIP.

    Preserves original proxy information alongside resolution and location data.
    """

    original_host: str = Field(..., description="Original hostname from ParseResult")
    original_port: int = Field(..., ge=1, le=65535)
    original_protocol: str = Field(..., min_length=1)

    resolved_ip: str | None = Field(default=None, description="Primary resolved IP")
    all_resolved_ips: list[str] = Field(
        default_factory=list, description="All resolved IPs, sorted"
    )
    resolution_error: str | None = Field(default=None)

    country_code: str | None = Field(default=None)
    country_name: str | None = Field(default=None)
    city: str | None = Field(default=None)
    latitude: float | None = Field(default=None)
    longitude: float | None = Field(default=None)
    geo_lookup_error: str | None = Field(default=None)

    model_config = {"frozen": True}
