"""URI normalization helpers."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse


def normalize_uri(uri: str) -> str:
    """Normalize a proxy URI for consistent handling."""
    if not uri:
        return ""

    stripped = uri.strip()
    if not stripped:
        return ""

    try:
        parsed = urlparse(stripped)
    except Exception:
        return stripped

    scheme = parsed.scheme.lower()

    # Reconstruct with lowercase scheme, preserving everything else
    normalized = urlunparse(
        (
            scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )

    return normalized
