"""Fuzzy matching for near-duplicate proxy configurations.

Fuzzy matching compares structured normalized fields, NOT the raw URI.
It identifies configurations that differ only in non-essential presentation
details (fragment, host_header, raw_uri) while requiring all identity-
significant fields to match.

Fields considered non-essential for fuzzy matching:
- fragment (cosmetic naming)
- host_header (HTTP Host header, not identity)
- raw_uri (original presentation)

All other fields must match exactly for a fuzzy match.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from proxyaggregator.parsers.base import ParseResult


def fuzzy_match(a: ParseResult, b: ParseResult) -> bool:
    """Return True if two configs are near-duplicates differing only in
    non-essential presentation fields.

    Identity fields that MUST match:
    - protocol, host (lowercased), port
    - user, password
    - sni, network, tls, path
    - service_name, flow, method
    - obfs, obfs_password
    """
    # Normalize and compare all identity fields
    identity_fields = (
        "protocol",
        "host",
        "port",
        "user",
        "password",
        "sni",
        "network",
        "tls",
        "path",
        "service_name",
        "flow",
        "method",
        "obfs",
        "obfs_password",
    )

    for field in identity_fields:
        val_a = getattr(a, field)
        val_b = getattr(b, field)

        # Normalize for comparison
        if isinstance(val_a, str):
            val_a = val_a.lower() if field == "host" else (val_a or "")
        if isinstance(val_b, str):
            val_b = val_b.lower() if field == "host" else (val_b or "")

        if val_a != val_b:
            return False

    return True
