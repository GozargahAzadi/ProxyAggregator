"""Deterministic subscription publisher (Phase 9).

Turns Phase 8 ``Subscription`` feeds into byte-exact, reproducible files on
disk together with a deterministic release manifest:

- ``write_artifact``  -- atomic, traversal-safe single-file write
- ``publish_subscriptions`` -- writes a set of named feeds, returns metadata
- ``build_release_manifest`` -- deterministic JSON manifest

Guarantees:

- Byte-exact: the written bytes are exactly ``content.encode("utf-8")`` for
  every feed; publishing twice yields identical files.
- No ephemeral state: no timestamps, random names, hostnames, run IDs,
  environment variables, or credentials enter file contents or errors.
- Atomic: files are staged under a sibling temp name and ``os.replace`` into
  place, so a failed run never leaves a partial feed.
- Safe: every filename must be a single plain path component; anything with a
  path separator, NUL byte, or empty name is rejected before touching disk.

Errors carry only the offending filename and a stable reason token.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from proxyaggregator.publishing.models import SubscriptionFormat
from proxyaggregator.publishing.serializer import SUPPORTED_PROTOCOLS

if TYPE_CHECKING:
    from collections.abc import Sequence

    from proxyaggregator.publishing.models import Subscription

#: Default directory (repo-relative) for generated subscription artifacts.
DEFAULT_OUTPUT_DIR = "output"

#: Canonical artifact filenames per supported feed format.
DEFAULT_FILENAMES: dict[SubscriptionFormat, str] = {
    SubscriptionFormat.PLAIN: "proxyaggregator.txt",
    SubscriptionFormat.BASE64: "proxyaggregator-base64.txt",
    SubscriptionFormat.JSON: "proxyaggregator.json",
}

#: Plain (non-base64) file stem per protocol for protocol-separated feeds.
#: Protocol keys come from the canonical serializer registry; the only stem
#: that differs from the protocol id is ``ss`` -> ``shadowsocks``.
DEFAULT_PROTOCOL_FILENAME_STEMS: dict[str, str] = {
    "vless": "vless",
    "vmess": "vmess",
    "trojan": "trojan",
    "ss": "shadowsocks",
    "hysteria": "hysteria",
    "hysteria2": "hysteria2",
    "socks4": "socks4",
    "socks5": "socks5",
    "http": "http",
    "https": "https",
}

#: Name of the deterministic release manifest written next to the feeds.
MANIFEST_FILENAME = "manifest.json"

#: Stable, credential-free reason tokens used in PublishError.
_EMPTY_FILENAME = "empty_filename"
_NUL_FILENAME = "nul_in_filename"
_PATH_FILENAME = "path_separator_in_filename"
_INVALID_CONTENT = "invalid_content_type"


class PublishError(Exception):
    """A subscription artifact could not be published.

    The message contains only the offending filename and a stable reason
    token; feed content, credentials, and paths are never echoed.
    """

    def __init__(self, filename: str, reason: str) -> None:
        self.filename = filename
        self.reason = reason
        super().__init__(f"cannot publish {filename!r}: {reason}")


class SubscriptionRelease(BaseModel):
    """Deterministic metadata for one published artifact.

    Every field is derived from the written bytes only; no time, random,
    host, or environment information is ever included. Frozen so a release
    cannot be mutated after it is produced.
    """

    filename: str = Field(..., min_length=1, description="Artifact file name")
    format: SubscriptionFormat = Field(..., description="Feed encoding")
    count: int = Field(..., ge=0, description="Number of unique proxies emitted")
    byte_size: int = Field(..., ge=0, description="Size of the written bytes")
    sha256: str = Field(
        ..., min_length=64, max_length=64, description="SHA-256 hex of the written bytes"
    )

    model_config = {"frozen": True}


def default_filename(format: SubscriptionFormat, /) -> str:
    """Return the canonical artifact filename for a feed format."""
    if isinstance(format, SubscriptionFormat):
        return DEFAULT_FILENAMES[format]
    raise ValueError(f"unsupported subscription format: {format!r}")


def default_protocol_filename(protocol: str, format: SubscriptionFormat, /) -> str:
    """Return the canonical artifact filename for a protocol-separated feed.

    Only plain and base64 artifacts exist per protocol; JSON is combined-feed
    only. ``format`` is validated with an ``is`` check against the canonical
    enum members (see ``default_filename``).
    """
    if protocol not in SUPPORTED_PROTOCOLS:
        raise ValueError(f"unsupported protocol feed: {protocol!r}")
    stem = DEFAULT_PROTOCOL_FILENAME_STEMS[protocol]
    if format is SubscriptionFormat.PLAIN:
        return f"{stem}.txt"
    if format is SubscriptionFormat.BASE64:
        return f"{stem}-base64.txt"
    raise ValueError(f"unsupported protocol feed format: {format!r}")


def _validate_filename(filename: str) -> None:
    if not isinstance(filename, str):
        raise PublishError(filename, "filename_must_be_string")
    if filename == "":
        raise PublishError(filename, _EMPTY_FILENAME)
    if "\x00" in filename:
        raise PublishError(filename, _NUL_FILENAME)
    if filename in (".", ".."):
        raise PublishError(filename, _PATH_FILENAME)
    if Path(filename).name != filename:
        raise PublishError(filename, _PATH_FILENAME)


def _encode(content: str | bytes) -> bytes:
    if isinstance(content, str):
        return content.encode("utf-8")
    if isinstance(content, bytes):
        return content
    raise PublishError("", _INVALID_CONTENT)


def write_artifact(
    filename: str,
    content: str | bytes,
    output_dir: str | Path,
) -> Path:
    """Deterministically write one artifact to ``output_dir``.

    The final bytes are exactly the UTF-8 encoding of ``content`` (or the
    raw ``bytes`` passed in). The write is atomic: content is staged under a
    fixed sibling temp name, fsynced, then ``os.replace`` into place.
    """
    _validate_filename(filename)
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    data = _encode(content)

    final = path / filename
    temp = path / f".{filename}.tmp"
    try:
        with temp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, final)
    except OSError:
        temp.unlink(missing_ok=True)
        raise
    return final


def release_metadata(
    filename: str,
    format: SubscriptionFormat,
    count: int,
    data: bytes,
) -> SubscriptionRelease:
    """Build release metadata derived only from the written bytes."""
    return SubscriptionRelease(
        filename=filename,
        format=format,
        count=count,
        byte_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def build_release_manifest(entries: Sequence[SubscriptionRelease]) -> str:
    """Serialize release metadata to deterministic JSON.

    Entries are sorted by filename regardless of input order. Output is a
    single compact JSON document (sorted keys, no trailing newline) so the
    bytes are identical for identical inputs.
    """
    ordered = sorted(entries, key=lambda entry: entry.filename)
    items = [entry.model_dump(mode="json") for entry in ordered]
    return json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_release_manifest(
    manifest: str,
    output_dir: str | Path,
    *,
    filename: str = MANIFEST_FILENAME,
) -> Path:
    """Write the release manifest as a deterministic artifact."""
    return write_artifact(filename, manifest, output_dir)


def publish_subscriptions(
    subscriptions: Sequence[tuple[str, Subscription]],
    output_dir: str | Path,
) -> list[SubscriptionRelease]:
    """Write every named feed and return its release metadata.

    The input is an ordered sequence of ``(filename, feed)`` pairs; entries
    are returned in that same order (the manifest serialization re-sorts by
    filename, the written files need no ordering guarantee). Writing is
    sequential and atomic per file.
    """
    entries: list[SubscriptionRelease] = []
    for filename, feed in subscriptions:
        data = feed.content.encode("utf-8")
        write_artifact(filename, data, output_dir)
        entries.append(release_metadata(filename, feed.format, feed.count, data))
    return entries
