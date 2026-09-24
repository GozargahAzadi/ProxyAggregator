"""End-to-end orchestration pipeline (Phase 9.1).

The ``pipeline`` command wires the existing phases into a single run:

    sources -> fetch -> parse -> dedup -> persist -> geoip -> health
             -> score -> rank -> subscribe -> publish

It never re-implements a phase: every stage delegates to the approved
Phase 2-9 modules and models.  Artifacts are byte-deterministic for
identical inputs, and the run is fully offline-capable when a test
health runner and enricher are injected.

Configured sources are read from the ``sources`` table (the only
supported production configuration mechanism).  If the table is empty
the run fails fast with ``no_configured_sources`` — the pipeline never
invents sources, and demo/sample content is never used here.

Failures are reported with stable, credential-free ``reason`` tokens via
:class:`PipelineError`.  No username, password, secret, or raw URI is
ever logged.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from proxyaggregator.config.settings import Settings
from proxyaggregator.db.crud import (
    create_proxy_config,
    create_source,
    get_proxy_config_by_hash,
    get_source_by_url,
    list_all_proxy_configs,
    list_health_checks,
    list_sources,
    record_health_result,
)
from proxyaggregator.dedup.canonical import compute_content_hash
from proxyaggregator.dedup.deduplicator import Deduplicator
from proxyaggregator.dedup.models import DedupMatchType
from proxyaggregator.geoip.enrich import GeoIpEnricher
from proxyaggregator.geoip.mmdb import MmdbReader
from proxyaggregator.health.models import HealthStatus
from proxyaggregator.health.runner import HealthEntry, build_health_runner
from proxyaggregator.models.source import SourceSchema
from proxyaggregator.parsers.base import ParseError, ParseResult
from proxyaggregator.parsers.detect import detect_protocol
from proxyaggregator.parsers.extract import extract_uris
from proxyaggregator.parsers.registry import get_registry as get_parser_registry
from proxyaggregator.publishing import DEFAULT_OUTPUT_DIR
from proxyaggregator.publishing.feeds import build_protocol_subscriptions, build_subscription
from proxyaggregator.publishing.models import (
    RankedProxy,
    Subscription,
    SubscriptionFormat,
)
from proxyaggregator.publishing.publisher import (
    SubscriptionRelease,
    build_release_manifest,
    default_filename,
    default_protocol_filename,
    publish_subscriptions,
    write_release_manifest,
)
from proxyaggregator.scoring.scorer import build_rank_candidates, rank_proxies
from proxyaggregator.sources.orchestrator import SourceOrchestrator
from proxyaggregator.sources.registry import (
    CollectorRegistry,
)
from proxyaggregator.sources.registry import (
    get_registry as get_collector_registry,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from sqlalchemy.orm import Session

    from proxyaggregator.db.models import ProxyConfigORM, SourceORM
    from proxyaggregator.geoip.models import EnrichmentResult
    from proxyaggregator.health.models import HealthCheckResult
    from proxyaggregator.health.runner import HealthRunner
    from proxyaggregator.scoring.models import ProxyScore
    from proxyaggregator.sources.result import SourceResult

logger = logging.getLogger("proxyaggregator.pipeline")

# Deterministic feed set; order and filenames are part of the release contract.
FEED_FORMATS = (SubscriptionFormat.PLAIN, SubscriptionFormat.BASE64, SubscriptionFormat.JSON)


class PipelineError(RuntimeError):
    """Fatal pipeline failure carrying a stable, credential-free reason token."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class PipelineConfig:
    """Everything the orchestrator needs, all injectable for tests."""

    settings: Settings
    sources: tuple[SourceSchema, ...]
    output_dir: str | Path = DEFAULT_OUTPUT_DIR
    max_items: int | None = None
    geoip_reader: MmdbReader | None = None
    enricher: Callable[[ParseResult], EnrichmentResult] | None = None
    health_runner: HealthRunner | None = None

    @property
    def resolved_enricher(self) -> Callable[[ParseResult], EnrichmentResult]:
        if self.enricher is not None:
            return self.enricher
        reader = self.geoip_reader or MmdbReader(self.settings.geoip_db_path)
        return GeoIpEnricher(reader).enrich

    @property
    def resolved_health_runner(self) -> HealthRunner:
        if self.health_runner is not None:
            return self.health_runner
        return build_health_runner(self.settings)


@dataclass(frozen=True)
class PipelineStats:
    """Per-stage counters for the final run summary (no URIs/credentials)."""

    sources_discovered: int = 0
    sources_fetched: int = 0
    parse_candidates: int = 0
    parsed_proxies: int = 0
    deduplicated_proxies: int = 0
    persisted_proxies: int = 0
    enriched_proxies: int = 0
    health_checks_completed: int = 0
    healthy_proxies: int = 0
    ranked_proxies: int = 0
    subscription_count: int = 0
    published_artifacts: int = 0

    def summarize(self) -> str:
        """Render a single credential-free summary line."""
        return (
            f"sources_discovered={self.sources_discovered}, "
            f"sources_fetched={self.sources_fetched}, "
            f"parse_candidates={self.parse_candidates}, "
            f"parsed_proxies={self.parsed_proxies}, "
            f"deduplicated_proxies={self.deduplicated_proxies}, "
            f"persisted_proxies={self.persisted_proxies}, "
            f"enriched_proxies={self.enriched_proxies}, "
            f"health_checks_completed={self.health_checks_completed}, "
            f"healthy_proxies={self.healthy_proxies}, "
            f"ranked_proxies={self.ranked_proxies}, "
            f"subscription_count={self.subscription_count}, "
            f"published_artifacts={self.published_artifacts}"
        )


def load_configured_sources(session: Session) -> list[SourceSchema]:
    """Load every configured source from the ``sources`` table in id order."""
    return [
        SourceSchema(
            name=row.name,
            source_type=row.source_type,
            url=row.url,
            last_fetched_at=row.last_fetched_at,
            config_count=row.config_count,
        )
        for row in list_sources(session)
    ]


async def _collect_sources(
    sources: Sequence[SourceSchema], registry: CollectorRegistry | None = None
) -> list[SourceResult]:
    """Fetch raw content for every configured source (per-source isolation)."""
    return await SourceOrchestrator(registry or get_collector_registry()).collect_sources(
        list(sources)
    )


def _parse_results(
    results: Sequence[SourceResult],
) -> tuple[list[tuple[SourceSchema, ParseResult]], int]:
    """Extract and parse candidate threads; per-entry parser failures are skipped."""
    registry = get_parser_registry()
    parsed: list[tuple[SourceSchema, ParseResult]] = []
    candidates = 0
    for result in results:
        if not result.is_success:
            continue
        schema = SourceSchema(
            name=result.source_name,
            source_type=result.source_type,
            url=result.source_url,
        )
        for uri in extract_uris(result.content):
            candidates += 1
            protocol = detect_protocol(uri)
            parser = registry.get(protocol)
            if parser is None:
                continue
            parsed_result = parser.parse(uri)
            if isinstance(parsed_result, ParseError):
                continue
            parsed.append((schema, parsed_result))
    return parsed, candidates


def _deduplicate(
    parsed_with_sources: Sequence[tuple[SourceSchema, ParseResult]],
) -> tuple[list[tuple[SourceSchema, ParseResult]], int]:
    """Keep first-occurrence survivors (``DedupMatchType.NONE``) in input order."""
    items = [parsed for _, parsed in parsed_with_sources]
    dedup_results = Deduplicator().deduplicate(items)
    survivors: list[tuple[SourceSchema, ParseResult]] = []
    for (schema, parsed), dedup_result in zip(parsed_with_sources, dedup_results, strict=True):
        if dedup_result.match_type is DedupMatchType.NONE:
            survivors.append((schema, parsed))
    return survivors, len(survivors)


def _get_or_create_source(session: Session, schema: SourceSchema) -> SourceORM:
    source = get_source_by_url(session, schema.url)
    if source is not None:
        return source
    return create_source(session, name=schema.name, source_type=schema.source_type, url=schema.url)


def _persist_and_enrich(
    session: Session,
    survivors: Sequence[tuple[SourceSchema, ParseResult]],
    enricher: Callable[[ParseResult], EnrichmentResult],
) -> tuple[list[tuple[ProxyConfigORM, ParseResult, EnrichmentResult]], int]:
    """Persist first-seen proxies (get-or-create) and enrich every survivor."""
    triples: list[tuple[ProxyConfigORM, ParseResult, EnrichmentResult]] = []
    persisted = 0
    counts: dict[str, int] = {}
    for schema, parsed in survivors:
        enrichment = enricher(parsed)
        content_hash = compute_content_hash(parsed)
        source = _get_or_create_source(session, schema)
        config = get_proxy_config_by_hash(session, content_hash)
        if config is None:
            config = create_proxy_config(
                session,
                protocol=parsed.protocol,
                host=parsed.host,
                port=parsed.port,
                raw_uri=parsed.raw_uri,
                content_hash=content_hash,
                source_id=source.id,
                country_code=enrichment.country_code,
                city=enrichment.city,
                latitude=enrichment.latitude,
                longitude=enrichment.longitude,
            )
            persisted += 1
        triples.append((config, parsed, enrichment))
        counts[schema.url] = counts.get(schema.url, 0) + 1
    for url, count in counts.items():
        source = get_source_by_url(session, url)
        if source is not None:
            source.config_count = count
    session.commit()
    return triples, persisted


async def _check_health(
    runner: HealthRunner,
    session: Session,
    triples: Sequence[tuple[ProxyConfigORM, ParseResult, EnrichmentResult]],
) -> tuple[list[HealthCheckResult], int]:
    """Health-check every survivor and persist each result via health CRUD."""
    entries = [
        HealthEntry(parsed=parsed, enrichment=enrichment, proxy_config_id=config.id)
        for config, parsed, enrichment in triples
    ]
    results = await runner.check_all(entries)
    for result in results:
        record_health_result(session, result)
    healthy = sum(1 for result in results if result.status is HealthStatus.OK)
    return results, healthy


def _score_all(session: Session) -> tuple[list[ProxyConfigORM], list[ProxyScore]]:
    """Build rank candidates from persisted state and rank eligible proxies."""
    configs = list_all_proxy_configs(session)
    checks = list_health_checks(session)
    candidates = build_rank_candidates(configs, checks)
    ranked = rank_proxies(candidates)
    return configs, ranked


def _to_ranked_proxies(
    ranked: Sequence[ProxyScore], configs: Sequence[ProxyConfigORM]
) -> list[RankedProxy]:
    """Project scorer output onto the Phase 8 input contract in rank order."""
    by_id = {config.id: config for config in configs}
    result: list[RankedProxy] = []
    for position, score in enumerate(ranked, start=1):
        config = by_id.get(score.proxy_config_id)
        if config is None:
            continue
        result.append(
            RankedProxy(
                proxy_config_id=config.id,
                protocol=config.protocol,
                host=config.host,
                port=config.port,
                raw_uri=config.raw_uri,
                content_hash=score.content_hash,
                score=score.score or 0.0,
                rank=position,
                country_code=config.country_code,
                latency_ms=(
                    score.latency_ms if score.latency_ms is not None else config.latency_ms
                ),
            )
        )
    return result


def _build_feeds(
    ranked_proxies: Sequence[RankedProxy], max_items: int | None = None
) -> list[tuple[str, Subscription]]:
    """Generate the deterministic feed set in release order.

    Order: the three combined feeds first (backward-compatible), then the
    per-protocol plain + base64 feeds in canonical protocol order. The global
    ``max_items`` cap and content-hash dedup are applied once, before the
    per-protocol split, so protocol feeds always mirror the combined feed.
    """
    feeds: list[tuple[str, Subscription]] = [
        (
            default_filename(subscription_format),
            build_subscription(ranked_proxies, format=subscription_format, max_items=max_items),
        )
        for subscription_format in FEED_FORMATS
    ]
    for protocol, plain, base64_feed in build_protocol_subscriptions(
        ranked_proxies, max_items=max_items
    ):
        feeds.append((default_protocol_filename(protocol, SubscriptionFormat.PLAIN), plain))
        feeds.append((default_protocol_filename(protocol, SubscriptionFormat.BASE64), base64_feed))
    return feeds


def _publish(
    feeds: Sequence[tuple[str, Subscription]], output_dir: str | Path
) -> list[SubscriptionRelease]:
    """Write artifacts and the release manifest, then return the releases."""
    releases = publish_subscriptions(feeds, output_dir)
    manifest = build_release_manifest(releases)
    write_release_manifest(manifest, output_dir)
    return releases


async def run_pipeline(session: Session, cfg: PipelineConfig) -> PipelineStats:
    """Run every stage in order and return the final per-stage summary.

    Raises:
        PipelineError: no configured sources, no fetched content, or no
            eligible proxies after health checks.  Publishing never runs
            when a fatal error is raised.
    """
    if not cfg.sources:
        raise PipelineError("no_configured_sources", "the sources table is empty")
    stats = PipelineStats(sources_discovered=len(cfg.sources))

    results = await _collect_sources(cfg.sources)
    stats = replace(stats, sources_fetched=sum(1 for result in results if result.is_success))

    parsed, candidates = _parse_results(results)
    stats = replace(stats, parse_candidates=candidates, parsed_proxies=len(parsed))

    survivors, _deduplicated = _deduplicate(parsed)
    stats = replace(stats, deduplicated_proxies=len(survivors))

    triples, persisted = _persist_and_enrich(session, survivors, cfg.resolved_enricher)
    stats = replace(stats, persisted_proxies=persisted, enriched_proxies=len(triples))

    _health_results, healthy = await _check_health(cfg.resolved_health_runner, session, triples)
    stats = replace(stats, health_checks_completed=len(_health_results), healthy_proxies=healthy)

    configs, ranked = _score_all(session)
    if not ranked:
        raise PipelineError("no_eligible_proxies", "no healthy proxies after health checks")
    ranked_proxies = _to_ranked_proxies(ranked, configs)
    stats = replace(stats, ranked_proxies=len(ranked_proxies))

    feeds = _build_feeds(ranked_proxies, cfg.max_items)
    stats = replace(stats, subscription_count=len(feeds))

    releases = _publish(feeds, cfg.output_dir)
    return replace(stats, published_artifacts=len(releases) + 1)


def run_pipeline_cli() -> int:
    """CLI entry: run the production pipeline and return a process exit code."""
    from proxyaggregator.db.engine import SessionLocal

    settings = Settings()
    try:
        with SessionLocal() as session:
            cfg = PipelineConfig(
                settings=settings,
                sources=tuple(load_configured_sources(session)),
            )
            stats = asyncio.run(run_pipeline(session, cfg))
    except PipelineError as exc:
        logger.error("pipeline failed: %s", exc.reason)
        return 1
    except Exception:
        logger.error("pipeline fatal error")
        return 1
    logger.info("pipeline complete: %s", stats.summarize())
    return 0
