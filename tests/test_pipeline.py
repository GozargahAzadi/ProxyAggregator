"""Phase 9.1 tests: end-to-end pipeline orchestration.

The ``pipeline`` command wires every existing phase into one deterministic
run.  These tests exercise the stage-by-stage contract, failure isolation and
empty-result policies, credential hygiene, determinism, and the offline
integration path.  No test performs network I/O: source collection is injected
and health checks use a deterministic stub.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
import logging
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from proxyaggregator import pipeline
from proxyaggregator.config.settings import Settings
from proxyaggregator.db.base import Base
from proxyaggregator.db.crud import (
    create_proxy_config,
    create_source,
    list_all_proxy_configs,
    list_health_checks,
    list_sources,
    record_health_result,
)
from proxyaggregator.geoip.mmdb import MmdbReader
from proxyaggregator.geoip.models import EnrichmentResult
from proxyaggregator.health.models import (
    CheckStage,
    HealthCheckResult,
    HealthStatus,
)
from proxyaggregator.models.source import SourceSchema
from proxyaggregator.parsers.base import ParseError, ParseResult
from proxyaggregator.publishing.models import (
    RankedProxy,
    Subscription,
    SubscriptionFormat,
)
from proxyaggregator.publishing.publisher import SubscriptionRelease
from proxyaggregator.scoring.models import ProxyScore
from proxyaggregator.sources.registry import CollectorRegistry
from proxyaggregator.sources.result import SourceResult, SourceResultStatus

ROOT_DIR = Path(__file__).resolve().parents[1]

SRC_A = SourceSchema(name="alpha", source_type="http", url="https://cdn.test/alpha.txt")
SRC_B = SourceSchema(name="beta", source_type="http", url="https://cdn.test/beta.txt")

CONTENT_A = "http://203.0.113.10:8080\nsocks5://user:secretpass@203.0.113.11:1080\n"
CONTENT_B = (
    "vless://11111111-2222-3333-4444-555555555555@203.0.113.12:443?security=none\n"
    "http://203.0.113.10:8080\n"
    "vmess://!!!notbase64!!!\n"
)

URI_HTTP = "http://203.0.113.10:8080"


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _source_result(source: SourceSchema, content: str) -> SourceResult:
    return SourceResult(
        source_name=source.name,
        source_type=source.source_type,
        source_url=source.url,
        status=SourceResultStatus.SUCCESS,
        content=content,
        fetched_at=_utcnow(),
        content_length=len(content),
    )


def _parse(uri: str) -> ParseResult:
    from proxyaggregator.parsers.detect import detect_protocol
    from proxyaggregator.parsers.registry import get_registry

    parser = get_registry().get(detect_protocol(uri))
    assert parser is not None, (uri, detect_protocol(uri))
    result = parser.parse(uri)
    assert not isinstance(result, ParseError), result
    assert isinstance(result, ParseResult)
    return result


def _enricher(parsed: ParseResult) -> EnrichmentResult:
    """Deterministic injected enricher; proves location plumbing only."""
    ip = parsed.host
    return EnrichmentResult(
        original_host=parsed.host,
        original_port=parsed.port,
        original_protocol=parsed.protocol,
        resolved_ip=ip,
        all_resolved_ips=[ip],
        country_code="US",
        country_name="United States",
        city="Testville",
        latitude=1.0,
        longitude=2.0,
    )


class DeterministicHealthRunner:
    """Async ``check_all`` stub: stable status and per-config latency."""

    def __init__(self, status: HealthStatus = HealthStatus.OK, latency_ms: float = 120.0) -> None:
        self.status = status
        self.latency_ms = latency_ms

    async def check_all(self, entries):
        results = []
        for entry in entries:
            ip = entry.parsed.host
            latency = 80.0 + (entry.proxy_config_id or 0) % 50
            results.append(
                HealthCheckResult(
                    proxy_config_id=entry.proxy_config_id,
                    protocol=entry.parsed.protocol,
                    host=entry.parsed.host,
                    port=entry.parsed.port,
                    status=self.status,
                    checked_ip=ip,
                    attempted_ips=[ip],
                    stage=CheckStage.PROTOCOL,
                    connect_ms=10.0,
                    tls_ms=0.0,
                    proxy_ms=latency,
                    latency_ms=latency if self.status is HealthStatus.OK else None,
                    tls_used=entry.parsed.protocol in ("https", "trojan"),
                    protocol_checked=True,
                )
            )
        return results


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _config(
    sources: tuple[SourceSchema, ...],
    *,
    output_dir,
    runner: DeterministicHealthRunner | None = None,
) -> pipeline.PipelineConfig:
    return pipeline.PipelineConfig(
        settings=Settings(),
        sources=sources,
        output_dir=output_dir,
        enricher=_enricher,
        health_runner=runner or DeterministicHealthRunner(),
    )


# A. CLI entry point ----------------------------------------------------------


class TestCli:
    def test_parser_recognizes_pipeline_command(self):
        from proxyaggregator.__main__ import _build_parser

        namespace = _build_parser().parse_args(["pipeline"])
        assert namespace.command == "pipeline"
        assert callable(namespace.handler)

    def test_parser_recognizes_sample_subscriptions(self):
        from proxyaggregator.__main__ import _build_parser

        namespace = _build_parser().parse_args(["sample-subscriptions", "--output", "x"])
        assert namespace.command == "sample-subscriptions"
        assert namespace.output == "x"
        assert namespace.max_items is None

    def test_bare_invocation_prints_version(self, capsys):
        from proxyaggregator.__main__ import main

        assert main([]) == 0
        assert "ProxyAggregator v" in capsys.readouterr().out

    def test_cli_pipeline_without_sources_exits_nonzero(self, tmp_path):
        db_path = tmp_path / "cli.db"
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        engine.dispose()

        env = dict(os.environ)
        env["PA_DATABASE_URL"] = f"sqlite:///{db_path}"
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT_DIR / "src"), env.get("PYTHONPATH", "")])
        result = subprocess.run(
            [sys.executable, "-m", "proxyaggregator", "pipeline"],
            capture_output=True,
            text=True,
            env=env,
            cwd=ROOT_DIR,
            timeout=120,
        )
        assert result.returncode == 1
        assert "pipeline failed: no_configured_sources" in result.stderr
        assert "secretpass" not in result.stderr


# B. Phase wiring order -------------------------------------------------------


class TestPhaseOrder:
    def test_run_pipeline_connects_phases_in_order(self, db_session, monkeypatch, tmp_path):
        called: list[str] = []
        parsed = _parse(URI_HTTP)
        content_hash = "c" * 64
        config = create_proxy_config(
            db_session,
            protocol=parsed.protocol,
            host=parsed.host,
            port=parsed.port,
            raw_uri=parsed.raw_uri,
            content_hash=content_hash,
        )

        async def fake_collect(sources, registry=None):
            called.append("collect")
            return [_source_result(SRC_A, CONTENT_A)]

        def fake_parse(results):
            called.append("parse")
            return ([(SRC_A, parsed)], 1)

        def fake_dedup(items):
            called.append("dedup")
            return ([(SRC_A, parsed)], 1)

        def fake_persist(session, survivors, enricher):
            called.append("persist")
            return ([(config, parsed, _enricher(parsed))], 1)

        async def fake_health(runner, session, triples):
            called.append("health")
            result = HealthCheckResult(
                proxy_config_id=config.id,
                protocol=parsed.protocol,
                host=parsed.host,
                port=parsed.port,
                status=HealthStatus.OK,
                checked_ip=parsed.host,
                attempted_ips=[parsed.host],
            )
            return ([result], 1)

        def fake_score(session):
            called.append("score")
            return (
                [config],
                [
                    ProxyScore(
                        proxy_config_id=config.id,
                        content_hash=content_hash,
                        status=HealthStatus.OK,
                        eligible=True,
                        score=0.9,
                        latency_ms=50.0,
                    )
                ],
            )

        def fake_feeds(ranked_proxies, max_items=None):
            called.append("feeds")
            feed = Subscription(format=SubscriptionFormat.PLAIN, content="", count=0)
            return [("proxyaggregator.txt", feed)]

        def fake_publish(feeds, output_dir):
            called.append("publish")
            return [
                SubscriptionRelease(
                    filename="proxyaggregator.txt",
                    format=SubscriptionFormat.PLAIN,
                    count=0,
                    byte_size=0,
                    sha256="0" * 64,
                )
            ]

        monkeypatch.setattr(pipeline, "_collect_sources", fake_collect)
        monkeypatch.setattr(pipeline, "_parse_results", fake_parse)
        monkeypatch.setattr(pipeline, "_deduplicate", fake_dedup)
        monkeypatch.setattr(pipeline, "_persist_and_enrich", fake_persist)
        monkeypatch.setattr(pipeline, "_check_health", fake_health)
        monkeypatch.setattr(pipeline, "_score_all", fake_score)
        monkeypatch.setattr(pipeline, "_build_feeds", fake_feeds)
        monkeypatch.setattr(pipeline, "_publish", fake_publish)

        cfg = _config((SRC_A,), output_dir=tmp_path / "out")
        stats = asyncio.run(pipeline.run_pipeline(db_session, cfg))

        assert called == [
            "collect",
            "parse",
            "dedup",
            "persist",
            "health",
            "score",
            "feeds",
            "publish",
        ]
        assert stats.published_artifacts == 2


# C. Source collection failure isolation --------------------------------------


class TestSourceIsolation:
    def test_one_failing_source_does_not_block_others(self):
        class FailingCollector:
            supported_type = "failing"

            async def collect(self, source: SourceSchema) -> SourceResult:
                return SourceResult(
                    source_name=source.name,
                    source_type=source.source_type,
                    source_url=source.url,
                    status=SourceResultStatus.ERROR,
                    content="",
                    fetched_at=_utcnow(),
                    error="boom",
                )

        class EchoCollector:
            supported_type = "http"

            async def collect(self, source: SourceSchema) -> SourceResult:
                return _source_result(source, URI_HTTP)

        registry = CollectorRegistry()
        registry.register(FailingCollector())
        registry.register(EchoCollector())
        failing = SourceSchema(name="bad", source_type="failing", url="https://cdn.test/bad")
        good = SourceSchema(name="good", source_type="http", url="https://cdn.test/good")

        async def collect():
            return await pipeline._collect_sources([failing, good], registry)

        results = asyncio.run(collect())
        assert len(results) == 2
        assert results[0].is_success is False
        assert results[1].is_success is True


# D. Parser failure isolation -------------------------------------------------


class TestParseIsolation:
    def test_invalid_entries_are_skipped_without_aborting(self):
        content = (
            "http://203.0.113.10:8080\nvmess://!!!notbase64!!!\nthis is not a proxy line at all\n"
        )
        results = [_source_result(SRC_A, content)]
        parsed, candidates = pipeline._parse_results(results)
        assert candidates == 2
        assert len(parsed) == 1
        assert parsed[0][1].protocol == "http"


# E. Dedup -> persistence -----------------------------------------------------


class TestDedupPersistence:
    def test_first_occurrence_survivors_are_persisted(self, db_session):
        http = _parse(URI_HTTP)
        socks = _parse("socks5://user:secretpass@203.0.113.11:1080")
        duplicate = _parse(URI_HTTP)

        survivors, count = pipeline._deduplicate(
            [(SRC_A, http), (SRC_A, socks), (SRC_A, duplicate)]
        )
        assert count == 2
        assert survivors[0][1] == http
        assert survivors[1][1] == socks

        triples, persisted = pipeline._persist_and_enrich(db_session, survivors, _enricher)
        assert persisted == 2
        hashes = {config.content_hash for config, _parsed, _enrichment in triples}
        assert len(hashes) == 2
        assert len(list_all_proxy_configs(db_session)) == 2


# F. GeoIP enrichment persistence --------------------------------------------


class TestGeoEnrichment:
    def test_country_from_enrichment_is_persisted(self, db_session):
        http = _parse(URI_HTTP)
        triples, _persisted = pipeline._persist_and_enrich(db_session, [(SRC_A, http)], _enricher)
        config = triples[0][0]
        assert config.country_code == "US"
        assert config.city == "Testville"

    def test_no_location_invented_when_geoip_db_missing(self, db_session, tmp_path):
        reader = MmdbReader(tmp_path / "missing.mmdb")
        assert reader.is_valid is False
        enricher = pipeline.PipelineConfig(
            settings=Settings(),
            sources=(SRC_A,),
            output_dir=tmp_path / "out",
            geoip_reader=reader,
        ).resolved_enricher

        http = _parse(URI_HTTP)
        enriched = enricher(http)
        assert enriched.resolved_ip == "203.0.113.10"
        assert enriched.country_code is None
        assert enriched.city is None


# G. Health persistence -------------------------------------------------------


class TestHealthPersistence:
    def test_results_are_persisted_and_denormalized(self, db_session, monkeypatch, tmp_path):
        async def fake_collect(sources, registry=None):
            return [_source_result(SRC_A, CONTENT_A)]

        monkeypatch.setattr(pipeline, "_collect_sources", fake_collect)
        cfg = _config((SRC_A,), output_dir=tmp_path / "out")
        asyncio.run(pipeline.run_pipeline(db_session, cfg))

        checks = list_health_checks(db_session)
        assert len(checks) == 2
        configs = list_all_proxy_configs(db_session)
        assert {config.is_alive for config in configs} == {True}
        assert all(config.working_ip for config in configs)


# H. Ranking consumes latest health ------------------------------------------


class TestRankingLatest:
    def test_ranking_uses_latest_health_row(self, db_session):
        config = create_proxy_config(
            db_session,
            protocol="http",
            host="203.0.113.10",
            port=8080,
            raw_uri=URI_HTTP,
            content_hash="b" * 64,
        )

        def _result(latency_ms: float) -> HealthCheckResult:
            return HealthCheckResult(
                proxy_config_id=config.id,
                protocol="http",
                host="203.0.113.10",
                port=8080,
                status=HealthStatus.OK,
                checked_ip="203.0.113.10",
                attempted_ips=["203.0.113.10"],
                latency_ms=latency_ms,
            )

        record_health_result(db_session, _result(900.0))
        record_health_result(db_session, _result(50.0))

        _configs, ranked = pipeline._score_all(db_session)
        assert len(ranked) == 1
        assert ranked[0].latency_ms == 50.0


# I. Subscription receives ranked proxies -------------------------------------


class TestSubscriptionInput:
    def test_feeds_built_from_ranked_proxies(self, db_session):
        ranked = [
            RankedProxy(
                proxy_config_id=1,
                protocol="http",
                host="203.0.113.10",
                port=8080,
                raw_uri=URI_HTTP,
                content_hash="c" * 64,
                score=0.9,
                rank=1,
            ),
            RankedProxy(
                proxy_config_id=2,
                protocol="socks5",
                host="203.0.113.11",
                port=1080,
                raw_uri="socks5://user:secretpass@203.0.113.11:1080",
                content_hash="d" * 64,
                score=0.8,
                rank=2,
            ),
        ]
        feeds = pipeline._build_feeds(ranked, max_items=None)
        assert len(feeds) == 3
        plain = feeds[0][1]
        assert plain.format is SubscriptionFormat.PLAIN
        assert plain.count == 2


# J/K/L. Fatal failures prevent publishing ------------------------------------


class TestFatalFailurePolicy:
    @staticmethod
    async def _fake_collect(sources, registry=None):
        return [_source_result(SRC_A, CONTENT_A)]

    def test_scoring_failure_prevents_publish(self, db_session, monkeypatch, tmp_path):
        monkeypatch.setattr(pipeline, "_collect_sources", self._fake_collect)

        def boom(session):
            raise pipeline.PipelineError("scoring_failed")

        published: list[object] = []
        monkeypatch.setattr(pipeline, "_score_all", boom)

        def fake_publish(feeds, output_dir):
            published.append(feeds)
            return []

        monkeypatch.setattr(pipeline, "_publish", fake_publish)

        cfg = _config((SRC_A,), output_dir=tmp_path / "out")
        with pytest.raises(pipeline.PipelineError) as excinfo:
            asyncio.run(pipeline.run_pipeline(db_session, cfg))
        assert excinfo.value.reason == "scoring_failed"
        assert published == []
        assert not (tmp_path / "out").exists()

    def test_subscription_failure_prevents_publish(self, db_session, monkeypatch, tmp_path):
        monkeypatch.setattr(pipeline, "_collect_sources", self._fake_collect)

        def boom(ranked_proxies, max_items=None):
            raise pipeline.PipelineError("subscription_failed")

        published: list[object] = []
        monkeypatch.setattr(pipeline, "_build_feeds", boom)

        def fake_publish(feeds, output_dir):
            published.append(feeds)
            return []

        monkeypatch.setattr(pipeline, "_publish", fake_publish)

        cfg = _config((SRC_A,), output_dir=tmp_path / "out")
        with pytest.raises(pipeline.PipelineError) as excinfo:
            asyncio.run(pipeline.run_pipeline(db_session, cfg))
        assert excinfo.value.reason == "subscription_failed"
        assert published == []
        assert not (tmp_path / "out").exists()


# N. Empty / zero-eligible policy ---------------------------------------------


class TestEmptyResultPolicy:
    def test_no_configured_sources_fails_fast(self, db_session, tmp_path):
        cfg = _config((), output_dir=tmp_path / "out")
        with pytest.raises(pipeline.PipelineError) as excinfo:
            asyncio.run(pipeline.run_pipeline(db_session, cfg))
        assert excinfo.value.reason == "no_configured_sources"

    def test_zero_eligible_proxies_publishes_nothing(self, db_session, monkeypatch, tmp_path):
        async def fake_collect(sources, registry=None):
            return [_source_result(SRC_A, CONTENT_A)]

        monkeypatch.setattr(pipeline, "_collect_sources", fake_collect)
        runner = DeterministicHealthRunner(status=HealthStatus.UNREACHABLE)
        cfg = _config((SRC_A,), output_dir=tmp_path / "out", runner=runner)
        with pytest.raises(pipeline.PipelineError) as excinfo:
            asyncio.run(pipeline.run_pipeline(db_session, cfg))
        assert excinfo.value.reason == "no_eligible_proxies"
        assert "http://" not in str(excinfo.value)
        assert not (tmp_path / "out").exists()


# O. Credential hygiene -------------------------------------------------------


class TestCredentialHygiene:
    def test_credentials_never_enter_logs_or_stats(self, db_session, monkeypatch, tmp_path, caplog):
        async def fake_collect(sources, registry=None):
            return [_source_result(SRC_A, CONTENT_A)]

        monkeypatch.setattr(pipeline, "_collect_sources", fake_collect)
        cfg = _config((SRC_A,), output_dir=tmp_path / "out")
        with caplog.at_level(logging.INFO, logger="proxyaggregator.pipeline"):
            stats = asyncio.run(pipeline.run_pipeline(db_session, cfg))
        rendered = stats.summarize()
        assert rendered
        assert "secretpass" not in rendered
        assert "203.0.113" not in rendered
        for record in caplog.records:
            assert "secretpass" not in record.getMessage()
            assert "203.0.113" not in record.getMessage()

    def test_credential_never_in_failure_detail(self, db_session, tmp_path):
        cfg = _config((), output_dir=tmp_path / "out")
        with pytest.raises(pipeline.PipelineError) as excinfo:
            asyncio.run(pipeline.run_pipeline(db_session, cfg))
        assert "secretpass" not in excinfo.value.detail
        assert "203.0.113" not in excinfo.value.detail


# P. No demo data in production pipeline --------------------------------------


class TestNoDemoData:
    def test_pipeline_never_imports_demo_sources(self):
        with pytest.raises(ImportError):
            from proxyaggregator.pipeline import (  # noqa: F401
                build_demo_subscriptions,
            )
        source = inspect.getsource(pipeline)
        assert "samples" not in source
        assert "build_demo_subscriptions" not in source


# Q. sample-subscriptions unchanged -------------------------------------------


class TestSampleUnchanged:
    def test_sample_subscriptions_still_work(self, tmp_path):
        from proxyaggregator.__main__ import main

        out = tmp_path / "demo-out"
        exit_code = main(["sample-subscriptions", "--output", str(out)])
        assert exit_code == 0
        files = sorted(path.name for path in out.iterdir())
        expected = [
            "manifest.json",
            "proxyaggregator-base64.txt",
            "proxyaggregator.json",
            "proxyaggregator.txt",
        ]
        assert files == expected


# R. Settings drive production defaults ---------------------------------------


class TestSettingsDriven:
    def test_resolved_runner_and_enricher_come_from_settings(self, tmp_path):
        settings = Settings()
        cfg = pipeline.PipelineConfig(settings=settings, sources=(SRC_A,), output_dir=tmp_path)
        runner = cfg.resolved_health_runner
        assert runner.concurrency == settings.health_check_concurrency
        assert runner.timeout == settings.health_check_timeout

        parsed = _parse(URI_HTTP)
        enriched = cfg.resolved_enricher(parsed)
        assert enriched.resolved_ip == "203.0.113.10"
        assert enriched.country_code is None


# Integration: deterministic end-to-end run -----------------------------------


class TestEndToEndRun:
    @staticmethod
    async def _fake_collect(sources, registry=None):
        results = []
        for source in sources:
            if source.url == SRC_A.url:
                results.append(_source_result(source, CONTENT_A))
            else:
                results.append(_source_result(source, CONTENT_B))
        return results

    def _run(self, db_session, out):
        cfg = pipeline.PipelineConfig(
            settings=Settings(),
            sources=(SRC_A, SRC_B),
            output_dir=out,
            enricher=_enricher,
            health_runner=DeterministicHealthRunner(),
        )
        with mock.patch.object(pipeline, "_collect_sources", self._fake_collect):
            return asyncio.run(pipeline.run_pipeline(db_session, cfg))

    def test_run_produces_expected_artifacts(self, db_session, tmp_path):
        out = tmp_path / "out"
        stats = self._run(db_session, out)

        assert stats.sources_discovered == 2
        assert stats.sources_fetched == 2
        assert stats.parse_candidates == 5
        assert stats.parsed_proxies == 4
        assert stats.deduplicated_proxies == 3
        assert stats.persisted_proxies == 3
        assert stats.enriched_proxies == 3
        assert stats.health_checks_completed == 3
        assert stats.healthy_proxies == 3
        assert stats.ranked_proxies == 3
        assert stats.subscription_count == 3
        assert stats.published_artifacts == 4

        files = sorted(path.name for path in out.iterdir())
        assert files == [
            "manifest.json",
            "proxyaggregator-base64.txt",
            "proxyaggregator.json",
            "proxyaggregator.txt",
        ]

        plain = (out / "proxyaggregator.txt").read_text(encoding="utf-8")
        assert len(plain.splitlines()) == 3

        base64_lines = (out / "proxyaggregator-base64.txt").read_text(encoding="utf-8")
        assert base64.b64decode(base64_lines).decode("utf-8") == plain

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        by_name = {entry["filename"]: entry for entry in manifest}
        assert set(by_name) == {
            "proxyaggregator-base64.txt",
            "proxyaggregator.json",
            "proxyaggregator.txt",
        }
        for name, entry in by_name.items():
            data = (out / name).read_bytes()
            assert entry["sha256"] == hashlib.sha256(data).hexdigest()
            assert entry["byte_size"] == len(data)

        assert [path for path in out.iterdir() if path.suffix == ".db"] == []

    def test_second_run_is_byte_identical(self, db_session, tmp_path):
        out = tmp_path / "out"
        self._run(db_session, out)
        first = {path.name: path.read_bytes() for path in out.iterdir()}
        self._run(db_session, out)
        second = {path.name: path.read_bytes() for path in out.iterdir()}

        assert sorted(first) == sorted(second)
        for name, data in first.items():
            assert data == second[name]

    def test_loaded_sources_come_from_db(self, db_session):
        create_source(db_session, name="one", source_type="http", url="https://cdn.test/one")
        create_source(db_session, name="two", source_type="http", url="https://cdn.test/two")
        schemas = pipeline.load_configured_sources(db_session)
        assert [schema.name for schema in schemas] == ["one", "two"]
        assert len(list_sources(db_session)) == 2
