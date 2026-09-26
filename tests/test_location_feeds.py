"""Phase 17 tests: country-separated subscription directories.

In addition to the three combined feeds and the per-protocol feeds, the
publisher emits, per selected (deduplicated, `max_items`-capped) candidate
set:

- a generated index ``countries/README.md`` listing every non-empty country
  directory, deterministically ordered by ISO code;
- one directory per non-empty country bucket ``countries/{CC}/`` with
  ``README.md``, an all-protocol feed (``all.txt`` / ``all-base64.txt``), and
  a plain + base64 feed per protocol only when that protocol has candidates.

Country buckets are uppercase ISO-3166-1 alpha-2; missing/invalid countries
map to the ``XX`` bucket. Country artifacts are pure, deterministic,
in-memory slices of the same already-ranked proxies used by combined and
protocol feeds: no extra DNS, GeoIP, health check, DB, or network I/O.

Contracts under test:

- Flag conversion: ``DE`` -> ``🇩🇪``; ``XX``/invalid -> ``🌐``.
- Country normalization: uppercase/lowercase valid codes -> one bucket; None /
  invalid values -> the ``XX`` bucket.
- Grouping: each selected proxy appears in exactly one country directory;
  every directory feed is a subset of the combined feed.
- Deterministic ordering: index entries and directories ordered by ISO code;
  rank order preserved inside every group.
- Country README / index README content, plain/base64 exact parity, and
  per-protocol feeds only for non-empty protocols; empty countries (no ``XX``
  directory when nothing is unknown) are never emitted.
- Existing combined/protocol feeds are byte-for-byte unchanged (additive-only,
  captured as a regression test).
- Generated artifact paths are always traversal-safe.
- Country generation performs no network/I/O and the pipeline re-runs no
  health/GeoIP/DNS work; repeated generation is byte-identical.

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
    COUNTRIES_DIR,
    COUNTRY_UNKNOWN_BUCKET,
    SubscriptionFormat,
    build_country_artifacts,
    build_protocol_subscriptions,
    build_subscription,
    country_bucket,
    country_code_to_flag,
    country_index_path,
    country_protocol_path,
    default_filename,
)
from proxyaggregator.publishing.models import RankedProxy, Subscription
from proxyaggregator.publishing.publisher import (
    DEFAULT_FILENAMES,
    _validate_artifact_path,
    canonical_artifact_filenames,
    country_all_path,
    country_readme_path,
    default_protocol_filename,
)

UUID = "d98d1c36-ccc8-4c77-9e9f-81c1b7584277"

VLESS = (
    f"vless://{UUID}@vless.example.com:443"
    "?network=ws&security=tls&sni=example.com&host=example.com&path=%2Fws#VLESSNode"
)
SS = (
    "ss://"
    + base64.b64encode(b"aes-128-gcm:passwd").decode("ascii")
    + "@ss.example.com:8388#SSNode"
)
SOCKS5 = "socks5://user:p%40ss@proxy.example.com:1080"
HTTP = "http://user:p%40ss@proxy.example.com:8080"


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


def _artifacts(
    candidates: tuple[RankedProxy, ...], *, max_items: int | None = None
) -> dict[str, Subscription]:
    return dict(build_country_artifacts(candidates, max_items=max_items))


# A. Flag conversion -----------------------------------------------------------


class TestCountryFlag:
    @pytest.mark.parametrize(
        ("code", "flag"),
        [
            ("DE", "\U0001f1e9\U0001f1ea"),
            ("de", "\U0001f1e9\U0001f1ea"),
            (" US ", "\U0001f1fa\U0001f1f8"),
            ("GB", "\U0001f1ec\U0001f1e7"),
            ("XX", "\U0001f310"),
        ],
    )
    def test_valid_codes_map_to_regional_indicator_flags(self, code, flag):
        assert country_code_to_flag(code) == flag

    @pytest.mark.parametrize(
        "value",
        [None, "", "D", "DEU", "DE1", "DÉ", "123", "../US", 123, True],
    )
    def test_invalid_values_and_unknown_bucket_use_globe(self, value):
        assert country_code_to_flag(value) == "\U0001f310"
        assert country_code_to_flag(COUNTRY_UNKNOWN_BUCKET) == "\U0001f310"


# B. Country normalization -----------------------------------------------------


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
    def test_valid_codes_normalize_to_a_single_bucket(self, value, bucket):
        assert country_bucket(value) == bucket

    @pytest.mark.parametrize(
        "value",
        [None, "", "D", "DEU", "DE1", "DÉ", "123", "../US", 123, True],
    )
    def test_invalid_values_map_to_xx_bucket(self, value):
        assert country_bucket(value) == COUNTRY_UNKNOWN_BUCKET

    def test_uppercase_feed_directories_group_into_uppercase_dir(self):
        candidates = [_ranked(1, "vless", VLESS, "vless.example.com", 443, country_code="DE")]
        paths = {path for path, _feed in build_country_artifacts(candidates)}
        assert "countries/DE/all.txt" in paths
        assert "countries/DE/vless.txt" in paths

    def test_missing_country_lands_in_xx_directory(self):
        candidates = [_ranked(1, "vless", VLESS, "vless.example.com", 443, country_code=None)]
        artifacts = _artifacts(candidates)
        assert "countries/XX/all.txt" in artifacts
        assert artifacts["countries/XX/all.txt"].count == 1


# C. Grouping -----------------------------------------------------------------


class TestGrouping:
    def test_grouping_counts(self):
        artifacts = _artifacts(_country_candidates())
        assert artifacts["countries/US/all.txt"].count == 3
        assert artifacts["countries/DE/all.txt"].count == 1
        assert artifacts["countries/XX/all.txt"].count == 1

    def test_country_feed_holds_multiple_protocols(self):
        candidates = [
            _ranked(1, "vless", VLESS, "vless.example.com", 443, country_code="US"),
            _ranked(2, "ss", SS, "ss.example.com", 8388, country_code="US"),
            _ranked(3, "http", HTTP, "proxy.example.com", 8080, country_code="US"),
        ]
        artifacts = _artifacts(candidates)
        assert artifacts["countries/US/all.txt"].count == 3
        protocols = {
            _parse(line).protocol for line in artifacts["countries/US/all.txt"].content.splitlines()
        }
        assert protocols == {"vless", "ss", "http"}

    def test_every_country_line_is_in_the_combined_feed(self):
        candidates = _country_candidates()
        combined_lines = set(build_subscription(candidates).content.splitlines())
        for path, feed in build_country_artifacts(candidates):
            if feed.format is not SubscriptionFormat.PLAIN or path.endswith("README.md"):
                continue
            assert set(feed.content.splitlines()) <= combined_lines


# D. Ordering -----------------------------------------------------------------


class TestOrdering:
    def test_directories_and_index_ordered_by_iso_code(self):
        candidates = [
            _ranked(1, "ss", SS, "ss.example.com", 8388, country_code="GB"),
            _ranked(2, "http", HTTP, "proxy.example.com", 8080, country_code="DE"),
            _ranked(3, "vless", VLESS, "vless.example.com", 443, country_code="US"),
        ]
        paths = [path for path, _feed in build_country_artifacts(candidates)]
        assert paths[0] == "countries/README.md"
        dir_order = []
        for path in paths:
            parts = path.split("/")
            if len(parts) == 3 and dir_order[-1:] != [parts[1]]:
                dir_order.append(parts[1])
        assert dir_order == ["DE", "GB", "US"]

        index = _artifacts(candidates)["countries/README.md"].content
        codes = [
            line.split(" ", 1)[1].split(" ")[0] for line in index.splitlines() if "[Open]" in line
        ]
        assert codes == ["DE", "GB", "US"]

    def test_rank_order_preserved_within_group(self):
        http_8080 = "http://user:p%40ss@proxy.example.com:8080"
        http_8081 = "http://user:p%40ss@proxy.example.com:8081"
        candidates = [
            _ranked(1, "http", http_8080, "proxy.example.com", 8080, country_code="US"),
            _ranked(2, "http", http_8081, "proxy.example.com", 8081, country_code="US"),
            _ranked(3, "http", http_8080, "proxy.example.com", 8080),
        ]
        artifacts = _artifacts(candidates)
        lines = [
            _parse(line).port for line in artifacts["countries/US/all.txt"].content.splitlines()
        ]
        assert lines == [8080, 8081]


# E. Directory artifacts: all + protocol feeds --------------------------------


class TestDirectoryFeeds:
    def test_all_plain_and_base64_parity(self):
        artifacts = _artifacts(_country_candidates())
        for path, feed in artifacts.items():
            if path.endswith("README.md"):
                assert feed.format is SubscriptionFormat.PLAIN
                assert feed.count == 0
                continue
            assert feed.count >= 1
            if feed.format is SubscriptionFormat.BASE64:
                plain_path = path.replace("-base64.txt", ".txt")
                decoded = base64.b64decode(feed.content.encode("ascii")).decode("utf-8")
                assert decoded == artifacts[plain_path].content

    def test_protocol_feed_grouped_in_directory(self):
        artifacts = _artifacts(_country_candidates())
        assert artifacts["countries/DE/shadowsocks.txt"].count == 1
        assert artifacts["countries/US/shadowsocks.txt"].count == 1
        assert artifacts["countries/US/vless.txt"].count == 1
        assert artifacts["countries/US/http.txt"].count == 1
        assert artifacts["countries/XX/socks5.txt"].count == 1

    def test_protocol_stem_map_respected_in_directory(self):
        candidates = [_ranked(1, "ss", SS, "ss.example.com", 8388, country_code="US")]
        artifacts = _artifacts(candidates)
        assert "countries/US/shadowsocks.txt" in artifacts
        assert "countries/US/shadowsocks-base64.txt" in artifacts

    def test_empty_protocols_omitted(self):
        candidates = [_ranked(1, "ss", SS, "ss.example.com", 8388, country_code="DE")]
        paths = {path for path, _feed in build_country_artifacts(candidates)}
        de_files = {path for path in paths if path.startswith("countries/DE/")}
        assert de_files == {
            "countries/DE/README.md",
            "countries/DE/all.txt",
            "countries/DE/all-base64.txt",
            "countries/DE/shadowsocks.txt",
            "countries/DE/shadowsocks-base64.txt",
        }

    def test_empty_countries_omitted(self):
        known = [
            _ranked(1, "vless", VLESS, "vless.example.com", 443, country_code="US"),
            _ranked(2, "ss", SS, "ss.example.com", 8388, country_code="DE"),
        ]
        paths = {path.split("/")[1] for path, _f in build_country_artifacts(known) if "/" in path}
        assert "XX" not in paths
        index = _artifacts(known)["countries/README.md"].content
        assert "XX" not in index
        unknown = [
            *known,
            _ranked(3, "http", HTTP, "proxy.example.com", 8080, country_code=None),
        ]
        assert "XX" in {
            path.split("/")[1] for path, _f in build_country_artifacts(unknown) if "/" in path
        }

    def test_protocol_only_generated_when_candidates_exist(self):
        candidates = [
            _ranked(1, "socks5", SOCKS5, "proxy.example.com", 1080, country_code="US"),
            _ranked(2, "ss", SS, "ss.example.com", 8388, country_code="US"),
        ]
        paths = {path for path, _feed in build_country_artifacts(candidates)}
        assert "countries/US/socks5.txt" in paths
        assert "countries/US/shadowsocks.txt" in paths
        assert "countries/US/vless.txt" not in paths


# F. Generated READMEs ---------------------------------------------------------


class TestGeneratedReadmes:
    def test_country_readme_content(self):
        candidates = [_ranked(1, "ss", SS, "ss.example.com", 8388, country_code="DE")]
        content = _artifacts(candidates)["countries/DE/README.md"].content
        assert content == (
            "# \U0001f1e9\U0001f1ea DE\n"
            "\n"
            "1 healthy proxy.\n"
            "\n"
            "## All protocols\n"
            "\n"
            "- [Plain](./all.txt)\n"
            "- [Base64](./all-base64.txt)\n"
            "\n"
            "## Protocols\n"
            "\n"
            "- [Shadowsocks](./shadowsocks.txt)\n"
            "- [Shadowsocks Base64](./shadowsocks-base64.txt)\n"
        )

    def test_country_readme_single_proxy_grammar(self):
        candidates = [_ranked(1, "vless", VLESS, "vless.example.com", 443, country_code="US")]
        content = _artifacts(candidates)["countries/US/README.md"].content
        assert "1 healthy proxy." in content

    def test_country_readme_protocol_section_only_for_present_protocols(self):
        candidates = [_ranked(1, "http", HTTP, "proxy.example.com", 8080, country_code="US")]
        content = _artifacts(candidates)["countries/US/README.md"].content
        assert "## Protocols" in content
        assert "- [HTTP](./http.txt)" in content
        assert "- [VLESS](./vless.txt)" not in content

    def test_country_readme_manual_protocol_display_map(self):
        candidates = [_ranked(1, "ss", SS, "ss.example.com", 8388, country_code="US")]
        content = _artifacts(candidates)["countries/US/README.md"].content
        assert "- [Shadowsocks](./shadowsocks.txt)" in content

    def test_index_readme_lists_every_country_with_count_and_link(self):
        index = _artifacts(_country_candidates())["countries/README.md"].content
        assert index.startswith("# \U0001f30d ProxyAggregator \u2014 Proxies by Country\n\n")
        assert "\U0001f1e9\U0001f1ea DE \u2014 1 proxy \u2014 [Open](./DE/)" in index
        assert "\U0001f1fa\U0001f1f8 US \u2014 3 proxies \u2014 [Open](./US/)" in index
        assert "\U0001f310 XX \u2014 1 proxy \u2014 [Open](./XX/)" in index

    def test_index_protocol_files_exist_for_every_indexed_country(self):
        artifacts = _artifacts(_country_candidates())
        index = artifacts["countries/README.md"].content
        codes = [
            line.split(" ", 1)[1].split(" ")[0] for line in index.splitlines() if "[Open]" in line
        ]
        for code in codes:
            assert f"countries/{code}/README.md" in artifacts
            assert f"countries/{code}/all.txt" in artifacts

    def test_index_count_matches_all_feed(self):
        artifacts = _artifacts(_country_candidates())
        index = artifacts["countries/README.md"].content
        for line in index.splitlines():
            if "[Open]" not in line:
                continue
            code = line.split(" ", 1)[1].split(" ")[0]
            count = line.split("\u2014 ")[1].split(" ")[0]
            assert artifacts[f"countries/{code}/all.txt"].count == int(count)


# G. Determinism + path safety -------------------------------------------------


class TestDeterminismAndPathSafety:
    def test_repeated_generation_is_byte_identical(self):
        first = build_country_artifacts(_country_candidates())
        second = build_country_artifacts(_country_candidates())
        assert [(path, feed.content) for path, feed in first] == [
            (path, feed.content) for path, feed in second
        ]

    def test_unsafe_country_values_never_produce_unsafe_paths(self):
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
            path = country_all_path(value, SubscriptionFormat.PLAIN)
            assert path == "countries/XX/all.txt"
            _validate_artifact_path(path)
            _validate_artifact_path(country_readme_path(value))
            _validate_artifact_path(country_protocol_path("vless", value, SubscriptionFormat.PLAIN))

    def test_generated_paths_all_pass_validation(self):
        for path, _feed in build_country_artifacts(_country_candidates()):
            _validate_artifact_path(path)

    def test_canonical_set_covers_generated_paths(self):
        canonical = canonical_artifact_filenames()
        for path, _feed in build_country_artifacts(_country_candidates()):
            assert path in canonical


# H. Backward compatibility regression ----------------------------------------


class TestBackwardCompat:
    def test_existing_feeds_byte_identical_when_country_feeds_enabled(self):
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

    def test_default_filename_mappings_untouched(self):
        assert DEFAULT_FILENAMES[SubscriptionFormat.PLAIN] == "proxyaggregator.txt"
        assert DEFAULT_FILENAMES[SubscriptionFormat.BASE64] == "proxyaggregator-base64.txt"
        assert DEFAULT_FILENAMES[SubscriptionFormat.JSON] == "proxyaggregator.json"
        assert default_protocol_filename("ss", SubscriptionFormat.PLAIN) == "shadowsocks.txt"


# I. Purity: no network, no I/O -------------------------------------------------


class TestPurity:
    def test_feed_modules_have_no_network_or_db_touchpoints(self):
        import proxyaggregator.publishing.countries as countries_module
        import proxyaggregator.publishing.feeds as feeds_module

        for source in (inspect.getsource(countries_module), inspect.getsource(feeds_module)):
            for forbidden in ("socket.", "subprocess", "sqlalchemy", "requests", "getaddrinfo"):
                assert forbidden not in source

    def test_country_generation_does_not_touch_network_or_files(self, monkeypatch, tmp_path):
        import socket as socket_module

        dns_calls: list[str] = []
        monkeypatch.setattr(
            socket_module, "getaddrinfo", lambda *a, **k: dns_calls.append("dns") or []
        )
        candidates = _country_candidates()
        build_country_artifacts(candidates)
        assert dns_calls == []
        assert list(tmp_path.iterdir()) == []


# J. Pipeline purity: health/GeoIP/DNS run exactly once -------------------------

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

    def test_country_directories_generated_end_to_end(self, db_session, tmp_path):
        stats = self._run(db_session, tmp_path, _enricher, _CountingHealthRunner())
        expected = {
            "countries/README.md",
            "countries/US/README.md",
            "countries/US/all.txt",
            "countries/US/all-base64.txt",
            "countries/US/http.txt",
            "countries/US/http-base64.txt",
            "countries/US/socks5.txt",
            "countries/US/socks5-base64.txt",
            "countries/US/vless.txt",
            "countries/US/vless-base64.txt",
        }
        out = tmp_path / "out"
        on_disk = {path for path in out.rglob("*") if path.is_file()}
        assert on_disk >= {out / name for name in expected}
        countries_dir = out / COUNTRIES_DIR
        assert countries_dir.is_dir()
        assert {p.name for p in countries_dir.iterdir()} == {"README.md", "US"}
        assert stats.published_artifacts == 20
        assert COUNTRY_UNKNOWN_BUCKET.upper() not in {p.name for p in countries_dir.iterdir()}
        assert (
            (countries_dir / "README.md")
            .read_text()
            .startswith("# \U0001f30d ProxyAggregator \u2014 Proxies by Country")
        )


# K. Pipeline-level x-country dependency tests ----------------------------------


class TestCountryProtocolPaths:
    def test_country_protocol_path_shape(self):
        assert country_protocol_path("vless", "DE", SubscriptionFormat.PLAIN) == (
            "countries/DE/vless.txt"
        )
        assert country_protocol_path("ss", "DE", SubscriptionFormat.BASE64) == (
            "countries/DE/shadowsocks-base64.txt"
        )
        assert country_protocol_path("vless", None, SubscriptionFormat.PLAIN) == (
            "countries/XX/vless.txt"
        )

    def test_country_protocol_path_json_rejected(self):
        with pytest.raises(ValueError):
            country_protocol_path("vless", "DE", SubscriptionFormat.JSON)

    def test_country_protocol_path_unknown_protocol_rejected(self):
        with pytest.raises(ValueError):
            country_protocol_path("wireguard", "DE", SubscriptionFormat.PLAIN)

    def test_country_index_constant_is_used_by_builders(self):
        assert country_index_path() == "countries/README.md"
