"""Parser registry for protocol lookup."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from proxyaggregator.parsers.base import BaseParser


class ParserRegistry:
    """Registry of protocol parsers indexed by protocol string."""

    def __init__(self) -> None:
        self._parsers: dict[str, BaseParser] = {}

    def register(self, parser: BaseParser) -> None:
        """Register a parser for its supported protocol."""
        self._parsers[parser.supported_protocol] = parser

    def get(self, protocol: str) -> BaseParser | None:
        """Return the parser for the given protocol, or None."""
        return self._parsers.get(protocol)

    def supported_protocols(self) -> list[str]:
        """Return a list of registered protocol identifiers."""
        return list(self._parsers.keys())


_registry: ParserRegistry | None = None


def get_registry() -> ParserRegistry:
    """Return the default parser registry with all parsers registered."""
    global _registry
    if _registry is None:
        _registry = ParserRegistry()
        from proxyaggregator.parsers.http_proxy import HttpProxyParser, HttpsProxyParser
        from proxyaggregator.parsers.hysteria import Hysteria2Parser, HysteriaParser
        from proxyaggregator.parsers.shadowsocks import ShadowsocksParser
        from proxyaggregator.parsers.socks import Socks4Parser, Socks5Parser
        from proxyaggregator.parsers.trojan import TrojanParser
        from proxyaggregator.parsers.vless import VlessParser
        from proxyaggregator.parsers.vmess import VmessParser

        for cls in [
            VlessParser, VmessParser, TrojanParser, ShadowsocksParser,
            HysteriaParser, Hysteria2Parser,
            Socks4Parser, Socks5Parser,
            HttpProxyParser, HttpsProxyParser,
        ]:
            _registry.register(cls())

        # Socks4Parser handles both socks4 and socks4a schemes
        socks4 = _registry.get("socks4")
        if socks4:
            _registry._parsers["socks4a"] = socks4
    return _registry
