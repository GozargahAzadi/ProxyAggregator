"""VLESS protocol parser."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from proxyaggregator.parsers.base import BaseParser, ParseError, ParseResult


class VlessParser(BaseParser):
    """Parse VLESS URIs: vless://uuid@host:port?params#fragment"""

    @property
    def supported_protocol(self) -> str:
        return "vless"

    def parse(self, uri: str) -> ParseResult | ParseError:
        try:
            parsed = urlparse(uri)
        except ValueError as e:
            return ParseError(protocol="vless", error=str(e), raw_uri=uri)

        if parsed.scheme.lower() != "vless":
            return ParseError(protocol="vless", error="not a vless URI", raw_uri=uri)

        host = parsed.hostname

        if not host:
            return ParseError(protocol="vless", error="missing host", raw_uri=uri)

        try:
            port = parsed.port
        except ValueError as e:
            return ParseError(protocol="vless", error=str(e), raw_uri=uri)

        if port is None:
            return ParseError(protocol="vless", error="missing or invalid port", raw_uri=uri)

        params = parse_qs(parsed.query)

        return ParseResult(
            protocol="vless",
            host=host,
            port=port,
            raw_uri=uri,
            user=parsed.username or "",
            password=parsed.password,
            sni=_first(params, "sni"),
            network=_first(params, "type") or _first(params, "network"),
            tls=_first(params, "security"),
            path=_first(params, "path"),
            host_header=_first(params, "host"),
            fragment=parsed.fragment or None,
            service_name=_first(params, "serviceName"),
            flow=_first(params, "flow"),
        )


def _first(params: dict[str, list[str]], key: str) -> str | None:
    """Return the first value for a query parameter, or None."""
    values = params.get(key)
    if values and values[0]:
        return values[0]
    return None
