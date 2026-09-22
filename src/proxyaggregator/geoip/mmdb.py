"""MaxMind MMDB reader using the maxminddb library.

Reads GeoLite2-City and similar MMDB databases. Handles IPv4 and IPv6 lookups,
returns structured records. Pure Python, no native extensions required.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import maxminddb


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
