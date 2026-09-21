"""VMess protocol parser."""

from __future__ import annotations

import base64
import json
from urllib.parse import urlparse

from proxyaggregator.parsers.base import BaseParser, ParseError, ParseResult


class VmessParser(BaseParser):
    """Parse VMess URIs: vmess://base64(json-config)"""

    @property
    def supported_protocol(self) -> str:
        return "vmess"

    def parse(self, uri: str) -> ParseResult | ParseError:
        try:
            parsed = urlparse(uri)
        except Exception as e:
            return ParseError(protocol="vmess", error=str(e), raw_uri=uri)

        if parsed.scheme.lower() != "vmess":
            return ParseError(protocol="vmess", error="not a vmess URI", raw_uri=uri)

        # The host part after vmess:// is base64-encoded JSON
        encoded = parsed.path or parsed.netloc
        if not encoded:
            return ParseError(protocol="vmess", error="empty payload", raw_uri=uri)

        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
        except Exception as e:
            return ParseError(protocol="vmess", error=f"invalid base64: {e}", raw_uri=uri)

        try:
            config = json.loads(decoded)
        except json.JSONDecodeError as e:
            return ParseError(protocol="vmess", error=f"invalid JSON: {e}", raw_uri=uri)

        required = ["add", "port", "id", "net"]
        for field in required:
            if field not in config:
                return ParseError(protocol="vmess", error=f"missing field: {field}", raw_uri=uri)

        host = config["add"]
        if not host:
            return ParseError(protocol="vmess", error="empty host", raw_uri=uri)

        try:
            port = int(config["port"])
        except (ValueError, TypeError):
            return ParseError(protocol="vmess", error="invalid port", raw_uri=uri)

        if port < 1 or port > 65535:
            return ParseError(protocol="vmess", error=f"port {port} out of range", raw_uri=uri)

        # Fragment comes from the URI fragment or ps field
        fragment = parsed.fragment or config.get("ps") or None

        return ParseResult(
            protocol="vmess",
            host=host,
            port=port,
            raw_uri=uri,
            user=config.get("id"),
            sni=config.get("sni") or None,
            network=config.get("net") or None,
            tls=config.get("tls") or None,
            path=config.get("path") or None,
            host_header=config.get("host") or None,
            fragment=fragment,
            service_name=config.get("scy") or None,
        )
