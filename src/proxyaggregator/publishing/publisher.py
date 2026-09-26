"""Deterministic subscription publisher (Phase 9).

Turns Phase 8 ``Subscription`` feeds into byte-exact, reproducible files on
disk together with a deterministic release manifest:

- ``write_artifact``  -- atomic, traversal-safe single-file write
- ``publish_subscriptions`` -- writes a set of named feeds, returns metadata
- ``publish_release`` -- atomically publishes a whole release and prunes stale artifacts
- ``build_release_manifest`` -- deterministic JSON manifest
- ``verify_release`` -- structural + integrity validation of a release on disk

Guarantees:

- Byte-exact: the written bytes are exactly ``content.encode("utf-8")`` for
  every feed; publishing twice yields identical files.
- No ephemeral state: no timestamps, random names, hostnames, run IDs,
  environment variables, or credentials enter file contents or errors.
- Atomic: files are staged under a sibling temp name and ``os.replace`` into
  place, so a failed run never leaves a partial feed.
- Whole-set atomic: ``publish_release`` stages the entire release (feeds +
  manifest) before promoting anything, so a failed generation leaves the
  previous output byte-for-byte intact; the manifest is promoted last so a
  partial on-disk release is never presented as complete.
- Current-release only: after a successful publish, canonical artifacts from
  a previous run that are not part of the current release (e.g. a protocol
  feed with zero candidates this run) are removed, so the output directory
  always reflects the current aggregation, never accidental leftovers. This
  covers the per-country directories too: a country that disappears from the
  current result set has its whole ``countries/{CC}/`` directory removed, and
  stale protocol files inside a surviving directory are unlinked. A directory
  that disappears is never left half-written (it is promoted whole then
  removed whole, under the same atomic publish).
- Safe: every artifact is addressed by a root name or by a ``countries/{CC}/``
  relative path, so write/verify operations can never escape the output
  directory; anything absolute, with a ``..``/empty/``.`` component, a NUL
  byte, or an otherwise malformed path is rejected before touching disk.

Errors carry only the offending filename and a stable reason token.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, ValidationError

from proxyaggregator.publishing.models import SubscriptionFormat
from proxyaggregator.publishing.naming import (
    COUNTRY_UNKNOWN_BUCKET,
    country_bucket,
)
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

#: Finite, enumerable lowercase alpha-2 bucket space for location feeds: every
#: two-letter combination (a superset of the assigned ISO-3166-1 alpha-2 codes
#: GeoIP can emit) plus the ``xx`` unknown bucket. This is the bounded
#: stale-cleanup surface for location artifacts; any protocol/country feed the
#: pipeline can ever produce is covered, and names outside it (e.g.
#: ``README.md``, ``proxyaggregator.db``) can never match.
_ALPHA2_BUCKETS: frozenset[str] = frozenset(
    a + b for a in "abcdefghijklmnopqrstuvwxyz" for b in "abcdefghijklmnopqrstuvwxyz"
) | frozenset({COUNTRY_UNKNOWN_BUCKET})

#: Directory under which country-separated artifacts are published. Every
#: country feed lives inside ``countries/{CC}/`` (uppercase ISO alpha-2, with
#: the unknown-country bucket ``XX``), plus a generated ``countries/README.md``
#: index listing the non-empty directories.
COUNTRIES_DIR = "countries"

#: Stable canonical stems/names used by the generated country directories.
_COUNTRY_README_NAME = "README.md"
_COUNTRY_INDEX_NAME = "README.md"
_COUNTRY_ALL_STEM = "all"

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


class ReleaseVerificationError(RuntimeError):
    """A release on disk failed structural or integrity validation.

    The message contains only artifact filenames and stable reason tokens;
    content and credentials are never echoed.
    """


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


def country_dir_name(country_code: object) -> str:
    """Return the uppercase directory name for a country bucket (``DE``/``XX``).

    Buckets are normalized via :func:`country_bucket`: valid two-letter codes
    are lowercased and anything unknown/invalid maps to ``xx``, so the
    uppercased name is always a safe two-letter directory component.
    """
    return country_bucket(country_code).upper()


def country_dir_path(country_code: object) -> str:
    """Return the relative ``countries/{CC}`` directory path for a bucket."""
    return f"{COUNTRIES_DIR}/{country_dir_name(country_code)}"


def country_index_path() -> str:
    """Return the relative path of the generated per-country index README."""
    return f"{COUNTRIES_DIR}/{_COUNTRY_INDEX_NAME}"


def country_readme_path(country_code: object) -> str:
    """Return the relative path of ``countries/{CC}/README.md`` for a bucket."""
    return f"{country_dir_path(country_code)}/{_COUNTRY_README_NAME}"


def country_all_path(country_code: object, format: SubscriptionFormat, /) -> str:
    """Return the relative path of the all-protocol feed for a country bucket.

    Only plain and base64 artifacts exist per country (JSON is combined-feed
    only); ``format`` is validated like ``default_filename``.
    """
    if format is SubscriptionFormat.PLAIN:
        return f"{country_dir_path(country_code)}/{_COUNTRY_ALL_STEM}.txt"
    if format is SubscriptionFormat.BASE64:
        return f"{country_dir_path(country_code)}/{_COUNTRY_ALL_STEM}-base64.txt"
    raise ValueError(f"unsupported country feed format: {format!r}")


def country_protocol_path(
    protocol: str, country_code: object, format: SubscriptionFormat, /
) -> str:
    """Return the relative path of a protocol feed inside a country directory.

    Combines the existing protocol stem map with the normalized uppercase
    country bucket (``vless`` + ``DE`` -> ``countries/DE/vless.txt``);
    unknown/invalid countries map to ``XX``. Only plain and base64 artifacts
    exist; JSON is combined-feed only.
    """
    if protocol not in SUPPORTED_PROTOCOLS:
        raise ValueError(f"unsupported protocol feed: {protocol!r}")
    stem = DEFAULT_PROTOCOL_FILENAME_STEMS[protocol]
    if format is SubscriptionFormat.PLAIN:
        return f"{country_dir_path(country_code)}/{stem}.txt"
    if format is SubscriptionFormat.BASE64:
        return f"{country_dir_path(country_code)}/{stem}-base64.txt"
    raise ValueError(f"unsupported protocol feed format: {format!r}")


def _is_country_dir_name(name: str) -> bool:
    """True for an uppercase two-letter bucket directory name (``DE``/``XX``).

    The check is purely lexical (ASCII uppercase alpha pair), matching exactly
    the directory names the publisher can generate from
    :func:`country_dir_name`, so unrelated directories are never pruned.
    """
    return len(name) == 2 and name.isascii() and name.isalpha() and name.isupper()


def _legacy_location_artifact_names() -> frozenset[str]:
    """Name space of the pre-redesign flat location feed files.

    The first country-feed generation wrote ``country-de.txt`` and per-protocol
    ``vless-de.txt`` flat files. The current publisher never generates them,
    but they remain canonical so an existing output directory created by that
    generation converges to the ``countries/{CC}/`` layout on the next run.
    """
    names: set[str] = set()
    for bucket in _ALPHA2_BUCKETS:
        names.add(f"country-{bucket}.txt")
        names.add(f"country-{bucket}-base64.txt")
        for protocol in SUPPORTED_PROTOCOLS:
            stem = DEFAULT_PROTOCOL_FILENAME_STEMS[protocol]
            names.add(f"{stem}-{bucket}.txt")
            names.add(f"{stem}-{bucket}-base64.txt")
    return frozenset(names)


def _validate_artifact_path(filename: str) -> None:
    """Reject any artifact path that could escape the output directory.

    Accepted shapes (replacing the old single-component-only rule):

    - a single plain path component (``proxyaggregator.txt``, ``manifest.json``)
    - ``countries/README.md``
    - ``countries/{CC}/{file}`` where ``CC`` is an uppercase two-letter bucket
      directory (``DE``, ``XX``) and ``{file}`` a single plain component

    Anything absolute, containing ``\\`` or a NUL byte, with an empty, ``.``,
    or ``..`` component, or otherwise outside the two shapes is rejected
    before touching disk.
    """
    if not isinstance(filename, str):
        raise PublishError(filename, "filename_must_be_string")
    if filename == "":
        raise PublishError(filename, _EMPTY_FILENAME)
    if "\x00" in filename:
        raise PublishError(filename, _NUL_FILENAME)
    parts = filename.split("/")
    if "\\" in filename or any(part in ("", ".", "..") for part in parts):
        raise PublishError(filename, _PATH_FILENAME)
    if len(parts) == 1:
        return
    if len(parts) == 2 and parts[0] == COUNTRIES_DIR and parts[1] == _COUNTRY_INDEX_NAME:
        return
    if (
        len(parts) == 3
        and parts[0] == COUNTRIES_DIR
        and _is_country_dir_name(parts[1])
        and Path(parts[2]).name == parts[2]
    ):
        return
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
    fixed sibling temp name, fsynced, then ``os.replace`` into place. Nested
    country-dir targets create their parent directories as needed.
    """
    _validate_artifact_path(filename)
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    data = _encode(content)

    final = path / filename
    temp = path / f".{filename}.tmp"
    final.parent.mkdir(parents=True, exist_ok=True)
    temp.parent.mkdir(parents=True, exist_ok=True)
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


def canonical_artifact_filenames() -> frozenset[str]:
    """Every artifact path the publisher can ever own (feeds + manifest).

    This is the enumerated cleanup surface: only these paths may ever be
    deleted from an output directory, so stale cleanup can never touch an
    unrelated file (e.g. ``proxyaggregator.db`` or a stray README).

    The set spans the fixed combined names, the root protocol feeds, the
    generated ``countries/README.md`` index, the closed per-country directory
    space (:data:`_ALPHA2_BUCKETS` uppercased, each with README, all-protocol,
    and per-protocol files), and the legacy flat location names
    (:func:`_legacy_location_artifact_names`) so output from the flat layout
    converges to the directory layout.
    """
    names = set(DEFAULT_FILENAMES.values())
    for protocol in SUPPORTED_PROTOCOLS:
        names.add(default_protocol_filename(protocol, SubscriptionFormat.PLAIN))
        names.add(default_protocol_filename(protocol, SubscriptionFormat.BASE64))
    names.add(MANIFEST_FILENAME)
    names.add(country_index_path())
    for bucket in _ALPHA2_BUCKETS:
        dir_path = f"{COUNTRIES_DIR}/{bucket.upper()}"
        names.add(f"{dir_path}/{_COUNTRY_README_NAME}")
        names.add(f"{dir_path}/{_COUNTRY_ALL_STEM}.txt")
        names.add(f"{dir_path}/{_COUNTRY_ALL_STEM}-base64.txt")
        for protocol in SUPPORTED_PROTOCOLS:
            stem = DEFAULT_PROTOCOL_FILENAME_STEMS[protocol]
            names.add(f"{dir_path}/{stem}.txt")
            names.add(f"{dir_path}/{stem}-base64.txt")
    names.update(_legacy_location_artifact_names())
    return frozenset(names)


def _latest_staged_write(order: list[tuple[str, bytes]]) -> tuple[str, bytes]:
    """Pick the manifest as the last promoted file; deterministic feed order."""
    return sorted(order, key=lambda item: (item[0] == MANIFEST_FILENAME, item[0]))


def publish_release(
    subscriptions: Sequence[tuple[str, Subscription]],
    output_dir: str | Path,
    *,
    manifest_filename: str = MANIFEST_FILENAME,
) -> list[SubscriptionRelease]:
    """Atomically publish an entire release and prune stale artifacts.

    Every feed plus the release manifest is first written into a private
    staging directory (a sibling of ``output_dir``, never inside it). Only
    when every single write succeeds are the files promoted into place with
    ``os.replace`` (each an atomic rename); the manifest is promoted last so a
    promotion interrupted mid-way cannot be mistaken for a complete release.
    After promotion, any canonical artifact left over from a previous release
    (e.g. a protocol feed with zero candidates in the current run) is removed.

    On any failure the staging directory is deleted and ``output_dir`` is left
    byte-for-byte untouched: a previous valid output is never partially
    replaced by a failed generation.

    Returns the release metadata for the feed entries (the manifest is
    excluded, matching ``publish_subscriptions``' contract).
    """
    feed_entries: list[SubscriptionRelease] = []
    materialized: list[tuple[str, bytes]] = []
    for filename, feed in subscriptions:
        _validate_artifact_path(filename)
        data = feed.content.encode("utf-8")
        materialized.append((filename, data))
        feed_entries.append(release_metadata(filename, feed.format, feed.count, data))

    manifest = build_release_manifest(feed_entries)
    materialized.append((manifest_filename, manifest.encode("utf-8")))
    written_names = {name for name, _ in materialized}

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=parent))
    try:
        for name, data in materialized:
            write_artifact(name, data, staging)
        for name, _data in _latest_staged_write(materialized):
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging / name, target)
        _prune_stale_artifacts(output, written_names)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return feed_entries


def _prune_stale_artifacts(output_dir: Path, keep: frozenset[str] | set[str]) -> None:
    """Remove canonical artifacts that are not part of the current release.

    Iterates the directory (never the full canonical set) so pruning stays
    proportional to the files actually present. Root-level canonical files not
    kept by the current release are unlinked. The ``countries/`` subtree is
    handled as a unit: the generated index README is pruned like a file, a
    ``countries/{CC}`` directory whose country is absent from the current
    release is removed whole with ``shutil.rmtree``, and a surviving directory
    only gets canonical per-country files that ``keep`` does not include
    unlinked (e.g. a pending protocol feed dropped this run). A vanished
    directory is therefore never left as a stale half; unrelated files,
    directories, and non-canonical names are never touched.
    """
    try:
        present = {entry.name for entry in output_dir.iterdir()}
    except FileNotFoundError:
        return
    canonical = canonical_artifact_filenames()
    root_keep = {name for name in keep if "/" not in name}
    current_dirs = _current_country_dirs(keep)

    for name in present - root_keep:
        path = output_dir / name
        if name == COUNTRIES_DIR and path.is_dir():
            _prune_countries_subtree(path, keep, canonical, current_dirs)
            continue
        if path.is_file() and name in canonical:
            _unlink(path)


def _current_country_dirs(keep: frozenset[str] | set[str]) -> frozenset[str]:
    """Country dirs referenced by the release: ``{CC}`` for ``countries/{CC}/{f}``."""
    return frozenset(
        parts[1]
        for parts in (name.split("/") for name in keep)
        if len(parts) == 3 and parts[0] == COUNTRIES_DIR and _is_country_dir_name(parts[1])
    )


def _prune_countries_subtree(
    countries_dir: Path,
    keep: frozenset[str] | set[str],
    canonical: frozenset[str],
    current_dirs: frozenset[str],
) -> None:
    """Prune a ``countries/`` directory to the current release."""
    try:
        names = {entry.name for entry in countries_dir.iterdir()}
    except FileNotFoundError:
        return
    if country_index_path() not in keep:
        _unlink(countries_dir / _COUNTRY_INDEX_NAME)
    for name in names:
        path = countries_dir / name
        if not path.is_dir() or not _is_country_dir_name(name):
            continue
        if name not in current_dirs:
            shutil.rmtree(path)
            continue
        try:
            files = {entry.name for entry in path.iterdir()}
        except FileNotFoundError:
            continue
        for fname in files:
            rel = f"{COUNTRIES_DIR}/{name}/{fname}"
            if rel not in keep and rel in canonical:
                _unlink(path / fname)


def _unlink(path: Path) -> None:
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


def verify_release(output_dir: str | Path) -> list[SubscriptionRelease]:
    """Structurally validate a release on disk and return its entries.

    Raises :class:`ReleaseVerificationError` when the release is not complete
    and valid:

    - ``manifest.json`` is missing, unreadable, not a JSON list, or invalid
    - the manifest declares no artifacts, or no feed with ``count >= 1``
    - a listed artifact is missing, has a different size than recorded, or its
      content does not match the recorded SHA-256 (a mismatch means the file
      was corrupted or the manifest does not describe what it claims)

    Names are validated as safe artifact paths (single root components or
    ``countries/{CC}/{file}``), so a traversal filename in a manifest can never
    redirect a read outside the output directory. Database files are never
    considered artifacts; they are simply ignored.
    """
    output = Path(output_dir)
    manifest_path = output / MANIFEST_FILENAME
    try:
        raw = manifest_path.read_bytes()
    except FileNotFoundError:
        raise ReleaseVerificationError("missing manifest.json") from None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ReleaseVerificationError("invalid manifest.json") from exc
    if not isinstance(payload, list):
        raise ReleaseVerificationError("manifest must be a JSON list")

    entries: list[SubscriptionRelease] = []
    for item in payload:
        try:
            entries.append(SubscriptionRelease.model_validate(item))
        except ValidationError as exc:
            raise ReleaseVerificationError("invalid manifest entry") from exc
    if not entries:
        raise ReleaseVerificationError("manifest is empty")
    if not any(entry.count >= 1 for entry in entries):
        raise ReleaseVerificationError("no non-empty feed in manifest")

    for entry in entries:
        _validate_artifact_path(entry.filename)
        path = output / entry.filename
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            raise ReleaseVerificationError(f"artifact missing: {entry.filename}") from None
        if size != entry.byte_size:
            raise ReleaseVerificationError(f"artifact size mismatch: {entry.filename}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry.sha256:
            raise ReleaseVerificationError(f"artifact checksum mismatch: {entry.filename}")
    return entries
