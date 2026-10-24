"""Verification — real proxy connectivity checks via subprocess + stdlib fallback."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from .models import ConfigItem, Protocol

# ── Xray-core binary path (set by workflow or user) ──────────────────────────
# The GitHub Actions workflow downloads and pins this binary.
# Environment variable override for local testing.
XRAY_BIN = os.environ.get("XRAY_BIN", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".cache", "xray"))

# ── Test endpoint (GET-only, no auth, small response) ──────────────────────
TEST_URL = "https://cp.cloudflare.com/generate_204"
TEST_HOST = "cp.cloudflare.com"
TEST_PORT = 443
TEST_PATH = "/generate_204"

# ── Timeouts (ms) ───────────────────────────────────────────────────────────
CONNECT_TIMEOUT_MS = int(os.environ.get("VERIFY_CONNECT_TIMEOUT_MS", "5000"))
REQUEST_TIMEOUT_MS = int(os.environ.get("VERIFY_REQUEST_TIMEOUT_MS", "8000"))
MAX_THREADS = int(os.environ.get("VERIFY_MAX_THREADS", "50"))
HARD_TIMEOUT_SEC = int(os.environ.get("VERIFY_HARD_TIMEOUT", "600"))
XRAY_TEST_TIMEOUT_SEC = int(os.environ.get("VERIFY_XRAY_TIMEOUT", "15"))

# Number of independent test rounds
TEST_ROUNDS = int(os.environ.get("VERIFY_ROUNDS", "3"))
# Latency threshold for "fast" bucket
FAST_THRESHOLD_MS = int(os.environ.get("VERIFY_FAST_MS", "800"))


# ── Xray config generation ──────────────────────────────────────────────────
# Translates a proxy URI into a minimal Xray client config for testing.

def _build_xray_config(link: str, protocol: Protocol, outbound_port: int) -> dict:
    """Build a minimal Xray client config that routes traffic through the proxy.

    Returns None if the protocol is not supported by Xray or the link is malformed.
    """
    import urllib.parse
    parsed = urllib.parse.urlparse(link)
    host = parsed.hostname
    port = parsed.port

    # For SS, host/port come from decoded base64, not urlparse
    if protocol == Protocol.SHADOWSOCKS:
        # SS parsing happens below; skip the early return
        pass
    elif not host or not port:
        return None

    inbound_port = outbound_port

    # Base config structure
    config = {
        "log": {"loglevel": "error"},
        "inbounds": [{
            "port": inbound_port,
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": True},
            "tag": "socks_in",
        }],
        "outbounds": [],
    }

    outbounds = config["outbounds"]

    if protocol == Protocol.VLESS:
        # Extract UUID from netloc (before @)
        uuid_part = ""
        if '@' in parsed.netloc:
            uuid_part = parsed.netloc.split('@')[0]
        if not uuid_part or len(uuid_part) < 8:
            return None

        ob = {
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": host,
                    "port": port,
                    "users": [{"id": uuid_part, "flow": ""}]
                }]
            },
            "streamSettings": {"network": "tcp"},
            "tag": "proxy_out",
        }
        # Handle TLS / Reality in query params
        query = urllib.parse.parse_qs(parsed.query)
        security = query.get('security', ['none'])[0]
        if security in ('tls', 'reality'):
            ob["streamSettings"] = {
                "network": "tcp",
                "security": security,
                "tcpSettings": {},
            }
            if security == 'reality':
                pbk = query.get('pbk', [None])[0]
                sid = query.get('sid', [''])[0]
                ob["streamSettings"]["realitySettings"] = {
                    "serverName": query.get('sni', [host])[0],
                    "publicKey": pbk or "",
                    "shortId": sid or "",
                }
            elif security == 'tls':
                ob["streamSettings"]["tlsSettings"] = {
                    "serverName": query.get('sni', [host])[0],
                }
        ob["streamSettings"].setdefault("tcpSettings", {})
        outbounds.append(ob)

    elif protocol == Protocol.VMESS:
        # Parse base64 JSON payload from netloc (VMess stores it there, not in path)
        try:
            raw = parsed.netloc
            if not raw:
                return None
            decoded = base64.b64decode(raw, validate=False)
            data = json.loads(decoded.decode("utf-8"))
        except Exception:
            return None

        uuid_part = data.get('id', '')
        if not uuid_part:
            return None

        ob = {
            "protocol": "vmess",
            "settings": {
                "vnext": [{
                    "address": data.get('add', host),
                    "port": data.get('port', port),
                    "users": [{
                        "id": uuid_part,
                        "alterId": data.get('aid', 0),
                        "security": data.get('scy', 'aes-128-gcm'),
                    }]
                }]
            },
            "tag": "proxy_out",
        }

        net = data.get('net', 'tcp')
        tls = data.get('tls', '')
        stream = {"network": net}

        if tls == 'tls' or tls == 'xtls':
            stream["security"] = tls
            if tls == 'xtls':
                ob["settings"]["vnext"][0]["users"][0]["flow"] = data.get('flow', '')

        if net in ('ws', 'httpupgrade', 'xhttp'):
            path = data.get('path', '/')
            host_hdr = data.get('host', '')
            stream[net + "Settings"] = {
                "path": path,
                "headers": {"Host": host_hdr} if host_hdr else {},
            }
        elif net == 'grpc':
            stream["grpcSettings"] = {
                "serviceName": data.get('path', ''),
            }
        elif net == 'http':
            stream["httpSettings"] = {
                "host": [data.get('host', '')],
                "path": [data.get('path', '/')],
            }
        elif net == 'kcp':
            kcp_type = data.get('type', 'none')
            seed = data.get('seed', '')
            stream["kcpSettings"] = {
                "mtu": data.get('mtu', 1350),
                "tti": data.get('tti', 50),
                "uplinkCapacity": data.get('uplinkCapacity', 5),
                "downlinkCapacity": data.get('downlinkCapacity', 20),
                "congestion": False,
                "header": {"type": kcp_type},
            }
            if seed:
                stream["kcpSettings"]["seed"] = seed

        if tls and tls != 'none':
            sni = data.get('sni', '')
            fp = data.get('fp', '')
            alpn_list = data.get('alpn', '')
            tls_settings = {}
            if sni:
                tls_settings["serverName"] = sni
            if fp:
                tls_settings["fingerprint"] = fp
            if alpn_list:
                tls_settings["allowInsecure"] = False
                tls_settings["alpn"] = [a.strip() for a in alpn_list.split(',')]
            stream["tlsSettings"] = tls_settings

        ob["streamSettings"] = stream
        outbounds.append(ob)

    elif protocol == Protocol.TROJAN:
        # Password is in netloc before @
        if '@' not in parsed.netloc:
            return None
        password = parsed.netloc.split('@')[0]
        if not password:
            return None

        ob = {
            "protocol": "trojan",
            "settings": {
                "servers": [{
                    "address": host,
                    "port": port,
                    "password": password,
                }]
            },
            "tag": "proxy_out",
        }

        query = urllib.parse.parse_qs(parsed.query)
        stream = {"network": "tcp"}
        security = query.get('security', ['none'])[0]
        if security == 'tls':
            stream["security"] = "tls"
            sni = query.get('sni', [host])[0]
            stream["tlsSettings"] = {"serverName": sni}
        elif security == 'reality':
            stream["security"] = "reality"
            sni = query.get('sni', [host])[0]
            pbk = query.get('pbk', [''])[0]
            sid = query.get('sid', [''])[0]
            spx = query.get('spx', [''])[0]
            stream["realitySettings"] = {
                "serverName": sni,
                "publicKey": pbk,
                "shortId": sid,
                "spiderX": spx,
            }
        ob["streamSettings"] = stream
        outbounds.append(ob)

    elif protocol == Protocol.HYSTERIA2:
        # Token is in netloc before @
        if '@' not in parsed.netloc:
            return None
        token = parsed.netloc.split('@')[0]
        if not token:
            return None

        query = urllib.parse.parse_qs(parsed.query)
        ob = {
            "protocol": "hysteria2",
            "settings": {
                "servers": [{
                    "address": host,
                    "port": port,
                    "password": token,
                }]
            },
            "tag": "proxy_out",
        }
        # Hysteria2 always uses QUIC (UDP) — no additional streamSettings needed
        outbounds.append(ob)

    elif protocol == Protocol.SHADOWSOCKS:
        # SS format: ss://base64(method:password@host:port)#remark
        # Parse from netloc (where base64 lives)
        try:
            raw = parsed.netloc.split('#')[0]  # Remove fragment
            decoded = base64.b64decode(raw, validate=False)
            text = decoded.decode("utf-8", errors="replace")
        except Exception as e:
            print(f"DEBUG SS: decode exception: {e}")
            return None
        if '@' not in text or ':' not in text:
            print(f"DEBUG SS: missing @ or : in text={text!r}")
            return None
        creds, rest = text.rsplit('@', 1)
        if ':' not in creds:
            print(f"DEBUG SS: no colon in creds={creds!r}")
            return None
        method, password = creds.split(':', 1)
        if not method or not password:
            print(f"DEBUG SS: empty method or password: method={method!r}, password={password!r}")
            return None
        # Extract host:port from the decoded text (after the @)
        if ':' not in rest:
            print(f"DEBUG SS: no colon in rest={rest!r}")
            return None
        server_host, server_port_str = rest.rsplit(':', 1)
        try:
            server_port = int(server_port_str)
        except ValueError:
            print(f"DEBUG SS: invalid port={server_port_str!r}")
            return None

        ob = {
            "protocol": "shadowsocks",
            "settings": {
                "servers": [{
                    "address": server_host,
                    "port": server_port,
                    "method": method,
                    "password": password,
                }]
            },
            "tag": "proxy_out",
        }
        outbounds.append(ob)

    elif protocol == Protocol.SOCKS:
        # socks://user:pass@host:port
        if '@' not in parsed.netloc:
            # Anonymous SOCKS
            ob = {
                "protocol": "socks",
                "settings": {
                    "servers": [{
                        "address": host,
                        "port": port,
                    }]
                },
                "tag": "proxy_out",
            }
        else:
            creds = parsed.netloc.split('@')[0]
            user, password = creds.split(':', 1) if ':' in creds else (creds, "")
            ob = {
                "protocol": "socks",
                "settings": {
                    "servers": [{
                        "address": host,
                        "port": port,
                        "users": [{"user": user, "pass": password}] if user or password else [],
                    }]
                },
                "tag": "proxy_out",
            }
        outbounds.append(ob)

    else:
        return None

    # Add direct outbounds (for DNS and the test target)
    outbounds.append({
        "protocol": "freedom",
        "tag": "direct",
    })

    # Route: proxy_out handles everything, direct is fallback
    config["routing"] = {
        "domainStrategy": "AsIs",
        "rules": [{
            "type": "field",
            "outboundTag": "proxy_out",
            "domain": ["geosite:private"],
        }],
    }

    return config


def _has_xray() -> bool:
    """Check if the xray binary is available and executable."""
    if not os.path.isfile(XRAY_BIN):
        return False
    return os.access(XRAY_BIN, os.X_OK)


def _verify_via_xray(cfg: ConfigItem, *,
                     connect_timeout_ms: int = CONNECT_TIMEOUT_MS,
                     request_timeout_ms: int = REQUEST_TIMEOUT_MS) -> Optional[Dict[str, Any]]:
    """Attempt verification using Xray-core binary.

    Returns result dict on success, or None if Xray is unavailable or protocol unsupported.
    """
    if not _has_xray():
        return None

    protocol = cfg.protocol
    if protocol == Protocol.HYSTERIA2:
        # Hysteria2 uses QUIC (UDP) — cannot tunnel HTTP through SOCKS5
        return {"success": False, "latency_ms": None,
                "error": "hysteria2-unsupported", "status_code": None,
                "method": "xray", "structural_only": False}
    if protocol not in (Protocol.VLESS, Protocol.VMESS, Protocol.TROJAN,
                        Protocol.SOCKS, Protocol.SHADOWSOCKS):
        return None

    # Generate a random outbound port for this test
    outbound_port = 10000 + hash(cfg.link) % 50000

    try:
        # Build Xray config
        xray_cfg = _build_xray_config(cfg.link, protocol, outbound_port)
        if xray_cfg is None:
            return None

        # Write config to temp file
        fd, cfg_path = tempfile.mkstemp(suffix=".json", prefix="xray_test_")
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(xray_cfg, f)

            # Run xray once — it will run as a proxy server on outbound_port
            # and exit after the test completes
            deadline = time.monotonic() + XRAY_TEST_TIMEOUT_SEC
            proc = None
            try:
                proc = subprocess.Popen(
                    [XRAY_BIN, "run", "-c", cfg_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=XRAY_TEST_TIMEOUT_SEC,
                )

                # Wait for proxy to be ready (poll the port)
                ready = False
                poll_start = time.monotonic()
                while time.monotonic() < deadline:
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(0.5)
                        sock.connect(('127.0.0.1', outbound_port))
                        sock.close()
                        ready = True
                        break
                    except (OSError, ConnectionRefusedError):
                        pass
                    time.sleep(0.1)

                if not ready:
                    return {"success": False, "latency_ms": None,
                            "error": "proxy-not-ready", "status_code": None,
                            "method": "xray"}

                # Now make an HTTP request through the SOCKS5 proxy on outbound_port
                start = time.monotonic()
                try:
                    # Use urllib with SOCKS proxy (we need a socks library...
                    # instead, use a simple raw SOCKS5 handshake or just
                    # test with the proxy's local SOCKS endpoint)
                    # For simplicity: send a test request via the local proxy
                    # We'll use a small helper that does SOCKS5 handshake
                    result = _http_through_socks5(
                        '127.0.0.1', outbound_port,
                        TEST_HOST, TEST_PORT, TEST_PATH,
                        connect_timeout_ms, request_timeout_ms,
                        deadline - time.monotonic(),
                    )
                    elapsed = (time.monotonic() - start) * 1000

                    if result["success"]:
                        return {
                            "success": True,
                            "latency_ms": round(elapsed, 1),
                            "error": "",
                            "status_code": result["status_code"],
                            "method": "xray",
                        }
                    else:
                        return {
                            "success": False,
                            "latency_ms": None,
                            "error": f"through-proxy-fail: {result.get('error', '')}",
                            "status_code": result.get("status_code"),
                            "method": "xray",
                        }
                except Exception as exc:
                    return {
                        "success": False,
                        "latency_ms": None,
                        "error": f"through-proxy-exception: {exc}",
                        "status_code": None,
                        "method": "xray",
                    }
            finally:
                if proc and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
        finally:
            try:
                os.remove(cfg_path)
            except OSError:
                pass
    except Exception:
        return None

    return None


def _http_through_socks5(socks_host: str, socks_port: int,
                         target_host: str, target_port: int,
                         target_path: str,
                         connect_timeout_ms: int, request_timeout_ms: int,
                         remaining_ms: float) -> Dict[str, Any]:
    """Perform a SOCKS5 handshake then an HTTP request through it.

    Pure stdlib implementation — no third-party SOCKS libraries needed.
    """
    import struct

    if not (1 <= target_port <= 65535):
        return {"success": False, "error": "invalid-port", "status_code": None}

    connect_timeout = connect_timeout_ms / 1000.0
    request_timeout = request_timeout_ms / 1000.0
    total_timeout = max(connect_timeout, 1.0)  # at least 1s

    # Pack target port as big-endian uint16 for SOCKS5 CONNECT
    port_bytes = struct.pack(">H", target_port)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(total_timeout)
        try:
            sock.connect((socks_host, socks_port))
        except (socket.timeout, OSError) as exc:
            sock.close()
            return {"success": False, "error": f"socks-connect: {exc}", "status_code": None}

        # SOCKS5 handshake: send methods [0x05, 0x01, 0x00] (no auth)
        sock.sendall(b"\x05\x01\x00")
        resp = sock.recv(256)
        if len(resp) < 2 or resp[0] != 0x05 or resp[1] != 0x00:
            sock.close()
            return {"success": False, "error": "socks-handshake-fail", "status_code": None}

        # SOCKS5 CONNECT request
        # Determine address type: IPv4 (0x01), IPv6 (0x04), or domain (0x03)
        try:
            addr_bytes = socket.inet_aton(target_host)
            connect_req = b"\x05\x01\x00\x01" + addr_bytes + port_bytes
        except OSError:
            # Not IPv4 — try IPv6
            try:
                addr_bytes = socket.inet_pton(socket.AF_INET6, target_host)
                connect_req = b"\x05\x01\x00\x04" + addr_bytes + port_bytes
            except (OSError, ValueError):
                # Domain name
                domain_bytes = target_host.encode('ascii')
                connect_req = b"\x05\x01\x00\x03" + bytes([len(domain_bytes)]) + domain_bytes + port_bytes
        sock.sendall(connect_req)
        reply = sock.recv(256)
        if len(reply) < 4 or reply[0] != 0x05 or reply[1] != 0x00:
            sock.close()
            return {"success": False, "error": "socks-connect-reject", "status_code": None}

        # Send HTTP request through the established tunnel
        sock.settimeout(request_timeout)
        http_req = (
            f"GET {target_path} HTTP/1.1\r\n"
            f"Host: {target_host}\r\n"
            f"User-Agent: ProxyAggregator-Test/1.0\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode()
        sock.sendall(http_req)

        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        sock.close()

        if not buf:
            return {"success": False, "error": "no-response", "status_code": None}

        status_line = buf.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
        parts = status_line.split(" ", 2)
        status_code = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
        return {
            "success": 200 <= status_code < 400,
            "error": f"http-{status_code}" if not (200 <= status_code < 400) else "",
            "status_code": status_code,
        }

    except Exception as exc:
        return {"success": False, "error": f"socks-exception: {exc}", "status_code": None}


def _verify_stdlib(cfg: ConfigItem, *,
                   connect_timeout_ms: int = CONNECT_TIMEOUT_MS,
                   request_timeout_ms: int = REQUEST_TIMEOUT_MS) -> Dict[str, Any]:
    """Fallback verification using only stdlib (TCP/TLS to proxy endpoint).

    This does NOT route traffic through the proxy — it only checks that the
    proxy endpoint is reachable. Results from this method are marked as
    'structurally valid' but NOT 'verified'.
    """
    result: Dict[str, Any] = {
        "success": False,
        "latency_ms": None,
        "error": "",
        "status_code": None,
        "method": "stdlib",
        "structural_only": True,  # Key marker: this did NOT go through the proxy
    }

    try:
        parsed = urllib.parse.urlparse(cfg.link)
        host = parsed.hostname
        port = parsed.port
        scheme = parsed.scheme.lower()

        if not host or not port:
            result["error"] = "invalid host/port"
            return result

        connect_timeout = connect_timeout_ms / 1000.0
        request_timeout = request_timeout_ms / 1000.0

        # TCP connect
        start = time.monotonic()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(connect_timeout)
        try:
            sock.connect((host, port))
        except (socket.timeout, OSError) as exc:
            result["error"] = f"tcp-fail: {exc}"
            sock.close()
            return result
        elapsed = (time.monotonic() - start) * 1000

        # TLS upgrade for protocols that use TLS
        if scheme in ("vless", "vmess", "trojan", "hysteria2"):
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False  # Structural check only — not for production
                ctx.verify_mode = ssl.CERT_NONE
                tls_start = time.monotonic()
                tls_sock = ctx.wrap_socket(sock, server_hostname=host)
                tls_sock.settimeout(request_timeout)
                try:
                    tls_sock.do_handshake()
                except (ssl.SSLError, OSError) as exc:
                    result["error"] = f"tls-fail: {exc}"
                    tls_sock.close()
                    return result
                tls_elapsed = (time.monotonic() - tls_start) * 1000

                # Structural check only: send HTTP to proxy endpoint (NOT through tunnel)
                http_req = (
                    f"GET {TEST_PATH} HTTP/1.1\r\n"
                    f"Host: {TEST_HOST}\r\n"
                    f"Connection: close\r\n"
                    f"\r\n"
                ).encode()
                tls_sock.sendall(http_req)
                buf = b""
                while b"\r\n\r\n" not in buf:
                    chunk = tls_sock.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                tls_sock.close()

                status_line = buf.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
                status_code = int(status_line.split(" ", 2)[1]) if " " in status_line else 0
                # Do NOT mark success — this is structural only
                result["status_code"] = status_code
                result["latency_ms"] = round(elapsed + tls_elapsed, 1)
                result["error"] = f"structural-check-only"
                return result
            except Exception as exc:
                result["error"] = f"tls-http-fail: {exc}"
                return result

        # Non-TLS: just report TCP success as structural check
        result["latency_ms"] = round(elapsed, 1)
        result["error"] = "structural-check-only"
        sock.close()
        return result

    except Exception as exc:
        result["error"] = f"verify-exception: {exc}"
        return result


def verify_config(cfg: ConfigItem, *,
                  round_num: int = 0,
                  connect_timeout_ms: int = CONNECT_TIMEOUT_MS,
                  request_timeout_ms: int = REQUEST_TIMEOUT_MS) -> Dict[str, Any]:
    """Verify a config by attempting a real through-proxy request.

    Tries Xray-core first (if available), falls back to stdlib structural check.
    A config is only marked 'verified' if Xray successfully routes a request
    through the proxy tunnel.

    Returns dict with keys: success, latency_ms, error, status_code, method,
        structural_only (bool — True means this was NOT a real proxy test).
    """
    # Try Xray first (real through-proxy verification)
    xray_result = _verify_via_xray(cfg, connect_timeout_ms=connect_timeout_ms,
                                    request_timeout_ms=request_timeout_ms)
    if xray_result is not None:
        return xray_result

    # Fallback: structural check (NOT sufficient for "verified" status)
    return _verify_stdlib(cfg, connect_timeout_ms=connect_timeout_ms,
                          request_timeout_ms=request_timeout_ms)


def run_verification_round(configs: List[ConfigItem],
                           round_num: int = 0) -> Dict[str, Any]:
    """Run one round of verification over a list of configs.

    Returns {ok: [...], failed: [...], broken: [...], stats: {...}}.
    Only configs that passed REAL through-proxy verification (method="xray"
    and success=True) are counted as "ok". Structural-only checks are flagged.
    """
    ok: List[str] = []
    failed: List[str] = []
    broken: List[str] = []
    structural_only: List[str] = []  # Tracks configs that only got structural checks
    latencies: Dict[str, float] = {}
    errors: Dict[str, str] = {}
    total_start = time.monotonic()

    def _verify_one(cfg: ConfigItem):
        return cfg.link, verify_config(cfg, round_num=round_num)

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = {executor.submit(_verify_one, cfg): cfg for cfg in configs}
        for future in as_completed(futures):
            cfg = futures[future]
            try:
                link, result = future.result(timeout=REQUEST_TIMEOUT_MS / 1000 * 3)
            except Exception as exc:
                broken.append(cfg.link)
                errors[cfg.link] = f"thread-exception: {exc}"
                continue

            # Only count as "ok" if it was a REAL through-proxy test
            if result.get("structural_only", False):
                structural_only.append(cfg.link)
                failed.append(cfg.link)
                errors[cfg.link] = "structural-only-check — not real proxy verification"
            elif result["success"]:
                ok.append(cfg.link)
                latencies[cfg.link] = result["latency_ms"] or 0.0
            else:
                failed.append(cfg.link)
                errors[cfg.link] = result.get("error", "unknown")

    elapsed = time.monotonic() - total_start
    stats = {
        "round": round_num,
        "total": len(configs),
        "ok": len(ok),
        "failed": len(failed),
        "broken": len(broken),
        "structural_only": len(structural_only),
        "elapsed_sec": round(elapsed, 2),
    }
    return {"ok": ok, "failed": failed, "broken": broken,
            "latencies": latencies, "errors": errors, "stats": stats,
            "structural_only_links": structural_only}


def merge_round_results(
    all_configs: List[ConfigItem],
    round_results: List[Dict[str, Any]],
) -> tuple:
    """Merge multiple verification rounds into final ConfigItems.

    A config is 'verified' only if it passed ALL rounds with REAL
    through-proxy verification (not structural-only checks).
    Latency is recorded as the median across successful rounds.
    """
    from typing import Tuple  # noqa

    link_data: Dict[str, Dict[str, Any]] = {}
    for cfg in all_configs:
        link_data[cfg.link] = {
            "cfg": cfg,
            "pass_count": 0,
            "round_count": len(round_results),
            "latencies": [],
        }

    for rnd in round_results:
        # Only count links that were genuinely verified (not structural-only)
        for link in rnd.get("ok", []):
            if link in link_data:
                link_data[link]["pass_count"] += 1
                lat = rnd.get("latencies", {}).get(link)
                if lat is not None:
                    link_data[link]["latencies"].append(lat)

    verified: List[ConfigItem] = []
    stats_summary = {
        "rounds": len(round_results),
        "ever_ok": 0,
        "stable": 0,
        "per_round_ok": [],
        "structural_only_total": sum(
            len(r.get("structural_only_links", [])) for r in round_results
        ),
    }

    for link, data in link_data.items():
        cfg = data["cfg"]
        pass_count = data["pass_count"]
        round_count = data["round_count"]

        if pass_count > 0:
            stats_summary["ever_ok"] += 1
        if pass_count == round_count:
            stats_summary["stable"] += 1

        latencies = data["latencies"]
        median_lat = None
        if latencies:
            sorted_lats = sorted(latencies)
            n = len(sorted_lats)
            mid = n // 2
            median_lat = (sorted_lats[mid] + sorted_lats[~mid]) / 2 \
                if n % 2 == 0 else sorted_lats[mid]

        object.__setattr__(cfg, "verified_rounds", pass_count)
        object.__setattr__(cfg, "total_rounds", round_count)
        object.__setattr__(cfg, "median_latency_ms", median_lat)
        object.__setattr__(cfg, "fast_threshold_ms", FAST_THRESHOLD_MS)

        if pass_count == round_count:
            verified.append(cfg)

    stats_summary["per_round_ok"] = [
        rnd.get("stats", {}).get("ok", 0) for rnd in round_results
    ]
    return verified, stats_summary
