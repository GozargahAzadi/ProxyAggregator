"""Phase 17 tests: country-separated subscription feeds.

In addition to the three combined feeds and the per-protocol feeds, the
publisher emits, per selected (deduplicated, `max_items`-capped) candidate
set:

- country-only feeds (all protocols of one country): ``country-{cc}.txt`` /
  ``country-{cc}-base64.txt``
- protocol + country feeds: ``{stem}-{cc}.txt`` / ``{stem}-{cc}-base64.txt``

Country buckets are lowercase ISO-3166-1 alpha-2; missing/invalid countries
map to the ``xx`` bucket. Location feeds are pure, deterministic,
in-memory slices of the same already-ranked proxies used by combined and
protocol feeds: no extra DNS, GeoIP, health check, DB, or network I/O.

Contracts under test:

- Country normalization: uppercase/lowercase valid codes -> lowercase bucket;
  None / invalid values -> ``xx``.
- Grouping is by (protocol, country) and by country alone; each proxy appears
  exactly once per family; interfaces are subset of the combined feed.
- Deterministic ordering: canonical protocol order, then sorted buckets; rank
  order preserved inside every group.
- Plain/base64 exact parity; empty groups are never published; no duplicate
  entries; ``xx`` bucket exists only when actually needed.
- Existing combined/protocol feeds are byte-for-byte unchanged (additive-only,
  captured as a regression test).
- Filename builders reuse the protocol stem map and are always filename-safe.
- Location generation performs no network/I/O and the pipeline re-runs no
  health/GeoIP/DNS work.

No network, no database (except the pipeline-level purity tests), no clock.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
from unittest import mock
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from proxyaggregator import pipeline as pipeline_module
from proxyaggregator.config.settings import Settings
from proxyaggregator.db.base import Base
from proxyaggregator.geoip.models import EnrichmentResult
from proxyaggregator.health.models import CheckStage, HealthCheckResult, HealthStatus
from proxyaggregator.models.source import SourceSchema
from proxyaggregator.publishing import (
    COUNTRY_UNKNOWN_BUCKET,
    SubscriptionFormat,
    build_protocol_subscriptions,
    build_subscription,
    country_bucket,
    default_country_filename,
    default_filename,
    default_protocol_country_filename,
)
from proxyaggregator.publishing.feeds import (
    build_country_subscriptions as _build_country,
)
from proxyaggregator.publishing.feeds import (
    build_protocol_country_subscriptions as _build_pc,
)
from proxyaggregator.publishing.models import RankedProxy, Subscription
from proxyaggregator.publishing.publisher import (
    DEFAULT_FILENAMES,
    _validate_filename,
    default_protocol_filename,
)

UUID = "d98d1c36-ccc8-4c77-9e9f-81c1b7584277"

VLESS = (
    f"vless://{UUID}@vless.example.com:443"
    "?network=ws&security=tls&sni=example.com&host=example.com&path=%2Fws#VLESSNode"
)
TROJAN = "trojan://s3cr3t-pw@trojan.example.com:443?security=tls&sni=example.com#TrojanNode"
SS = (
    "ss://"
    + base64.b64encode(b"aes-128-gcm:passwd").decode("ascii")
    + "@ss.example.com:8388#SSNode"
)
SOCKS5 = "socks5://user:p%40ss@proxy.example.com:1080"
HTTP = "http://user:p%40ss@proxy.example.com:8080"
HTTPS = "https://proxy.example.com:8443"


def _vmess_uri() -> str:
    import json

    payload = {
        "v": "2",
        "ps": "VMessNode",
        "add": "vmess.example.com",
        "port": "443",
        "id": UUID,
        "net": "ws",
        "tls": "tls",
        "sni": "example.com",
        "host": "example.com",
        "path": "/ws",
    }
    raw = json.dumps(payload, separators=(",", ":"))
    return "vmess://" + base64.b64encode(raw.encode("utf-8")).decode("ascii")


VMESS = _vmess_uri()


def _ranked(
    proxy_config_id: int,
    protocol: str,
    raw_uri: str,
    host: str,
    port: int,
    *,
    country_code: str | None = None,
    latency_ms: float | None = None,
    content_hash: str | None = None,
) -> RankedProxy:
    return RankedProxy(
        proxy_config_id=proxy_config_id,
        protocol=protocol,
        host=host,
        port=port,
        raw_uri=raw_uri,
        content_hash=content_hash or f"{proxy_config_id:04d}" * 16,
        score=1.0 - proxy_config_id / 1000,
        rank=proxy_config_id,
        country_code=country_code,
        latency_ms=latency_ms,
    )


def _parse(line: str):
    from proxyaggregator.parsers.registry import get_registry

    return get_registry().get(urlparse(line).scheme).parse(line)


def _country_candidates() -> tuple[RankedProxy, ...]:
    """Five proxies across US/DE with mixed protocols; one None country."""
    ss_alt = (
        "ss://" + base64.b64encode(b"aes-128-gcm:passwd").decode("ascii") + "@ss2.example.com:8388"
    )
    return (
        _ranked(1, "vless", VLESS, "vless.example.com", 443, country_code="US", latency_ms=50.0),
        _ranked(2, "ss", SS, "ss.example.com", 8388, country_code="DE", latency_ms=51.0),
        _ranked(3, "ss", ss_alt, "ss2.example.com", 8388, country_code="US", latency_ms=52.0),
        _ranked(4, "http", HTTP, "proxy.example.com", 8080, country_code="US", latency_ms=53.0),
        _ranked(5, "socks5", SOCKS5, "proxy.example.com", 1080, country_code=None, latency_ms=54.0),
    )


# A. Country normalization ----------------------------------------------------


class TestCountryNormalization:
    @pytest.mark.parametrize(
        ("value", "bucket"),
        [
            ("DE", "de"),
            ("de", "de"),
            (" DE ", "de"),
            ("US", "us"),
            ("GB", "gb"),
        ],
    )
    def test_valid_codes_lowercase_to_filename_bucket(self, value, bucket):
        assert country_bucket(value) == bucket
        assert default_country_filename(value, SubscriptionFormat.PLAIN) == f"country-{bucket}.txt"

    @pytest.mark.parametrize(
        "value",
        [None, "", "D", "DEU", "DE1", "DÉ", "123", "../US", 123, True],
    )
    def test_invalid_values_map_to_xx_bucket(self, value):
        assert country_bucket(value) == COUNTRY_UNKNOWN_BUCKET
        assert default_country_filename(value, SubscriptionFormat.PLAIN) == "country-xx.txt"
        assert (
            default_protocol_country_filename("vless", value, SubscriptionFormat.PLAIN)
            == "vless-xx.txt"
        )

    def test_uppercase_feeds_group_into_lowercase_file(self):
        candidates = [_ranked(1, "vless", VLESS, "vless.example.com", 443, country_code="DE")]
        feeds = _build_country(candidates)
        assert [(bucket, plain.count) for bucket, plain, _b64 in feeds] == [("de", 1)]
        pc = _build_pc(candidates)
        assert [(protocol, bucket, plain.count) for protocol, bucket, plain, _b64 in pc] == [
            ("vless", "de", 1)
        ]

    def test_missing_country_lands_in_xx_group(self):
        candidates = [_ranked(1, "vless", VLESS, "vless.example.com", 443, country_code=None)]
        feeds = _build_country(candidates)
        assert [bucket for bucket, plain, _b64 in feeds] == [COUNTRY_UNKNOWN_BUCKET]


# B. Grouping -----------------------------------------------------------------


class TestGrouping:
    def test_protocol_country_grouping_counts(self):
        feeds = _build_pc(_country_candidates())
        grouped = {(protocol, bucket): plain.count for protocol, bucket, plain, _b64 in feeds}
        assert grouped == {
            ("vless", "us"): 1,
            ("ss", "de"): 1,
            ("ss", "us"): 1,
            ("http", "us"): 1,
            ("socks5", "xx"): 1,
        }

    def test_country_only_grouping(self):
        feeds = _build_country(_country_candidates())
        grouped = {bucket: plain.count for bucket, plain, _b64 in feeds}
        assert grouped == {"de": 1, "us": 3, COUNTRY_UNKNOWN_BUCKET: 1}

    def test_country_only_feed_holds_multiple_protocols(self):
        candidates = [
            _ranked(1, "vless", VLESS, "vless.example.com", 443, country_code="US"),
            _ranked(2, "ss", SS, "ss.example.com", 8388, country_code="US"),
            _ranked(3, "http", HTTP, "proxy.example.com", 8080, country_code="US"),
        ]
        feeds = {bucket: plain for bucket, plain, _b64 in _build_country(candidates)}
        assert feeds["us"].count == 3
        protocols = {_parse(line).protocol for line in feeds["us"].content.splitlines()}
        assert protocols == {"vless", "ss", "http"}

    def test_every_location_line_is_in_the_combined_feed(self):
        candidates = _country_candidates()
        combined_lines = set(build_subscription(candidates).content.splitlines())
        for _bucket, plain, _b64 in _build_country(candidates):
            assert set(plain.content.splitlines()) <= combined_lines
        for _protocol, _bucket, plain, _b64 in _build_pc(candidates):
            assert set(plain.content.splitlines()) <= combined_lines


# C. Ordering -----------------------------------------------------------------


class TestOrdering:
    def test_country_groups_ordered_by_bucket(self):
        candidates = [
            _ranked(1, "ss", SS, "ss.example.com", 8388, country_code="GB"),
            _ranked(2, "http", HTTP, "proxy.example.com", 8080, country_code="DE"),
            _ranked(3, "vless", VLESS, "vless.example.com", 443, country_code="US"),
        ]
        buckets = [bucket for bucket, _plain, _b64 in _build_country(candidates)]
        assert buckets == sorted(buckets) == ["de", "gb", "us"]

    def test_protocol_country_feed_order_is_canonical_then_bucket(self):
        vless_444 = f"vless://{UUID}@vless.example.com:444?security=none"
        candidates = [
            _ranked(1, "ss", SS, "ss.example.com", 8388, country_code="GB"),
            _ranked(2, "vless", VLESS, "vless.example.com", 443, country_code="DE"),
            _ranked(3, "vless", vless_444, "vless.example.com", 444, country_code="US"),
        ]
        order = [(protocol, bucket) for protocol, bucket, _p, _b in _build_pc(candidates)]
        assert order == [("vless", "de"), ("vless", "us"), ("ss", "gb")]

    def test_rank_order_preserved_within_group(self):
        http_8080 = "http://user:p%40ss@proxy.example.com:8080"
        http_8081 = "http://user:p%40ss@proxy.example.com:8081"
        candidates = [
            _ranked(1, "http", http_8080, "proxy.example.com", 8080, country_code="US"),
            _ranked(2, "http", http_8081, "proxy.example.com", 8081, country_code="US"),
            _ranked(3, "http", http_8080, "proxy.example.com", 8080),
        ]
        feeds = {bucket: plain for bucket, plain, _b64 in _build_country(candidates)}
        lines = [_parse(line).port for line in feeds["us"].content.splitlines()]
        assert lines == [8080, 8081]


# D. Base64 parity + empty groups + duplicates + xx ---------------------------


class TestBase64AndEmpties:
    def test_base64_decodes_to_plain_for_all_location_feeds(self):
        for _bucket, plain, b64 in _build_country(_country_candidates()):
            assert plain.format is SubscriptionFormat.PLAIN
            assert b64.format is SubscriptionFormat.BASE64
            assert base64.b64decode(b64.content.encode("ascii")).decode("utf-8") == plain.content
            assert b64.count == plain.count
        for _protocol, _bucket, plain, b64 in _build_pc(_country_candidates()):
            assert base64.b64decode(b64.content.encode("ascii")).decode("utf-8") == plain.content
            assert b64.count == plain.count

    def test_empty_groups_omitted(self):
        candidates = [_ranked(1, "vless", VLESS, "vless.example.com", 443, country_code="DE")]
        country_buckets = [bucket for bucket, _p, _b in _build_country(candidates)]
        assert country_buckets == ["de"]
        pc = [f"{protocol}-{bucket}" for protocol, bucket, _p, _b in _build_pc(candidates)]
        assert pc == ["vless-de"]

    def test_duplicate_content_hashes_deduped_once(self):
        candidate = _ranked(1, "http", HTTP, "proxy.example.com", 8080, country_code="US")
        duplicate = candidate.model_copy(update={"proxy_config_id": 9})
        assert duplicate.content_hash == candidate.content_hash
        feeds = _build_country([candidate, duplicate])
        (bucket, plain, _b64) = feeds[0]
        assert bucket == "us"
        assert plain.count == 1
        assert len(plain.content.splitlines()) == 1

    def test_xx_bucket_only_when_needed(self):
        all_known = [
            _ranked(1, "vless", VLESS, "vless.example.com", 443, country_code="US"),
            _ranked(2, "ss", SS, "ss.example.com", 8388, country_code="DE"),
        ]
        assert COUNTRY_UNKNOWN_BUCKET not in [b for b, _p, _b in _build_country(all_known)]
        one_unknown = [
            *all_known,
            _ranked(3, "http", HTTP, "proxy.example.com", 8080, country_code=None),
        ]
        assert COUNTRY_UNKNOWN_BUCKET in [b for b, _p, _b in _build_country(one_unknown)]

    def test_repeated_generation_is_byte_identical(self):
        first_c = _build_country(_country_candidates())
        second_c = _build_country(_country_candidates())
        assert [(b, p.content, x.content) for b, p, x in first_c] == [
            (b, p.content, x.content) for b, p, x in second_c
        ]
        first_pc = _build_pc(_country_candidates())
        second_pc = _build_pc(_country_candidates())
        assert [(p, b, f.content) for p, b, f, _x in first_pc] == [
            (p, b, f.content) for p, b, f, _x in second_pc
        ]


# E. Filename builders --------------------------------------------------------


class TestLocationFilenames:
    @pytest.mark.parametrize(
        ("protocol", "stem"),
        [
            ("vless", "vless"),
            ("vmess", "vmess"),
            ("trojan", "trojan"),
            ("ss", "shadowsocks"),
            ("hysteria", "hysteria"),
            ("hysteria2", "hysteria2"),
            ("socks4", "socks4"),
            ("socks5", "socks5"),
            ("http", "http"),
            ("https", "https"),
        ],
    )
    def test_protocol_country_filenames_use_stem_map(self, protocol, stem):
        assert (
            default_protocol_country_filename(protocol, "US", SubscriptionFormat.PLAIN)
            == f"{stem}-us.txt"
        )
        assert (
            default_protocol_country_filename(protocol, "US", SubscriptionFormat.BASE64)
            == f"{stem}-us-base64.txt"
        )

    def test_country_filename_shapes(self):
        assert default_country_filename("DE", SubscriptionFormat.PLAIN) == "country-de.txt"
        assert default_country_filename("DE", SubscriptionFormat.BASE64) == "country-de-base64.txt"
        assert default_country_filename(None, SubscriptionFormat.PLAIN) == "country-xx.txt"

    def test_unknown_protocol_rejected(self):
        with pytest.raises(ValueError):
            default_protocol_country_filename("wireguard", "DE", SubscriptionFormat.PLAIN)

    def test_json_rejected_for_location_feeds(self):
        with pytest.raises(ValueError):
            default_country_filename("DE", SubscriptionFormat.JSON)
        with pytest.raises(ValueError):
            default_protocol_country_filename("vless", "DE", SubscriptionFormat.JSON)

    def test_unsafe_country_values_never_produce_unsafe_filenames(self):
        hostile = [
            "DEU",
            "../DE",
            "de/de",
            "DE\x00",
            None,
            "D",
            "123",
            "a" * 50,
        ]
        for value in hostile:
            country_name = default_country_filename(value, SubscriptionFormat.PLAIN)
            pc_name = default_protocol_country_filename("vless", value, SubscriptionFormat.PLAIN)
            assert country_name == "country-xx.txt"
            assert pc_name == "vless-xx.txt"
            _validate_filename(country_name)
            _validate_filename(pc_name)

    def test_default_filename_mappings_untouched(self):
        assert DEFAULT_FILENAMES[SubscriptionFormat.PLAIN] == "proxyaggregator.txt"
        assert DEFAULT_FILENAMES[SubscriptionFormat.BASE64] == "proxyaggregator-base64.txt"
        assert DEFAULT_FILENAMES[SubscriptionFormat.JSON] == "proxyaggregator.json"
        assert default_protocol_filename("ss", SubscriptionFormat.PLAIN) == "shadowsocks.txt"


# F. Backward compatibility regression ----------------------------------------


class TestBackwardCompat:
    def test_existing_feeds_byte_identical_when_location_feeds_enabled(self):
        candidates = _country_candidates()
        expected: list[tuple[str, Subscription]] = []
        for subscription_format in (
            SubscriptionFormat.PLAIN,
            SubscriptionFormat.BASE64,
            SubscriptionFormat.JSON,
        ):
            expected.append(
                (
                    default_filename(subscription_format),
                    build_subscription(candidates, format=subscription_format),
                )
            )
        for protocol, plain, b64 in build_protocol_subscriptions(candidates):
            expected.append((default_protocol_filename(protocol, SubscriptionFormat.PLAIN), plain))
            expected.append((default_protocol_filename(protocol, SubscriptionFormat.BASE64), b64))

        feeds = pipeline_module._build_feeds(candidates)
        assert len(feeds) > len(expected)
        assert [(name, feed.content) for name, feed in feeds[: len(expected)]] == [
            (name, feed.content) for name, feed in expected
        ]

    def test_combined_protocol_serializer_bytes_unchanged(self):
        candidates = _country_candidates()
        assert (
            build_subscription(candidates, format=SubscriptionFormat.PLAIN).content
            == build_subscription(
                candidates, format=SubscriptionFormat.PLAIN, max_items=None
            ).content
        )


# G. Purity: no network, no I/O -----------------------------------------------


class TestPurity:
    def test_feed_module_has_no_network_or_db_touchpoints(self):
        import proxyaggregator.publishing.feeds as feeds_module

        source = inspect.getsource(feeds_module)
        for forbidden in ("socket.", "subprocess", "sqlalchemy", "requests", "getaddrinfo"):
            assert forbidden not in source

    def test_location_generation_does_not_touch_network_or_files(self, monkeypatch, tmp_path):
        import socket as socket_module

        dns_calls: list[str] = []
        monkeypatch.setattr(
            socket_module, "getaddrinfo", lambda *a, **k: dns_calls.append("dns") or []
        )
        candidates = _country_candidates()
        _build_country(candidates)
        _build_pc(candidates)
        assert dns_calls == []
        assert list(tmp_path.iterdir()) == []


# H. Pipeline purity: health/GeoIP/DNS run exactly once -------------------------

_SRC_A = SourceSchema(name="alpha", source_type="http", url="https://cdn.test/alpha.txt")
_SRC_B = SourceSchema(name="beta", source_type="http", url="https://cdn.test/beta.txt")

_CONTENT_A = "http://203.0.113.10:8080\nsocks5://user:secretpass@203.0.113.11:1080\n"
_CONTENT_B = (
    "vless://11111111-2222-3333-4444-555555555555@203.0.113.12:443?security=none\n"
    "http://203.0.113.10:8080\n"
    "vmess://!!!notbase64!!!\n"
)


def _enricher(parsed) -> EnrichmentResult:
    return EnrichmentResult(
        original_host=parsed.host,
        original_port=parsed.port,
        original_protocol=parsed.protocol,
        resolved_ip=parsed.host,
        all_resolved_ips=[parsed.host],
        country_code="US",
        country_name="United States",
        city="Testville",
        latitude=1.0,
        longitude=2.0,
    )


class _CountingHealthRunner:
    def __init__(self) -> None:
        self.calls = 0

    async def check_all(self, entries):
        self.calls += 1
        results = []
        for entry in entries:
            ip = entry.parsed.host
            results.append(
                HealthCheckResult(
                    proxy_config_id=entry.proxy_config_id,
                    protocol=entry.parsed.protocol,
                    host=entry.parsed.host,
                    port=entry.parsed.port,
                    status=HealthStatus.OK,
                    checked_ip=ip,
                    attempted_ips=[ip],
                    stage=CheckStage.PROTOCOL,
                    connect_ms=10.0,
                    tls_ms=0.0,
                    proxy_ms=40.0,
                    latency_ms=40.0,
                    tls_used=False,
                    protocol_checked=True,
                )
            )
        return results


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class TestPipelinePurity:
    @staticmethod
    async def _fake_collect(sources, registry=None, **kwargs):
        from datetime import UTC, datetime

        from proxyaggregator.sources.result import SourceResult, SourceResultStatus

        def result(source, content):
            return SourceResult(
                source_name=source.name,
                source_type=source.source_type,
                source_url=source.url,
                status=SourceResultStatus.SUCCESS,
                content=content,
                fetched_at=datetime.now(tz=UTC),
                content_length=len(content),
            )

        return [
            result(source, _CONTENT_A if source.url == _SRC_A.url else _CONTENT_B)
            for source in sources
        ]

    def _run(self, db_session, tmp_path, enricher, runner):
        cfg = pipeline_module.PipelineConfig(
            settings=Settings(),
            sources=(_SRC_A, _SRC_B),
            output_dir=tmp_path / "out",
            enricher=enricher,
            health_runner=runner,
        )
        with mock.patch.object(pipeline_module, "_collect_sources", self._fake_collect):
            return asyncio.run(pipeline_module.run_pipeline(db_session, cfg))

    def test_health_runner_called_exactly_once(self, db_session, tmp_path):
        runner = _CountingHealthRunner()
        stats = self._run(db_session, tmp_path, _enricher, runner)
        assert runner.calls == 1
        assert stats.health_checks_completed == 3

    def test_geoip_enricher_and_dns_calls_unchanged(self, db_session, tmp_path):
        calls = {"geoip": 0}

        def counting_enricher(parsed):
            calls["geoip"] += 1
            return _enricher(parsed)

        runner = _CountingHealthRunner()
        stats = self._run(db_session, tmp_path, counting_enricher, runner)
        assert stats.deduplicated_proxies == 3
        assert stats.enriched_proxies == 3
        assert stats.health_checks_completed == 3
        assert stats.dns_attempts == 3
        assert calls["geoip"] == 3
        assert runner.calls == 1

    def test_location_filenames_generated_end_to_end(self, db_session, tmp_path):
        stats = self._run(db_session, tmp_path, _enricher, _CountingHealthRunner())
        expected_location = {
            "country-us.txt",
            "country-us-base64.txt",
            "http-us.txt",
            "http-us-base64.txt",
            "socks5-us.txt",
            "socks5-us-base64.txt",
            "vless-us.txt",
            "vless-us-base64.txt",
        }
        assert {path.name for path in (tmp_path / "out").iterdir()} >= expected_location
        assert stats.published_artifacts == 3 + 2 * 3 + 2 * 1 + 2 * 3 + 1
        assert COUNTRY_UNKNOWN_BUCKET not in {p.name for p in (tmp_path / "out").iterdir()}
