"""HTTP/HTTPS proxy protocol parsers."""

from __future__ import annotations

from urllib.parse import urlparse

from proxyaggregator.parsers.base import BaseParser, ParseError, ParseResult


class HttpProxyParser(BaseParser):
    """Parse HTTP proxy URIs: http://[user:password@]host:port"""

    @property
    def supported_protocol(self) -> str:
        return "http"

    def parse(self, uri: str) -> ParseResult | ParseError:
        try:
            parsed = urlparse(uri)
        except Exception as e:
            return ParseError(protocol="http", error=str(e), raw_uri=uri)

        if parsed.scheme.lower() != "http":
            return ParseError(protocol="http", error="not an http URI", raw_uri=uri)

        host = parsed.hostname
        port = parsed.port

        if not host:
            return ParseError(protocol="http", error="missing host", raw_uri=uri)
        if port is None:
            return ParseError(protocol="http", error="missing or invalid port", raw_uri=uri)
        if port < 1 or port > 65535:
            return ParseError(protocol="http", error=f"port {port} out of range", raw_uri=uri)

        return ParseResult(
            protocol="http",
            host=host,
            port=port,
            raw_uri=uri,
            user=parsed.username or None,
            password=parsed.password,
        )


class HttpsProxyParser(BaseParser):
    """Parse HTTPS proxy URIs: https://[user:password@]host:port"""

    @property
    def supported_protocol(self) -> str:
        return "https"

    def parse(self, uri: str) -> ParseResult | ParseError:
        try:
            parsed = urlparse(uri)
        except Exception as e:
            return ParseError(protocol="https", error=str(e), raw_uri=uri)

        if parsed.scheme.lower() != "https":
            return ParseError(protocol="https", error="not an https URI", raw_uri=uri)

        host = parsed.hostname
        port = parsed.port

        if not host:
            return ParseError(protocol="https", error="missing host", raw_uri=uri)
        if port is None:
            return ParseError(protocol="https", error="missing or invalid port", raw_uri=uri)
        if port < 1 or port > 65535:
            return ParseError(protocol="https", error=f"port {port} out of range", raw_uri=uri)

        return ParseResult(
            protocol="https",
            host=host,
            port=port,
            raw_uri=uri,
            user=parsed.username or None,
            password=parsed.password,
        )
