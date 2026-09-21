"""Trojan protocol parser."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from proxyaggregator.parsers.base import BaseParser, ParseError, ParseResult


class TrojanParser(BaseParser):
    """Parse Trojan URIs: trojan://password@host:port?params#fragment"""

    @property
    def supported_protocol(self) -> str:
        return "trojan"

    def parse(self, uri: str) -> ParseResult | ParseError:
        try:
            parsed = urlparse(uri)
        except Exception as e:
            return ParseError(protocol="trojan", error=str(e), raw_uri=uri)

        if parsed.scheme.lower() != "trojan":
            return ParseError(protocol="trojan", error="not a trojan URI", raw_uri=uri)

        host = parsed.hostname
        port = parsed.port

        if not host:
            return ParseError(protocol="trojan", error="missing host", raw_uri=uri)
        if port is None:
            return ParseError(protocol="trojan", error="missing or invalid port", raw_uri=uri)
        if port < 1 or port > 65535:
            return ParseError(protocol="trojan", error=f"port {port} out of range", raw_uri=uri)

        params = parse_qs(parsed.query)

        return ParseResult(
            protocol="trojan",
            host=host,
            port=port,
            raw_uri=uri,
            user=parsed.username or "",
            password=parsed.password,
            sni=_first(params, "sni"),
            network=_first(params, "type"),
            tls=_first(params, "security") or "tls",
            path=_first(params, "path"),
            host_header=_first(params, "host"),
            fragment=parsed.fragment or None,
            service_name=_first(params, "serviceName"),
        )


def _first(params: dict[str, list[str]], key: str) -> str | None:
    """Return the first value for a query parameter, or None."""
    values = params.get(key)
    if values and values[0]:
        return values[0]
    return None
