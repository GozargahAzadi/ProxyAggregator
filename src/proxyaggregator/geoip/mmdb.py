"""MMDB reader using the maxminddb library.

Reads GeoLite2-City, ip-location-db, and other MMDB databases. Handles IPv4
and IPv6 lookups, returns structured records. Pure Python, no native
extensions required.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import maxminddb


class GeoIpDatabaseError(Exception):
    """Raised when the configured GeoIP MMDB database is unusable.

    The message is deliberately credential-free: it never includes account IDs,
    license keys, tokens, or other secrets.
    """


def validate_mmdb(
    path: str | Path,
    *,
    allowed_types: tuple[str, ...] = ("country ipvAll", "GeoLite2-City"),
) -> str:
    """Validate that an MMDB file is present, readable, and a supported GeoIP DB.

    ``allowed_types`` is an explicit allowlist of ``database_type`` values the
    caller considers usable. The default covers the two database schemas this
    project supports: the production ``country ipvAll`` database
    (ip-location-db ``user-country.mmdb``) and the legacy ``GeoLite2-City``
    format. Pass a narrower allowlist to require a specific type.

    Checks, in order:
        1. the path exists and is a regular file,
        2. the file is readable,
        3. it opens as a valid MaxMind DB,
        4. its ``database_type`` is in ``allowed_types``.

    Raises :class:`GeoIpDatabaseError` with a clear, credential-free message on
    any failure. Returns the database type string on success.
    """
    db_path = Path(path)

    if not db_path.exists():
        raise GeoIpDatabaseError(f"GeoIP database not found: {db_path}")
    if not db_path.is_file():
        raise GeoIpDatabaseError(f"GeoIP database path is not a file: {db_path}")
    if not os.access(db_path, os.R_OK):
        raise GeoIpDatabaseError(f"GeoIP database is not readable: {db_path}")

    try:
        reader = maxminddb.Reader(str(db_path))
    except Exception as exc:
        raise GeoIpDatabaseError(f"GeoIP database is not a valid MaxMind DB: {db_path}") from exc

    try:
        metadata = reader.metadata()
        database_type = getattr(metadata, "database_type", "")
        if not database_type:
            raise GeoIpDatabaseError(f"GeoIP database has no database_type: {db_path}")
        if database_type not in allowed_types:
            allowed = ", ".join(repr(item) for item in allowed_types)
            raise GeoIpDatabaseError(
                f"Unsupported GeoIP database type {database_type!r}; "
                f"expected one of: {allowed} ({db_path})"
            )
        return database_type
    finally:
        reader.close()


class MmdbReader:
    """Reader for MaxMind MMDB database files.

    Supports IPv4 and IPv6 lookups. Returns raw dict records from the
    data section. Missing IPs return None.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._reader: maxminddb.Reader | None = None
        self.is_valid = False
        self.database_type: str = ""
        self._load()

    def _load(self) -> None:
        """Load and open the MMDB file."""
        if not self._path.exists():
            return

        try:
            self._reader = maxminddb.Reader(str(self._path))
            self.is_valid = True
            metadata = self._reader.metadata()
            self.database_type = getattr(metadata, "database_type", "")
        except Exception:
            self._reader = None
            self.is_valid = False

    def lookup(self, ip_address: str) -> dict | None:
        """Look up an IP address in the MMDB database.

        Returns the record dict if found, None if not found or on error.
        """
        if not self._reader or not self.is_valid:
            return None

        try:
            result = self._reader.get(ip_address)
            if result is None:
                return None
            if isinstance(result, dict):
                return result
            return None
        except Exception:
            return None

    def close(self) -> None:
        """Release resources."""
        if self._reader is not None:
            with contextlib.suppress(Exception):
                self._reader.close()
            self._reader = None
