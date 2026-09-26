"""Deterministic node Remark generation (Phase 10).

The publishing layer stamps every emitted proxy with a single canonical
Remark — ``{FLAG} {COUNTRY} | {PROTOCOL} | {LATENCY}ms | GozargahAzadi`` —
built purely from the persisted GeoIP country, the persisted protocol, and the
persisted latency. The module is a pure function of its inputs: no network, no
clock, no random values, no database access, and no external dependencies, so
identical inputs always produce identical bytes.

Design rules:

- The flag is derived from an ISO-3166-1 alpha-2 country code via the Unicode
  regional-indicator symbols (``DE`` -> ``🇩🇪``). Missing or invalid codes fall
  back to the ``🌐 XX`` pair.
- Latency milliseconds are rounded half-up (``124.5`` -> ``125``; Python's
  ``round()`` uses banker's rounding so it is never used here). Missing or
  invalid latencies fall back to ``N/A`` without the ``ms`` suffix.
- The protocol rendering is a stable, centralized display-name map; anything
  unknown is rendered as the uppercased identifier.
- The Remark is presentation-only. It never carries credentials and is applied
  at the serialization boundary, leaving ``raw_uri``, ``content_hash``, dedup,
  scoring, health, and ranking untouched.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

#: Regional-indicator symbol for ASCII letter ``A`` (U+1F1E6). Letters A-Z
#: map contiguously, so ``DE`` -> ``🇩🇪``.
_REGIONAL_INDICATOR_A = 0x1F1E6
_ASCII_A = ord("A")

_FALLBACK_FLAG = "🌐"
_FALLBACK_COUNTRY = "XX"
_FALLBACK_LATENCY = "N/A"
_FALLBACK_PROTOCOL_DISPLAY = "UNKNOWN"

#: Lowercase bucket key used for location feeds whose country is unknown or
#: invalid. It is the lowercase counterpart of the ``🌐 XX`` Remark fallback.
COUNTRY_UNKNOWN_BUCKET = "xx"

#: Author suffix used in every Remark (the project's public identity).
REMARK_AUTHOR = "GozargahAzadi"

#: Canonical, deterministic protocol display-name map (Phase 10). Unknown
#: protocols are rendered as their uppercased identifier rather than a map
#: miss, so the Remark never degrades to an untested token.
PROTOCOL_DISPLAY_NAMES: Mapping[str, str] = {
    "vless": "VLESS",
    "vmess": "VMESS",
    "trojan": "TROJAN",
    "ss": "SS",
    "hysteria": "HYSTERIA",
    "hysteria2": "HYSTERIA2",
    "socks4": "SOCKS4",
    "socks5": "SOCKS5",
    "http": "HTTP",
    "https": "HTTPS",
}


def normalize_country_code(country_code: object) -> str | None:
    """Return an uppercase ISO-3166-1 alpha-2 code, or ``None`` if invalid.

    Valid codes are exactly two ASCII alphabetic characters (surrounding
    whitespace is tolerated). Anything else — ``None``, numbers, three-letter
    codes, non-ASCII letters — is invalid and leads to the ``🌐 XX`` fallback.
    """
    if not isinstance(country_code, str):
        return None
    code = country_code.strip().upper()
    if len(code) != 2 or not code.isascii() or not code.isalpha():
        return None
    return code


def _regional_indicator(letter: str) -> str:
    return chr(_REGIONAL_INDICATOR_A + (ord(letter) - _ASCII_A))


def country_bucket(country_code: object) -> str:
    """Return the lowercase alpha-2 location bucket for a country code.

    Valid codes are lowercased (``DE`` -> ``de``); missing or invalid values
    map to the :data:`COUNTRY_UNKNOWN_BUCKET` ``xx`` bucket (mirroring the
    ``🌐 XX`` Remark fallback). The result is always exactly two lowercase
    ASCII letters, so it is filename-safe by construction.
    """
    normalized = normalize_country_code(country_code)
    if normalized is None:
        return COUNTRY_UNKNOWN_BUCKET
    return normalized.lower()


def country_flag(country_code: object) -> tuple[str, str]:
    """Resolve ``(flag, code)`` for a country code (falling back to ``🌐 XX``)."""
    code = normalize_country_code(country_code)
    if code is None:
        return _FALLBACK_FLAG, _FALLBACK_COUNTRY
    return "".join(_regional_indicator(ch) for ch in code), code


def country_code_to_flag(country_code: object) -> str:
    """Return the flag emoji for an ISO-3166-1 alpha-2 code (``DE`` -> ``🇩🇪``).

    The two-character contiguous regional-indicator space means the flag is
    derived deterministically from the code with no lookup table. The reserved
    ``XX`` sentinel (the unknown-country bucket) and every invalid value render
    as ``🌐``; a real (unassigned) code would otherwise produce a meaningless
    ``XX`` flag pair.
    """
    code = normalize_country_code(country_code)
    if code is None or code == _FALLBACK_COUNTRY:
        return _FALLBACK_FLAG
    return "".join(_regional_indicator(ch) for ch in code)


def protocol_display_name(protocol: object) -> str:
    """Render a protocol identifier as its canonical public display name."""
    if isinstance(protocol, str):
        key = protocol.strip().lower()
        if key in PROTOCOL_DISPLAY_NAMES:
            return PROTOCOL_DISPLAY_NAMES[key]
        if key:
            return key.upper()
    return _FALLBACK_PROTOCOL_DISPLAY


def _round_half_up(value: float) -> int:
    """Round a non-negative value half-up to the nearest integer.

    ``round()`` performs banker's rounding (``round(124.5) == 124``); the
    publishing contract requires half-up (``124.5 -> 125``).
    """
    return math.floor(value + 0.5)


def format_latency_ms(latency_ms: object) -> str:
    """Render a latency in milliseconds as ``NNNms`` (fallback ``N/A``)."""
    if isinstance(latency_ms, bool) or not isinstance(latency_ms, (int, float)):
        return _FALLBACK_LATENCY
    if not math.isfinite(latency_ms) or latency_ms < 0:
        return _FALLBACK_LATENCY
    return f"{_round_half_up(latency_ms)}ms"


def build_remark(country_code: object, protocol: object, latency_ms: object) -> str:
    """Build the deterministic public Remark for one published proxy.

    Example: ``build_remark("DE", "vless", 124.5)``
    returns ``"🇩🇪 DE | VLESS | 125ms | GozargahAzadi"``.

    The result is a pure string; callers decide where to attach it. Missing
    or invalid country/latency never raise — they produce the ``🌐 XX`` and
    ``N/A`` fallbacks respectively.
    """
    flag, code = country_flag(country_code)
    latency = format_latency_ms(latency_ms)
    return f"{flag} {code} | {protocol_display_name(protocol)} | {latency} | {REMARK_AUTHOR}"
