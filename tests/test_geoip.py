"""Phase 5 tests: DNS resolver, MMDB reader, GeoIP enrichment, IP-based dedup.

All DNS and GeoIP tests use mocked/local deterministic data.
No live network calls. No real MMDB downloads.
"""

from __future__ import annotations

import ipaddress
import socket
import struct
from unittest.mock import patch

import pytest

from proxyaggregator.dedup.models import DedupMatchType
from proxyaggregator.parsers.base import ParseResult

# ---------------------------------------------------------------------------
# Helper: build a minimal valid MMDB file for testing
# ---------------------------------------------------------------------------

_MMDB_MAGIC = b"\xab\xcd\xefMaxMind.com"


def _encode_controller(buf: bytearray, type_num: int, size: int) -> None:
    """Encode an MMDB data type controller byte(s).

    Types 0-7 use a single byte: (type << 5) | size.
    Types 8+ use extended: first byte (0 << 5) | size, second byte = type - 7.
    """
    if type_num <= 7:
        if size < 29:
            buf.append((type_num << 5) | size)
        elif size < 29 + 256:
            buf.append((type_num << 5) | 29)
            buf.append(size - 29)
        elif size < 29 + 256 + 65536:
            buf.append((type_num << 5) | 30)
            buf.extend(struct.pack("!H", size - 29 - 256))
        else:
            buf.append((type_num << 5) | 31)
            buf.extend(struct.pack("!I", size - 29 - 256 - 65536))
    else:
        # Extended type: type 0 in first byte, actual type - 7 in second byte
        if size < 29:
            buf.append(size)
        elif size < 29 + 256:
            buf.append(29)
            buf.append(size - 29)
        elif size < 29 + 256 + 65536:
            buf.append(30)
            buf.extend(struct.pack("!H", size - 29 - 256))
        else:
            buf.append(31)
            buf.extend(struct.pack("!I", size - 29 - 256 - 65536))
        buf.append(type_num - 7)


def _encode_string(buf: bytearray, s: str) -> None:
    """Encode a string (type 2)."""
    raw = s.encode("utf-8")
    _encode_controller(buf, 2, len(raw))
    buf.extend(raw)


def _encode_uint(buf: bytearray, n: int) -> None:
    """Encode an unsigned integer (type 6 for small values)."""
    if n == 0:
        _encode_controller(buf, 6, 0)
    elif n <= 0xFF:
        _encode_controller(buf, 6, 1)
        buf.append(n)
    elif n <= 0xFFFF:
        _encode_controller(buf, 6, 2)
        buf.extend(struct.pack("!H", n))
    elif n <= 0xFFFFFFFF:
        _encode_controller(buf, 6, 4)
        buf.extend(struct.pack("!I", n))
    else:
        _encode_controller(buf, 6, 8)
        buf.extend(struct.pack("!Q", n))


def _encode_double(buf: bytearray, f: float) -> None:
    """Encode a double (type 3)."""
    _encode_controller(buf, 3, 8)
    buf.extend(struct.pack("!d", f))


def _encode_array(buf: bytearray, arr: list) -> None:
    """Encode an array (type 11, extended)."""
    _encode_controller(buf, 11, len(arr))
    for item in arr:
        _encode_value(buf, item)


def _encode_bool(buf: bytearray, b: bool) -> None:
    """Encode boolean (type 14, extended)."""
    _encode_controller(buf, 14, 1 if b else 0)


def _encode_value(buf: bytearray, value) -> None:
    """Encode a single value using MMDB data format."""
    if isinstance(value, bool):
        _encode_bool(buf, value)
    elif isinstance(value, dict):
        _encode_map(buf, value)
    elif isinstance(value, str):
        _encode_string(buf, value)
    elif isinstance(value, int):
        _encode_uint(buf, value)
    elif isinstance(value, float):
        _encode_double(buf, value)
    elif isinstance(value, list):
        _encode_array(buf, value)
    # None values are skipped (no null type in MMDB)


def _encode_map(buf: bytearray, data: dict) -> None:
    """Encode a dict using MMDB data format (type 7)."""
    items = list(data.items())
    _encode_controller(buf, 7, len(items))
    for key, value in items:
        _encode_string(buf, key)
        _encode_value(buf, value)


def _build_mmdb(ip_data: dict[str, dict], *, database_type: str = "GeoLite2-City") -> bytes:
    """Build a minimal MMDB binary from an {ip_string: record_dict} mapping.

    Uses record_size=24, ip_version=4. ``database_type`` sets the metadata
    ``database_type`` (defaults to the legacy GeoLite2-City value; pass
    "country ipvAll" for the production ip-location-db schema).
    Builds a correct binary search tree that routes IPs to data entries.

    MMDB file layout:
        [tree] [16-byte separator] [data section] [metadata] [magic marker]

    Data pointer formula (from maxminddb reader):
        pointer = node_count + 16 + data_offset
        resolved = pointer - node_count + search_tree_size
                 = data_offset + search_tree_size + 16
    """
    record_size = 24
    node_bytes_per_record = record_size // 8  # 3
    data_separator_size = 16

    # Encode data section
    data_section = bytearray()
    ip_data_offsets: dict[str, int] = {}

    for ip_str, record in ip_data.items():
        ip_data_offsets[ip_str] = len(data_section)
        _encode_map(data_section, record)

    # Pad data section to 16-byte alignment
    while len(data_section) % 16 != 0:
        data_section.append(0)

    # Build binary search tree in two passes:
    # Pass 1: build node structure, record which node/bit leads to each IP
    # Pass 2: set data pointers using final node_count
    nodes: list[list[int]] = [[0, 0]]  # root node at index 0
    # Store (node_idx, last_bit, data_offset) for each IP
    leaf_targets: list[tuple[int, int, int]] = []

    for ip_str in ip_data:
        ip = ipaddress.ip_address(ip_str)
        ip_int = int.from_bytes(ip.packed, "big")

        node_idx = 0
        for bit_idx in range(31):  # 31 levels (bits 31 down to 1)
            bit = (ip_int >> (31 - bit_idx)) & 1
            if nodes[node_idx][bit] == 0:
                new_idx = len(nodes)
                nodes.append([0, 0])
                nodes[node_idx][bit] = new_idx
            node_idx = nodes[node_idx][bit]

        # Level 31 (last bit): record the leaf target
        last_bit = ip_int & 1
        data_offset = ip_data_offsets[ip_str]
        leaf_targets.append((node_idx, last_bit, data_offset))

    node_count = len(nodes)

    # Pass 2: set data pointers using final node_count
    for node_idx, last_bit, data_offset in leaf_targets:
        nodes[node_idx][last_bit] = node_count + data_separator_size + data_offset

    # Fill unset records with node_count (empty data pointer)
    for node in nodes:
        for i in range(2):
            if node[i] == 0:
                node[i] = node_count

    # Encode tree nodes
    tree_buf = bytearray()
    for node in nodes:
        for record in node:
            tree_buf.extend(record.to_bytes(node_bytes_per_record, "big"))

    # Metadata
    metadata = {
        "binary_format_major_version": 2,
        "binary_format_minor_version": 0,
        "build_epoch": 1700000000,
        "database_type": database_type,
        "description": {"en": "Test DB"},
        "ip_version": 4,
        "languages": ["en"],
        "node_count": node_count,
        "record_size": record_size,
    }

    meta_buf = bytearray()
    _encode_map(meta_buf, metadata)

    # Layout: [tree] [16-byte separator] [data section] [metadata marker] [metadata]
    separator = b"\x00" * data_separator_size
    return bytes(tree_buf) + separator + bytes(data_section) + _MMDB_MAGIC + bytes(meta_buf)


# ---------------------------------------------------------------------------
# Helper: create a minimal ParseResult
# ---------------------------------------------------------------------------


def _make_result(
    host: str = "example.com",
    port: int = 443,
    protocol: str = "vless",
    **kwargs,
) -> ParseResult:
    return ParseResult(
        protocol=protocol,
        host=host,
        port=port,
        raw_uri=f"{protocol}://{host}:{port}",
        **kwargs,
    )


# ===========================================================================
# DNS RESOLVER TESTS
# ===========================================================================


class TestDnsResolverLiteralIPs:
    """Literal IPv4/IPv6 addresses should skip DNS lookup."""

    def test_ipv4_literal_no_lookup(self):
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("1.2.3.4")
        assert result.resolved is True
        assert result.addresses == ["1.2.3.4"]
        assert result.is_ipv4 is True
        assert result.is_ipv6 is False

    def test_ipv6_literal_no_lookup(self):
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("2001:db8::1")
        assert result.resolved is True
        assert result.addresses == ["2001:db8::1"]
        assert result.is_ipv4 is False
        assert result.is_ipv6 is True

    def test_ipv4_loopback(self):
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("127.0.0.1")
        assert result.resolved is True
        assert result.addresses == ["127.0.0.1"]

    def test_ipv6_loopback(self):
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("::1")
        assert result.resolved is True
        assert result.addresses == ["::1"]

    def test_ipv4_mapped_ipv6(self):
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("::ffff:192.168.1.1")
        assert result.resolved is True
        assert len(result.addresses) == 1


class TestDnsResolverHostnames:
    """Hostnames should be resolved via socket.getaddrinfo."""

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    def test_single_ipv4_address(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
        ]
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("example.com")
        assert result.resolved is True
        assert result.addresses == ["93.184.216.34"]
        assert result.is_ipv4 is True
        mock_getaddrinfo.assert_called_once()

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    def test_multiple_addresses_sorted(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.1", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 0)),
        ]
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("multi.example.com")
        assert result.resolved is True
        assert result.addresses == ["1.2.3.4", "10.0.0.1", "192.168.1.1"]
        assert result.is_ipv4 is True

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    def test_mixed_ipv4_ipv6(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("2001:db8::1", 0, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
        ]
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("dual.example.com")
        assert result.resolved is True
        assert len(result.addresses) == 2
        # IPv4 first (sorted by version: AF_INET < AF_INET6)
        assert result.addresses[0] == "93.184.216.34"

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    def test_dns_failure(self, mock_getaddrinfo):
        mock_getaddrinfo.side_effect = socket.gaierror("Name resolution failed")
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("nonexistent.example.com")
        assert result.resolved is False
        assert result.addresses == []
        assert result.error is not None

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    def test_dns_timeout(self, mock_getaddrinfo):
        mock_getaddrinfo.side_effect = TimeoutError("DNS timeout")
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("slow.example.com")
        assert result.resolved is False
        assert result.addresses == []

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    def test_dns_empty_result(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = []
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("noaddresses.example.com")
        assert result.resolved is False
        assert result.addresses == []


class TestDnsResolverTimeoutEnforcement:
    """The timeout parameter must actually bound DNS resolution.

    Uses the real socket default-timeout primitives (process-global but
    harmless in tests) and only mocks getaddrinfo, so we observe the actual
    timeout in effect during the lookup rather than trusting mocks.
    """

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    def test_timeout_is_set_during_resolution(self, mock_getaddrinfo):
        observed: list[float | None] = []

        def fake_getaddrinfo(*args, **kwargs):
            observed.append(socket.getdefaulttimeout())
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 0))]

        mock_getaddrinfo.side_effect = fake_getaddrinfo
        from proxyaggregator.geoip.resolver import resolve_host

        saved = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(77.0)
            result = resolve_host("example.com", timeout=3.0)
            assert result.resolved is True
            # The timeout in effect *during* the lookup must be the requested one
            assert observed == [3.0]
            # The previous default must be restored afterward
            assert socket.getdefaulttimeout() == 77.0
        finally:
            socket.setdefaulttimeout(saved)

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    def test_previous_timeout_restored_after_success(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 0)),
        ]
        from proxyaggregator.geoip.resolver import resolve_host

        saved = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(99.0)
            resolve_host("example.com", timeout=2.0)
            assert socket.getdefaulttimeout() == 99.0
        finally:
            socket.setdefaulttimeout(saved)

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    def test_previous_timeout_restored_on_exception(self, mock_getaddrinfo):
        mock_getaddrinfo.side_effect = socket.gaierror("fail")
        from proxyaggregator.geoip.resolver import resolve_host

        saved = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(42.0)
            result = resolve_host("bad.example.com", timeout=1.0)
            assert result.resolved is False
            assert result.error is not None
            # Restoration must still happen despite the exception
            assert socket.getdefaulttimeout() == 42.0
        finally:
            socket.setdefaulttimeout(saved)

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    @patch("proxyaggregator.geoip.resolver.socket.setdefaulttimeout")
    @patch("proxyaggregator.geoip.resolver.socket.getdefaulttimeout")
    def test_invalid_timeout_returns_error_without_dns(
        self, mock_getdefaulttimeout, mock_setdefaulttimeout, mock_getaddrinfo
    ):
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("example.com", timeout=-1.0)
        assert result.resolved is False
        assert result.error is not None
        mock_getaddrinfo.assert_not_called()
        mock_setdefaulttimeout.assert_not_called()

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    @patch("proxyaggregator.geoip.resolver.socket.setdefaulttimeout")
    @patch("proxyaggregator.geoip.resolver.socket.getdefaulttimeout")
    def test_zero_timeout_returns_error_without_dns(
        self, mock_getdefaulttimeout, mock_setdefaulttimeout, mock_getaddrinfo
    ):
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("example.com", timeout=0.0)
        assert result.resolved is False
        assert result.error is not None
        mock_getaddrinfo.assert_not_called()
        mock_setdefaulttimeout.assert_not_called()

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    @patch("proxyaggregator.geoip.resolver.socket.setdefaulttimeout")
    @patch("proxyaggregator.geoip.resolver.socket.getdefaulttimeout")
    def test_non_numeric_timeout_returns_error_without_dns(
        self, mock_getdefaulttimeout, mock_setdefaulttimeout, mock_getaddrinfo
    ):
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("example.com", timeout="fast")  # type: ignore[arg-type]
        assert result.resolved is False
        assert result.error is not None
        mock_getaddrinfo.assert_not_called()
        mock_setdefaulttimeout.assert_not_called()


class TestDnsResolverInvalidInputs:
    """Invalid or empty hostnames should produce clear errors."""

    def test_empty_string(self):
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("")
        assert result.resolved is False
        assert result.error is not None

    def test_whitespace_only(self):
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("   ")
        assert result.resolved is False

    def test_none_input(self):
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host(None)  # type: ignore[arg-type]
        assert result.resolved is False


class TestDnsResolverDeterminism:
    """Multiple addresses must be sorted deterministically."""

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    def test_alphabetical_sort(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("5.5.5.5", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.1.1.1", 0)),
        ]
        from proxyaggregator.geoip.resolver import resolve_host

        result = resolve_host("test.example.com")
        assert result.addresses == ["1.1.1.1", "5.5.5.5", "10.0.0.1"]

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    def test_same_result_on_repeated_calls(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("3.3.3.3", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.1.1.1", 0)),
        ]
        from proxyaggregator.geoip.resolver import resolve_host

        r1 = resolve_host("test.example.com")
        r2 = resolve_host("test.example.com")
        assert r1.addresses == r2.addresses


# ===========================================================================
# MMDB READER TESTS
# ===========================================================================


class TestMmdbReaderBasic:
    """Test MMDB reader with a minimal synthetic database."""

    def test_open_valid_mmdb(self, tmp_path):
        from proxyaggregator.geoip.mmdb import MmdbReader

        db_path = tmp_path / "test.mmdb"
        db_path.write_bytes(_build_mmdb({"1.2.3.4": {"country": {"iso_code": "US"}}}))
        reader = MmdbReader(str(db_path))
        assert reader.is_valid
        reader.close()

    def test_lookup_ipv4(self, tmp_path):
        from proxyaggregator.geoip.mmdb import MmdbReader

        db_path = tmp_path / "test.mmdb"
        db_path.write_bytes(_build_mmdb({"1.2.3.4": {"country": {"iso_code": "US"}}}))
        reader = MmdbReader(str(db_path))
        record = reader.lookup("1.2.3.4")
        assert record is not None
        assert record.get("country", {}).get("iso_code") == "US"
        reader.close()

    def test_lookup_missing_ip(self, tmp_path):
        from proxyaggregator.geoip.mmdb import MmdbReader

        db_path = tmp_path / "test.mmdb"
        db_path.write_bytes(_build_mmdb({"1.2.3.4": {"country": {"iso_code": "US"}}}))
        reader = MmdbReader(str(db_path))
        record = reader.lookup("99.99.99.99")
        assert record is None
        reader.close()

    def test_invalid_path(self):
        from proxyaggregator.geoip.mmdb import MmdbReader

        reader = MmdbReader("/nonexistent/path.mmdb")
        assert not reader.is_valid

    def test_malformed_file(self, tmp_path):
        from proxyaggregator.geoip.mmdb import MmdbReader

        db_path = tmp_path / "bad.mmdb"
        db_path.write_bytes(b"this is not an mmdb file")
        reader = MmdbReader(str(db_path))
        assert not reader.is_valid


class TestMmdbReaderFields:
    """Test optional and missing GeoIP fields."""

    def test_optional_fields_present(self, tmp_path):
        from proxyaggregator.geoip.mmdb import MmdbReader

        record = {
            "country": {"iso_code": "DE", "names": {"en": "Germany"}},
            "city": {"names": {"en": "Berlin"}},
            "location": {"latitude": 52.52, "longitude": 13.405},
        }
        db_path = tmp_path / "test.mmdb"
        db_path.write_bytes(_build_mmdb({"5.5.5.5": record}))
        reader = MmdbReader(str(db_path))
        result = reader.lookup("5.5.5.5")
        assert result is not None
        assert result["country"]["iso_code"] == "DE"
        assert result["city"]["names"]["en"] == "Berlin"
        assert result["location"]["latitude"] == 52.52
        reader.close()

    def test_missing_optional_fields(self, tmp_path):
        from proxyaggregator.geoip.mmdb import MmdbReader

        record = {"country": {"iso_code": "XX"}}
        db_path = tmp_path / "test.mmdb"
        db_path.write_bytes(_build_mmdb({"1.1.1.1": record}))
        reader = MmdbReader(str(db_path))
        result = reader.lookup("1.1.1.1")
        assert result is not None
        assert "city" not in result
        assert "location" not in result
        reader.close()

    def test_empty_data_section(self, tmp_path):
        from proxyaggregator.geoip.mmdb import MmdbReader

        db_path = tmp_path / "empty.mmdb"
        db_path.write_bytes(_build_mmdb({}))
        reader = MmdbReader(str(db_path))
        assert reader.is_valid
        record = reader.lookup("1.2.3.4")
        assert record is None
        reader.close()

    def test_database_type_metadata(self, tmp_path):
        from proxyaggregator.geoip.mmdb import MmdbReader

        db_path = tmp_path / "test.mmdb"
        db_path.write_bytes(_build_mmdb({"1.2.3.4": {}}))
        reader = MmdbReader(str(db_path))
        assert reader.database_type == "GeoLite2-City"
        reader.close()


class TestValidateMmdb:
    """Production provisioning guard: fail fast when the GeoIP DB is unusable."""

    def _valid_db(self, tmp_path):
        db_path = tmp_path / "valid.mmdb"
        db_path.write_bytes(_build_mmdb({"1.2.3.4": {"country": {"iso_code": "US"}}}))
        return db_path

    def _user_country_db(self, tmp_path):
        db_path = tmp_path / "user-country.mmdb"
        db_path.write_bytes(
            _build_mmdb(
                {"1.2.3.4": {"country_code": "US"}},
                database_type="country ipvAll",
            )
        )
        return db_path

    def test_valid_geolite2_database_returns_type(self, tmp_path):
        from proxyaggregator.geoip.mmdb import validate_mmdb

        result = validate_mmdb(str(self._valid_db(tmp_path)))
        assert result == "GeoLite2-City"

    def test_valid_user_country_database_returns_type(self, tmp_path):
        from proxyaggregator.geoip.mmdb import validate_mmdb

        result = validate_mmdb(str(self._user_country_db(tmp_path)))
        assert result == "country ipvAll"

    def test_valid_database_accepts_pathlib(self, tmp_path):
        from proxyaggregator.geoip.mmdb import validate_mmdb

        result = validate_mmdb(self._valid_db(tmp_path))
        assert result == "GeoLite2-City"

    def test_explicit_strict_allowlist_user_country(self, tmp_path):
        from proxyaggregator.geoip.mmdb import validate_mmdb

        result = validate_mmdb(self._user_country_db(tmp_path), allowed_types=("country ipvAll",))
        assert result == "country ipvAll"

    def test_explicit_allowlist_accepts_both_supported_types(self, tmp_path):
        from proxyaggregator.geoip.mmdb import validate_mmdb

        both = ("country ipvAll", "GeoLite2-City")
        assert (
            validate_mmdb(self._user_country_db(tmp_path), allowed_types=both) == "country ipvAll"
        )
        assert validate_mmdb(self._valid_db(tmp_path), allowed_types=both) == "GeoLite2-City"

    def test_missing_file_raises(self, tmp_path):
        from proxyaggregator.geoip.mmdb import GeoIpDatabaseError, validate_mmdb

        with pytest.raises(GeoIpDatabaseError, match="not found"):
            validate_mmdb(tmp_path / "missing.mmdb")

    def test_directory_path_raises(self, tmp_path):
        from proxyaggregator.geoip.mmdb import GeoIpDatabaseError, validate_mmdb

        with pytest.raises(GeoIpDatabaseError, match="not a file"):
            validate_mmdb(tmp_path)

    @patch("proxyaggregator.geoip.mmdb.os.access", return_value=False)
    def test_unreadable_file_raises(self, _mock_access, tmp_path):
        from proxyaggregator.geoip.mmdb import GeoIpDatabaseError, validate_mmdb

        with pytest.raises(GeoIpDatabaseError, match="not readable"):
            validate_mmdb(self._valid_db(tmp_path))

    def test_malformed_file_raises(self, tmp_path):
        from proxyaggregator.geoip.mmdb import GeoIpDatabaseError, validate_mmdb

        db_path = tmp_path / "bad.mmdb"
        db_path.write_bytes(b"this is not an mmdb file")
        with pytest.raises(GeoIpDatabaseError, match="not a valid MaxMind DB"):
            validate_mmdb(db_path)

    def test_unsupported_database_type_raises(self, tmp_path):
        from proxyaggregator.geoip.mmdb import GeoIpDatabaseError, validate_mmdb

        with pytest.raises(GeoIpDatabaseError, match="Unsupported GeoIP database type"):
            validate_mmdb(self._valid_db(tmp_path), allowed_types=("country ipvAll",))

    def test_geolite2_rejected_under_strict_user_country_allowlist(self, tmp_path):
        from proxyaggregator.geoip.mmdb import GeoIpDatabaseError, validate_mmdb

        with pytest.raises(GeoIpDatabaseError, match="Unsupported GeoIP database type"):
            validate_mmdb(self._valid_db(tmp_path), allowed_types=("country ipvAll",))

    def test_error_never_contains_credentials(self, tmp_path):
        from proxyaggregator.geoip.mmdb import GeoIpDatabaseError, validate_mmdb

        secret_token = "S0ME-SECRET-LICENSE-KEY"
        db_path = tmp_path / "bad.mmdb"
        db_path.write_bytes(secret_token.encode())
        with pytest.raises(GeoIpDatabaseError) as exc_info:
            validate_mmdb(db_path)
        assert secret_token not in str(exc_info.value)


class TestVerifyGeoIpCli:
    """CLI verify-geoip command (the workflow's pre-pipeline guard)."""

    def test_cli_verify_geoip_geolite2_ok(self, tmp_path, capsys):
        from proxyaggregator.__main__ import main

        db_path = tmp_path / "valid.mmdb"
        db_path.write_bytes(_build_mmdb({"1.2.3.4": {"country": {"iso_code": "US"}}}))
        assert main(["verify-geoip", "--path", str(db_path)]) == 0
        assert "GeoIP database OK: GeoLite2-City" in capsys.readouterr().out

    def test_cli_verify_geoip_user_country_ok(self, tmp_path, capsys):
        from proxyaggregator.__main__ import main

        db_path = tmp_path / "user-country.mmdb"
        db_path.write_bytes(
            _build_mmdb({"1.2.3.4": {"country_code": "US"}}, database_type="country ipvAll")
        )
        assert main(["verify-geoip", "--path", str(db_path)]) == 0
        assert "GeoIP database OK: country ipvAll" in capsys.readouterr().out

    def test_cli_verify_geoip_missing_fails(self, tmp_path, capsys):
        from proxyaggregator.__main__ import main

        missing = tmp_path / "missing.mmdb"
        assert main(["verify-geoip", "--path", str(missing)]) == 1
        assert "ERROR:" in capsys.readouterr().err


# ===========================================================================
# GEOIP RECORD EXTRACTION: BOTH DATABASE SCHEMAS
# ===========================================================================


class TestGeoIpRecordExtraction:
    """Raw record -> GeoIpRecord for GeoLite2-City and ip-location-db schemas."""

    def test_geolite2_city_schema(self):
        from proxyaggregator.geoip.enrich import _extract_geo_record

        record = _extract_geo_record(
            "1.2.3.4",
            {"country": {"iso_code": "DE", "names": {"en": "Germany"}}},
        )
        assert record.country_code == "DE"
        assert record.country_name == "Germany"

    def test_user_country_schema(self):
        from proxyaggregator.geoip.enrich import _extract_geo_record

        record = _extract_geo_record("1.2.3.4", {"country_code": "US"})
        assert record.country_code == "US"
        assert record.country_name is None
        assert record.city is None
        assert record.latitude is None
        assert record.longitude is None

    def test_both_schemas_produce_same_country_code(self):
        from proxyaggregator.geoip.enrich import _extract_geo_record

        geolite = _extract_geo_record(
            "1.2.3.4",
            {"country": {"iso_code": "US"}, "city": {"names": {"en": "X"}}},
        )
        user_country = _extract_geo_record("1.2.3.4", {"country_code": "US"})
        assert geolite.country_code == user_country.country_code == "US"

    def test_prefers_nested_iso_code_over_top_level(self):
        from proxyaggregator.geoip.enrich import _extract_geo_record

        record = _extract_geo_record(
            "1.2.3.4", {"country": {"iso_code": "DE"}, "country_code": "US"}
        )
        assert record.country_code == "DE"

    def test_missing_country_data_returns_none_fields(self):
        from proxyaggregator.geoip.enrich import _extract_geo_record

        record = _extract_geo_record("1.2.3.4", {})
        assert record.country_code is None
        assert record.country_name is None
        assert record.city is None
        assert record.latitude is None
        assert record.longitude is None


# ===========================================================================
# GEOIP ENRICHMENT PIPELINE TESTS
# ===========================================================================


class TestGeoIpEnrichment:
    """Test the full pipeline: ParseResult -> DNS -> MMDB -> EnrichedResult."""

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    def test_successful_enrichment(self, mock_getaddrinfo, tmp_path):
        from proxyaggregator.geoip.enrich import GeoIpEnricher
        from proxyaggregator.geoip.mmdb import MmdbReader

        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 0)),
        ]
        db_path = tmp_path / "test.mmdb"
        db_path.write_bytes(
            _build_mmdb(
                {
                    "1.2.3.4": {
                        "country": {"iso_code": "US", "names": {"en": "United States"}},
                        "city": {"names": {"en": "New York"}},
                        "location": {"latitude": 40.71, "longitude": -74.01},
                    }
                }
            )
        )
        reader = MmdbReader(str(db_path))
        enricher = GeoIpEnricher(reader)

        result = enricher.enrich(_make_result(host="example.com", port=443))
        assert result.resolved_ip == "1.2.3.4"
        assert result.country_code == "US"
        assert result.city == "New York"
        assert result.latitude == pytest.approx(40.71)
        assert result.longitude == pytest.approx(-74.01)
        reader.close()

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    def test_dns_failure_no_location(self, mock_getaddrinfo, tmp_path):
        from proxyaggregator.geoip.enrich import GeoIpEnricher
        from proxyaggregator.geoip.mmdb import MmdbReader

        mock_getaddrinfo.side_effect = socket.gaierror("fail")
        db_path = tmp_path / "test.mmdb"
        db_path.write_bytes(_build_mmdb({}))
        reader = MmdbReader(str(db_path))
        enricher = GeoIpEnricher(reader)

        result = enricher.enrich(_make_result(host="fail.example.com"))
        assert result.resolved_ip is None
        assert result.country_code is None
        assert result.city is None
        reader.close()

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    def test_geoip_miss_no_location(self, mock_getaddrinfo, tmp_path):
        from proxyaggregator.geoip.enrich import GeoIpEnricher
        from proxyaggregator.geoip.mmdb import MmdbReader

        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 0)),
        ]
        db_path = tmp_path / "test.mmdb"
        db_path.write_bytes(_build_mmdb({}))  # empty DB
        reader = MmdbReader(str(db_path))
        enricher = GeoIpEnricher(reader)

        result = enricher.enrich(_make_result(host="unknown.example.com"))
        assert result.resolved_ip == "10.0.0.1"
        assert result.country_code is None
        assert result.city is None
        reader.close()

    def test_literal_ip_enrichment(self, tmp_path):
        from proxyaggregator.geoip.enrich import GeoIpEnricher
        from proxyaggregator.geoip.mmdb import MmdbReader

        db_path = tmp_path / "test.mmdb"
        db_path.write_bytes(
            _build_mmdb(
                {
                    "8.8.8.8": {
                        "country": {"iso_code": "US"},
                        "city": {"names": {"en": "Mountain View"}},
                        "location": {"latitude": 37.386, "longitude": -122.084},
                    }
                }
            )
        )
        reader = MmdbReader(str(db_path))
        enricher = GeoIpEnricher(reader)

        result = enricher.enrich(_make_result(host="8.8.8.8", port=53))
        assert result.resolved_ip == "8.8.8.8"
        assert result.country_code == "US"
        assert result.city == "Mountain View"
        reader.close()

    def test_user_country_database_enrichment(self, tmp_path):
        from proxyaggregator.geoip.enrich import GeoIpEnricher
        from proxyaggregator.geoip.mmdb import MmdbReader

        db_path = tmp_path / "user-country.mmdb"
        db_path.write_bytes(
            _build_mmdb(
                {"1.1.1.1": {"country_code": "AU"}, "8.8.8.8": {"country_code": "US"}},
                database_type="country ipvAll",
            )
        )
        reader = MmdbReader(str(db_path))
        assert reader.database_type == "country ipvAll"
        enricher = GeoIpEnricher(reader)

        au = enricher.enrich(_make_result(host="1.1.1.1", port=53))
        us = enricher.enrich(_make_result(host="8.8.8.8", port=53))
        assert au.country_code == "AU"
        assert us.country_code == "US"
        assert au.country_name is None
        assert au.city is None
        reader.close()

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    def test_multiple_ips_uses_first(self, mock_getaddrinfo, tmp_path):
        from proxyaggregator.geoip.enrich import GeoIpEnricher
        from proxyaggregator.geoip.mmdb import MmdbReader

        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.1.1.1", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("2.2.2.2", 0)),
        ]
        db_path = tmp_path / "test.mmdb"
        db_path.write_bytes(
            _build_mmdb(
                {
                    "1.1.1.1": {"country": {"iso_code": "AU"}},
                    "2.2.2.2": {"country": {"iso_code": "JP"}},
                }
            )
        )
        reader = MmdbReader(str(db_path))
        enricher = GeoIpEnricher(reader)

        result = enricher.enrich(_make_result(host="multi.example.com"))
        assert result.resolved_ip == "1.1.1.1"
        assert result.country_code == "AU"
        assert result.all_resolved_ips == ["1.1.1.1", "2.2.2.2"]
        reader.close()

    def test_no_guessing_from_hostname(self, tmp_path):
        """Location must NEVER be derived from hostname text."""
        from proxyaggregator.geoip.enrich import GeoIpEnricher
        from proxyaggregator.geoip.mmdb import MmdbReader

        db_path = tmp_path / "test.mmdb"
        db_path.write_bytes(_build_mmdb({}))  # empty
        reader = MmdbReader(str(db_path))
        enricher = GeoIpEnricher(reader)

        result = enricher.enrich(_make_result(host="us-proxy-germany-tokyo.example.com"))
        assert result.country_code is None
        assert result.city is None
        reader.close()

    @patch("proxyaggregator.geoip.resolver.socket.getaddrinfo")
    def test_enrichment_preserves_original(self, mock_getaddrinfo, tmp_path):
        from proxyaggregator.geoip.enrich import GeoIpEnricher
        from proxyaggregator.geoip.mmdb import MmdbReader

        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 0)),
        ]
        db_path = tmp_path / "test.mmdb"
        db_path.write_bytes(
            _build_mmdb(
                {
                    "1.2.3.4": {"country": {"iso_code": "US"}},
                }
            )
        )
        reader = MmdbReader(str(db_path))
        enricher = GeoIpEnricher(reader)

        original = _make_result(host="example.com", port=443, protocol="vless")
        result = enricher.enrich(original)
        assert result.original_host == "example.com"
        assert result.original_port == 443
        assert result.original_protocol == "vless"
        assert result.resolved_ip == "1.2.3.4"
        reader.close()

    def test_invalid_ip_not_resolved(self, tmp_path):
        """An invalid host that isn't a valid IP and fails DNS should remain unknown."""
        from proxyaggregator.geoip.enrich import GeoIpEnricher
        from proxyaggregator.geoip.mmdb import MmdbReader

        db_path = tmp_path / "test.mmdb"
        db_path.write_bytes(_build_mmdb({}))
        reader = MmdbReader(str(db_path))
        enricher = GeoIpEnricher(reader)

        result = enricher.enrich(_make_result(host="not-a-hostname"))
        assert result.resolved_ip is None
        assert result.country_code is None
        reader.close()


# ===========================================================================
# IP-BASED DEDUP TESTS
# ===========================================================================


class TestIpDedup:
    """Test IP-based deduplication as an additional identity/collision signal."""

    def test_same_resolved_ip_detected(self):
        from proxyaggregator.geoip.dedup import IpDeduplicator

        dedup = IpDeduplicator()
        items = [
            _make_result(host="1.2.3.4", port=443),
            _make_result(host="1.2.3.4", port=443),
        ]
        results = dedup.deduplicate(items)
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.EXACT
        assert results[1].match_index == 0

    def test_different_ips_remain_distinct(self):
        from proxyaggregator.geoip.dedup import IpDeduplicator

        dedup = IpDeduplicator()
        items = [
            _make_result(host="1.1.1.1", port=443),
            _make_result(host="2.2.2.2", port=443),
        ]
        results = dedup.deduplicate(items)
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.NONE

    def test_same_ip_different_ports_distinguishable(self):
        from proxyaggregator.geoip.dedup import IpDeduplicator

        dedup = IpDeduplicator()
        items = [
            _make_result(host="1.2.3.4", port=443),
            _make_result(host="1.2.3.4", port=8443),
        ]
        results = dedup.deduplicate(items)
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.NONE

    def test_same_ip_different_protocols_distinguishable(self):
        from proxyaggregator.geoip.dedup import IpDeduplicator

        dedup = IpDeduplicator()
        items = [
            _make_result(host="1.2.3.4", port=443, protocol="vless"),
            _make_result(host="1.2.3.4", port=443, protocol="trojan"),
        ]
        results = dedup.deduplicate(items)
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.NONE

    def test_same_ip_port_different_credentials_distinguishable(self):
        from proxyaggregator.geoip.dedup import IpDeduplicator

        dedup = IpDeduplicator()
        items = [
            _make_result(host="1.2.3.4", port=443, user="user1"),
            _make_result(host="1.2.3.4", port=443, user="user2"),
        ]
        results = dedup.deduplicate(items)
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.NONE

    def test_multiple_resolved_ips_deterministic(self):
        """When a host resolves to multiple IPs, the first (sorted) is used for dedup."""
        from proxyaggregator.geoip.dedup import IpDeduplicator

        dedup = IpDeduplicator()
        items = [
            _make_result(host="multi.example.com", port=443),
            _make_result(host="multi.example.com", port=443),
        ]
        results = dedup.deduplicate(
            items,
            ip_map={
                "multi.example.com": ["2.2.2.2", "1.1.1.1"],
            },
        )
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.EXACT

    def test_unresolved_hosts_not_equal(self):
        """Unresolved hosts should not be treated as IP-duplicates."""
        from proxyaggregator.geoip.dedup import IpDeduplicator

        dedup = IpDeduplicator()
        items = [
            _make_result(host="fail1.example.com", port=443),
            _make_result(host="fail2.example.com", port=443),
        ]
        results = dedup.deduplicate(items, ip_map={})
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.NONE


class TestIpDedupNumericOrdering:
    """Primary IP selection must use numeric ordering, not lexicographic.

    Lexicographic: "10.0.0.1" < "2.2.2.2"  (string comparison)
    Numeric:       "2.2.2.2"  < "10.0.0.1" (integer comparison)
    """

    def test_numeric_ordering_not_lexicographic(self):
        """ip_map with lexicographically-smaller-but-numerically-larger IP."""
        from proxyaggregator.geoip.dedup import IpDeduplicator

        dedup = IpDeduplicator()
        items = [
            _make_result(host="multi.example.com", port=443),
            _make_result(host="multi.example.com", port=443),
        ]
        # Lexicographic sort would pick "10.0.0.1" first.
        # Numeric sort must pick "2.2.2.2" first.
        results = dedup.deduplicate(
            items,
            ip_map={"multi.example.com": ["10.0.0.1", "2.2.2.2"]},
        )
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.EXACT
        # The EXACT match reason echoes the primary IP used for the dedup key.
        assert "2.2.2.2" in results[1].match_reason

    def test_numeric_ordering_matches_resolver(self):
        """Dedup primary IP must match what resolver.py would pick."""
        from proxyaggregator.geoip.dedup import IpDeduplicator
        from proxyaggregator.geoip.resolver import _ip_sort_key

        ip_list = ["192.168.1.1", "10.0.0.1", "2.2.2.2"]
        sorted_expected = sorted(ip_list, key=_ip_sort_key)
        assert sorted_expected[0] == "2.2.2.2"

        dedup = IpDeduplicator()
        items = [
            _make_result(host="multi.example.com", port=443),
            _make_result(host="multi.example.com", port=443),
        ]
        results = dedup.deduplicate(
            items,
            ip_map={"multi.example.com": ip_list},
        )
        # Dedup must select the same primary IP the resolver would sort first.
        assert sorted_expected[0] in results[1].match_reason

    def test_ipv4_before_ipv6_ordering(self):
        """IPv4 must sort before IPv6 in dedup primary selection."""
        from proxyaggregator.geoip.dedup import IpDeduplicator

        dedup = IpDeduplicator()
        items = [
            _make_result(host="dual.example.com", port=443),
            _make_result(host="dual.example.com", port=443),
        ]
        # IPv6 address sorts before IPv4 lexicographically in some cases,
        # but resolver's rule is IPv4 always first.
        results = dedup.deduplicate(
            items,
            ip_map={"dual.example.com": ["2001:db8::1", "1.2.3.4"]},
        )
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.EXACT
        assert "1.2.3.4" in results[1].match_reason

    def test_single_ip_unchanged(self):
        """Single IP in ip_map works regardless of ordering."""
        from proxyaggregator.geoip.dedup import IpDeduplicator

        dedup = IpDeduplicator()
        items = [
            _make_result(host="single.example.com", port=443),
            _make_result(host="single.example.com", port=443),
        ]
        results = dedup.deduplicate(
            items,
            ip_map={"single.example.com": ["5.5.5.5"]},
        )
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.EXACT


# ===========================================================================
# REGRESSION: ensure Phase 4 dedup still works
# ===========================================================================


class TestRegressionPhase4StillWorks:
    """Verify Phase 4 deduplication is not broken by Phase 5 imports."""

    def test_phase4_imports(self):
        from proxyaggregator.dedup.canonical import (
            canonicalize,  # noqa: F401
            compute_content_hash,  # noqa: F401
        )
        from proxyaggregator.dedup.deduplicator import Deduplicator  # noqa: F401
        from proxyaggregator.dedup.endpoint import (
            EndpointIdentity,  # noqa: F401
            endpoint_identity,  # noqa: F401
        )
        from proxyaggregator.dedup.fuzzy import fuzzy_match  # noqa: F401
        from proxyaggregator.dedup.models import (
            DedupMatchType,
            DedupResult,  # noqa: F401
        )

        assert DedupMatchType.EXACT == "exact"
        assert DedupMatchType.ENDPOINT == "endpoint"
        assert DedupMatchType.FUZZY == "fuzzy"
        assert DedupMatchType.NONE == "none"

    def test_phase4_dedup_still_works(self):
        from proxyaggregator.dedup.deduplicator import Deduplicator

        dedup = Deduplicator()
        items = [
            _make_result(host="example.com", port=443, user="a"),
            _make_result(host="example.com", port=443, user="b"),  # endpoint dup
            _make_result(host="other.com", port=443),  # unique
        ]
        results = dedup.deduplicate(items)
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.ENDPOINT
        assert results[2].match_type == DedupMatchType.NONE
