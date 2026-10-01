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


def clean_path(path: str | None) -> str | None:
    """Strip query-string leakage from a proxy ``path`` value.

    Some upstream sources omit the ``&`` between the path value and the next
    query parameter, so ``parse_qs`` hands back values such as
    ``/?ed=2560security=tls`` where the query part is no longer a ``k=v`` list.
    Only the genuine path portion is kept, so a well-formed path query such as
    ``/?ed=2560`` survives untouched while a leaked tail is discarded. The
    proxy itself is never dropped, and an empty value becomes ``None`` so that
    no empty ``path`` parameter is ever emitted.

    Args:
        path: The raw ``path`` query value, already percent-decoded.

    Returns:
        The cleaned path, or ``None`` when nothing usable remains.
    """
    if not path:
        return None

    cleaned = path.strip()
    if not cleaned:
        return None

    head, sep, tail = cleaned.partition("&")
    if sep and "=" in tail:
        cleaned = head

    head, sep, query = cleaned.partition("?")
    if sep and (not query or not _is_well_formed_query(query)):
        cleaned = head

    return cleaned.strip() or None


def _is_well_formed_query(query: str) -> bool:
    """Return whether a path query is a proper ``&``-separated ``k=v`` list."""
    if "?" in query:
        return False
    return all(pair.count("=") <= 1 for pair in query.split("&"))
