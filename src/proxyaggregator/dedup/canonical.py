"""Canonicalization and content hashing for proxy configurations.

The canonical form is a deterministic, sorted dictionary of all meaningful
configuration fields. Transient fields (raw_uri, fragment) are excluded.
Host values are lowercased. None/empty values are normalized to empty strings.

The content hash is SHA-256 of the JSON-serialized canonical form.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from proxyaggregator.parsers.base import ParseResult


def canonicalize(config: ParseResult) -> dict[str, object]:
    """Return a deterministic canonical representation of the config.

    - Sorted keys for deterministic JSON serialization.
    - Host lowercased.
    - None values become empty strings.
    - Only identity fields included (no raw_uri, no fragment).
    """
    raw = {
        "protocol": config.protocol,
        "host": config.host.lower(),
        "port": config.port,
        "user": config.user or "",
        "password": config.password or "",
        "sni": config.sni or "",
        "network": config.network or "",
        "tls": config.tls or "",
        "path": config.path or "",
        "host_header": config.host_header or "",
        "service_name": config.service_name or "",
        "flow": config.flow or "",
        "method": config.method or "",
        "obfs": config.obfs or "",
        "obfs_password": config.obfs_password or "",
    }
    return dict(sorted(raw.items()))


def compute_content_hash(config: ParseResult) -> str:
    """Compute SHA-256 fingerprint of the canonical form.

    Returns a 64-character lowercase hex string.
    Deterministic and stable across process restarts.
    """
    canon = canonicalize(config)
    payload = json.dumps(canon, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
