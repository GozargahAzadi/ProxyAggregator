"""Real protocol handshakes used for proxy health checks.

These are true, minimal protocol checks (not merely "TCP connected"). Each
function performs the actual on-wire handshake for its protocol, validates
the response, and returns a stable, sanitized outcome.

A successful handshake is the only thing that sets ``protocol_checked=True``
upstream. Credentials supplied by the caller are used on the wire only and
are never returned in the outcome.
"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING

from proxyaggregator.health import errors
from proxyaggregator.health.checks import CheckError, monotonic_ms

if TYPE_CHECKING:
    from asyncio import StreamReader, StreamWriter

# Upper bound on bytes read while accumulating an HTTP header block.
_MAX_HEADER_BYTES = 16 * 1024


@dataclass(frozen=True)
class ProtocolCheckOutcome:
    """Result of a single protocol handshake attempt."""

    ok: bool
    proxy_ms: float
    error: str | None = None


async def _read_until_headers(
    reader: StreamReader,
    *,
    timeout: float,
) -> bytes:
    """Read from the stream until a blank line or the size/time cap."""
    buf = b""
    while b"\r\n\r\n" not in buf:
        if len(buf) >= _MAX_HEADER_BYTES:
            raise CheckError(errors.HTTP_MALFORMED)
        chunk = await asyncio.wait_for(reader.read(1), timeout)
        if not chunk:
            raise CheckError(errors.HTTP_MALFORMED)
        buf += chunk
    return buf


async def _read_exactly(reader: StreamReader, n: int, *, timeout: float) -> bytes:
    """Read exactly ``n`` bytes or raise a sanitized error."""
    try:
        return await asyncio.wait_for(reader.readexactly(n), timeout)
    except asyncio.IncompleteReadError as exc:
        raise CheckError(errors.SOCKS_MALFORMED) from exc


async def check_http_connect(
    reader: StreamReader,
    writer: StreamWriter,
    *,
    target_host: str,
    target_port: int,
    user: str | None,
    password: str | None,
    timeout: float,
) -> ProtocolCheckOutcome:
    """Perform an HTTP ``CONNECT`` handshake and validate the status line."""
    start = monotonic_ms()
    try:
        authority = f"{target_host}:{target_port}"
        lines = [
            f"CONNECT {authority} HTTP/1.1",
            f"Host: {authority}",
            "Proxy-Connection: keep-alive",
        ]
        if user is not None:
            cred = base64.b64encode(f"{user}:{password or ''}".encode()).decode("ascii")
            lines.append(f"Proxy-Authorization: Basic {cred}")
        request = ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")

        writer.write(request)
        await asyncio.wait_for(writer.drain(), timeout)

        raw = await _read_until_headers(reader, timeout=timeout)
        first_line = raw.split(b"\r\n", 1)[0].decode("latin-1")
        if not first_line.startswith("HTTP/"):
            raise CheckError(errors.HTTP_MALFORMED)
        parts = first_line.split(" ", 2)
        if len(parts) < 2:
            raise CheckError(errors.HTTP_MALFORMED)
        try:
            status_code = int(parts[1])
        except ValueError as exc:
            raise CheckError(errors.HTTP_MALFORMED) from exc

        proxy_ms = monotonic_ms() - start
        if 200 <= status_code < 300:
            return ProtocolCheckOutcome(ok=True, proxy_ms=proxy_ms)
        if status_code == 407:
            return ProtocolCheckOutcome(ok=False, proxy_ms=proxy_ms, error=errors.HTTP_STATUS_407)
        return ProtocolCheckOutcome(ok=False, proxy_ms=proxy_ms, error=errors.HTTP_REJECTED)
    except TimeoutError:
        return ProtocolCheckOutcome(
            ok=False, proxy_ms=monotonic_ms() - start, error=errors.CONNECTION_TIMEOUT
        )
    except CheckError as exc:
        return ProtocolCheckOutcome(ok=False, proxy_ms=monotonic_ms() - start, error=exc.code)
    except (ConnectionError, OSError):
        return ProtocolCheckOutcome(
            ok=False, proxy_ms=monotonic_ms() - start, error=errors.CONNECTION_ERROR
        )


async def _socks5_read_reply(
    reader: StreamReader,
    *,
    timeout: float,
) -> int:
    """Read a SOCKS5 reply and return the REP code."""
    head = await _read_exactly(reader, 4, timeout=timeout)
    ver, rep, _rsv, atyp = head
    if ver != 0x05:
        raise CheckError(errors.SOCKS_MALFORMED)

    if atyp == 0x01:
        await _read_exactly(reader, 4, timeout=timeout)
    elif atyp == 0x04:
        await _read_exactly(reader, 16, timeout=timeout)
    elif atyp == 0x03:
        length = await _read_exactly(reader, 1, timeout=timeout)
        await _read_exactly(reader, length[0], timeout=timeout)
    else:
        raise CheckError(errors.SOCKS_MALFORMED)

    await _read_exactly(reader, 2, timeout=timeout)
    return rep


async def _socks5_negotiate(
    reader: StreamReader,
    writer: StreamWriter,
    *,
    user: str | None,
    password: str | None,
    timeout: float,
) -> None:
    """Perform the SOCKS5 method negotiation (RFC 1928) and optional auth."""
    methods = bytearray([0x00])
    if user is not None:
        methods.append(0x02)
    greeting = bytes([0x05, len(methods)]) + bytes(methods)
    writer.write(greeting)
    await asyncio.wait_for(writer.drain(), timeout)

    resp = await _read_exactly(reader, 2, timeout=timeout)
    ver, method = resp
    if ver != 0x05:
        raise CheckError(errors.SOCKS_MALFORMED)
    if method == 0xFF:
        raise CheckError(errors.SOCKS_REJECTED)
    if method == 0x02:
        if user is None:
            raise CheckError(errors.SOCKS_AUTH_FAILURE)
        ubytes = user.encode("utf-8")[:255]
        pbytes = (password or "").encode("utf-8")[:255]
        subneg = bytes([0x01, len(ubytes)]) + ubytes + bytes([len(pbytes)]) + pbytes
        writer.write(subneg)
        await asyncio.wait_for(writer.drain(), timeout)
        subresp = await _read_exactly(reader, 2, timeout=timeout)
        if subresp[1] != 0x00:
            raise CheckError(errors.SOCKS_AUTH_FAILURE)
    elif method != 0x00:
        raise CheckError(errors.SOCKS_REJECTED)


async def check_socks5(
    reader: StreamReader,
    writer: StreamWriter,
    *,
    target_host: str,
    target_port: int,
    user: str | None,
    password: str | None,
    timeout: float,
) -> ProtocolCheckOutcome:
    """Perform a SOCKS5 handshake (negotiation, auth, CONNECT)."""
    start = monotonic_ms()
    try:
        await _socks5_negotiate(reader, writer, user=user, password=password, timeout=timeout)

        atyp, addr = _socks5_address(target_host)
        request = bytes([0x05, 0x01, 0x00, atyp]) + addr + struct.pack("!H", target_port)
        writer.write(request)
        await asyncio.wait_for(writer.drain(), timeout)

        rep = await _socks5_read_reply(reader, timeout=timeout)
        proxy_ms = monotonic_ms() - start
        if rep == 0x00:
            return ProtocolCheckOutcome(ok=True, proxy_ms=proxy_ms)
        return ProtocolCheckOutcome(ok=False, proxy_ms=proxy_ms, error=errors.SOCKS_REJECTED)
    except TimeoutError:
        return ProtocolCheckOutcome(
            ok=False, proxy_ms=monotonic_ms() - start, error=errors.CONNECTION_TIMEOUT
        )
    except CheckError as exc:
        return ProtocolCheckOutcome(ok=False, proxy_ms=monotonic_ms() - start, error=exc.code)
    except (ConnectionError, OSError):
        return ProtocolCheckOutcome(
            ok=False, proxy_ms=monotonic_ms() - start, error=errors.CONNECTION_ERROR
        )


def _socks5_address(target_host: str) -> tuple[int, bytes]:
    """Return the SOCKS5 ATYP byte and encoded address for a target host."""
    try:
        addr = ipaddress.ip_address(target_host)
    except ValueError:
        host_bytes = target_host.encode("idna")
        return 0x03, bytes([len(host_bytes)]) + host_bytes

    if addr.version == 4:
        return 0x01, addr.packed
    return 0x04, addr.packed


async def check_socks4(
    reader: StreamReader,
    writer: StreamWriter,
    *,
    target_host: str,
    target_port: int,
    user: str | None,
    password: str | None = None,
    timeout: float,
) -> ProtocolCheckOutcome:
    """Perform a SOCKS4 / SOCKS4a CONNECT handshake.

    When ``target_host`` is a hostname, the SOCKS4a extension is used so the
    domain is passed to the proxy rather than requiring a local resolution.
    """
    start = monotonic_ms()
    try:
        is_ipv4 = False
        dst_ip = b"\x00\x00\x00\x00"
        try:
            addr = ipaddress.ip_address(target_host)
            if addr.version == 4:
                dst_ip = addr.packed
                is_ipv4 = True
        except ValueError:
            is_ipv4 = False

        userid = (user or "").encode("utf-8")[:255]
        request = bytes([0x04, 0x01]) + struct.pack("!H", target_port) + dst_ip + userid + b"\x00"
        if not is_ipv4:
            # SOCKS4a: non-zero 4th octet marks a following domain string.
            request = (
                bytes([0x04, 0x01])
                + struct.pack("!H", target_port)
                + b"\x00\x00\x00\x01"
                + userid
                + b"\x00"
                + target_host.encode("idna")
                + b"\x00"
            )
        writer.write(request)
        await asyncio.wait_for(writer.drain(), timeout)

        reply = await _read_exactly(reader, 8, timeout=timeout)
        proxy_ms = monotonic_ms() - start
        if reply[1] == 0x5A:
            return ProtocolCheckOutcome(ok=True, proxy_ms=proxy_ms)
        return ProtocolCheckOutcome(ok=False, proxy_ms=proxy_ms, error=errors.SOCKS_REJECTED)
    except TimeoutError:
        return ProtocolCheckOutcome(
            ok=False, proxy_ms=monotonic_ms() - start, error=errors.CONNECTION_TIMEOUT
        )
    except CheckError as exc:
        return ProtocolCheckOutcome(ok=False, proxy_ms=monotonic_ms() - start, error=exc.code)
    except (ConnectionError, OSError):
        return ProtocolCheckOutcome(
            ok=False, proxy_ms=monotonic_ms() - start, error=errors.CONNECTION_ERROR
        )
