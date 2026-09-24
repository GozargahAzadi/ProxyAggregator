"""Phase 9.3 tests: protocol-separated subscription feeds.

The publisher emits, in addition to the three canonical combined feeds,
one plain plus one base64 feed per protocol present in the globally
selected (deduplicated, `max_items`-capped) candidate set.

Contracts under test:

- Only candidates whose parsed protocol matches a feed appear in it
  (no cross-protocol contamination).
- The per-protocol feed set comes from the canonical serializer protocol
  registry (`SUPPORTED_PROTOCOLS`); file stems match the required output
  names exactly (``ss`` -> ``shadowsocks``).
- Global selection (dedup + `max_items`) happens once, *before* splitting,
  so every protocol feed is a subset of the combined feed.
- Protocols with zero selected candidates produce no feed file.
- Ordering is deterministic: rank order within a protocol, canonical
  protocol order across feeds.
- Base64 protocol feeds decode to their plain text.
- The release manifest covers every artifact, including protocol feeds,
  with the unchanged schema (no scores/ranks/ids).
- README raw links match the artifact set exactly.
- The combined feeds are byte-for-byte unchanged.

No network, no database, no clock.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

from proxyaggregator.publishing import (
    SUPPORTED_PROTOCOLS,
    SubscriptionFormat,
    build_subscription,
)
from proxyaggregator.publishing.feeds import build_protocol_subscriptions
from proxyaggregator.publishing.models import RankedProxy
from proxyaggregator.publishing.publisher import (
    DEFAULT_FILENAMES,
    DEFAULT_PROTOCOL_FILENAME_STEMS,
    MANIFEST_FILENAME,
    default_protocol_filename,
    publish_subscriptions,
)
from proxyaggregator.publishing.samples import build_demo_subscriptions

ROOT_DIR = Path(__file__).resolve().parents[1]

UUID = "d98d1c36-ccc8-4c77-9e9f-81c1b7584277"

# One raw URI per canonical protocol (mirrors test_subscription coverage).
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
HYSTERIA = "hysteria://hy.example.com:443?auth=secretkey&sni=example.com#HyNode"
HYSTERIA2 = "hysteria2://hy2secret@hy2.example.com:443?sni=example.com#Hy2Node"
SOCKS4 = "socks4://user@proxy.example.com:1080"
SOCKS4A = "socks4a://proxy.example.com:1080"
SOCKS5 = "socks5://user:p%40ss@proxy.example.com:1080"
HTTP = "http://user:p%40ss@proxy.example.com:8080"
HTTPS = "https://proxy.example.com:8443"


def _vmess_uri() -> str:
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

PROTOCOL_URIS: tuple[tuple[str, str, str, int], ...] = (
    ("vless", VLESS, "vless.example.com", 443),
    ("vmess", VMESS, "vmess.example.com", 443),
    ("trojan", TROJAN, "trojan.example.com", 443),
    ("ss", SS, "ss.example.com", 8388),
    ("hysteria", HYSTERIA, "hy.example.com", 443),
    ("hysteria2", HYSTERIA2, "hy2.example.com", 443),
    ("socks4", SOCKS4, "proxy.example.com", 1080),
    ("socks5", SOCKS5, "proxy.example.com", 1080),
    ("http", HTTP, "proxy.example.com", 8080),
    ("https", HTTPS, "proxy.example.com", 8443),
)

# A socks4a URI normalizes to the socks4 protocol/feed.
SOCKS4A_CANDIDATE = RankedProxy(
    proxy_config_id=90,
    protocol="socks4",
    host="proxy.example.com",
    port=1080,
    raw_uri=SOCKS4A,
    content_hash="9" * 64,
    score=0.5,
    rank=90,
)


def _ranked(
    proxy_config_id: int,
    protocol: str,
    raw_uri: str,
    host: str,
    port: int,
    *,
    content_hash: str | None = None,
    score: float | None = None,
    rank: int | None = None,
) -> RankedProxy:
    return RankedProxy(
        proxy_config_id=proxy_config_id,
        protocol=protocol,
        host=host,
        port=port,
        raw_uri=raw_uri,
        content_hash=content_hash or f"{proxy_config_id:04d}" * 16,
        score=score if score is not None else 1.0 - proxy_config_id / 1000,
        rank=rank if rank is not None else proxy_config_id,
    )


def _all_protocol_candidates() -> list[RankedProxy]:
    return [
        _ranked(index + 1, protocol, uri, host, port)
        for index, (protocol, uri, host, port) in enumerate(PROTOCOL_URIS)
    ]


def _parse(line: str):
    from proxyaggregator.parsers.registry import get_registry

    return get_registry().get(urlparse(line).scheme).parse(line)


def _feeds_by_name(feeds):
    return {name: sub for name, sub in feeds}


# A. Canonical protocol source ------------------------------------------------


class TestCanonicalProtocolSource:
    def test_supported_protocols_from_serializer_registry(self):
        from proxyaggregator.publishing.serializer import _SERIALIZERS

        assert set(SUPPORTED_PROTOCOLS) == set(_SERIALIZERS)
        assert len(SUPPORTED_PROTOCOLS) == 10

    def test_filename_stems_cover_every_supported_protocol(self):
        assert set(DEFAULT_PROTOCOL_FILENAME_STEMS) == set(SUPPORTED_PROTOCOLS)

    def test_shadowsocks_stem_for_ss_protocol(self):
        assert DEFAULT_PROTOCOL_FILENAME_STEMS["ss"] == "shadowsocks"


# B. Protocol filtering -------------------------------------------------------


class TestProtocolFiltering:
    def test_feed_contains_only_its_own_protocol(self):
        candidates = _all_protocol_candidates()
        feeds = build_protocol_subscriptions(candidates)
        for protocol, plain, _b64 in feeds:
            for line in plain.content.splitlines():
                assert _parse(line).protocol == protocol

    def test_every_supported_protocol_produces_a_feed(self):
        feeds = build_protocol_subscriptions(_all_protocol_candidates())
        assert {protocol for protocol, _, _ in feeds} == set(SUPPORTED_PROTOCOLS)

    def test_no_empty_protocol_feeds(self):
        feeds = build_protocol_subscriptions(
            [
                _ranked(1, "http", HTTP, "proxy.example.com", 8080),
                _ranked(2, "socks5", SOCKS5, "proxy.example.com", 1080),
            ]
        )
        emitted = {protocol for protocol, _, _ in feeds}
        assert emitted == {"http", "socks5"}
        assert all(plain.count > 0 and _b64.count > 0 for _, plain, _b64 in feeds)

    def test_socks4a_normalizes_into_socks4_feed(self):
        candidates = [
            SOCKS4A_CANDIDATE,
            _ranked(1, "socks4", SOCKS4, "proxy.example.com", 1080),
        ]
        feeds = {
            protocol: (plain, _b64)
            for protocol, plain, _b64 in build_protocol_subscriptions(candidates)
        }
        assert set(feeds) == {"socks4"}
        lines = feeds["socks4"][0].content.splitlines()
        assert "socks4a://" not in "\n".join(lines)
        assert len(lines) == 2
        assert all(line.startswith("socks4://") for line in lines)


# C. Deterministic ordering ---------------------------------------------------


class TestOrdering:
    def test_rank_order_preserved_within_protocol(self):
        http_8080 = "http://user:p%40ss@proxy.example.com:8080"
        http_8081 = "http://user:p%40ss@proxy.example.com:8081"
        vless_443 = f"vless://{UUID}@vless.example.com:443?security=none"
        vless_8443 = f"vless://{UUID}@vless.example.com:8443?security=none"
        candidates = [
            _ranked(1, "http", http_8080, "proxy.example.com", 8080),
            _ranked(2, "vless", vless_443, "vless.example.com", 443),
            _ranked(3, "http", http_8081, "proxy.example.com", 8081),
            _ranked(4, "vless", vless_8443, "vless.example.com", 8443),
        ]
        feeds = {
            protocol: plain for protocol, plain, _b64 in build_protocol_subscriptions(candidates)
        }
        http_lines = [_parse(line).port for line in feeds["http"].content.splitlines()]
        vless_lines = [_parse(line).port for line in feeds["vless"].content.splitlines()]
        assert http_lines == [8080, 8081]
        assert vless_lines == [443, 8443]

    def test_protocol_feed_order_is_canonical(self):
        feeds = [
            (protocol, plain)
            for protocol, plain, _b64 in build_protocol_subscriptions(
                [
                    _ranked(1, "https", HTTPS, "proxy.example.com", 8443),
                    _ranked(2, "vless", VLESS, "vless.example.com", 443),
                ]
            )
        ]
        assert [protocol for protocol, _ in feeds] == ["vless", "https"]


# D. Base64 output ------------------------------------------------------------


class TestBase64ProtocolFeeds:
    def test_base64_decodes_to_plain(self):
        feeds = build_protocol_subscriptions(_all_protocol_candidates())
        for _protocol, plain, b64 in feeds:
            assert b64.format is SubscriptionFormat.BASE64
            assert base64.b64decode(b64.content.encode("ascii")).decode("utf-8") == plain.content
            assert b64.count == plain.count

    def test_base64_has_no_newlines(self):
        feeds = build_protocol_subscriptions(_all_protocol_candidates())
        for _protocol, _plain, b64 in feeds:
            assert "\n" not in b64.content


# E. max_items ----------------------------------------------------------------


class TestMaxItems:
    def test_cap_applies_globally_before_split(self):
        candidates = [
            _ranked(1, "vless", VLESS, "vless.example.com", 443),
            _ranked(2, "http", HTTP, "proxy.example.com", 8080),
            _ranked(3, "http", HTTP, "proxy.example.com", 8080, content_hash="3" * 64),
            _ranked(4, "socks5", SOCKS5, "proxy.example.com", 1080),
        ]
        combined = build_subscription(candidates, max_items=2)
        protocol_feeds = build_protocol_subscriptions(candidates, max_items=2)
        assert combined.count == 2
        assert sum(plain.count for _p, plain, _b in protocol_feeds) == combined.count
        for _protocol, plain, _b64 in protocol_feeds:
            assert plain.count <= combined.count

    def test_protocol_feeds_are_subset_of_combined(self):
        candidates = [
            _ranked(1, "vless", VLESS, "vless.example.com", 443),
            _ranked(2, "http", HTTP, "proxy.example.com", 8080),
        ]
        combined = build_subscription(candidates)
        combined_lines = set(combined.content.splitlines())
        assert combined_lines
        for _protocol, plain, _b64 in build_protocol_subscriptions(candidates):
            feed_lines = set(plain.content.splitlines())
            assert feed_lines and feed_lines <= combined_lines

    def test_invalid_max_items_rejected(self):
        candidates = [_ranked(1, "http", HTTP, "proxy.example.com", 8080)]
        with pytest.raises(ValueError):
            build_protocol_subscriptions(candidates, max_items=0)
        with pytest.raises(ValueError):
            build_protocol_subscriptions(candidates, max_items=-1)
        with pytest.raises(ValueError):
            build_protocol_subscriptions(candidates, max_items=2.5)


# F. Publisher filenames ------------------------------------------------------


class TestProtocolFilenames:
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
    def test_plain_and_base64_filenames(self, protocol, stem):
        assert default_protocol_filename(protocol, SubscriptionFormat.PLAIN) == f"{stem}.txt"
        assert (
            default_protocol_filename(protocol, SubscriptionFormat.BASE64) == f"{stem}-base64.txt"
        )

    def test_unknown_protocol_rejected(self):
        with pytest.raises(ValueError):
            default_protocol_filename("wireguard", SubscriptionFormat.PLAIN)

    def test_json_not_a_protocol_format(self):
        with pytest.raises(ValueError):
            default_protocol_filename("vless", SubscriptionFormat.JSON)


# G. Publishing + manifest ----------------------------------------------------


class TestProtocolManifest:
    def test_protocol_feeds_published_with_manifest(self, tmp_path):
        feeds = build_demo_subscriptions()
        entries = publish_subscriptions(feeds, tmp_path)
        names = {entry.filename for entry in entries}
        for protocol in SUPPORTED_PROTOCOLS:
            plain_name = default_protocol_filename(protocol, SubscriptionFormat.PLAIN)
            b64_name = default_protocol_filename(protocol, SubscriptionFormat.BASE64)
            assert plain_name in names
            assert b64_name in names
            assert (tmp_path / plain_name).exists()
            assert (tmp_path / b64_name).exists()

    def test_manifest_entries_keep_unchanged_schema(self, tmp_path):
        entries = publish_subscriptions(build_demo_subscriptions(), tmp_path)
        payload = json.loads(_manifest(entries))
        for item in payload:
            assert set(item) == {"filename", "format", "count", "byte_size", "sha256"}
            assert not any(key in item for key in ("score", "rank", "proxy_config_id", "raw_uri"))

    def test_manifest_sha_and_bytes_match_files(self, tmp_path):
        entries = publish_subscriptions(build_demo_subscriptions(), tmp_path)
        for entry in entries:
            data = (tmp_path / entry.filename).read_bytes()
            assert entry.sha256 == hashlib.sha256(data).hexdigest()
            assert entry.byte_size == len(data)

    def test_demo_output_contains_all_artifacts(self, tmp_path):
        from proxyaggregator.publishing.publisher import (
            build_release_manifest,
            write_release_manifest,
        )

        entries = publish_subscriptions(build_demo_subscriptions(), tmp_path)
        write_release_manifest(build_release_manifest(entries), tmp_path)
        files = sorted(path.name for path in tmp_path.iterdir())
        expected = {
            DEFAULT_FILENAMES[SubscriptionFormat.PLAIN],
            DEFAULT_FILENAMES[SubscriptionFormat.BASE64],
            DEFAULT_FILENAMES[SubscriptionFormat.JSON],
            MANIFEST_FILENAME,
        }
        expected |= {
            default_protocol_filename(protocol, fmt)
            for protocol in SUPPORTED_PROTOCOLS
            for fmt in (SubscriptionFormat.PLAIN, SubscriptionFormat.BASE64)
        }
        assert set(files) == expected


# H. README links -------------------------------------------------------------


class TestReadmeLinks:
    def test_readme_lists_every_artifact_as_raw_link(self):
        readme = (ROOT_DIR / "README.md").read_text(encoding="utf-8")
        expected = {
            DEFAULT_FILENAMES[SubscriptionFormat.PLAIN],
            DEFAULT_FILENAMES[SubscriptionFormat.BASE64],
            MANIFEST_FILENAME,
        }
        expected |= {
            default_protocol_filename(protocol, fmt)
            for protocol in SUPPORTED_PROTOCOLS
            for fmt in (SubscriptionFormat.PLAIN, SubscriptionFormat.BASE64)
        }
        links = set(
            re.findall(
                r"https://raw\.githubusercontent\.com/GozargahAzadi/ProxyAggregator/main/output/[A-Za-z0-9_.-]+",
                readme,
            )
        )
        linked_files = {link.split("/output/")[1] for link in links}
        assert expected <= linked_files

    def test_readme_has_subscriptions_section(self):
        readme = (ROOT_DIR / "README.md").read_text(encoding="utf-8")
        assert "## Subscriptions" in readme


# I. Backward compatibility ---------------------------------------------------


class TestBackwardCompat:
    def test_combined_feeds_unchanged(self):
        candidates = _all_protocol_candidates()
        for fmt in SubscriptionFormat:
            assert (
                build_subscription(candidates, format=fmt).content
                == build_subscription(candidates, format=fmt, max_items=None).content
            )

    def test_protocol_feeds_reuse_canonical_serializer(self):
        candidates = _all_protocol_candidates()
        combined_lines = set(build_subscription(candidates).content.splitlines())
        for _protocol, plain, _b64 in build_protocol_subscriptions(candidates):
            for line in plain.content.splitlines():
                assert line in combined_lines


def _manifest(entries):
    from proxyaggregator.publishing.publisher import build_release_manifest

    return build_release_manifest(entries)
