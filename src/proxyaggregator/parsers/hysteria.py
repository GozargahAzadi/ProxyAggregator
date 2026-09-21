"""Hysteria and Hysteria2 protocol parsers."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from proxyaggregator.parsers.base import BaseParser, ParseError, ParseResult


class HysteriaParser(BaseParser):
    """Parse Hysteria URIs: hysteria://host:port?params#fragment"""

    @property
    def supported_protocol(self) -> str:
        return "hysteria"

    def parse(self, uri: str) -> ParseResult | ParseError:
        try:
            parsed = urlparse(uri)
        except Exception as e:
            return ParseError(protocol="hysteria", error=str(e), raw_uri=uri)

        if parsed.scheme.lower() != "hysteria":
            return ParseError(protocol="hysteria", error="not a hysteria URI", raw_uri=uri)

        host = parsed.hostname
        port = parsed.port

        if not host:
            return ParseError(protocol="hysteria", error="missing host", raw_uri=uri)
        if port is None:
            return ParseError(protocol="hysteria", error="missing or invalid port", raw_uri=uri)
        if port < 1 or port > 65535:
            return ParseError(protocol="hysteria", error=f"port {port} out of range", raw_uri=uri)

        params = parse_qs(parsed.query)

        return ParseResult(
            protocol="hysteria",
            host=host,
            port=port,
            raw_uri=uri,
            user=_first(params, "auth"),
            sni=_first(params, "sni"),
            fragment=parsed.fragment or None,
            obfs=_first(params, "obfs"),
            obfs_password=_first(params, "obfs-password"),
        )


class Hysteria2Parser(BaseParser):
    """Parse Hysteria2 URIs: hysteria2://password@host:port?params#fragment"""

    @property
    def supported_protocol(self) -> str:
        return "hysteria2"

    def parse(self, uri: str) -> ParseResult | ParseError:
        try:
            parsed = urlparse(uri)
        except Exception as e:
            return ParseError(protocol="hysteria2", error=str(e), raw_uri=uri)

        if parsed.scheme.lower() != "hysteria2":
            return ParseError(protocol="hysteria2", error="not a hysteria2 URI", raw_uri=uri)

        host = parsed.hostname
        port = parsed.port

        if not host:
            return ParseError(protocol="hysteria2", error="missing host", raw_uri=uri)
        if port is None:
            return ParseError(protocol="hysteria2", error="missing or invalid port", raw_uri=uri)
        if port < 1 or port > 65535:
            return ParseError(protocol="hysteria2", error=f"port {port} out of range", raw_uri=uri)

        params = parse_qs(parsed.query)

        return ParseResult(
            protocol="hysteria2",
            host=host,
            port=port,
            raw_uri=uri,
            user=parsed.username or "",
            password=parsed.password,
            sni=_first(params, "sni"),
            fragment=parsed.fragment or None,
            obfs=_first(params, "obfs"),
            obfs_password=_first(params, "obfs-password"),
        )


def _first(params: dict[str, list[str]], key: str) -> str | None:
    """Return the first value for a query parameter, or None."""
    values = params.get(key)
    if values and values[0]:
        return values[0]
    return None
