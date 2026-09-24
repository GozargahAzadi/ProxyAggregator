"""Deterministic canonical URI serialization (Phase 8).

Each Phase 3 protocol is rebuilt from its ``ParseResult`` into a canonical URI
with:

- a stable scheme,
- canonical percent-encoding (every byte outside the unreserved set encoded),
- explicit, sorted query parameter ordering,
- no random values, timestamps, dbi ids, or scores,

so that identical configurations always produce byte-identical URIs.

Protocol parameters that the persistence layer (and Phase 3 parsers) do not
carry — e.g. VMess ``aid``/``cipher``, Shadowsocks plugins, Hysteria bandwidth —
cannot be recovered and are intentionally absent. Missing mandatory identity
fields are reported as ``ValueError`` with a short reason; the span is never
silently skipped.
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING
from urllib.parse import quote, unquote

if TYPE_CHECKING:
    from collections.abc import Callable

    from proxyaggregator.parsers.base import ParseResult

_QUERY_FIELDS: dict[str, dict[str, str]] = {
    "vless": {
        "flow": "flow",
        "host": "host_header",
        "network": "network",
        "path": "path",
        "security": "tls",
        "serviceName": "service_name",
        "sni": "sni",
    },
    "trojan": {
        "host": "host_header",
        "path": "path",
        "security": "tls",
        "serviceName": "service_name",
        "sni": "sni",
        "type": "network",
    },
    "hysteria": {
        "auth": "user",
        "obfs": "obfs",
        "obfs-password": "obfs_password",
        "sni": "sni",
    },
    "hysteria2": {
        "obfs": "obfs",
        "obfs-password": "obfs_password",
        "sni": "sni",
    },
}


def _quote(value: str) -> str:
    """Percent-encode a value so it is URI-standard and UTF-8 based."""
    return quote(value, safe="")


def _canonical_quote(value: str) -> str:
    """Percent-decode a parsed value first, then re-encode it canonically.

    ``urlparse`` leaves ``userinfo`` and ``fragment`` in their raw
    percent-encoded form (query values are already decoded by the Phase 3
    parsers via ``parse_qs``). Decoding first avoids double-encoding a value
    such as ``p%40ss``.
    """
    return _quote(unquote(value))


def _host_port(host: str, port: int) -> str:
    rendered_host = f"[{host}]" if ":" in host else host
    return f"{rendered_host}:{port}"


def _userinfo(user: str | None, password: str | None) -> str | None:
    if not user:
        return None
    encoded_user = _canonical_quote(user)
    if password is None:
        return encoded_user
    return f"{encoded_user}:{_canonical_quote(password)}"


def _fragment(fragment: str | None) -> str:
    if not fragment:
        return ""
    return f"#{_canonical_quote(fragment)}"


def _query(result, mapping: dict[str, str]) -> str:
    pairs = []
    for param, attr in mapping.items():
        value = getattr(result, attr)
        if value is not None and value != "":
            pairs.append((param, _quote(value)))
    pairs.sort(key=lambda item: item[0])
    return "&".join(f"{key}={value}" for key, value in pairs)


def _simple(scheme: str) -> Callable:
    """Build a serializer for userinfo-style URIs (socks/http/https)."""

    def serialize(result) -> str:
        cred = _userinfo(result.user, result.password)
        netloc = _host_port(result.host, result.port)
        uri = f"{scheme}://{netloc}" if cred is None else f"{scheme}://{cred}@{netloc}"
        return uri + _fragment(result.fragment)

    return serialize


def _serialize_vless(result) -> str:
    if not result.user:
        raise ValueError("missing user (uuid)")
    cred = _userinfo(result.user, result.password)
    uri = f"vless://{cred}@{_host_port(result.host, result.port)}"
    q = _query(result, _QUERY_FIELDS["vless"])
    if q:
        uri += f"?{q}"
    return uri + _fragment(result.fragment)


def _serialize_vmess(result) -> str:
    if not result.user:
        raise ValueError("missing user (id)")
    if not result.network:
        raise ValueError("missing network")
    config: dict[str, str] = {
        "v": "2",
        "add": result.host,
        "port": str(result.port),
        "id": result.user,
        "net": result.network,
    }
    if result.tls:
        config["tls"] = result.tls
    if result.sni:
        config["sni"] = result.sni
    if result.host_header:
        config["host"] = result.host_header
    if result.path:
        config["path"] = result.path
    if result.fragment:
        config["ps"] = result.fragment
    raw = json.dumps(config, sort_keys=True, separators=(",", ":"))
    encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    return f"vmess://{encoded}"


def _serialize_trojan(result) -> str:
    if not result.user and not result.password:
        raise ValueError("missing password")
    cred = _userinfo(result.user, result.password)
    uri = f"trojan://{cred}@{_host_port(result.host, result.port)}"
    q = _query(result, _QUERY_FIELDS["trojan"])
    if q:
        uri += f"?{q}"
    return uri + _fragment(result.fragment)


def _serialize_shadowsocks(result) -> str:
    if not result.method or not result.password:
        raise ValueError("missing method or password")
    payload = base64.b64encode(f"{result.method}:{result.password}".encode()).decode("ascii")
    return f"ss://{payload}@{_host_port(result.host, result.port)}" + _fragment(result.fragment)


def _serialize_hysteria(result) -> str:
    uri = f"hysteria://{_host_port(result.host, result.port)}"
    q = _query(result, _QUERY_FIELDS["hysteria"])
    if q:
        uri += f"?{q}"
    return uri + _fragment(result.fragment)


def _serialize_hysteria2(result) -> str:
    if not result.user and not result.password:
        raise ValueError("missing auth password")
    cred = _userinfo(result.user, result.password)
    uri = f"hysteria2://{cred}@{_host_port(result.host, result.port)}"
    q = _query(result, _QUERY_FIELDS["hysteria2"])
    if q:
        uri += f"?{q}"
    return uri + _fragment(result.fragment)


_SERIALIZERS: dict[str, Callable] = {
    "vless": _serialize_vless,
    "vmess": _serialize_vmess,
    "trojan": _serialize_trojan,
    "ss": _serialize_shadowsocks,
    "hysteria": _serialize_hysteria,
    "hysteria2": _serialize_hysteria2,
    "socks4": _simple("socks4"),
    "socks5": _simple("socks5"),
    "http": _simple("http"),
    "https": _simple("https"),
}

#: Canonical, deterministic order of serializable protocols. Derived from
#: ``_SERIALIZERS`` (single source of truth) so protocol feed generation can
#: never drift from what can actually be serialized.
SUPPORTED_PROTOCOLS: tuple[str, ...] = tuple(_SERIALIZERS)


def canonical_uri(result: ParseResult) -> str:
    """Return the deterministic canonical URI for a parsed proxy configuration.

    Raises:
        ValueError: unsupported protocol or missing mandatory field. The reason
            is a short stable token and never contains credentials.
    """
    serializer = _SERIALIZERS.get(result.protocol)
    if serializer is None:
        raise ValueError("unsupported_protocol")
    return serializer(result)
