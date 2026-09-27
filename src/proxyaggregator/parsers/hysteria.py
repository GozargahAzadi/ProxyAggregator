"""Hysteria and Hysteria2 protocol parsers.

Both Hysteria protocols support URI "port hopping": the port field may be a
single port, a comma-separated list of ports, port ranges, or a mix
(e.g. ``51286,50000-53000``). Every listed alternative is a reachable server
endpoint and a client may connect to any single one of them, so the parsers
deterministically select the first listed port, then validate it in range.
Malformed port fields become a controlled :class:`ParseError` and never raise.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from proxyaggregator.parsers.base import BaseParser, ParseError, ParseResult

_PORT_RANGE_SEPARATOR = "-"
_MAX_PORT = 65535


def _port_field_from_netloc(netloc: str) -> str | None:
    """Return the raw port substring of a URI netloc, or ``None`` if absent.

    Handles userinfo (``user@host:port``) and bracketed IPv6 hosts
    (``[2001:db8::1]:port``). The value is returned verbatim so the caller
    can decide how to interpret it.
    """
    rest = netloc.rsplit("@", 1)[-1]
    if not rest:
        return None
    if rest.startswith("["):
        close = rest.find("]")
        if close == -1:
            return None
        tail = rest[close + 1 :]
    else:
        tail = rest
    if ":" not in tail:
        return None
    return tail.rsplit(":", 1)[-1]


def _first_port(port_field: str) -> int | None:
    """Return the first usable port from a hysteria port field, else ``None``.

    Port-hopping fields combine single ports and/or ranges (``51286``,
    ``50000-53000``, ``51286,50000-53000``). The first listed alternative is
    the operator's primary endpoint, so it is selected deterministically.
    Malformed tokens (non-numeric, reversed or unbounded ranges, stray
    delimiters, duplicate ranges) make the whole field invalid.
    """
    if not port_field:
        return None
    first: int | None = None
    for token in port_field.split(","):
        token = token.strip()
        if not token:
            return None
        if _PORT_RANGE_SEPARATOR in token:
            if token.count(_PORT_RANGE_SEPARATOR) != 1:
                return None
            start_token, end_token = (part.strip() for part in token.split(_PORT_RANGE_SEPARATOR))
            if not (start_token.isdigit() and end_token.isdigit()):
                return None
            start, end = int(start_token), int(end_token)
            if start < 1 or end > _MAX_PORT or start > end:
                return None
            port = start
        elif not token.isdigit():
            return None
        else:
            port = int(token)
            if port < 1 or port > _MAX_PORT:
                return None
        if first is None:
            first = port
    return first


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
        port_field = _port_field_from_netloc(parsed.netloc)
        port = _first_port(port_field) if port_field else None

        if not host:
            return ParseError(protocol="hysteria", error="missing host", raw_uri=uri)
        if port is None:
            error = "missing or invalid port" if not port_field else f"invalid port '{port_field}'"
            return ParseError(protocol="hysteria", error=error, raw_uri=uri)

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
        port_field = _port_field_from_netloc(parsed.netloc)
        port = _first_port(port_field) if port_field else None

        if not host:
            return ParseError(protocol="hysteria2", error="missing host", raw_uri=uri)
        if port is None:
            error = "missing or invalid port" if not port_field else f"invalid port '{port_field}'"
            return ParseError(protocol="hysteria2", error=error, raw_uri=uri)

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
