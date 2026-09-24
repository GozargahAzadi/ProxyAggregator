"""Phase 10 tests: deterministic node Remark naming.

Phase 10 stamps every published proxy URI with a single canonical Remark
``{FLAG} {COUNTRY} | {PROTOCOL} | {LATENCY}ms | GozargahAzadi`` built purely
from the persisted GeoIP country, protocol, and latency. The naming module is
unit-tested here; the feeds integration is covered by asserting the Remark in
every public feed format (plain, base64, protocol-specific, JSON ``uri``) and
that the original source fragment no longer controls the public name.

No network, no database, no clock.
"""

from __future__ import annotations

import base64
import json
from urllib.parse import unquote, urlparse

import pytest

from proxyaggregator.parsers.registry import get_registry
from proxyaggregator.publishing import (
    PROTOCOL_DISPLAY_NAMES,
    REMARK_AUTHOR,
    RankedProxy,
    SubscriptionFormat,
    build_protocol_subscriptions,
    build_remark,
    build_subscription,
    country_flag,
    format_latency_ms,
    normalize_country_code,
    protocol_display_name,
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
    return get_registry().get(urlparse(line).scheme).parse(line)


# --- Unit: Remark construction -------------------------------------------------


def test_build_remark_de_vless_exact():
    assert build_remark("DE", "vless", 124.5) == "🇩🇪 DE | VLESS | 125ms | GozargahAzadi"


def test_build_remark_us_ss_exact():
    assert build_remark("US", "ss", 87.2) == "🇺🇸 US | SS | 87ms | GozargahAzadi"


def test_build_remark_gb_https_integer_latency():
    assert build_remark("GB", "https", 100) == "🇬🇧 GB | HTTPS | 100ms | GozargahAzadi"


def test_build_remark_author_and_separators():
    remark = build_remark("DE", "vless", 100.0)
    assert remark.endswith(f"| {REMARK_AUTHOR}")
    assert remark.count("|") == 3


def test_lowercase_country_normalized_to_uppercase():
    assert build_remark("de", "vless", 100.0) == build_remark("DE", "vless", 100.0)
    assert build_remark("de", "vless", 100.0).startswith("🇩🇪 DE ")


@pytest.mark.parametrize(
    ("country", "expected"),
    [
        (None, "🌐 XX"),
        ("", "🌐 XX"),
        ("USA", "🌐 XX"),
        ("D", "🌐 XX"),
        ("DE1", "🌐 XX"),
        ("DÉ", "🌐 XX"),  # non-ASCII letters are invalid
        ("123", "🌐 XX"),
        (123, "🌐 XX"),
    ],
)
def test_missing_or_invalid_country_falls_back(country, expected):
    flag, code = country_flag(country)
    assert f"{flag} {code}" == expected
    assert build_remark(country, "vless", 100).startswith(expected)


@pytest.mark.parametrize(
    ("latency", "expected"),
    [
        (None, "N/A"),
        (-1, "N/A"),
        (float("nan"), "N/A"),
        (float("inf"), "N/A"),
        ("fast", "N/A"),
        (True, "N/A"),
    ],
)
def test_missing_or_invalid_latency_falls_back(latency, expected):
    assert format_latency_ms(latency) == expected


@pytest.mark.parametrize(
    ("latency", "expected"),
    [
        (124.4, "124ms"),
        (124.5, "125ms"),  # half-up, guards against banker's rounding
        (87.2, "87ms"),
        (99.9, "100ms"),
        (150.0, "150ms"),
        (65.4, "65ms"),
        (0, "0ms"),
    ],
)
def test_latency_rounding_half_up(latency, expected):
    assert format_latency_ms(latency) == expected


def test_build_remark_missing_latency_has_no_ms_suffix():
    assert build_remark("US", "vmess", None) == "🇺🇸 US | VMESS | N/A | GozargahAzadi"


def test_missing_country_example():
    assert build_remark(None, "vless", 100) == "🌐 XX | VLESS | 100ms | GozargahAzadi"


@pytest.mark.parametrize(
    ("protocol", "display"),
    [
        ("vless", "VLESS"),
        ("vmess", "VMESS"),
        ("trojan", "TROJAN"),
        ("ss", "SS"),
        ("hysteria", "HYSTERIA"),
        ("hysteria2", "HYSTERIA2"),
        ("socks4", "SOCKS4"),
        ("socks5", "SOCKS5"),
        ("http", "HTTP"),
        ("https", "HTTPS"),
    ],
)
def test_protocol_display_names(protocol, display):
    assert PROTOCOL_DISPLAY_NAMES[protocol] == display
    assert protocol_display_name(protocol) == display


@pytest.mark.parametrize("protocol", ["VLESS", " VLess "])
def test_protocol_display_is_case_and_whitespace_insensitive(protocol):
    assert protocol_display_name(protocol) == "VLESS"


def test_unknown_protocol_display_is_uppercased_identifier():
    assert protocol_display_name("wireguard") == "WIREGUARD"
    assert protocol_display_name("") == "UNKNOWN"
    assert protocol_display_name(None) == "UNKNOWN"


def test_country_flag_regional_indicators():
    assert country_flag("DE")[0] == "🇩🇪"
    assert country_flag("US")[0] == "🇺🇸"
    assert country_flag("GB")[0] == "🇬🇧"


def test_normalize_country_code():
    assert normalize_country_code("de") == "DE"
    assert normalize_country_code(" DE ") == "DE"
    assert normalize_country_code("USA") is None
    assert normalize_country_code("D") is None
    assert normalize_country_code(None) is None


def test_remark_deterministic_and_credential_free():
    a = build_remark("DE", "vless", 124.5)
    b = build_remark("DE", "vless", 124.5)
    assert a == b
    assert "password" not in a
    assert "secret" not in a


# --- Integration: Remark in every published feed ------------------------------


class TestRemarkInPublishedFeeds:
    def test_vless_uri_remark_replaces_fragment(self):
        candidate = _ranked(
            1, "vless", VLESS, "vless.example.com", 443, country_code="DE", latency_ms=124.5
        )
        line = build_subscription([candidate]).content.splitlines()[0]
        assert urlparse(line).scheme == "vless"
        assert unquote(urlparse(line).fragment) == "🇩🇪 DE | VLESS | 125ms | GozargahAzadi"
        assert "VLESSNode" not in line

    def test_vmess_ps_becomes_remark(self):
        candidate = _ranked(
            1, "vmess", VMESS, "vmess.example.com", 443, country_code="US", latency_ms=87.2
        )
        line = build_subscription([candidate]).content.splitlines()[0]
        parsed = _parse(line)
        assert parsed.fragment == "🇺🇸 US | VMESS | 87ms | GozargahAzadi"
        assert "VMessNode" not in line

    def test_shadowsocks_fragment_becomes_remark(self):
        candidate = _ranked(1, "ss", SS, "ss.example.com", 8388, country_code="US", latency_ms=87.2)
        line = build_subscription([candidate]).content.splitlines()[0]
        assert unquote(urlparse(line).fragment) == "🇺🇸 US | SS | 87ms | GozargahAzadi"
        assert "SSNode" not in line

    def test_original_fragment_never_leaks_into_any_feed(self):
        candidates = [
            _ranked(
                1,
                "vless",
                VLESS,
                "vless.example.com",
                443,
                country_code="DE",
                latency_ms=124.5,
            ),
            _ranked(
                2,
                "vmess",
                VMESS,
                "vmess.example.com",
                443,
                country_code="US",
                latency_ms=87.2,
            ),
            _ranked(3, "ss", SS, "ss.example.com", 8388, country_code="DE", latency_ms=88.1),
        ]
        content = build_subscription(candidates).content
        for leaked in ("VLESSNode", "VMessNode", "SSNode"):
            assert leaked not in content

    def test_remark_in_protocol_specific_feeds(self):
        candidates = [
            _ranked(
                1,
                "vless",
                VLESS,
                "vless.example.com",
                443,
                country_code="DE",
                latency_ms=124.5,
            ),
            _ranked(
                2,
                "ss",
                SS,
                "ss.example.com",
                8388,
                country_code="US",
                latency_ms=87.2,
            ),
        ]
        feeds = {
            protocol: plain for protocol, plain, _b64 in build_protocol_subscriptions(candidates)
        }
        vless_lines = feeds["vless"].content.splitlines()
        ss_lines = feeds["ss"].content.splitlines()
        assert unquote(urlparse(vless_lines[0]).fragment) == "🇩🇪 DE | VLESS | 125ms | GozargahAzadi"
        assert unquote(urlparse(ss_lines[0]).fragment) == "🇺🇸 US | SS | 87ms | GozargahAzadi"

    def test_base64_feed_decodes_to_plain_with_remark(self):
        candidate = _ranked(
            1, "vless", VLESS, "vless.example.com", 443, country_code="DE", latency_ms=124.5
        )
        plain = build_subscription([candidate]).content
        encoded = build_subscription([candidate], format=SubscriptionFormat.BASE64).content
        assert base64.b64decode(encoded.encode("ascii")).decode("utf-8") == plain
        line = plain.splitlines()[0]
        assert unquote(urlparse(line).fragment) == "🇩🇪 DE | VLESS | 125ms | GozargahAzadi"
        assert "125" in line
        assert "GozargahAzadi" in line

    def test_json_uri_has_remark_no_separate_field(self):
        candidate = _ranked(
            1, "vless", VLESS, "vless.example.com", 443, country_code="DE", latency_ms=124.5
        )
        content = build_subscription([candidate], format=SubscriptionFormat.JSON).content
        items = json.loads(content)
        (item,) = items
        assert "remark" not in item
        assert "Remark" not in item
        assert item["uri"].startswith("vless://")
        assert unquote(urlparse(item["uri"]).fragment) == "🇩🇪 DE | VLESS | 125ms | GozargahAzadi"
        assert "VLESSNode" not in item["uri"]

    def test_content_hash_unchanged_by_remark(self):
        candidate = _ranked(
            1,
            "ss",
            SS,
            "ss.example.com",
            8388,
            country_code="US",
            latency_ms=87.2,
            content_hash="ab" * 32,
        )
        content = build_subscription([candidate], format=SubscriptionFormat.JSON).content
        (item,) = json.loads(content)
        assert item["content_hash"] == "ab" * 32
        assert item["uri"].startswith("ss://")


# --- Integration: Phase 9.3 behavior unchanged --------------------------------


class TestPhaseNineThreeUnchanged:
    def test_empty_protocol_feeds_still_skipped(self):
        candidates = [
            _ranked(
                1,
                "http",
                "http://user:p%40ss@proxy.example.com:8080",
                "proxy.example.com",
                8080,
                country_code="US",
                latency_ms=73.0,
            )
        ]
        emitted = {protocol for protocol, _plain, _b64 in build_protocol_subscriptions(candidates)}
        assert emitted == {"http"}

    def test_protocol_feeds_still_subset_of_combined(self):
        candidates = [
            _ranked(
                1,
                "vless",
                VLESS,
                "vless.example.com",
                443,
                country_code="DE",
                latency_ms=124.5,
            ),
            _ranked(
                2,
                "ss",
                SS,
                "ss.example.com",
                8388,
                country_code="US",
                latency_ms=87.2,
            ),
        ]
        combined = set(build_subscription(candidates).content.splitlines())
        for _protocol, plain, _b64 in build_protocol_subscriptions(candidates):
            assert set(plain.content.splitlines()) <= combined

    def test_combined_and_protocol_feeds_are_deterministic(self):
        candidates = [
            _ranked(
                1,
                "vless",
                VLESS,
                "vless.example.com",
                443,
                country_code="DE",
                latency_ms=124.5,
            )
        ]
        assert build_subscription(candidates).content == build_subscription(candidates).content
        first = build_protocol_subscriptions(candidates)
        second = build_protocol_subscriptions(candidates)
        assert [(protocol, plain.content, b64.content) for protocol, plain, b64 in first] == [
            (protocol, plain.content, b64.content) for protocol, plain, b64 in second
        ]
