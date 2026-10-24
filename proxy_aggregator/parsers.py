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

    # Try recursive (for nested base64) — only match pure base64 chunks
    if max_depth > 0:
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


# ── Connection-relevant parameter extraction ────────────────────────────────
# These functions extract the fields that make two configs DIFFERENT.
# Cosmetic fields (remarks, comments) are intentionally EXCLUDED.

def _extract_vless_params(parsed: urllib.parse.ParseResult) -> Optional[dict]:
    """Extract connection-relevant params from a VLESS URI.

    VLESS format: vless://UUID@host:port?params#remark
    """
    try:
        query = urllib.parse.parse_qs(parsed.query)
        params = {}
        # UUID is the primary connection identifier
        netloc = parsed.netloc
        if '@' in netloc:
            uuid_part = netloc.split('@')[0]
            if uuid_part and len(uuid_part) >= 1:
                params['uuid'] = uuid_part
        # Flow (authentication method)
        if 'flow' in query:
            params['flow'] = query['flow'][0]
        # Security
        if 'security' in query:
            params['security'] = query['security'][0]
        # Encryption
        if 'encryption' in query:
            params['encryption'] = query['encryption'][0]
        # Transport type (websocket, grpc, etc.)
        if 'type' in query:
            params['type'] = query['type'][0]
        # Reality public key (short-id is less important)
        if 'pbk' in query:
            params['pbk'] = query['pbk'][0]
        return params if params else None
    except Exception:
        return None


def _extract_vmess_params(parsed: urllib.parse.ParseResult) -> Optional[dict]:
    """Extract connection-relevant params from a VMess URI.

    VMess format: vmess://base64(json) where json has:
    ps (remark), add (address), port, id (UUID), aid, scy, net, type, host, path, tls, sni, alpn, fp
    """
    try:
        # VMess payload is in the netloc (not path)
        raw = parsed.netloc
        if not raw:
            return None
        decoded = base64.b64decode(raw, validate=False)
        data = json.loads(decoded.decode("utf-8"))
        params = {}
        # UUID is the primary connection identifier
        if data.get('id'):
            params['uuid'] = data['id']
        # Alter ID
        if data.get('aid'):
            params['aid'] = str(data['aid'])
        # Security method
        if data.get('scy'):
            params['scy'] = data['scy']
        # Network type (tcp, kcp, ws, grpc, h2, http)
        if data.get('net'):
            params['net'] = data['net']
        # Header type (type in VMess is the "fake HTTP header" type)
        if data.get('type'):
            params['header_type'] = data['type']
        # Host (Host header for ws/grpc/h2)
        if data.get('host'):
            params['host'] = data['host']
        # Path
        if data.get('path'):
            params['path'] = data['path']
        # TLS
        if data.get('tls') == 'tls' or data.get('tls') == 'xtls':
            params['tls'] = data['tls']
        # SNI
        if data.get('sni'):
            params['sni'] = data['sni']
        # NOTE: 'ps' (remark) is intentionally excluded — it is cosmetic
        return params if params else None
    except Exception:
        return None


def _extract_trojan_params(parsed: urllib.parse.ParseResult) -> Optional[dict]:
    """Extract connection-relevant params from a Trojan URI.

    Trojan format: trojan://password@host:port?params#remark
    """
    try:
        netloc = parsed.netloc
        if '@' not in netloc:
            return None
        password_part = netloc.split('@')[0]
        query = urllib.parse.parse_qs(parsed.query)
        params = {}
        if password_part:
            params['password_hash'] = hashlib.sha256(password_part.encode()).hexdigest()[:16]
        if 'plugin' in query:
            params['plugin'] = query['plugin'][0]
        return params if params else None
    except Exception:
        return None


def _extract_ss_params(parsed: urllib.parse.ParseResult) -> Optional[dict]:
    """Extract connection-relevant params from a Shadowsocks URI.

    SS format: ss://base64(method:password@host:port#remark)
    Note: base64 payload is in netloc, not path.
    """
    try:
        # SS URIs store base64 in netloc, not path
        raw = parsed.netloc
        if not raw:
            return None
        # Remove any trailing fragment/remark
        raw = raw.split('#')[0]
        decoded = base64.b64decode(raw, validate=False)
        text = decoded.decode("utf-8", errors="replace")
        # ss://base64(method:password@host:port)
        if '@' in text:
            creds, _ = text.rsplit('@', 1)
            if ':' in creds:
                method, password = creds.split(':', 1)
                params = {}
                if method:
                    params['method'] = method
                if password:
                    params['password_hash'] = hashlib.sha256(password.encode()).hexdigest()[:16]
                return params if params else None
        return None
    except Exception:
        return None


def _extract_hysteria2_params(parsed: urllib.parse.ParseResult) -> Optional[dict]:
    """Extract connection-relevant params from a Hysteria2 URI.

    Hysteria2 format: hysteria2://token@host:port?params#remark
    """
    try:
        netloc = parsed.netloc
        if '@' not in netloc:
            return None
        token_part = netloc.split('@')[0]
        query = urllib.parse.parse_qs(parsed.query)
        params = {}
        if token_part:
            params['token_hash'] = hashlib.sha256(token_part.encode()).hexdigest()[:16]
        if 'insecure' in query:
            params['insecure'] = query['insecure'][0]
        return params if params else None
    except Exception:
        return None


def _extract_socks_params(parsed: urllib.parse.ParseResult) -> Optional[dict]:
    """Extract connection-relevant params from a SOCKS URI.

    SOCKS format: socks://user:pass@host:port
    """
    try:
        netloc = parsed.netloc
        if '@' not in netloc:
            return None
        creds = netloc.split('@')[0]
        if ':' in creds:
            user, password = creds.split(':', 1)
            params = {}
            if user:
                params['username'] = user
            if password:
                params['password_hash'] = hashlib.sha256(password.encode()).hexdigest()[:16]
            return params if params else None
        return None
    except Exception:
        return None


# Map each protocol to its extractor
_PARAM_EXTRACTORS = {
    Protocol.VLESS: _extract_vless_params,
    Protocol.VMESS: _extract_vmess_params,
    Protocol.TROJAN: _extract_trojan_params,
    Protocol.SHADOWSOCKS: _extract_ss_params,
    Protocol.HYSTERIA2: _extract_hysteria2_params,
    Protocol.SOCKS: _extract_socks_params,
}


def compute_fingerprint(link: str, protocol: Protocol = Protocol.UNKNOWN) -> str:
    """Compute a CDN-aware, connection-relevant fingerprint for deduplication.

    Includes scheme + host + port (CDN-aware) AND connection-relevant params
    (UUID, password, auth token, flow, etc.) so that two configs on the same
    server with different credentials produce DIFFERENT fingerprints.

    Cosmetic fields (remarks, comments) are intentionally EXCLUDED.
    """
    try:
        parsed = urllib.parse.urlparse(link)
        # Auto-detect protocol if not provided (handles direct compute_fingerprint() calls)
        if protocol == Protocol.UNKNOWN:
            protocol = detect_protocol(link)

        # For VMess, host/port come from the decoded JSON payload, not urlparse
        # (urlparse treats the base64 netloc as a hostname, which is wrong)
        if protocol == Protocol.VMESS:
            try:
                raw = parsed.netloc
                if raw:
                    decoded = base64.b64decode(raw, validate=False)
                    data = json.loads(decoded.decode("utf-8"))
                    host = (data.get("add") or "").lower()
                    try:
                        port = int(data.get("port", 443))
                    except (ValueError, TypeError):
                        port = 443
                else:
                    host = ""
                    port = 443
            except Exception:
                host = ""
                port = 443
        else:
            host = (parsed.hostname or "").lower()
            port = parsed.port or (443 if parsed.scheme.lower() in
                                   ("vless", "vmess", "trojan", "hysteria2") else 80)

        # Build the base: scheme + host + port (CDN-aware anchor)
        parts = [f"{parsed.scheme.lower()}://{host}:{port}"]

        # Add connection-relevant params (these distinguish same-server configs)
        extractor = _PARAM_EXTRACTORS.get(protocol)
        if extractor:
            params = extractor(parsed)
            if params:
                # Hash the params dict to keep the fingerprint short and stable
                param_str = json.dumps(params, sort_keys=True, ensure_ascii=True)
                params_hash = hashlib.sha256(param_str.encode()).hexdigest()[:12]
                parts.append(params_hash)

        raw = "|".join(parts)
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

    fingerprint = compute_fingerprint(link, protocol)
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
        # Check fragment first (URL-encoded remark)
        fragment = parsed.fragment or ""
        if fragment:
            try:
                return urllib.parse.unquote(fragment)
            except Exception:
                return fragment
        # For VMess, try the JSON payload
        if protocol == Protocol.VMESS:
            try:
                decoded = base64.b64decode(parsed.path, validate=False)
                data = json.loads(decoded.decode("utf-8"))
                return data.get("ps", "")
            except Exception:
                pass
        # Default: use host
        return parsed.hostname or ""
    except Exception:
        return ""
