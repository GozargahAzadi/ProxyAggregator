"""Protocol detection from URI scheme."""

from __future__ import annotations

from urllib.parse import urlparse


def detect_protocol(uri: str) -> str | None:
    """Return the protocol string if the URI can be recognized, else None."""
    if not uri or not uri.strip():
        return None

    stripped = uri.strip()
    # URI schemes must start with a letter
    if not stripped[0].isalpha():
        return None

    try:
        parsed = urlparse(stripped)
    except Exception:
        return None

    scheme = parsed.scheme.lower()

    # Map standard schemes to protocol identifiers
    scheme_map = {
        "vless": "vless",
        "vmess": "vmess",
        "trojan": "trojan",
        "ss": "ss",
        "hysteria": "hysteria",
        "hysteria2": "hysteria2",
        "socks4": "socks4",
        "socks4a": "socks4a",
        "socks5": "socks5",
        "http": "http",
        "https": "https",
    }

    return scheme_map.get(scheme)
