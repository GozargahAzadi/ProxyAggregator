"""Local health-runner concurrency benchmark (Phase 15, Step 4).

Measures wall-clock throughput of ``HealthRunner.check_all`` at a given
``PA_HEALTH_CHECK_CONCURRENCY``-style concurrency against local loopback
servers that emulate per-connection latency.  No public proxies, no external
network, no credentials.  The results are relative, machine-specific numbers
used to decide whether higher concurrency is safe to adopt in production.

Usage:

    uv run python scripts/benchmark_health_concurrency.py
    uv run python scripts/benchmark_health_concurrency.py --concurrency 50 75 100 --count 800
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass

from proxyaggregator.health.models import HealthStatus
from proxyaggregator.health.policy import TargetPolicy
from proxyaggregator.health.runner import HealthEntry, HealthRunner
from proxyaggregator.parsers.base import ParseResult


@dataclass
class _Activity:
    current: int = 0
    max_concurrent: int = 0


async def _read_request(reader: asyncio.StreamReader) -> None:
    while True:
        line = await reader.readline()
        if not line or line in (b"\r\n", b"\n"):
            break


def _handler(latency_ms: int, activity: _Activity):
    lock = asyncio.Lock()

    async def handler(reader, writer) -> None:
        nonlocal lock
        async with lock:
            activity.current += 1
            activity.max_concurrent = max(activity.max_concurrent, activity.current)
        try:
            await _read_request(reader)
            await asyncio.sleep(latency_ms / 1000.0)
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
        finally:
            async with lock:
                activity.current -= 1
            writer.close()

    return handler


async def _start(latency_ms: int, activity: _Activity) -> tuple[str, int, asyncio.Server]:
    server = await asyncio.start_server(_handler(latency_ms, activity), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return "127.0.0.1", port, server


def _entry(host: str, port: int) -> HealthEntry:
    parsed = ParseResult(
        protocol="http",
        host=host,
        port=port,
        raw_uri=f"http://{host}:{port}",
        user=None,
        password=None,
        sni=None,
        transport="tcp",
        tls="none",
        network="",
        path="",
        remark="",
    )
    return HealthEntry(parsed=parsed)


async def _measure(concurrency: int, count: int, latency_ms: int) -> tuple[float, int]:
    activity = _Activity()
    host, port, server = await _start(latency_ms, activity)
    runner = HealthRunner(
        policy=TargetPolicy(allow_private=True),
        timeout=10.0,
        concurrency=concurrency,
        max_ips_per_host=8,
        verify_tls=False,
    )
    entries = [_entry(host, port) for _ in range(count)]
    try:
        start = time.perf_counter()
        results = await runner.check_all(entries)
        elapsed = time.perf_counter() - start
    finally:
        server.close()
        await server.wait_closed()
    ok = sum(1 for r in results if r.status is HealthStatus.OK)
    if ok != count:
        raise RuntimeError(f"expected {count} OK, got {ok} (unstable under concurrency)")
    return elapsed, activity.max_concurrent


async def _run(concurrencies: list[int], count: int, latency_ms: int, repeats: int) -> None:
    print(f"count={count} latency={latency_ms}ms repeats={repeats}\n")
    for concurrency in concurrencies:
        samples: list[float] = []
        max_active = 0
        for _ in range(repeats):
            elapsed, active = await _measure(concurrency, count, latency_ms)
            samples.append(elapsed)
            max_active = max(max_active, active)
        mean = statistics.mean(samples)
        per_check = (mean / count) * 1000.0
        print(
            f"concurrency={concurrency:>4d}: "
            f"mean={mean:.3f}s  checks/s={count / mean:.1f}  "
            f"per-check={per_check:.2f}ms  max_active={max_active}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, nargs="*", default=[50, 75, 100])
    parser.add_argument("--count", type=int, default=800)
    parser.add_argument("--latency", type=int, default=300, help="per-connection ms")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    asyncio.run(_run(args.concurrency, args.count, args.latency, args.repeats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
