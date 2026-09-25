"""Local DNS-enrichment benchmark (Phase 15, Step 3).

Compares the sequential per-proxy ``GeoIpEnricher.enrich`` path (the
Phase 13/14 behavior) against the new bounded-concurrent
``enrich_many`` path.  Uses a mocked ``getaddrinfo`` with a fixed
per-lookup latency, so the comparison is deterministic and touches no
network.  Numbers are relative, machine-specific.

Usage:

    uv run python scripts/benchmark_dns.py
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from proxyaggregator.geoip.enrich import GeoIpEnricher
from proxyaggregator.geoip.mmdb import MmdbReader
from proxyaggregator.parsers.base import ParseResult

LATENCY = 0.05  # simulated per-lookup latency in seconds
COUNT = 400


def _fake_getaddrinfo(host, port=None, family=0, socktype=0, proto=0, flags=0):
    time.sleep(LATENCY)
    return [
        (2, 1, 6, "", ("203.0.113.10", port or 0)),
    ]


def _parse(host: str) -> ParseResult:
    return ParseResult(
        protocol="vless",
        host=host,
        port=443,
        raw_uri=f"vless://{host}:443",
    )


def _sequential(enricher: GeoIpEnricher, results: list[ParseResult]) -> float:
    start = time.perf_counter()
    for result in results:
        enricher.enrich(result)
    return time.perf_counter() - start


async def _concurrent(enricher: GeoIpEnricher, results: list[ParseResult]) -> float:
    start = time.perf_counter()
    await enricher.enrich_many(results, concurrency=50)
    return time.perf_counter() - start


def main() -> int:
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".mmdb", delete=False) as handle:
        path = handle.name
        handle.write(b"\x00")
    with patch("proxyaggregator.geoip.resolver.socket.getaddrinfo", _fake_getaddrinfo):
        reader = MmdbReader(str(path))
        try:
            enricher = GeoIpEnricher(reader)
            results = [_parse(f"h{i}.example.com") for i in range(COUNT)]

            seq = _sequential(enricher, results)
            conc = asyncio.run(_concurrent(enricher, results))

            print(
                f"sequential enrich: {COUNT} lookups in {seq:.3f}s ({COUNT / max(seq, 1e-9):.0f} lookups/s)"
            )
            print(
                f"concurrent enrich:  {COUNT} lookups in {conc:.3f}s ({COUNT / max(conc, 1e-9):.0f} lookups/s)"
            )
            print(f"speedup: {seq / conc:.1f}x")
        finally:
            reader.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
