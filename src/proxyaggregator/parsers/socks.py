"""SOCKS4/SOCKS5 protocol parsers."""

from __future__ import annotations

from urllib.parse import urlparse

from proxyaggregator.parsers.base import BaseParser, ParseError, ParseResult


class Socks4Parser(BaseParser):
    """Parse SOCKS4/4a URIs: socks4://[user@]host:port"""

    @property
    def supported_protocol(self) -> str:
        return "socks4"

    def parse(self, uri: str) -> ParseResult | ParseError:
        try:
            parsed = urlparse(uri)
        except Exception as e:
            return ParseError(protocol="socks4", error=str(e), raw_uri=uri)

        scheme = parsed.scheme.lower()
        if scheme not in ("socks4", "socks4a"):
            return ParseError(protocol="socks4", error="not a socks4 URI", raw_uri=uri)

        host = parsed.hostname
        port = parsed.port

        if not host:
            return ParseError(protocol="socks4", error="missing host", raw_uri=uri)
        if port is None:
            return ParseError(protocol="socks4", error="missing or invalid port", raw_uri=uri)
        if port < 1 or port > 65535:
            return ParseError(protocol="socks4", error=f"port {port} out of range", raw_uri=uri)

        return ParseResult(
            protocol="socks4",
            host=host,
            port=port,
            raw_uri=uri,
            user=parsed.username or None,
        )


class Socks5Parser(BaseParser):
    """Parse SOCKS5 URIs: socks5://[user:password@]host:port"""

    @property
    def supported_protocol(self) -> str:
        return "socks5"

    def parse(self, uri: str) -> ParseResult | ParseError:
        try:
            parsed = urlparse(uri)
        except Exception as e:
            return ParseError(protocol="socks5", error=str(e), raw_uri=uri)

        if parsed.scheme.lower() != "socks5":
            return ParseError(protocol="socks5", error="not a socks5 URI", raw_uri=uri)

        host = parsed.hostname
        port = parsed.port

        if not host:
            return ParseError(protocol="socks5", error="missing host", raw_uri=uri)
        if port is None:
            return ParseError(protocol="socks5", error="missing or invalid port", raw_uri=uri)
        if port < 1 or port > 65535:
            return ParseError(protocol="socks5", error=f"port {port} out of range", raw_uri=uri)

        return ParseResult(
            protocol="socks5",
            host=host,
            port=port,
            raw_uri=uri,
            user=parsed.username or None,
            password=parsed.password,
        )
