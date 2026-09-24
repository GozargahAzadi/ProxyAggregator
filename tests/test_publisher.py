"""Phase 9 tests: deterministic GitHub publisher artifacts.

Phase 9 writes generated subscription feeds (plain, base64, JSON) to an
output directory and produces a deterministic release manifest. All output
is byte-exact and reproducible: no timestamps, random values, hostnames,
environment info, or credentials ever enter file contents or errors.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError

import proxyaggregator.publishing.publisher as publisher_module
from proxyaggregator.publishing import (
    SubscriptionFormat,
    build_subscription,
)
from proxyaggregator.publishing.publisher import (
    DEFAULT_FILENAMES,
    MANIFEST_FILENAME,
    PublishError,
    SubscriptionRelease,
    build_release_manifest,
    default_filename,
    default_protocol_filename,
    publish_subscriptions,
    release_metadata,
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
