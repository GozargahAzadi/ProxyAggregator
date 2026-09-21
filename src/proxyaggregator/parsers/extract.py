"""Extract proxy URIs from raw source content."""

from __future__ import annotations

import base64
import binascii

from proxyaggregator.parsers.detect import detect_protocol


def _try_decode_base64(text: str) -> str | None:
    """Attempt base64 decoding; return decoded text or None."""
    try:
        decoded = base64.b64decode(text, validate=True)
        return decoded.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


def _is_proxy_uri(line: str) -> bool:
    """Return True if the line looks like a proxy URI."""
    return detect_protocol(line) is not None


def extract_uris(content: str) -> list[str]:
    """Extract proxy URIs from raw content.

    Handles:
    - One URI per line
    - Blank lines (skipped)
    - Lines starting with # (comments, skipped)
    - Whitespace trimming
    - Base64-encoded subscription content
    """
    if not content or not content.strip():
        return []

    lines = content.splitlines()
    uris: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _is_proxy_uri(stripped):
            uris.append(stripped)

    # If no URIs found, try interpreting entire content as base64
    if not uris:
        decoded = _try_decode_base64(content.strip())
        if decoded:
            return extract_uris(decoded)

    return uris
