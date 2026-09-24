"""GeoIP lookup modules -- Phase 5.

Provides DNS resolution, MaxMind MMDB reading, GeoIP enrichment,
and IP-based deduplication.

Location is determined ONLY through:
    endpoint -> real IP -> GeoIP database

Never from hostname, domain, TLD, SNI, remark, or server name.
"""

from proxyaggregator.geoip.dedup import IpDeduplicator
from proxyaggregator.geoip.enrich import GeoIpEnricher
from proxyaggregator.geoip.mmdb import GeoIpDatabaseError, validate_mmdb
from proxyaggregator.geoip.models import EnrichmentResult, GeoIpRecord
from proxyaggregator.geoip.resolver import ResolveResult, resolve_host

__all__ = [
    "EnrichmentResult",
    "GeoIpDatabaseError",
    "GeoIpEnricher",
    "GeoIpRecord",
    "IpDeduplicator",
    "ResolveResult",
    "resolve_host",
    "validate_mmdb",
]
