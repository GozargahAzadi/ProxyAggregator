"""Parser module — detects protocol, parses, normalizes proxy configs."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import urllib.parse
from typing import List, Optional

from .models import ConfigItem, Protocol

# ── Protocol scheme registry ────────────────────────────────────────────────

PROTOCOL_SCHEMES = frozenset({
    "vless", "vmess", "trojan", "shadowsocks", "ss",
    "hysteria2", "hy2", "hysteria", "hy",
    "tuic", "socks", "socks5",
})

# ── Parsing helpers ──────────────────────────────────────────────────────────

def detect_protocol(link: str) -> Protocol:
    """Detect the protocol from the URI scheme."""
    if "://" not in link:
        return Protocol.UNKNOWN
    scheme = link.split("://", 1)[0].lower()
    mapping = {
        "vless": Protocol.VLESS,
        "vmess": Protocol.VMESS,
        "trojan": Protocol.TROJAN,
        "shadowsocks": Protocol.SHADOWSOCKS,
        "ss": Protocol.SHADOWSOCKS,
        "hysteria2": Protocol.HYSTERIA2,
        "hy2": Protocol.HYSTERIA2,
        "hysteria": Protocol.HYSTERIA2,
        "hy": Protocol.HYSTERIA2,
        "tuic": Protocol.HYSTERIA2,
        "socks": Protocol.SOCKS,
        "socks5": Protocol.SOCKS,
    }
    return mapping.get(scheme, Protocol.UNKNOWN)


def is_dummy_config(link: str) -> bool:
    """Return True for obviously broken or placeholder entries."""
    # Decode URL-encoded fragments (e.g., #App%20not%20supported)
    try:
        decoded = urllib.parse.unquote(link)
    except Exception:
        decoded = link
    lower = decoded.lower()
    dummy_patterns = [
        "app not supported",
        "this is a dummy",
        "replace me",
        "invalid config",
        "example.com",
        "your-server.com",
        "add here",
    ]
    for pat in dummy_patterns:
        if pat in lower:
            return True
    if len(link.strip()) < 10:
        return True
    return False


def try_base64_decode(text: str, max_depth: int = 3) -> str:
    """Try to decode a base64-encoded subscription block.

    Returns the decoded text if successful, otherwise the original.
    Handles wrapped/multipart base64.
    """
    stripped = text.strip()
    if not stripped:
        return stripped

    # Try direct decode
    try:
        decoded = base64.b64decode(stripped, validate=True)
        result = decoded.decode("utf-8", errors="replace").strip()
        if result and len(result) > 5 and any(c.isalnum() for c in result):
            return result
    except Exception:
        pass

    # Try with wrapped lines
    joined = stripped.replace("\n", "").replace("\r", "")
    try:
        decoded = base64.b64decode(joined, validate=True)
        result = decoded.decode("utf-8", errors="replace").strip()
        if result and len(result) > 5:
            return result
    except Exception:
        pass

    # Try recursive (for nested base64)
    if max_depth > 0:
        # Only match pure base64 chunks (no spaces in middle unless padding)
        chunks = re.findall(r'[A-Za-z0-9+/=]{20,}={0,2}', stripped)
        for chunk in chunks:
            decoded = try_base64_decode(chunk, max_depth - 1)
            if decoded != chunk:
                return decoded

    return stripped


def extract_valid_lines(text: str) -> List[str]:
    """Extract valid proxy config lines from a blob (plain or base64)."""
    decoded = try_base64_decode(text)
    if decoded != text.strip():
        text = decoded

    lines: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "://" not in line:
            continue
        scheme = line.split("://", 1)[0].lower()
        if scheme in ("http", "https", "ftp", "file", "mailto", "tel",
                       "magnet", "git", "ssh", "javascript", "about",
                       "chrome", "blob", "data"):
            continue
        lines.append(line)
    return lines


def compute_fingerprint(link: str) -> str:
    """Compute a CDN-aware fingerprint for deduplication.

    Based on scheme + lowercase host + port only.
    Same server behind different CDN IPs or with different query params
    gets the same fingerprint (CDN-aware dedup).
    """
    try:
        parsed = urllib.parse.urlparse(link)
        host = (parsed.hostname or "").lower()
        port = parsed.port or 443 if parsed.scheme.lower() in ("vless", "vmess", "trojan", "hysteria2") else 80
        raw = f"{parsed.scheme.lower()}://{host}:{port}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]


def parse_config(link: str) -> Optional[ConfigItem]:
    """Parse a single config line into a ConfigItem, or None if invalid."""
    link = link.strip()
    if not link or "://" not in link:
        return None
    if is_dummy_config(link):
        return None

    protocol = detect_protocol(link)
    if protocol == Protocol.UNKNOWN:
        return None

    fingerprint = compute_fingerprint(link)
    remark = _extract_remark(link, protocol)

    return ConfigItem(
        link=link,
        protocol=protocol,
        fingerprint=fingerprint,
        remark=remark,
    )


def _extract_remark(link: str, protocol: Protocol) -> str:
    """Extract or synthesize a remark from the config link."""
    try:
        parsed = urllib.parse.urlparse(link)
        # For VMess, the remark is in the JSON payload
        if protocol == Protocol.VMESS:
            try:
                decoded = base64.b64decode(parsed.path, validate=False)
                data = json.loads(decoded.decode("utf-8"))
                return data.get("ps", "")
            except Exception:
                pass
        comment = parsed.fragment or ""
        if comment:
            try:
                return urllib.parse.unquote(comment)
            except Exception:
                return comment
        return parsed.hostname or ""
    except Exception:
        return ""
