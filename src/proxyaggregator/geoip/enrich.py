"""GeoIP enrichment pipeline.

Combines DNS resolution and MMDB lookup to produce enriched proxy endpoint data.
No location is ever guessed from hostname, domain, TLD, or any non-IP source.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from proxyaggregator.geoip.models import EnrichmentResult, GeoIpRecord
from proxyaggregator.geoip.resolver import ResolveResult, resolve_host, resolve_host_async

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
        resolved = resolve_host(result.host)
        return self._build_result(result, resolved)

    async def enrich_many(
        self,
        results: list[ParseResult],
        *,
        concurrency: int = 50,
    ) -> list[EnrichmentResult]:
        """Enrich many parsed proxies with bounded DNS concurrency.

        DNS lookups run in worker threads (``asyncio.to_thread``) limited to
        ``concurrency`` simultaneous operations via an ``asyncio.Semaphore``.
        The returned list is in the **original input order**, never in
        completion order.  A single lookup failure never aborts the batch: it
        degrades to a per-entry error result, and the MMDB lookup is skipped
        for that entry.  Any mix of failures and successes across entries is
        preserved independently.

        Literal-IP entries bypass DNS entirely (identical to :meth:`enrich`).
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def _resolve_one(result: ParseResult) -> ResolveResult:
            async with semaphore:
                return await resolve_host_async(result.host)

        resolved = await asyncio.gather(*(_resolve_one(result) for result in results))
        return [
            self._build_result(result, res) for result, res in zip(results, resolved, strict=True)
        ]

    def _build_result(self, result: ParseResult, resolved: ResolveResult) -> EnrichmentResult:
        """Build an EnrichmentResult from a parsed proxy and its DNS outcome."""
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

    Supports both database schemas:
      - GeoLite2-City:      {"country": {"iso_code": "DE", ...}, ...}
      - ip-location-db:     {"country_code": "DE", ...}

    The nested GeoLite2-City field is preferred when present; the top-level
    ``country_code`` is used as a fallback. Only actual database fields are
    used; names/city/coordinates are never invented.
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

    # ip-location-db (user-country / user-cities) stores the code at the top
    # level under "country_code". Fall back only when the nested field is
    # absent, so GeoLite2-City records keep precedence.
    if not country_code:
        country_code = raw.get("country_code")

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
