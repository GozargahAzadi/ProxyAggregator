"""Protocol parsers for proxy configurations.

Supported protocols:
- VLESS
- VMess
- Trojan
- Shadowsocks (SS)
- Hysteria
- Hysteria2
- SOCKS4 / SOCKS4a
- SOCKS5
- HTTP proxy
- HTTPS proxy
"""

from proxyaggregator.parsers.base import BaseParser, ParseError, ParseResult
from proxyaggregator.parsers.detect import detect_protocol
from proxyaggregator.parsers.extract import extract_uris
from proxyaggregator.parsers.normalize import normalize_uri
from proxyaggregator.parsers.registry import ParserRegistry, get_registry

__all__ = [
    "BaseParser",
    "ParseError",
    "ParseResult",
    "ParserRegistry",
    "detect_protocol",
    "extract_uris",
    "get_registry",
    "normalize_uri",
]
