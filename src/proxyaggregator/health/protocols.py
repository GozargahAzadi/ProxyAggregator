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
import hashlib
import hmac
import ipaddress
import os
import struct
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305

from proxyaggregator.health import errors
from proxyaggregator.health.checks import CheckError, monotonic_ms

if TYPE_CHECKING:
    from asyncio import StreamReader, StreamWriter

    from proxyaggregator.parsers.base import ParseResult

# Upper bound on bytes read while accumulating an HTTP header block.
_MAX_HEADER_BYTES = 16 * 1024

# How long we observe an "accepted session" before declaring success for
# protocols that lack an on-wire success acknowledgement (Trojan, SS).
_OBSERVATION_WINDOW = 1.0

# Shadowsocks AEAD ciphers this project can actually talk on the wire.
_SS_SUPPORTED_METHODS = frozenset({"aes-128-gcm", "aes-256-gcm", "chacha20-ietf-poly1305"})
_SS_KEY_SIZES = {
    "aes-128-gcm": 16,
    "aes-256-gcm": 32,
    "chacha20-ietf-poly1305": 32,
}

# VLESS network values that map to a plain TCP stream over the checked
# transport. Anything else (ws/grpc/httpupgrade/xhttp overlays) is unsupported.
_VLESS_SUPPORTED_NETWORKS = frozenset({None, "", "tcp", "raw"})
_TROJAN_SUPPORTED_NETWORKS = frozenset({None, "", "tcp"})


def transport_gate(parsed: ParseResult) -> str | None:
    """Return the unsupported variant token before any dialing, else ``None``.

    Called before a TCP connection is even attempted so that variants this
    project cannot speak on the wire (REALITY, WS overlays, SS-2022 ciphers)
    are reported as unsupported rather than probed and misclassified.
    """
    if parsed.protocol == "vless":
        if parsed.tls == "reality":
            return errors.TLS_REALITY
        if parsed.network not in _VLESS_SUPPORTED_NETWORKS:
            return errors.TRANSPORT_WS
        return None
    if parsed.protocol == "trojan":
        if parsed.network not in _TROJAN_SUPPORTED_NETWORKS:
            return errors.TRANSPORT_WS
        return None
    if parsed.protocol == "ss":
        if parsed.method not in _SS_SUPPORTED_METHODS:
            return errors.SS_CIPHER_UNSUPPORTED
        return None
    return None


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
    parsed: ParseResult | None = None,
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
    parsed: ParseResult | None = None,
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
    parsed: ParseResult | None = None,
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


def _vless_address(target_host: str) -> tuple[int, bytes]:
    """Return the VLESS address type byte and encoded address.

    VLESS uses its own address types: 0x01=IPv4, 0x02=domain, 0x03=IPv6.
    """
    try:
        addr = ipaddress.ip_address(target_host)
    except ValueError:
        host_bytes = target_host.encode("idna")
        return 0x02, bytes([len(host_bytes)]) + host_bytes
    if addr.version == 4:
        return 0x01, addr.packed
    return 0x03, addr.packed


async def check_vless(
    reader: StreamReader,
    writer: StreamWriter,
    *,
    target_host: str,
    target_port: int,
    user: str | None,
    password: str | None = None,
    timeout: float,
    parsed: ParseResult | None = None,
) -> ProtocolCheckOutcome:
    """Perform a VLESS TCP CONNECT handshake and validate the reply.

    The client sends the VLESS request header (version ``0x00``, so the check
    is compatible with xtls-rprx-vision inbound flows) asking the proxy to
    tunnel back to its own advertised endpoint. Success is the server's
    defined ``0x54`` version response.
    """
    start = monotonic_ms()
    try:
        uuid_str = (parsed.user if parsed is not None else user) or ""
        try:
            uuid_bytes = uuid.UUID(uuid_str).bytes
        except (ValueError, AttributeError, TypeError):
            return ProtocolCheckOutcome(
                ok=False, proxy_ms=monotonic_ms() - start, error=errors.PROTOCOL_MALFORMED
            )

        atyp, addr = _vless_address(target_host)
        request = (
            b"\x00"
            + uuid_bytes
            + b"\x00"
            + b"\x01"
            + struct.pack("!H", target_port)
            + bytes([atyp])
            + addr
        )
        writer.write(request)
        await asyncio.wait_for(writer.drain(), timeout)

        try:
            head = await asyncio.wait_for(reader.readexactly(2), timeout)
        except asyncio.IncompleteReadError as exc:
            raise CheckError(errors.PROTOCOL_MALFORMED) from exc

        proxy_ms = monotonic_ms() - start
        if head[0] != 0x54:
            return ProtocolCheckOutcome(
                ok=False, proxy_ms=proxy_ms, error=errors.PROTOCOL_MALFORMED
            )
        return ProtocolCheckOutcome(ok=True, proxy_ms=proxy_ms)
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


async def check_trojan(
    reader: StreamReader,
    writer: StreamWriter,
    *,
    target_host: str,
    target_port: int,
    user: str | None = None,
    password: str | None = None,
    timeout: float,
    parsed: ParseResult | None = None,
) -> ProtocolCheckOutcome:
    """Perform a Trojan CONNECT handshake over the already-established TLS.

    The TLS layer is established by the caller (``upgrade_tls``). The proxy
    credential is sent as hex(SHA-224(password)). Trojan has no success
    acknowledgement: acceptance is inferred when the server keeps the session
    open and sends nothing during a bounded observation window.
    """
    start = monotonic_ms()
    try:
        secret = parsed.password if parsed is not None else password
        if secret is None:
            return ProtocolCheckOutcome(
                ok=False, proxy_ms=monotonic_ms() - start, error=errors.PROTOCOL_MALFORMED
            )

        digest = hashlib.sha224(secret.encode("utf-8")).hexdigest()
        atyp, addr = _socks5_address(target_host)
        request = (
            digest.encode("ascii")
            + b"\r\n"
            + bytes([0x01])
            + struct.pack("!H", target_port)
            + bytes([atyp])
            + addr
            + b"\r\n"
        )
        writer.write(request)
        await asyncio.wait_for(writer.drain(), timeout)

        proxy_ms, error = await _observe_session(reader, timeout)
        return ProtocolCheckOutcome(ok=error is None, proxy_ms=proxy_ms, error=error)
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


def _ss_evp_bytes_to_key(password: bytes, key_len: int) -> bytes:
    """Legacy EVP_BytesToKey(MD5) master key derivation used by SS-AEAD."""
    key = b""
    last = b""
    while len(key) < key_len:
        last = hashlib.md5(last + password).digest()
        key += last
    return key[:key_len]


def _ss_hkdf_sha1(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    """RFC 5869 HKDF built on SHA-1, as required by the SS-AEAD spec."""
    prk = hmac.new(salt, ikm, hashlib.sha1).digest()
    okm = b""
    prev = b""
    counter = 1
    while len(okm) < length:
        prev = hmac.new(prk, prev + info + bytes([counter]), hashlib.sha1).digest()
        okm += prev
        counter += 1
    return okm[:length]


def _ss_chunk_cipher(method: str, session_key: bytes) -> AESGCM | ChaCha20Poly1305:
    if method == "chacha20-ietf-poly1305":
        return ChaCha20Poly1305(session_key)
    return AESGCM(session_key)


def _ss_encrypt_chunk(cipher: AESGCM | ChaCha20Poly1305, nonce_counter: int, data: bytes) -> bytes:
    """Encrypt one SS-AEAD TCP chunk with its big-endian 96-bit nonce."""
    nonce = nonce_counter.to_bytes(12, "big")
    return cipher.encrypt(nonce, data, b"")


def _ss_decrypt_chunk(
    cipher: AESGCM | ChaCha20Poly1305, nonce_counter: int, data_plus_tag: bytes
) -> bytes:
    """Decrypt one SS-AEAD TCP chunk; raises on authentication failure."""
    nonce = nonce_counter.to_bytes(12, "big")
    return cipher.decrypt(nonce, data_plus_tag, b"")


async def check_shadowsocks(
    reader: StreamReader,
    writer: StreamWriter,
    *,
    target_host: str,
    target_port: int,
    user: str | None = None,
    password: str | None = None,
    timeout: float,
    parsed: ParseResult | None = None,
) -> ProtocolCheckOutcome:
    """Perform a Shadowsocks AEAD TCP connect for supported ciphers.

    Sends a single AEAD chunk that asks the proxy to connect its own
    advertised endpoint. As with Trojan there is no success ack: a session
    the server keeps open silently is treated as accepted.
    """
    start = monotonic_ms()
    try:
        method = parsed.method if parsed is not None else None
        secret = parsed.password if parsed is not None else password
        if method is None or secret is None or method not in _SS_SUPPORTED_METHODS:
            return ProtocolCheckOutcome(
                ok=False, proxy_ms=monotonic_ms() - start, error=errors.SS_CIPHER_UNSUPPORTED
            )

        key_len = _SS_KEY_SIZES[method]
        master_key = _ss_evp_bytes_to_key(secret.encode("utf-8"), key_len)
        salt = os.urandom(key_len)
        session_key = _ss_hkdf_sha1(salt, master_key, b"ss-subkey", key_len)
        cipher = _ss_chunk_cipher(method, session_key)

        atyp, addr = _socks5_address(target_host)
        payload = bytes([atyp]) + addr + struct.pack("!H", target_port)
        length_enc = _ss_encrypt_chunk(cipher, 0, struct.pack("!H", len(payload)))
        payload_enc = _ss_encrypt_chunk(cipher, 1, payload)

        writer.write(salt + length_enc + payload_enc)
        await asyncio.wait_for(writer.drain(), timeout)

        proxy_ms, error = await _observe_session(reader, timeout)
        return ProtocolCheckOutcome(ok=error is None, proxy_ms=proxy_ms, error=error)
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


async def _observe_session(reader: StreamReader, timeout: float) -> tuple[float, str | None]:
    """Observe a tunneled session and return ``(elapsed_ms, error_or_None)``.

    A peer that sends nothing and keeps the connection open is accepted; a
    peer that closes right after the credentialed request is treated as a
    rejection; a peer that replies is malformed.
    """
    start = monotonic_ms()
    window = min(timeout, _OBSERVATION_WINDOW)
    try:
        data = await asyncio.wait_for(reader.read(1), window)
    except TimeoutError:
        return monotonic_ms() - start, None
    if not data:
        return monotonic_ms() - start, errors.PROTOCOL_AUTH
    return monotonic_ms() - start, errors.PROTOCOL_MALFORMED
