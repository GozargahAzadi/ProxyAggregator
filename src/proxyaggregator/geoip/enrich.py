"""GeoIP enrichment pipeline.

Combines DNS resolution and MMDB lookup to produce enriched proxy endpoint data.
No location is ever guessed from hostname, domain, TLD, or any non-IP source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from proxyaggregator.geoip.models import EnrichmentResult, GeoIpRecord
from proxyaggregator.geoip.resolver import resolve_host

if TYPE_CHECKING:
    from proxyaggregator.geoip.mmdb import MmdbReader
    from proxyaggregator.parsers.base import ParseResult


class GeoIpEnricher:
    """Enriches parsed proxy results with DNS resolution and GeoIP data.

    Pipeline:
        ParseResult -> DNS resolve -> MMDB lookup -> EnrichmentResult
    """

    def __init__(self, reader: MmdbReader) -> None:
        self._reader = reader

    def enrich(self, result: ParseResult) -> EnrichmentResult:
        """Enrich a single parsed proxy with IP and location data.

        Does NOT mutate the original ParseResult.
        """
        # Step 1: DNS resolution
        resolved = resolve_host(result.host)

        resolved_ip = None
        all_ips: list[str] = []
        resolution_error = None

        if resolved.resolved and resolved.addresses:
            all_ips = resolved.addresses
            resolved_ip = resolved.addresses[0]  # deterministic: first sorted IP
        else:
            resolution_error = resolved.error

        # Step 2: GeoIP lookup (only if we have a resolved IP)
        geo_record = None
        geo_error = None

        if resolved_ip is not None:
            try:
                raw_record = self._reader.lookup(resolved_ip)
                if raw_record is not None:
                    geo_record = _extract_geo_record(resolved_ip, raw_record)
            except Exception as exc:
                geo_error = str(exc)

        # Step 3: Build result
        return EnrichmentResult(
            original_host=result.host,
            original_port=result.port,
            original_protocol=result.protocol,
            resolved_ip=resolved_ip,
            all_resolved_ips=all_ips,
            resolution_error=resolution_error,
            country_code=geo_record.country_code if geo_record else None,
            country_name=geo_record.country_name if geo_record else None,
            city=geo_record.city if geo_record else None,
            latitude=geo_record.latitude if geo_record else None,
            longitude=geo_record.longitude if geo_record else None,
            geo_lookup_error=geo_error,
        )


def _extract_geo_record(ip: str, raw: dict) -> GeoIpRecord:
    """Extract a GeoIpRecord from raw MMDB data dict.

    Only uses actual database fields. Never invents values.
    """
    country_code = None
    country_name = None
    city = None
    latitude = None
    longitude = None

    country_data = raw.get("country")
    if isinstance(country_data, dict):
        country_code = country_data.get("iso_code")
        names = country_data.get("names")
        if isinstance(names, dict):
            country_name = names.get("en")

    city_data = raw.get("city")
    if isinstance(city_data, dict):
        names = city_data.get("names")
        if isinstance(names, dict):
            city = names.get("en")

    location_data = raw.get("location")
    if isinstance(location_data, dict):
        latitude = location_data.get("latitude")
        longitude = location_data.get("longitude")

    return GeoIpRecord(
        ip=ip,
        country_code=country_code,
        country_name=country_name,
        city=city,
        latitude=latitude,
        longitude=longitude,
    )
