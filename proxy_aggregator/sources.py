"""Source fetching — concurrent, resilient, with bounded retries."""
from __future__ import annotations

import os
import re
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

from .models import SourceResult

# ── Timeout and size limits (tunable) ───────────────────────────────────────

CONNECTION_TIMEOUT = int(os.environ.get("AGG_CONN_TIMEOUT", "10"))
READ_TIMEOUT = int(os.environ.get("AGG_READ_TIMEOUT", "30"))
MAX_RESPONSE_SIZE = int(os.environ.get("AGG_MAX_SIZE", "10_000_000"))  # 10 MB
MAX_RETRIES = int(os.environ.get("AGG_MAX_RETRIES", "3"))
RETRY_BACKOFF = float(os.environ.get("AGG_RETRY_BACKOFF", "1.0"))

# ── User-Agent ──────────────────────────────────────────────────────────────

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# ── 4xx codes that indicate a permanently dead source ──────────────────────

_HARD_4XX = frozenset({404, 410, 403})


def _build_request(url: str) -> urllib.request.Request:
    req = urllib.request.Request(url, headers={
        "User-Agent": _USER_AGENT,
        "Accept": "*/*",
    })
    return req


def fetch_source(url: str, *, timeout: Optional[int] = None) -> Tuple[str, Optional[int], str]:
    """Fetch a single source URL.

    Returns (content, http_code, error_or_empty_string).
    On hard 4xx, returns ("", code, "dead").
    On timeout/network error, returns ("", None, "timeout"/"network").
    On success, content may be truncated if > MAX_RESPONSE_SIZE.
    """
    tox = timeout or READ_TIMEOUT
    conn_tox = CONNECTION_TIMEOUT
    last_err = ""

    for attempt in range(1, MAX_RETRIES + 2):
        try:
            req = _build_request(url)
            with urllib.request.urlopen(req, timeout=tox) as resp:
                code = resp.status
                raw = resp.read(MAX_RESPONSE_SIZE + 1)
                if len(raw) > MAX_RESPONSE_SIZE:
                    return (
                        raw[:MAX_RESPONSE_SIZE].decode("utf-8", errors="replace"),
                        code,
                        "truncated",
                    )
                text = raw.decode("utf-8", errors="replace")
                # Hard 4xx → dead source
                if code in _HARD_4XX:
                    return ("", code, "dead")
                return (text, code, "")
        except urllib.error.HTTPError as exc:
            code = exc.code
            if code in _HARD_4XX:
                return ("", code, "dead")
            last_err = f"http-{code}"
            if attempt <= MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * attempt)
                continue
            return ("", code, last_err)
        except urllib.error.URLError as exc:
            reason = str(exc.reason)
            if "timeout" in reason.lower() or "timed out" in reason:
                last_err = "timeout"
            else:
                last_err = f"network-{reason[:60]}"
            if attempt <= MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * attempt)
                continue
            return ("", None, last_err)
        except Exception as exc:
            last_err = f"error-{type(exc).__name__}: {str(exc)[:80]}"
            if attempt <= MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * attempt)
                continue
            return ("", None, last_err)

    return ("", None, last_err)


def classify_source(url: str, text: str, http_code: Optional[int],
                    error: str) -> SourceResult:
    """Classify the fetch outcome into a SourceResult."""
    if error == "dead":
        return SourceResult(url=url, status="fail", http_code=http_code,
                            error="source returned permanent 4xx")
    if error and error != "truncated":
        return SourceResult(url=url, status="fail", http_code=http_code,
                            error=error)
    if http_code and http_code >= 400:
        return SourceResult(url=url, status="fail", http_code=http_code,
                            error=f"http-{http_code}")
    if not text.strip():
        return SourceResult(url=url, status="empty", http_code=http_code)
    return SourceResult(url=url, status="ok", http_code=http_code,
                        config_count=0)  # count filled later by parser
