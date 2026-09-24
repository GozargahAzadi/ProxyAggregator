"""IP-based deduplication for proxy configurations.

Adds resolved-IP identity as an additional collision signal.
Does NOT replace Phase 4 dedup — it complements it.

Two proxies resolving to the same IP are NOT automatically identical.
Same IP + different port, protocol, or credentials remain distinct.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from proxyaggregator.dedup.endpoint import EndpointIdentity
from proxyaggregator.dedup.models import DedupMatchType, DedupResult
from proxyaggregator.geoip.resolver import _ip_sort_key, resolve_host

if TYPE_CHECKING:
    from proxyaggregator.parsers.base import ParseResult


def _ip_endpoint_key(
    ip: str, port: int, protocol: str, user: str, password: str
) -> tuple[str, int, str, str, str]:
    """Create a dedup key from resolved IP, port, protocol, and credentials."""
    return (ip.lower(), port, protocol.lower(), user, password)


class IpDeduplicator:
    """IP-based deduplication as an additional collision signal.

    Processes ParseResult items and detects:
    - Exact same resolved IP + port + protocol + credentials (EXACT duplicate)
    - Same IP but different port/protocol/credentials remain distinct
    - Unresolved hosts are not treated as IP-duplicates of each other
    """

    def deduplicate(
        self,
        items: list[ParseResult],
        ip_map: dict[str, list[str]] | None = None,
    ) -> list[DedupResult]:
        """Deduplicate a list of parsed configs using resolved IP identity.

        Args:
            items: List of ParseResult items to deduplicate.
            ip_map: Optional pre-resolved hostname -> list of IPs mapping.
                    If not provided, DNS is performed for each unique host.

        Returns:
            One DedupResult per input item, preserving order.
        """
        if ip_map is None:
            ip_map = {}

        # Build resolved IP cache
        resolved_cache: dict[str, str | None] = {}

        def _get_primary_ip(host: str) -> str | None:
            if host in resolved_cache:
                return resolved_cache[host]

            if host in ip_map:
                ips = ip_map[host]
                if ips:
                    sorted_ips = sorted(ips, key=_ip_sort_key)
                    resolved_cache[host] = sorted_ips[0]
                else:
                    resolved_cache[host] = None
            else:
                result = resolve_host(host)
                if result.resolved and result.addresses:
                    resolved_cache[host] = result.addresses[0]
                else:
                    resolved_cache[host] = None

            return resolved_cache[host]

        # Track seen IP identities
        seen_by_ip_key: dict[tuple[str, int, str, str, str], int] = {}
        results: list[DedupResult] = []

        for item in items:
            primary_ip = _get_primary_ip(item.host)
            ep = EndpointIdentity(
                protocol=item.protocol,
                host=item.host.lower(),
                port=item.port,
            )

            if primary_ip is not None:
                ip_key = _ip_endpoint_key(
                    primary_ip,
                    item.port,
                    item.protocol,
                    item.user or "",
                    item.password or "",
                )

                if ip_key in seen_by_ip_key:
                    orig_idx = seen_by_ip_key[ip_key]
                    results.append(
                        DedupResult(
                            content_hash="0" * 64,
                            endpoint=ep,
                            match_type=DedupMatchType.EXACT,
                            match_index=orig_idx,
                            match_reason=f"Same resolved IP ({primary_ip}) + port + protocol + credentials",
                        )
                    )
                else:
                    results.append(
                        DedupResult(
                            content_hash="0" * 64,
                            endpoint=ep,
                            match_type=DedupMatchType.NONE,
                            match_index=None,
                            match_reason=None,
                        )
                    )
                    seen_by_ip_key[ip_key] = len(results) - 1
            else:
                results.append(
                    DedupResult(
                        content_hash="0" * 64,
                        endpoint=ep,
                        match_type=DedupMatchType.NONE,
                        match_index=None,
                        match_reason=None,
                    )
                )

        return results
