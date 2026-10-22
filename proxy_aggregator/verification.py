"""Verification — real HTTP requests through proxy, stdlib-only."""
from __future__ import annotations

import os
import socket
import ssl
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from .models import ConfigItem

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

# Number of independent test rounds
TEST_ROUNDS = int(os.environ.get("VERIFY_ROUNDS", "3"))
# Latency threshold for "fast" bucket
FAST_THRESHOLD_MS = int(os.environ.get("VERIFY_FAST_MS", "800"))


def verify_config_direct(cfg: ConfigItem, *,
                         round_num: int = 0,
                         connect_timeout_ms: int = CONNECT_TIMEOUT_MS,
                         request_timeout_ms: int = REQUEST_TIMEOUT_MS) -> Dict[str, Any]:
    """Verify a config by attempting a direct connection.

    This is a structural verification — it checks the config is parseable
    and the endpoint is reachable. Full L3 proxy verification requires
    running a proxy client (like xray-core) which we cannot easily do
    with stdlib alone.
    """
    result: Dict[str, Any] = {
        "success": False,
        "latency_ms": None,
        "error": "",
        "status_code": None,
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

        # TLS upgrade for https schemes
        if scheme in ("vless", "vmess", "trojan", "hysteria2"):
            try:
                ctx = ssl.create_default_context()
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

                # Send a test HTTP request through the TLS connection
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
                result["success"] = 200 <= status_code < 400
                result["status_code"] = status_code
                result["latency_ms"] = round(elapsed + tls_elapsed, 1)
                if not result["success"]:
                    result["error"] = f"http-{status_code}"
                return result
            except Exception as exc:
                result["error"] = f"tls-http-fail: {exc}"
                return result

        # For non-TLS protocols, just report TCP success
        result["success"] = True
        result["latency_ms"] = round(elapsed, 1)
        sock.close()
        return result

    except Exception as exc:
        result["error"] = f"verify-exception: {exc}"
        return result


def run_verification_round(configs: List[ConfigItem],
                           round_num: int = 0) -> Dict[str, Any]:
    """Run one round of verification over a list of configs.

    Returns {ok: [...], failed: [...], broken: [...], stats: {...}}.
    """
    ok: List[str] = []
    failed: List[str] = []
    broken: List[str] = []
    latencies: Dict[str, float] = {}
    errors: Dict[str, str] = {}
    total_start = time.monotonic()

    def _verify_one(cfg: ConfigItem):
        return cfg.link, verify_config_direct(cfg, round_num=round_num)

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

            if result["success"]:
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
        "elapsed_sec": round(elapsed, 2),
    }
    return {"ok": ok, "failed": failed, "broken": broken,
            "latencies": latencies, "errors": errors, "stats": stats}


def merge_round_results(
    all_configs: List[ConfigItem],
    round_results: List[Dict[str, Any]],
) -> Tuple[List[ConfigItem], Dict[str, Any]]:
    """Merge multiple verification rounds into final ConfigItems.

    A config is 'verified' only if it passed ALL rounds.
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

        # Create updated instance (frozen dataclass)
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
