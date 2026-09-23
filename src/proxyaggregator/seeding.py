"""Production source seeding (Phase 9.2).

The repository-controlled, version-controlled source definition file is the
authoritative input for the ``sources`` table. This module:

1. validates every definition **before any database mutation**,
2. upserts definitions keyed by ``url`` (the existing ``get_source_by_url``
   identity) — inserts new rows and refreshes changed fields,
3. never contacts the network and never inspects source content; the Phase
   9.1 collector remains solely responsible for fetching.

Lifecycle: additive/upsert only. ``SourceORM`` has no enabled/deleted
fields, so sources absent from the definition file are **retained**, never
silently deleted.

Security: a definition whose URL carries credentials is rejected without
echoing the URL; error ``reason`` tokens are stable and the seed file must
never contain secrets.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from proxyaggregator.db.crud import create_source, get_source_by_url
from proxyaggregator.models.source import SourceSchema
from proxyaggregator.sources.registry import get_registry as get_collector_registry

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

logger = logging.getLogger("proxyaggregator.seeding")

#: Only these URL schemes may identify a source; anything else (file://, ...)
#: is rejected so a definition can never steer the pipeline at local files.
_SUPPORTED_URL_SCHEMES = ("http", "https")

#: Persisted column width limits (String(255)/String(50)/String(2048)).
_MAX_NAME_LENGTH = 255
_MAX_TYPE_LENGTH = 50
_MAX_URL_LENGTH = 2048


class SeedError(RuntimeError):
    """A rejected source definition. ``reason`` is a stable credential-free token."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


@dataclass
class SeedStats:
    """Per-seed counters for the CLI summary (no URLs or credentials)."""

    defined: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0

    def summarize(self) -> str:
        return (
            f"defined={self.defined}, inserted={self.inserted}, "
            f"updated={self.updated}, unchanged={self.unchanged}"
        )


def _trim(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def load_defined_sources(path: str | Path) -> list[SourceSchema]:
    """Load and validate a JSON source definition file into ``SourceSchema``.

    Raises:
        SeedError: file missing/unreadable, malformed JSON, a non-list root,
            or any definition that fails validation — with a stable reason
            token and never the offending URL.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise SeedError("sources_file_not_found")
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SeedError("invalid_sources_file") from exc

    if not isinstance(payload, list):
        raise SeedError("invalid_sources_file", detail="expected a JSON array")

    supported_types = set(get_collector_registry().supported_types)
    schemas: list[SourceSchema] = []
    seen_urls: set[str] = set()

    for index, entry in enumerate(payload):
        if not isinstance(entry, dict):
            raise SeedError("invalid_source_entry", detail=f"entry {index}")

        name = _trim(entry.get("name"))
        source_type = _trim(entry.get("type"))
        url = _trim(entry.get("url"))

        if not name:
            raise SeedError("missing_source_name", detail=f"entry {index}")
        if not source_type:
            raise SeedError("missing_source_type", detail=f"entry {index}")
        if not url:
            raise SeedError("missing_source_url", detail=f"entry {index}")

        if len(name) > _MAX_NAME_LENGTH:
            raise SeedError("source_name_too_long", detail=f"entry {index}")
        if len(source_type) > _MAX_TYPE_LENGTH:
            raise SeedError("source_type_too_long", detail=f"entry {index}")
        if len(url) > _MAX_URL_LENGTH:
            raise SeedError("source_url_too_long", detail=f"entry {index}")

        if source_type not in supported_types:
            raise SeedError("unsupported_source_type", detail=f"entry {index}")
        if url in seen_urls:
            raise SeedError("duplicate_source_definition", detail=f"entry {index}")

        parts = urlsplit(url)
        if parts.scheme not in _SUPPORTED_URL_SCHEMES:
            raise SeedError("unsupported_url_scheme", detail=f"entry {index}")
        if parts.username is not None or parts.password is not None:
            raise SeedError("url_contains_credentials", detail=f"entry {index}")

        seen_urls.add(url)
        schemas.append(SourceSchema(name=name, source_type=source_type, url=url))

    return schemas


def seed_sources(session: Session, schemas: Sequence[SourceSchema]) -> SeedStats:
    """Upsert validated definitions into ``sources`` keyed by URL.

    Idempotent: running twice with identical definitions produces an
    equivalent table (the second run reports ``inserted=0, unchanged=N``).
    Sources absent from the definition file are retained (no deletion).
    """
    stats = SeedStats(defined=len(schemas))
    for schema in schemas:
        existing = get_source_by_url(session, schema.url)
        if existing is None:
            create_source(session, name=schema.name, source_type=schema.source_type, url=schema.url)
            stats.inserted += 1
            continue
        if existing.name != schema.name or existing.source_type != schema.source_type:
            existing.name = schema.name
            existing.source_type = schema.source_type
            session.commit()
            stats.updated += 1
        else:
            stats.unchanged += 1
    return stats


def run_seed_cli(sources_file: str) -> int:
    """Seed the production database from a definition file; return exit code."""
    from proxyaggregator.db.engine import SessionLocal

    try:
        schemas = load_defined_sources(sources_file)
        with SessionLocal() as session:
            stats = seed_sources(session, schemas)
    except SeedError as exc:
        logger.error("seed-sources failed: %s", exc.reason)
        return 1
    except Exception:
        logger.error("seed-sources fatal error")
        return 1
    logger.info("seed-sources complete: %s", stats.summarize())
    return 0
