"""Local persistence-batching benchmark (Phase 15, Step 5).

Compares per-row CRUD commits against the batched bulk path used by
``pipeline._persist_and_enrich``.  Runs against an in-memory SQLite DB,
so numbers are relative (not production throughput), but they quantify
how many SQL statements the pipeline issues per run.

Usage:

    uv run python scripts/benchmark_persist.py
"""

from __future__ import annotations

import time

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from proxyaggregator.db.base import Base
from proxyaggregator.db.crud import (
    create_proxy_config,
    create_source,
    get_proxy_configs_by_hashes,
    get_sources_by_urls,
)
from proxyaggregator.dedup.canonical import compute_content_hash
from proxyaggregator.parsers.base import ParseResult


def _measure_legacy(engine) -> None:
    n = 2000
    with Session(engine) as session:
        start = time.perf_counter()
        for _ in range(n):
            create_source(session, name="s", source_type="http", url="https://x.example")
        legacy = time.perf_counter() - start
    print(
        f"legacy per-row creates: {n} commits in {legacy:.3f}s ({n / max(legacy, 1e-9):.0f} rows/s)"
    )


def _measure_batched(engine) -> None:
    n = 5000
    urls = [f"https://cdn{i}.example/proxies" for i in range(20)]
    with Session(engine) as session:
        start = time.perf_counter()
        sources = get_sources_by_urls(session, urls)
        for url in urls:
            if url not in sources:
                sources[url] = create_source(
                    session, name="s", source_type="http", url=url, commit=False
                )
        session.flush()

        parsed = [
            ParseResult(
                protocol="vless",
                host=f"h{i}.example.com",
                port=443,
                raw_uri=f"vless://h{i}.example.com:443",
            )
            for i in range(n)
        ]
        hashes = [compute_content_hash(p) for p in parsed]
        existing = get_proxy_configs_by_hashes(session, hashes)
        for i, (p, h) in enumerate(zip(parsed, hashes, strict=True)):
            if h not in existing:
                existing[h] = create_proxy_config(
                    session,
                    protocol=p.protocol,
                    host=p.host,
                    port=p.port,
                    raw_uri=p.raw_uri,
                    content_hash=h,
                    source_id=sources[urls[i % len(urls)]].id,
                    commit=False,
                )
        session.commit()
        batched = time.perf_counter() - start
    print(f"batched bulk create: {n} rows in {batched:.3f}s ({n / max(batched, 1e-9):.0f} rows/s)")


def main() -> int:
    events = {"statements": 0}

    def _on_execute(conn, cursor, statement, parameters, context, executemany):
        events["statements"] += 1

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    event.listen(engine, "before_cursor_execute", _on_execute)
    Base.metadata.create_all(engine)

    _measure_legacy(engine)
    _measure_batched(engine)
    print(f"total SQL statements observed: {events['statements']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
