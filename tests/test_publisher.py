"""Phase 9 tests: deterministic GitHub publisher artifacts.

Phase 9 writes generated subscription feeds (plain, base64, JSON) to an
output directory and produces a deterministic release manifest. All output
is byte-exact and reproducible: no timestamps, random values, hostnames,
environment info, or credentials ever enter file contents or errors.
"""

from __future__ import annotations

import base64
import hashlib
import json

import pytest
from pydantic import ValidationError

import proxyaggregator.publishing.publisher as publisher_module
from proxyaggregator.publishing import (
    RankedProxy,
    Subscription,
    SubscriptionFormat,
    build_subscription,
)
from proxyaggregator.publishing.naming import COUNTRY_UNKNOWN_BUCKET
from proxyaggregator.publishing.publisher import (
    DEFAULT_FILENAMES,
    MANIFEST_FILENAME,
    PublishError,
    ReleaseVerificationError,
    SubscriptionRelease,
    build_release_manifest,
    canonical_artifact_filenames,
    default_country_filename,
    default_filename,
    default_protocol_country_filename,
    default_protocol_filename,
    publish_release,
    publish_subscriptions,
    release_metadata,
    verify_release,
    write_artifact,
    write_release_manifest,
)
from proxyaggregator.publishing.samples import build_demo_subscriptions

PLAIN_NAME = DEFAULT_FILENAMES[SubscriptionFormat.PLAIN]
B64_NAME = DEFAULT_FILENAMES[SubscriptionFormat.BASE64]
JSON_NAME = DEFAULT_FILENAMES[SubscriptionFormat.JSON]

DEMO_FEED_COUNT = 3 + 2 * len(publisher_module.DEFAULT_PROTOCOL_FILENAME_STEMS)


class TestWriteArtifact:
    """Deterministic, atomic, traversal-safe file publishing."""

    def test_writes_utf8_bytes_exactly(self, tmp_path):
        content = "vless://a@b.example.com:443#Node\n"
        written = write_artifact("plain.txt", content, tmp_path)
        assert written == tmp_path / "plain.txt"
        assert (tmp_path / "plain.txt").read_bytes() == content.encode("utf-8")

    def test_accepts_bytes_passthrough(self, tmp_path):
        data = b"raw\0bytes\xff"
        write_artifact("bin.dat", data, tmp_path)
        assert (tmp_path / "bin.dat").read_bytes() == data

    def test_repeated_write_is_byte_identical(self, tmp_path):
        content = "trojan://pw@x.example.com:443\n"
        write_artifact("feed.txt", content, tmp_path)
        write_artifact("feed.txt", content, tmp_path)
        assert (tmp_path / "feed.txt").read_bytes() == content.encode("utf-8")

    def test_overwrite_replaces_previous_content(self, tmp_path):
        write_artifact("feed.txt", "old", tmp_path)
        write_artifact("feed.txt", "new", tmp_path)
        assert (tmp_path / "feed.txt").read_bytes() == b"new"

    def test_output_dir_is_created_when_missing(self, tmp_path):
        out = tmp_path / "nested" / "deep"
        write_artifact("feed.txt", "x", out)
        assert (out / "feed.txt").exists()

    def test_no_temp_files_left_on_success(self, tmp_path):
        write_artifact("feed.txt", "x", tmp_path)
        leftovers = [p for p in tmp_path.iterdir() if ".tmp" in p.name]
        assert leftovers == []

    def test_no_temp_files_left_on_failure(self, tmp_path):
        with pytest.raises(PublishError):
            write_artifact("../escape.txt", "x", tmp_path)
        assert list(tmp_path.iterdir()) == []


class TestPathTraversal:
    """Filenames must be a single plain component; anything else is rejected."""

    @pytest.mark.parametrize(
        "name",
        [
            "../escape.txt",
            "a/b.txt",
            "x/../y.txt",
            "/absolute.txt",
            ".",
            "..",
            "",
            "a\x00b.txt",
            "sub/dir/feed.txt",
        ],
    )
    def test_rejects_dangerous_filenames(self, tmp_path, name):
        with pytest.raises(PublishError):
            write_artifact(name, "content", tmp_path)

    def test_rejects_without_creating_files(self, tmp_path):
        with pytest.raises(PublishError):
            write_artifact("../escape.txt", "x", tmp_path)
        assert not (tmp_path.parent / "escape.txt").exists()
        assert list(tmp_path.iterdir()) == []

    def test_reject_reason_is_stable_token(self, tmp_path):
        with pytest.raises(PublishError) as exc_info:
            write_artifact("a/b.txt", "x", tmp_path)
        assert exc_info.value.reason == "path_separator_in_filename"
        with pytest.raises(PublishError) as exc_info:
            write_artifact("", "x", tmp_path)
        assert exc_info.value.reason == "empty_filename"
        with pytest.raises(PublishError) as exc_info:
            write_artifact("a\x00b", "x", tmp_path)
        assert exc_info.value.reason == "nul_in_filename"


class TestManifest:
    """Deterministic release metadata; never any time/random/host info."""

    def _entries(self) -> list[SubscriptionRelease]:
        data = b"proxy://a@b.example.com:443\n"
        return [
            release_metadata(JSON_NAME, SubscriptionFormat.JSON, 3, data),
            release_metadata(B64_NAME, SubscriptionFormat.BASE64, 3, data),
            release_metadata(PLAIN_NAME, SubscriptionFormat.PLAIN, 3, data),
        ]

    def test_sorted_by_filename_regardless_of_input_order(self):
        manifest = build_release_manifest(self._entries())
        names = [item["filename"] for item in json.loads(manifest)]
        assert names == sorted(names)

    def test_exact_fields_present_and_only_those(self):
        payload = json.loads(build_release_manifest(self._entries()))
        first = payload[0]
        assert set(first) == {"filename", "format", "count", "byte_size", "sha256"}

    def test_deterministic_identical_runs(self):
        e1 = self._entries()
        e2 = self._entries()
        assert build_release_manifest(e1) == build_release_manifest(e2)

    def test_sha256_and_byte_size_match_written_bytes(self):
        data = b"vless://x@y.example.com:443\n"
        entry = release_metadata("feed.txt", SubscriptionFormat.JSON, 1, data)
        assert entry.byte_size == len(data)
        assert entry.sha256 == hashlib.sha256(data).hexdigest()

    def test_no_runtime_metadata_keys(self):
        payload = json.loads(build_release_manifest(self._entries()))
        for item in payload:
            assert "time" not in item
            assert "timestamp" not in item
            assert "uuid" not in item
            assert "run_id" not in item
            assert "hostname" not in item
            assert "environment" not in item

    def test_manifest_written_deterministically(self, tmp_path):
        entries = self._entries()
        manifest = build_release_manifest(entries)
        path = write_release_manifest(manifest, tmp_path)
        assert path == tmp_path / MANIFEST_FILENAME
        assert (tmp_path / MANIFEST_FILENAME).read_bytes() == manifest.encode("utf-8")

    def test_empty_entries_manifest(self):
        assert build_release_manifest([]) == "[]"


class TestReleaseMetadata:
    def test_shape(self):
        entry = release_metadata("feed.txt", SubscriptionFormat.PLAIN, 5, b"abc")
        assert entry.filename == "feed.txt"
        assert entry.format is SubscriptionFormat.PLAIN
        assert entry.count == 5
        assert entry.byte_size == 3
        assert len(entry.sha256) == 64

    def test_is_frozen_model(self):
        entry = release_metadata("feed.txt", SubscriptionFormat.PLAIN, 0, b"")
        with pytest.raises(ValidationError):
            entry.count = 1


class TestPublishSubscriptions:
    """High-level: write feeds + collect release metadata."""

    def test_writes_all_feeds_and_returns_entries(self, tmp_path):
        plain = build_subscription([], format=SubscriptionFormat.PLAIN)
        b64 = build_subscription([], format=SubscriptionFormat.BASE64)
        json_feed = build_subscription([], format=SubscriptionFormat.JSON)
        subs = [
            (PLAIN_NAME, plain),
            (B64_NAME, b64),
            (JSON_NAME, json_feed),
        ]
        entries = publish_subscriptions(subs, tmp_path)
        assert len(entries) == 3
        assert [e.filename for e in entries] == [PLAIN_NAME, B64_NAME, JSON_NAME]
        assert (tmp_path / PLAIN_NAME).read_bytes() == b""
        assert (tmp_path / B64_NAME).read_bytes() == b""
        assert (tmp_path / JSON_NAME).read_bytes() == b"[]"

    def test_publish_is_byte_identical_across_runs(self, tmp_path):
        cands = build_demo_subscriptions()
        publish_subscriptions(cands, tmp_path)
        first = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        publish_subscriptions(cands, tmp_path)
        second = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        assert first == second

    def test_empty_feed_produces_zero_byte_plain_file(self, tmp_path):
        plain = build_subscription([], format=SubscriptionFormat.PLAIN)
        entries = publish_subscriptions([(PLAIN_NAME, plain)], tmp_path)
        assert entries[0].count == 0
        assert (tmp_path / PLAIN_NAME).read_bytes() == b""


class TestPublishErrors:
    """Errors are constant and never echo feed content or credentials."""

    def test_publish_error_never_echoes_content(self, tmp_path):
        secret = "ss://c3VwZXJzZWNyZXQ@host.example.com:8388#SecretNode"
        with pytest.raises(PublishError) as exc_info:
            write_artifact("../up.txt", secret, tmp_path)
        message = str(exc_info.value)
        assert secret not in message
        assert "supersecret" not in message
        assert message.startswith("cannot publish")

    def test_error_carries_stable_reason(self, tmp_path):
        with pytest.raises(PublishError) as exc_info:
            write_artifact("a/../b.txt", "x", tmp_path)
        assert exc_info.value.filename == "a/../b.txt"
        assert exc_info.value.reason == "path_separator_in_filename"


class TestDefaultFilenames:
    def test_mapping_covers_all_formats(self):
        assert set(DEFAULT_FILENAMES) == set(SubscriptionFormat)
        assert DEFAULT_FILENAMES[SubscriptionFormat.PLAIN] == "proxyaggregator.txt"
        assert DEFAULT_FILENAMES[SubscriptionFormat.BASE64] == "proxyaggregator-base64.txt"
        assert DEFAULT_FILENAMES[SubscriptionFormat.JSON] == "proxyaggregator.json"

    def test_default_filename_backs_manifest_entries(self):
        for fmt in SubscriptionFormat:
            assert default_filename(fmt) == DEFAULT_FILENAMES[fmt]

    def test_unknown_format_rejected(self):
        with pytest.raises(ValueError):
            default_filename("clash")


class TestLocationFilenames:
    """Phase 17: canonical country / protocol+country artifact names."""

    def test_country_filename_shapes(self):
        assert default_country_filename("DE", SubscriptionFormat.PLAIN) == "country-de.txt"
        assert default_country_filename("DE", SubscriptionFormat.BASE64) == "country-de-base64.txt"
        assert default_country_filename(None, SubscriptionFormat.PLAIN) == "country-xx.txt"

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
    def test_protocol_country_filename_shapes(self, protocol, stem):
        assert (
            default_protocol_country_filename(protocol, "US", SubscriptionFormat.PLAIN)
            == f"{stem}-us.txt"
        )
        assert (
            default_protocol_country_filename(protocol, "US", SubscriptionFormat.BASE64)
            == f"{stem}-us-base64.txt"
        )

    def test_unknown_protocol_rejected(self):
        with pytest.raises(ValueError):
            default_protocol_country_filename("wireguard", "US", SubscriptionFormat.PLAIN)

    def test_json_rejected_for_location_names(self):
        with pytest.raises(ValueError):
            default_country_filename("DE", SubscriptionFormat.JSON)
        with pytest.raises(ValueError):
            default_protocol_country_filename("vless", "DE", SubscriptionFormat.JSON)

    def test_generated_names_pass_safety_validation(self, tmp_path):
        names = [
            default_country_filename("DE", SubscriptionFormat.PLAIN),
            default_country_filename("DE", SubscriptionFormat.BASE64),
            default_country_filename(None, SubscriptionFormat.PLAIN),
            default_protocol_country_filename("ss", "US", SubscriptionFormat.PLAIN),
            default_protocol_country_filename("ss", "US", SubscriptionFormat.BASE64),
        ]
        for name in names:
            write_artifact(name, "x", tmp_path)
            assert (tmp_path / name).read_bytes() == b"x"
            assert (tmp_path / name).name == name


class TestDemoSamples:
    """Local dry-run feeds are deterministic and use example.com only."""

    def test_three_feeds_in_canonical_order(self):
        feeds = build_demo_subscriptions()
        names = [name for name, _ in feeds]
        assert names[:3] == [PLAIN_NAME, B64_NAME, JSON_NAME]
        protocol_names = names[3:]
        assert len(protocol_names) == 2 * len(publisher_module.DEFAULT_PROTOCOL_FILENAME_STEMS)
        assert protocol_names[::2] == [
            default_protocol_filename(protocol, SubscriptionFormat.PLAIN)
            for protocol in publisher_module.SUPPORTED_PROTOCOLS
        ]
        assert protocol_names[1::2] == [
            default_protocol_filename(protocol, SubscriptionFormat.BASE64)
            for protocol in publisher_module.SUPPORTED_PROTOCOLS
        ]

    def test_deterministic_across_calls(self):
        a = build_demo_subscriptions()
        b = build_demo_subscriptions()
        assert [(n, s.content) for n, s in a] == [(n, s.content) for n, s in b]

    def test_sample_hosts_are_synthetic(self):
        feeds = build_demo_subscriptions()
        plain = next(s for n, s in feeds if n == PLAIN_NAME)
        assert "example.com" in plain.content
        assert "proxyaggregator.txt" in plain.content or plain.count >= 0

    def test_plain_feed_is_line_terminated(self):
        feeds = build_demo_subscriptions()
        plain = next(s for n, s in feeds if n == PLAIN_NAME)
        lines = plain.content.splitlines()
        assert len(lines) == plain.count
        assert plain.content.endswith("\n")

    def test_publish_demo_end_to_end(self, tmp_path):
        entries = publish_subscriptions(build_demo_subscriptions(), tmp_path)
        assert len(entries) == DEMO_FEED_COUNT
        manifest = build_release_manifest(entries)
        payload = json.loads(manifest)
        total = sum(item["byte_size"] for item in payload)
        assert total > 0
        assert all(item["count"] > 0 for item in payload)

    def test_max_items_limits_emitted_proxies(self):
        feeds = build_demo_subscriptions(max_items=1)
        plain = next(s for n, s in feeds if n == PLAIN_NAME)
        assert plain.count == 1
        assert len(plain.content.splitlines()) == 1


class TestNoGIBits:
    """Nothing in publisher output references ephemeral environments."""

    def test_manifest_json_has_no_trailing_newline_or_bom(self, tmp_path):
        manifest = build_release_manifest([])
        assert not manifest.endswith("\n")
        assert not manifest.startswith("\ufeff")

    def test_releases_do_not_export_scores_or_ranks(self, tmp_path):
        entries = publish_subscriptions(build_demo_subscriptions(), tmp_path)
        payload = json.loads(build_release_manifest(entries))
        for item in payload:
            assert "score" not in item
            assert "rank" not in item
            assert "proxy_config_id" not in item
            assert "raw_uri" not in item
            assert "content_hash" not in item


def test_written_files_byte_exact_with_feeds(tmp_path):
    """Manifest byte_size + sha256 match the actual written bytes."""
    feeds = build_demo_subscriptions()
    entries = publish_subscriptions(feeds, tmp_path)
    for entry, (name, sub) in zip(entries, feeds, strict=True):
        path = tmp_path / name
        assert path.read_bytes() == sub.content.encode("utf-8")
        assert entry.byte_size == path.stat().st_size
        assert entry.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


class TestCanonicalArtifactFilenames:
    """The cleanup surface is exactly the artifacts the publisher can own."""

    def test_covers_default_formats_and_manifest(self):
        names = canonical_artifact_filenames()
        assert set(DEFAULT_FILENAMES.values()) <= names
        assert MANIFEST_FILENAME in names

    def test_covers_every_supported_protocol_in_both_formats(self):
        names = canonical_artifact_filenames()
        for protocol in publisher_module.SUPPORTED_PROTOCOLS:
            assert default_protocol_filename(protocol, SubscriptionFormat.PLAIN) in names
            assert default_protocol_filename(protocol, SubscriptionFormat.BASE64) in names

    def test_covers_country_and_protocol_country_location_names(self):
        names = canonical_artifact_filenames()
        for bucket in ("de", "us", "gb", "xx"):
            assert default_country_filename(bucket, SubscriptionFormat.PLAIN) in names
            assert default_country_filename(bucket, SubscriptionFormat.BASE64) in names
            assert (
                default_protocol_country_filename("vless", bucket, SubscriptionFormat.PLAIN)
                in names
            )
            assert (
                default_protocol_country_filename("ss", bucket, SubscriptionFormat.BASE64)
                == f"shadowsocks-{bucket}-base64.txt"
            )
            assert f"shadowsocks-{bucket}-base64.txt" in names

    def test_boundary_2_letter_codes_and_xx_are_prunable(self):
        names = canonical_artifact_filenames()
        for bucket in ("aa", "zz", "de", COUNTRY_UNKNOWN_BUCKET):
            assert f"country-{bucket}.txt" in names
            assert f"vless-{bucket}.txt" in names

    def test_never_touches_unrelated_names(self):
        names = canonical_artifact_filenames()
        for bogus in ("README.md", "proxyaggregator.db", "notes.txt", "output"):
            assert bogus not in names
        assert "country.txt" not in names
        assert "country-de.json" not in names
        assert "vless-USA.txt" not in names
        assert "vless-us-extra.txt" not in names


class TestPublishRelease:
    """Whole-set staged atomic publish plus stale-artifact pruning (Phase 16)."""

    def test_publishes_feeds_and_manifest(self, tmp_path):
        plain = build_subscription([], format=SubscriptionFormat.PLAIN)
        b64 = build_subscription([], format=SubscriptionFormat.BASE64)
        entries = publish_release([(PLAIN_NAME, plain), (B64_NAME, b64)], tmp_path)
        assert [e.filename for e in entries] == [PLAIN_NAME, B64_NAME]
        assert (tmp_path / PLAIN_NAME).read_bytes() == b""
        assert (tmp_path / B64_NAME).read_bytes() == b""
        payload = json.loads((tmp_path / MANIFEST_FILENAME).read_text(encoding="utf-8"))
        assert [item["filename"] for item in payload] == sorted([PLAIN_NAME, B64_NAME])

    def test_second_run_is_byte_identical(self, tmp_path):
        feeds = build_demo_subscriptions()
        publish_release(feeds, tmp_path)
        first = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        publish_release(feeds, tmp_path)
        second = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        assert sorted(first) == sorted(second)
        for name, data in first.items():
            assert data == second[name]

    def test_manifest_promoted_last(self):
        items = [
            (JSON_NAME, b"[]"),
            (PLAIN_NAME, b"a"),
            (B64_NAME, b"b"),
            (MANIFEST_FILENAME, b"{}"),
        ]
        ordered = publisher_module._latest_staged_write(items)
        assert [name for name, _ in ordered][-1] == MANIFEST_FILENAME
        assert [name for name, _ in ordered][:-1] == sorted([PLAIN_NAME, B64_NAME, JSON_NAME])

    def test_no_staging_dir_left_behind(self, tmp_path):
        publish_release(build_demo_subscriptions(), tmp_path)
        leftovers = [p for p in tmp_path.parent.iterdir() if ".staging-" in p.name]
        assert leftovers == []

    def test_prunes_stale_canonical_artifacts_only(self, tmp_path):
        stale = ["hysteria.txt", "hysteria-base64.txt", "http.txt", "http-base64.txt"]
        for name in stale:
            (tmp_path / name).write_text("stale-bytes")
        (tmp_path / "unrelated.txt").write_text("keep me")
        (tmp_path / "proxyaggregator.db").write_bytes(b"sqlite")

        feed = build_subscription([], format=SubscriptionFormat.PLAIN)
        entries = publish_release([(PLAIN_NAME, feed)], tmp_path)
        assert [e.filename for e in entries] == [PLAIN_NAME]

        for name in stale:
            assert not (tmp_path / name).exists(), name
        assert (tmp_path / "unrelated.txt").read_text() == "keep me"
        assert (tmp_path / "proxyaggregator.db").read_bytes() == b"sqlite"
        assert (tmp_path / PLAIN_NAME).exists()
        assert (tmp_path / MANIFEST_FILENAME).exists()

    def test_prunes_stale_location_artifacts(self, tmp_path):
        stale_location = [
            default_country_filename("de", SubscriptionFormat.PLAIN),
            default_country_filename("de", SubscriptionFormat.BASE64),
            default_protocol_country_filename("vless", "de", SubscriptionFormat.PLAIN),
            default_protocol_country_filename("vless", "de", SubscriptionFormat.BASE64),
            default_protocol_country_filename("ss", "us", SubscriptionFormat.BASE64),
        ]
        for name in stale_location:
            (tmp_path / name).write_text("stale-bytes")
        (tmp_path / "README.md").write_text("# readme")
        (tmp_path / "proxyaggregator.db").write_bytes(b"sqlite")

        feed = build_subscription([], format=SubscriptionFormat.PLAIN)
        publish_release([(PLAIN_NAME, feed)], tmp_path)

        for name in stale_location:
            assert not (tmp_path / name).exists(), name
        assert (tmp_path / "README.md").read_text() == "# readme"
        assert (tmp_path / "proxyaggregator.db").read_bytes() == b"sqlite"

    def test_stale_location_artifacts_removed_when_group_disappears(self, tmp_path):
        feed = build_subscription([], format=SubscriptionFormat.PLAIN)
        publish_release([(PLAIN_NAME, feed)], tmp_path)
        assert not (
            tmp_path / default_protocol_country_filename("vless", "us", SubscriptionFormat.PLAIN)
        ).exists()
        assert not (tmp_path / default_country_filename("us", SubscriptionFormat.PLAIN)).exists()

    def test_location_artifacts_carry_over_in_next_release(self, tmp_path):
        from proxyaggregator import pipeline as pipeline_module

        vless = "vless://11111111-2222-3333-4444-555555555555@vless.example.com:443?security=none"
        candidates = [
            RankedProxy(
                proxy_config_id=1,
                protocol="vless",
                host="vless.example.com",
                port=443,
                raw_uri=vless,
                content_hash="a" * 64,
                score=0.9,
                rank=1,
                country_code="US",
            )
        ]
        feeds = pipeline_module._build_feeds(candidates)
        publish_release(feeds, tmp_path)
        assert (tmp_path / default_country_filename("us", SubscriptionFormat.PLAIN)).exists()
        assert (
            tmp_path / default_protocol_country_filename("vless", "us", SubscriptionFormat.PLAIN)
        ).exists()

    def test_failed_generation_leaves_previous_output_intact(self, tmp_path, monkeypatch):
        plain = build_subscription([], format=SubscriptionFormat.PLAIN)
        b64 = build_subscription([], format=SubscriptionFormat.BASE64)
        publish_release([(PLAIN_NAME, plain), (B64_NAME, b64)], tmp_path)
        before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}

        changed = Subscription(format=SubscriptionFormat.PLAIN, content="changed\n", count=1)
        changed_b64 = Subscription(format=SubscriptionFormat.BASE64, content="changed\n", count=1)

        real_write = publisher_module.write_artifact

        def failing_write(filename, content, output_dir):
            if filename == B64_NAME:
                raise PublishError(filename, "injected_failure")
            return real_write(filename, content, output_dir)

        monkeypatch.setattr(publisher_module, "write_artifact", failing_write)
        with pytest.raises(PublishError):
            publish_release([(PLAIN_NAME, changed), (B64_NAME, changed_b64)], tmp_path)

        after = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        assert after == before
        leftovers = [p for p in tmp_path.parent.iterdir() if ".staging-" in p.name]
        assert leftovers == []

    def test_matches_byte_for_byte_with_publish_subscriptions(self, tmp_path):
        feeds = build_demo_subscriptions()
        publish_release(feeds, tmp_path)
        same = {p.name: p.read_bytes() for p in tmp_path.iterdir()}

        other = tmp_path / "other"
        publish_subscriptions(feeds, other)
        write_release_manifest(
            build_release_manifest(
                [
                    release_metadata(n, s.format, s.count, s.content.encode("utf-8"))
                    for n, s in feeds
                ]
            ),
            other,
        )
        assert same == {p.name: p.read_bytes() for p in other.iterdir()}


class TestLocationReleaseManifest:
    """Phase 17: manifest and verify_release cover location artifacts."""

    def _release(self, tmp_path):
        from proxyaggregator import pipeline as pipeline_module

        vless = "vless://11111111-2222-3333-4444-555555555555@vless.example.com:443?security=none"
        vless_444 = (
            "vless://11111111-2222-3333-4444-555555555555@vless.example.com:444?security=none"
        )
        ss = (
            "ss://"
            + base64.b64encode(b"aes-128-gcm:passwd").decode("ascii")
            + "@ss.example.com:8388"
        )
        candidates = [
            RankedProxy(
                proxy_config_id=1,
                protocol="vless",
                host="vless.example.com",
                port=443,
                raw_uri=vless,
                content_hash="a" * 64,
                score=0.9,
                rank=1,
                country_code="DE",
                latency_ms=50.0,
            ),
            RankedProxy(
                proxy_config_id=2,
                protocol="vless",
                host="vless.example.com",
                port=444,
                raw_uri=vless_444,
                content_hash="b" * 64,
                score=0.8,
                rank=2,
                country_code="US",
                latency_ms=60.0,
            ),
            RankedProxy(
                proxy_config_id=3,
                protocol="ss",
                host="ss.example.com",
                port=8388,
                raw_uri=ss,
                content_hash="c" * 64,
                score=0.7,
                rank=3,
                country_code="DE",
                latency_ms=70.0,
            ),
        ]
        feeds = pipeline_module._build_feeds(candidates, max_items=None)
        publish_release(feeds, tmp_path)
        return feeds

    def test_manifest_lists_location_artifacts_with_exact_metadata(self, tmp_path):
        self._release(tmp_path)
        payload = json.loads((tmp_path / MANIFEST_FILENAME).read_text(encoding="utf-8"))
        by_name = {item["filename"]: item for item in payload}
        expected_location = {
            "country-de.txt",
            "country-de-base64.txt",
            "country-us.txt",
            "country-us-base64.txt",
            "vless-de.txt",
            "vless-de-base64.txt",
            "vless-us.txt",
            "vless-us-base64.txt",
            "shadowsocks-de.txt",
            "shadowsocks-de-base64.txt",
        }
        assert expected_location <= set(by_name)
        for name in expected_location:
            data = (tmp_path / name).read_bytes()
            assert by_name[name]["byte_size"] == len(data)
            assert by_name[name]["sha256"] == hashlib.sha256(data).hexdigest()

    def test_location_counts_reflect_group_membership(self, tmp_path):
        self._release(tmp_path)
        payload = json.loads((tmp_path / MANIFEST_FILENAME).read_text(encoding="utf-8"))
        by_name = {item["filename"]: item for item in payload}
        assert by_name["country-de.txt"]["count"] == 2
        assert by_name["country-us.txt"]["count"] == 1
        assert by_name["vless-de.txt"]["count"] == 1
        assert by_name["shadowsocks-de.txt"]["count"] == 1

    def test_verify_release_passes_with_location_artifacts(self, tmp_path):
        self._release(tmp_path)
        entries = verify_release(tmp_path)
        names = {entry.filename for entry in entries}
        assert "country-de.txt" in names
        assert "vless-us.txt" in names
        assert all(entry.count >= 1 for entry in entries)


class TestVerifyRelease:
    """Structural + integrity validation of a release on disk (Phase 16)."""

    def _published(self, tmp_path):
        publish_release(build_demo_subscriptions(), tmp_path)
        return tmp_path

    def test_valid_release_passes_and_returns_entries(self, tmp_path):
        entries = verify_release(self._published(tmp_path))
        assert len(entries) == DEMO_FEED_COUNT
        assert all(entry.count >= 1 for entry in entries)

    def test_missing_manifest(self, tmp_path):
        (tmp_path / "feed.txt").write_text("x")
        with pytest.raises(ReleaseVerificationError):
            verify_release(tmp_path)

    def test_invalid_manifest_json(self, tmp_path):
        (tmp_path / MANIFEST_FILENAME).write_text("{not json", encoding="utf-8")
        with pytest.raises(ReleaseVerificationError):
            verify_release(tmp_path)

    def test_manifest_must_be_list(self, tmp_path):
        (tmp_path / MANIFEST_FILENAME).write_text("null", encoding="utf-8")
        with pytest.raises(ReleaseVerificationError):
            verify_release(tmp_path)

    def test_manifest_must_be_non_empty(self, tmp_path):
        (tmp_path / MANIFEST_FILENAME).write_text("[]", encoding="utf-8")
        with pytest.raises(ReleaseVerificationError):
            verify_release(tmp_path)

    def test_missing_artifact_rejected(self, tmp_path):
        out = self._published(tmp_path)
        (out / PLAIN_NAME).unlink()
        with pytest.raises(ReleaseVerificationError, match=PLAIN_NAME):
            verify_release(out)

    def test_size_mismatch_rejected(self, tmp_path):
        out = self._published(tmp_path)
        (out / PLAIN_NAME).write_text("longer-than-recorded", encoding="utf-8")
        with pytest.raises(ReleaseVerificationError, match=PLAIN_NAME):
            verify_release(out)

    def test_checksum_mismatch_rejected(self, tmp_path):
        out = self._published(tmp_path)
        data = (out / PLAIN_NAME).read_bytes()
        (out / PLAIN_NAME).write_bytes(b"X" + data[1:])
        with pytest.raises(ReleaseVerificationError, match="checksum"):
            verify_release(out)

    def test_no_nonempty_feed_rejected(self, tmp_path):
        data = b""
        entries = [release_metadata(PLAIN_NAME, SubscriptionFormat.PLAIN, 0, data)]
        write_release_manifest(build_release_manifest(entries), tmp_path)
        write_artifact(PLAIN_NAME, data, tmp_path)
        with pytest.raises(ReleaseVerificationError, match="non-empty"):
            verify_release(tmp_path)

    def test_error_never_echoes_content(self, tmp_path):
        secret = "ss://c3VwZXJzZWNyZXQ@host.example.com:8388#SecretNode\n"
        feed = Subscription(format=SubscriptionFormat.PLAIN, content=secret, count=1)
        publish_release([(PLAIN_NAME, feed)], tmp_path)
        (tmp_path / PLAIN_NAME).write_bytes(b"tampered")
        with pytest.raises(ReleaseVerificationError) as exc_info:
            verify_release(tmp_path)
        assert secret not in str(exc_info.value)
        assert "SecretNode" not in str(exc_info.value)
