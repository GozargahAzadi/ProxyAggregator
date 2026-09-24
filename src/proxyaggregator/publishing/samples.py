"""Deterministic demo sample feeds for the local dry-run (Phase 9).

``build_demo_subscriptions`` produces the three canonical Phase 8 feeds from
an embedded set of SYNTHETIC proxies. Every URI uses ``example.com`` and
obviously fake credentials; this data exists solely so the publisher can be
exercised end-to-end locally (``python -m proxyaggregator sample-subscriptions``)
without GitHub, a database, or live sources. It must never be mistaken for
production traffic.
"""

from __future__ import annotations

import base64
import json

from proxyaggregator.publishing.feeds import build_protocol_subscriptions, build_subscription
from proxyaggregator.publishing.models import RankedProxy, Subscription, SubscriptionFormat
from proxyaggregator.publishing.publisher import default_filename, default_protocol_filename

# Documented example network; see RFC 6761. Never real.
_VLESS_HOST = "vless.example.com"
_VMESS_HOST = "vmess.example.com"
_TROJAN_HOST = "trojan.example.com"
_SS_HOST = "ss.example.com"
_HY_HOST = "hy.example.com"
_HY2_HOST = "hy2.example.com"
_PROXY_HOST = "proxy.example.com"

_UUID = "d98d1c36-ccc8-4c77-9e9f-81c1b7584277"

# (protocol, raw_uri, host, port, country_code, latency_ms) — the last two
# drive the deterministic Phase 10 Remark and are purely illustrative.
_DEMO_URIS: tuple[tuple[str, str, str, int, str, float], ...] = (
    (
        "vless",
        f"vless://{_UUID}@{_VLESS_HOST}:443"
        "?network=ws&security=tls&sni=example.com&host=example.com&path=%2Fws#DemoVLESS",
        _VLESS_HOST,
        443,
        "DE",
        124.5,
    ),
    (
        "vmess",
        "vmess://"
        + base64.b64encode(
            json.dumps(
                {
                    "v": "2",
                    "ps": "DemoVMess",
                    "add": "vmess.example.com",
                    "port": "443",
                    "id": _UUID,
                    "net": "ws",
                    "tls": "tls",
                    "sni": "example.com",
                    "host": "example.com",
                    "path": "/ws",
                },
                separators=(",", ":"),
            ).encode("utf-8")
        ).decode("ascii"),
        _VMESS_HOST,
        443,
        "US",
        87.2,
    ),
    (
        "trojan",
        f"trojan://demo-secret@{_TROJAN_HOST}:443?security=tls&sni=example.com#DemoTrojan",
        _TROJAN_HOST,
        443,
        "FR",
        133.7,
    ),
    (
        "ss",
        "ss://"
        + base64.b64encode(b"aes-128-gcm:demo-password").decode("ascii")
        + f"@{_SS_HOST}:8388#DemoSS",
        _SS_HOST,
        8388,
        "DE",
        88.1,
    ),
    (
        "hysteria",
        f"hysteria://{_HY_HOST}:443?auth=demokey&sni=example.com#DemoHy",
        _HY_HOST,
        443,
        "SG",
        150.0,
    ),
    (
        "hysteria2",
        f"hysteria2://demo@{_HY2_HOST}:443?sni=example.com#DemoHy2",
        _HY2_HOST,
        443,
        "JP",
        99.9,
    ),
    ("socks4", f"socks4://demo@{_PROXY_HOST}:1080", _PROXY_HOST, 1080, "DE", 200.3),
    (
        "socks4",
        f"socks4a://{_PROXY_HOST}:1080",
        _PROXY_HOST,
        1080,
        "US",
        201.0,
    ),
    ("socks5", f"socks5://demo:p%40ss@{_PROXY_HOST}:1080", _PROXY_HOST, 1080, "GB", 65.4),
    ("http", f"http://demo:p%40ss@{_PROXY_HOST}:8080", _PROXY_HOST, 8080, "US", 73.0),
    ("https", f"https://{_PROXY_HOST}:8443", _PROXY_HOST, 8443, "US", 73.0),
)


def _demo_candidates() -> list[RankedProxy]:
    candidates: list[RankedProxy] = []
    for index, (protocol, raw_uri, host, port, country_code, latency_ms) in enumerate(
        _DEMO_URIS, start=1
    ):
        candidates.append(
            RankedProxy(
                proxy_config_id=index,
                protocol=protocol,
                host=host,
                port=port,
                raw_uri=raw_uri,
                content_hash=(f"{index:010d}" * 7)[:64],
                score=1.0 - index / 1000,
                rank=index,
                country_code=country_code,
                latency_ms=latency_ms,
            )
        )
    return candidates


def build_demo_subscriptions(
    *,
    max_items: int | None = None,
) -> list[tuple[str, Subscription]]:
    """Build the demo feeds in deterministic order.

    Returns ``(filename, Subscription)`` pairs for the three combined feeds
    (plain, base64, JSON) followed by the per-protocol plain + base64 feeds,
    all using the canonical artifact filenames of the publisher.
    """
    candidates = _demo_candidates()
    feeds: list[tuple[str, Subscription]] = [
        (
            default_filename(fmt),
            build_subscription(candidates, format=fmt, max_items=max_items),
        )
        for fmt in (SubscriptionFormat.PLAIN, SubscriptionFormat.BASE64, SubscriptionFormat.JSON)
    ]
    for protocol, plain, base64_feed in build_protocol_subscriptions(
        candidates, max_items=max_items
    ):
        feeds.append((default_protocol_filename(protocol, SubscriptionFormat.PLAIN), plain))
        feeds.append((default_protocol_filename(protocol, SubscriptionFormat.BASE64), base64_feed))
    return feeds
