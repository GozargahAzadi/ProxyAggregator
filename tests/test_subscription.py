"""Phase 8 tests: deterministic subscription generation.

Pure, deterministic serialization of Phase 7 ranked proxies into subscription
feeds (plain URI list, base64, JSON). Canonical URIs are derived from the
Phase 3 ``ParseResult`` (re-parsing the persisted ``raw_uri``), cross-checked
against the persisted identity fields. No network, no database, no clock.
"""

from __future__ import annotations

import base64
import json
from urllib.parse import unquote, urlparse

import pytest

from proxyaggregator.parsers.base import ParseResult
from proxyaggregator.parsers.registry import get_registry
from proxyaggregator.publishing import (
    RankedProxy,
    SubscriptionError,
    SubscriptionFormat,
    build_subscription,
    canonical_uri,
)

UUID = "d98d1c36-ccc8-4c77-9e9f-81c1b7584277"

# --- Sample raw URIs for every Phase 3 protocol -----------------------------

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
    country_code: str | None = None,
    latency_ms: float | None = None,
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
        country_code=country_code,
        latency_ms=latency_ms,
    )


SUPPORTED = [
    (VLESS, "vless", "vless.example.com", 443),
    (VMESS, "vmess", "vmess.example.com", 443),
    (TROJAN, "trojan", "trojan.example.com", 443),
    (SS, "ss", "ss.example.com", 8388),
    (HYSTERIA, "hysteria", "hy.example.com", 443),
    (HYSTERIA2, "hysteria2", "hy2.example.com", 443),
    (SOCKS4, "socks4", "proxy.example.com", 1080),
    (SOCKS4A, "socks4", "proxy.example.com", 1080),
    (SOCKS5, "socks5", "proxy.example.com", 1080),
    (HTTP, "http", "proxy.example.com", 8080),
    (HTTPS, "https", "proxy.example.com", 8443),
]


def _parse(line: str):
    return get_registry().get(urlparse(line).scheme).parse(line)


# A. Empty input -------------------------------------------------------------


class TestEmptyInput:
    def test_empty_plain(self):
        feed = build_subscription([], format=SubscriptionFormat.PLAIN)
        assert feed.content == ""
        assert feed.count == 0
        assert feed.format is SubscriptionFormat.PLAIN

    def test_empty_base64(self):
        feed = build_subscription([], format=SubscriptionFormat.BASE64)
        assert feed.content == ""
        assert feed.count == 0

    def test_empty_json(self):
        feed = build_subscription([], format=SubscriptionFormat.JSON)
        assert feed.content == "[]"
        assert feed.count == 0


# B. Single proxy ------------------------------------------------------------


class TestSingleProxy:
    def test_one_vless(self):
        candidate = _ranked(1, "vless", VLESS, "vless.example.com", 443)
        feed = build_subscription([candidate])
        lines = feed.content.splitlines()
        assert feed.count == 1
        assert len(lines) == 1
        assert _parse(lines[0]).user == UUID

    def test_one_socks5(self):
        candidate = _ranked(1, "socks5", SOCKS5, "proxy.example.com", 1080)
        feed = build_subscription([candidate])
        parsed = _parse(feed.content.splitlines()[0])
        assert parsed.user == "user"
        assert unquote(parsed.password) == "p@ss"


# C. Ranking preservation ----------------------------------------------------


class TestRankingPreservation:
    def test_order_is_rank_order(self):
        candidates = [
            _ranked(1, "vless", VLESS, "vless.example.com", 443),
            _ranked(2, "trojan", TROJAN, "trojan.example.com", 443),
            _ranked(3, "ss", SS, "ss.example.com", 8388),
        ]
        feed = build_subscription(candidates)
        lines = feed.content.splitlines()
        assert _parse(lines[0]).protocol == "vless"
        assert _parse(lines[1]).protocol == "trojan"
        assert _parse(lines[2]).protocol == "ss"

    def test_json_keeps_order(self):
        candidates = [
            _ranked(1, "vless", VLESS, "vless.example.com", 443),
            _ranked(2, "trojan", TROJAN, "trojan.example.com", 443),
        ]
        feed = build_subscription(candidates, format=SubscriptionFormat.JSON)
        assert [item["host"] for item in json.loads(feed.content)] == [
            "vless.example.com",
            "trojan.example.com",
        ]


# D + M. max_items -----------------------------------------------------------


class TestMaxItems:
    def test_none_returns_all(self):
        candidates = [_ranked(i, "http", HTTP, "proxy.example.com", 8080) for i in range(1, 4)]
        assert build_subscription(candidates).count == 3

    def test_one_returns_first(self):
        candidates = [
            _ranked(1, "vless", VLESS, "vless.example.com", 443),
            _ranked(2, "trojan", TROJAN, "trojan.example.com", 443),
        ]
        feed = build_subscription(candidates, max_items=1)
        assert feed.count == 1
        assert _parse(feed.content.splitlines()[0]).protocol == "vless"

    def test_exact_length(self):
        candidates = [_ranked(i, "http", HTTP, "proxy.example.com", 8080) for i in range(1, 3)]
        assert build_subscription(candidates, max_items=2).count == 2

    def test_greater_than_length(self):
        candidates = [_ranked(1, "http", HTTP, "proxy.example.com", 8080)]
        assert build_subscription(candidates, max_items=99).count == 1

    def test_zero_is_invalid(self):
        candidates = [_ranked(1, "http", HTTP, "proxy.example.com", 8080)]
        with pytest.raises(ValueError):
            build_subscription(candidates, max_items=0)

    def test_negative_is_invalid(self):
        candidates = [_ranked(1, "http", HTTP, "proxy.example.com", 8080)]
        with pytest.raises(ValueError):
            build_subscription(candidates, max_items=-1)

    def test_non_int_is_invalid(self):
        candidates = [_ranked(1, "http", HTTP, "proxy.example.com", 8080)]
        with pytest.raises(ValueError):
            build_subscription(candidates, max_items=2.5)


# E. Determinism -------------------------------------------------------------


class TestDeterminism:
    def test_same_input_same_bytes(self):
        candidates = [
            _ranked(i, row[1], row[0], row[2], row[3])
            for i, row in enumerate(SUPPORTED[:5], start=1)
        ]
        first = build_subscription(candidates, format=SubscriptionFormat.BASE64)
        second = build_subscription(candidates, format=SubscriptionFormat.BASE64)
        assert first.content == second.content
        assert first.content.encode("ascii") == second.content.encode("ascii")

    def test_repeated_canonical_uri_stable(self):
        parsed = get_registry().get("vless").parse(VLESS)
        assert canonical_uri(parsed) == canonical_uri(get_registry().get("vless").parse(VLESS))


# F. Protocol coverage -------------------------------------------------------


class TestProtocolCoverage:
    @pytest.mark.parametrize(("raw_uri", "protocol", "host", "port"), SUPPORTED)
    def test_each_protocol_serializes(self, raw_uri, protocol, host, port):
        candidate = _ranked(7, protocol, raw_uri, host, port)
        feed = build_subscription([candidate])
        line = feed.content.splitlines()[0]
        parsed = _parse(line)
        assert parsed.protocol == protocol
        assert parsed.host == host
        assert parsed.port == port

    def test_socks4a_scheme_normalized_to_socks4(self):
        candidate = _ranked(
            1,
            "socks4",
            SOCKS4A,
            "proxy.example.com",
            1080,
            country_code="DE",
            latency_ms=124.5,
        )
        feed = build_subscription([candidate])
        line = feed.content.splitlines()[0]
        assert line.startswith("socks4://proxy.example.com:1080")
        assert "socks4a://" not in line
        assert unquote(urlparse(line).fragment) == "🇩🇪 DE | SOCKS4 | 125ms | GozargahAzadi"


# G. URI validity ------------------------------------------------------------


class TestUriValidity:
    @pytest.mark.parametrize(("raw_uri", "protocol", "host", "port"), SUPPORTED)
    def test_scheme_is_valid(self, raw_uri, protocol, host, port):
        candidate = _ranked(9, protocol, raw_uri, host, port)
        line = build_subscription([candidate]).content.splitlines()[0]
        assert urlparse(line).scheme in {
            "vless",
            "vmess",
            "trojan",
            "ss",
            "hysteria",
            "hysteria2",
            "socks4",
            "socks5",
            "http",
            "https",
        }


# H. Percent encoding --------------------------------------------------------


class TestPercentEncoding:
    def test_path_and_remark_fragment_encoded(self):
        raw = f"vless://{UUID}@vless.example.com:443?network=ws&security=tls&path=/ws#香港 节点 01"
        candidate = _ranked(
            1,
            "vless",
            raw,
            "vless.example.com",
            443,
            country_code="DE",
            latency_ms=124.5,
        )
        line = build_subscription([candidate]).content.splitlines()[0]
        assert "%2Fws" in line
        assert "%20" in line
        assert "香港" not in line
        fragment = unquote(urlparse(line).fragment)
        assert fragment == "🇩🇪 DE | VLESS | 125ms | GozargahAzadi"

    def test_password_special_chars_roundtrip(self):
        candidate = _ranked(1, "socks5", SOCKS5, "proxy.example.com", 1080)
        line = build_subscription([candidate]).content.splitlines()[0]
        assert unquote(urlparse(line).password) == "p@ss"
        assert "p%40ss" in line


# I. Query parameter ordering ------------------------------------------------


class TestQueryOrdering:
    def test_parameter_order_canonicalized(self):
        a = (
            f"vless://{UUID}@vless.example.com:443"
            "?security=tls&network=ws&sni=example.com&host=example.com"
        )
        b = (
            f"vless://{UUID}@vless.example.com:443"
            "?host=example.com&sni=example.com&network=ws&security=tls"
        )
        candidate_a = _ranked(1, "vless", a, "vless.example.com", 443)
        candidate_b = _ranked(2, "vless", b, "vless.example.com", 443)
        line_a = build_subscription([candidate_a]).content.splitlines()[0]
        line_b = build_subscription([candidate_b]).content.splitlines()[0]
        assert line_a == line_b
        query = parse_qs_line(line_a)
        assert list(query) == sorted(list(query))


# J. Remarks / public names ---------------------------------------------------


class TestFragments:
    def test_ss_fragment_is_remark(self):
        candidate = _ranked(
            1, "ss", SS, "ss.example.com", 8388, country_code="DE", latency_ms=124.5
        )
        line = build_subscription([candidate]).content.splitlines()[0]
        assert unquote(urlparse(line).fragment) == "🇩🇪 DE | SS | 125ms | GozargahAzadi"
        assert "SSNode" not in line

    def test_trojan_fragment_is_remark(self):
        candidate = _ranked(
            1, "trojan", TROJAN, "trojan.example.com", 443, country_code="US", latency_ms=87.2
        )
        line = build_subscription([candidate]).content.splitlines()[0]
        assert unquote(_parse(line).fragment) == "🇺🇸 US | TROJAN | 87ms | GozargahAzadi"
        assert "TrojanNode" not in line

    def test_vmess_ps_is_remark(self):
        candidate = _ranked(
            1, "vmess", VMESS, "vmess.example.com", 443, country_code="DE", latency_ms=200.0
        )
        line = build_subscription([candidate]).content.splitlines()[0]
        assert _parse(line).fragment == "🇩🇪 DE | VMESS | 200ms | GozargahAzadi"
        assert "VMessNode" not in line

    def test_no_fragment_source_still_gets_remark(self):
        raw = "https://proxy.example.com:8443"
        candidate = _ranked(
            1, "https", raw, "proxy.example.com", 8443, country_code="GB", latency_ms=65.4
        )
        line = build_subscription([candidate]).content.splitlines()[0]
        assert unquote(urlparse(line).fragment) == "🇬🇧 GB | HTTPS | 65ms | GozargahAzadi"


# K. Credentials -------------------------------------------------------------


class TestCredentials:
    def test_socks5_credentials_roundtrip(self):
        candidate = _ranked(1, "socks5", SOCKS5, "proxy.example.com", 1080)
        line = build_subscription([candidate]).content.splitlines()[0]
        parsed = _parse(line)
        assert parsed.user == "user"
        assert unquote(parsed.password) == "p@ss"

    def test_credentials_never_leak_in_errors(self):
        payload = base64.b64encode(b"aes-128-gcm:secret-token-xyz").decode("ascii")
        bad = f"vmess://{payload}"
        candidate = _ranked(1, "vmess", bad, "vmess.example.com", 443)
        with pytest.raises(SubscriptionError) as exc:
            build_subscription([candidate])
        message = str(exc.value)
        assert "secret-token-xyz" not in message
        assert payload not in message
        assert exc.value.proxy_config_id == 1
        assert exc.value.protocol == "vmess"

    def test_failed_parse_does_not_expose_raw_uri(self):
        raw = "vless://u@broken-%%%-uri-with-secret:443"
        candidate = _ranked(1, "vless", raw, "broken.example.com", 443)
        with pytest.raises(SubscriptionError) as exc:
            build_subscription([candidate])
        assert "secret" not in str(exc.value)
        assert raw not in str(exc.value)


# L. Duplicate candidates ----------------------------------------------------


class TestDuplicateCandidates:
    def test_duplicate_content_hash_emitted_once(self):
        same_hash = "ab" * 32
        candidates = [
            _ranked(1, "vless", VLESS, "vless.example.com", 443, content_hash=same_hash),
            _ranked(
                2,
                "trojan",
                TROJAN,
                "trojan.example.com",
                443,
                content_hash=same_hash,
                score=0.9,
                rank=2,
            ),
        ]
        feed = build_subscription(candidates)
        assert feed.count == 1
        assert _parse(feed.content.splitlines()[0]).protocol == "vless"

    def test_distinct_hashes_all_kept(self):
        candidates = [
            _ranked(1, "vless", VLESS, "vless.example.com", 443, content_hash="a" * 64),
            _ranked(2, "trojan", TROJAN, "trojan.example.com", 443, content_hash="b" * 64),
        ]
        assert build_subscription(candidates).count == 2


# N. Unsupported / missing serialization data --------------------------------


class TestSerializeFailures:
    def test_unknown_protocol(self):
        candidate = _ranked(1, "wireguard", "wireguard://x@y:51820", "y", 51820)
        with pytest.raises(SubscriptionError) as exc:
            build_subscription([candidate])
        assert exc.value.protocol == "wireguard"
        assert exc.value.proxy_config_id == 1
        assert "unsupported" in exc.value.reason

    def test_missing_uuid_vless(self):
        raw = "vless://vless.example.com:443"
        candidate = _ranked(1, "vless", raw, "vless.example.com", 443)
        with pytest.raises(SubscriptionError) as exc:
            build_subscription([candidate])
        assert exc.value.protocol == "vless"
        assert "missing user" in exc.value.reason

    def test_identity_mismatch(self):
        candidate = _ranked(
            1,
            "vless",
            VLESS,
            "wrong.example.com",
            443,
        )
        with pytest.raises(SubscriptionError) as exc:
            build_subscription([candidate])
        assert "identity_mismatch" in exc.value.reason


# O. Base64 round trip -------------------------------------------------------


class TestBase64Feed:
    def test_decoding_reproduces_plain(self):
        candidates = [
            _ranked(1, "vless", VLESS, "vless.example.com", 443),
            _ranked(2, "trojan", TROJAN, "trojan.example.com", 443),
        ]
        plain = build_subscription(candidates).content
        encoded = build_subscription(candidates, format=SubscriptionFormat.BASE64).content
        assert base64.b64decode(encoded.encode("ascii")).decode("utf-8") == plain

    def test_base64_has_no_newlines(self):
        candidates = [_ranked(1, "http", HTTP, "proxy.example.com", 8080)]
        content = build_subscription(candidates, format=SubscriptionFormat.BASE64).content
        assert "\n" not in content


# P. Newline behavior --------------------------------------------------------


class TestNewlineBehavior:
    def test_each_line_terminated_by_single_newline(self):
        candidates = [
            _ranked(1, "vless", VLESS, "vless.example.com", 443),
            _ranked(2, "trojan", TROJAN, "trojan.example.com", 443),
        ]
        content = build_subscription(candidates).content
        assert content.endswith("\n")
        assert not content.endswith("\n\n")
        assert len(content.splitlines()) == 2

    def test_json_no_trailing_newline(self):
        candidates = [_ranked(1, "http", HTTP, "proxy.example.com", 8080)]
        content = build_subscription(candidates, format=SubscriptionFormat.JSON).content
        assert not content.endswith("\n")


# JSON feed ------------------------------------------------------------------


class TestJsonFeed:
    def test_deterministic_sorted_keys_no_score_or_id(self):
        raw = "https://proxy.example.com:8443"
        candidates = [
            _ranked(
                1,
                "https",
                raw,
                "proxy.example.com",
                8443,
                country_code="US",
                latency_ms=73.0,
            )
        ]
        content = build_subscription(candidates, format=SubscriptionFormat.JSON).content
        items = json.loads(content)
        assert len(items) == 1
        (item,) = items
        assert list(item) == sorted(item)
        assert item["uri"].startswith("https://proxy.example.com:8443#")
        assert unquote(urlparse(item["uri"]).fragment) == "🇺🇸 US | HTTPS | 73ms | GozargahAzadi"
        assert item["host"] == "proxy.example.com"
        assert item["port"] == 8443
        assert not any(key in item for key in ("score", "rank", "proxy_config_id"))

    def test_identical_twice(self):
        candidates = [_ranked(1, "http", HTTP, "proxy.example.com", 8080)]
        first = build_subscription(candidates, format=SubscriptionFormat.JSON)
        second = build_subscription(candidates, format=SubscriptionFormat.JSON)
        assert first.content == second.content


# Phase 7 integration --------------------------------------------------------


class TestPhase7Integration:
    def test_rank_output_maps_to_feed_order(self):
        from proxyaggregator.health.models import HealthStatus
        from proxyaggregator.scoring.models import RankCandidate
        from proxyaggregator.scoring.scorer import rank_proxies

        candidates = [
            RankCandidate(
                proxy_config_id=1,
                content_hash="a" * 64,
                status=HealthStatus.OK,
                latency_ms=500.0,
            ),
            RankCandidate(
                proxy_config_id=2,
                content_hash="b" * 64,
                status=HealthStatus.OK,
                latency_ms=80.0,
            ),
            RankCandidate(
                proxy_config_id=3,
                content_hash="c" * 64,
                status=HealthStatus.TIMEOUT,
                latency_ms=None,
            ),
        ]
        ranked = rank_proxies(candidates)
        by_id = {
            1: (VLESS, "vless", "vless.example.com", 443),
            2: (TROJAN, "trojan", "trojan.example.com", 443),
        }
        inputs = [
            _ranked(
                r.proxy_config_id,
                by_id[r.proxy_config_id][1],
                by_id[r.proxy_config_id][0],
                by_id[r.proxy_config_id][2],
                by_id[r.proxy_config_id][3],
                score=r.score,
                rank=index,
            )
            for index, r in enumerate(ranked, start=1)
        ]
        feed = build_subscription(inputs)
        assert feed.count == 2
        lines = feed.content.splitlines()
        assert _parse(lines[0]).protocol == "trojan"
        assert _parse(lines[1]).protocol == "vless"


# --- helpers ---


def parse_qs_line(line: str) -> dict[str, str]:
    query = urlparse(line).query
    return dict(pair.split("=", 1) for pair in query.split("&") if pair)


def test_canonical_uri_is_deterministic_and_exact():
    result = ParseResult(
        protocol="vless",
        host="1.2.3.4",
        port=8443,
        raw_uri="placeholder",
        user="u",
        password="pass",
        sni="sni.example.com",
        network="ws",
        tls="tls",
        path="/path",
        fragment="MyProxy",
    )
    uri = canonical_uri(result)
    assert (
        uri
        == "vless://u:pass@1.2.3.4:8443?network=ws&path=%2Fpath&security=tls&sni=sni.example.com#MyProxy"
    )
    reparsed = _parse(uri)
    assert reparsed.protocol == "vless"
    assert reparsed.user == "u"
    assert reparsed.password == "pass"
    assert reparsed.path == "/path"
    assert reparsed.fragment == "MyProxy"
