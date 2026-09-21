"""Shadowsocks protocol parser."""

from __future__ import annotations

import base64
import binascii
from urllib.parse import urlparse

from proxyaggregator.parsers.base import BaseParser, ParseError, ParseResult


class ShadowsocksParser(BaseParser):
    """Parse Shadowsocks URIs: ss://base64(method:password)@host:port#fragment"""

    @property
    def supported_protocol(self) -> str:
        return "ss"

    def parse(self, uri: str) -> ParseResult | ParseError:
        try:
            parsed = urlparse(uri)
        except ValueError as e:
            return ParseError(protocol="ss", error=str(e), raw_uri=uri)

        if parsed.scheme.lower() != "ss":
            return ParseError(protocol="ss", error="not an ss URI", raw_uri=uri)

        host = parsed.hostname

        if not host:
            return ParseError(protocol="ss", error="missing host", raw_uri=uri)

        try:
            port = parsed.port
        except ValueError as e:
            return ParseError(protocol="ss", error=str(e), raw_uri=uri)

        if port is None:
            return ParseError(protocol="ss", error="missing or invalid port", raw_uri=uri)

        # The userinfo is base64(method:password) in SIP002 format
        userinfo = parsed.username
        if not userinfo:
            return ParseError(protocol="ss", error="missing method:password", raw_uri=uri)

        try:
            decoded = base64.b64decode(userinfo).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError) as e:
            return ParseError(protocol="ss", error=f"invalid base64 userinfo: {e}", raw_uri=uri)

        parts = decoded.split(":", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return ParseError(protocol="ss", error="invalid method:password format", raw_uri=uri)

        method, password = parts

        return ParseResult(
            protocol="ss",
            host=host,
            port=port,
            raw_uri=uri,
            method=method,
            password=password,
            fragment=parsed.fragment or None,
        )
