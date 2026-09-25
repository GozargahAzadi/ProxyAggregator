"""VMess AEAD (VMess v1) wire helpers.

Implements the current VMess authenticated request/response header exactly as
v2ray-core / Xray-core / sing-box speak it. This is NOT the simplified KDF
found in most write-ups: V2Ray's KDF is a recursive ``hMacCreator`` composition
where every path element wraps the previous factory outward, and the input key
is written into the innermost ``"VMess AEAD KDF"``-keyed hash.

Correctness is anchored to the golden value in
``v2ray-core/proxy/vmess/aead/kdf_test.go``; the byte layout follows
``proxy/vmess/encoding/server.go`` and ``client.go``.
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import struct
import time
import uuid
import zlib
from dataclasses import dataclass
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KDF_SALT = b"VMess AEAD KDF"
_CONFIG_KEY_SALT = b"c48619fe-8f02-49e0-b9e9-edf763e17e21"

_SALT_AUTH_ID = b"AES Auth ID Encryption"
_SALT_LEN_KEY = b"VMess Header AEAD Key_Length"
_SALT_LEN_IV = b"VMess Header AEAD Nonce_Length"
_SALT_HDR_KEY = b"VMess Header AEAD Key"
_SALT_HDR_IV = b"VMess Header AEAD Nonce"
_SALT_RESP_LEN_KEY = b"AEAD Resp Header Len Key"
_SALT_RESP_LEN_IV = b"AEAD Resp Header Len IV"
_SALT_RESP_KEY = b"AEAD Resp Header Key"
_SALT_RESP_IV = b"AEAD Resp Header IV"

_SECURITY_AES128_GCM = 0x03
_COMMAND_TCP = 0x01
_VERSION = 0x01

_ATYP_IPV4 = 0x01
_ATYP_DOMAIN = 0x02
_ATYP_IPV6 = 0x03


class _HashFactory(Protocol):
    """Minimal Go ``hash.Hash``-style factory used by the recursive KDF."""

    def new(self) -> _Hash: ...

    def size(self) -> int: ...

    def blocksize(self) -> int: ...

    def sum(self, data: bytes) -> bytes: ...


class _Hash:
    __slots__ = ("buf", "f")

    def __init__(self, f: _HashFactory) -> None:
        self.f = f
        self.buf = b""

    def write(self, p: bytes) -> None:
        self.buf += p

    def size(self) -> int:
        return self.f.size()

    def block_size(self) -> int:
        return self.f.blocksize()

    def sum(self, inb: bytes = b"") -> bytes:
        return inb + self.f.sum(self.buf)


class _SHA256Factory:
    def new(self) -> _Hash:
        return _Hash(self)

    def size(self) -> int:
        return 32

    def blocksize(self) -> int:
        return 64

    def sum(self, data: bytes) -> bytes:
        return hashlib.sha256(data).digest()


class _HMACHash:
    """Lazy Go-style HMAC whose base hash may itself be an HMAC."""

    __slots__ = ("done", "f", "inner", "key", "outer")

    def __init__(self, f: _HMACFactory, key: bytes) -> None:
        self.f = f
        self.key = key
        self.inner: _Hash | None = None
        self.outer: _Hash | None = None
        self.done = False

    def _init(self) -> None:
        if self.done:
            return
        self.done = True
        inner, outer = self.f.new(), self.f.new()
        key = self.key
        if len(key) > inner.size():
            inner.write(key)
            key = inner.sum()
        bs = self.f.blocksize()
        key = key.ljust(bs, b"\x00")
        inner.write(bytes(b ^ 0x36 for b in key))
        outer.write(bytes(b ^ 0x5C for b in key))
        self.inner, self.outer = inner, outer

    def write(self, p: bytes) -> None:
        self._init()
        assert self.inner is not None
        self.inner.write(p)

    def size(self) -> int:
        return 32

    def block_size(self) -> int:
        return self.f.blocksize()

    def sum(self, inb: bytes = b"") -> bytes:
        self._init()
        assert self.inner is not None and self.outer is not None
        self.outer.write(self.inner.sum())
        return self.outer.sum(inb)


class _HMACFactory:
    __slots__ = ("f", "key")

    def __init__(self, f: _HMACFactory | _SHA256Factory, key: bytes) -> None:
        self.f = f
        self.key = key

    def new(self) -> _HMACHash:
        return _HMACHash(self.f, self.key)

    def size(self) -> int:
        return 32

    def blocksize(self) -> int:
        return self.f.blocksize()


def _kdf(key: bytes, *path: bytes) -> bytes:
    """V2Ray KDF: recursive HMAC composition, exact to the Go golden test."""
    factory: _HMACFactory | _SHA256Factory = _SHA256Factory()
    factory = _HMACFactory(factory, _KDF_SALT)
    for p in path:
        factory = _HMACFactory(factory, p)
    h = factory.new()
    h.write(key)
    return h.sum()


def _kdf16(key: bytes, *path: bytes) -> bytes:
    return _kdf(key, *path)[:16]


def fnv1a32(data: bytes) -> int:
    """FNV-1a 32-bit hash used as the record integrity trailer."""
    h = 0x811C9DC5
    for byte in data:
        h ^= byte
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def cmd_key(uuid_val: bytes | str) -> bytes:
    """The MD5-based command key for a VMess UUID (raw bytes or UUID string)."""
    uuid_bytes = uuid_val if isinstance(uuid_val, bytes) else uuid.UUID(uuid_val).bytes
    return hashlib.md5(uuid_bytes + _CONFIG_KEY_SALT).digest()


def _aes_ecb_encrypt(key: bytes, plaintext: bytes) -> bytes:
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return encryptor.update(plaintext) + encryptor.finalize()


def create_auth_id(
    cmd_key: bytes,
    *,
    timestamp: int | None = None,
    rand4: bytes | None = None,
) -> bytes:
    """Produce the 16-byte AEAD authID for the given command key."""
    ts = int(time.time()) if timestamp is None else timestamp
    r4 = os.urandom(4) if rand4 is None else rand4
    pre = struct.pack(">q", ts) + r4
    plain = pre + struct.pack(">I", zlib.crc32(pre) & 0xFFFFFFFF)
    return _aes_ecb_encrypt(_kdf16(cmd_key, _SALT_AUTH_ID), plain)


def _vmess_address(target_host: str) -> tuple[int, bytes]:
    """Encode the destination address with the VMess ATYP layout."""
    try:
        addr = ipaddress.ip_address(target_host)
    except ValueError:
        host_bytes = target_host.encode("idna")
        return _ATYP_DOMAIN, bytes([len(host_bytes)]) + host_bytes
    if addr.version == 4:
        return _ATYP_IPV4, addr.packed
    return _ATYP_IPV6, addr.packed


def _build_command_block(
    *,
    body_key: bytes,
    body_iv: bytes,
    v: int,
    target_host: str,
    target_port: int,
) -> bytes:
    atyp, addr = _vmess_address(target_host)
    record = (
        bytes([_VERSION])
        + body_iv
        + body_key
        + bytes([v])
        + b"\x00"  # option: no chunking
        + bytes([_SECURITY_AES128_GCM])  # (padding_len << 4) | security, padding 0
        + b"\x00"  # reserved
        + bytes([_COMMAND_TCP])
        + struct.pack("!H", target_port)
        + bytes([atyp])
        + addr
    )
    return record + struct.pack(">I", fnv1a32(record))


@dataclass(frozen=True)
class SealedRequest:
    """A fully assembled VMess AEAD request plus the keys needed to parse the
    server's response."""

    stream: bytes
    body_key: bytes
    body_iv: bytes
    v: int


def seal_request(
    uuid_bytes: bytes,
    target_host: str,
    target_port: int,
    *,
    timestamp: int | None = None,
    rand4: bytes | None = None,
    conn_nonce: bytes | None = None,
    body_key: bytes | None = None,
    body_iv: bytes | None = None,
    v: int | None = None,
) -> SealedRequest:
    """Seal a VMess v1 request header and return it plus its session keys.

    The returned :data:`SealedRequest.stream` is written verbatim to the
    wire (optionally inside a WebSocket binary frame). ``body_key``/``body_iv``
    identify this session so the caller can decrypt the server's response.
    """
    key = cmd_key(uuid_bytes)
    if body_key is None:
        body_key = os.urandom(16)
    if body_iv is None:
        body_iv = os.urandom(16)
    response_header = os.urandom(1)[0] if v is None else v
    auth_id = create_auth_id(key, timestamp=timestamp, rand4=rand4)
    nonce = os.urandom(8) if conn_nonce is None else conn_nonce

    record = _build_command_block(
        body_key=body_key,
        body_iv=body_iv,
        v=response_header,
        target_host=target_host,
        target_port=target_port,
    )
    length_key = _kdf16(key, _SALT_LEN_KEY, auth_id, nonce)
    length_nonce = _kdf(key, _SALT_LEN_IV, auth_id, nonce)[:12]
    header_key = _kdf16(key, _SALT_HDR_KEY, auth_id, nonce)
    header_nonce = _kdf(key, _SALT_HDR_IV, auth_id, nonce)[:12]

    length_block = AESGCM(length_key).encrypt(length_nonce, struct.pack("!H", len(record)), auth_id)
    header_block = AESGCM(header_key).encrypt(header_nonce, record, auth_id)

    stream = auth_id + length_block + nonce + header_block
    return SealedRequest(stream=stream, body_key=body_key, body_iv=body_iv, v=response_header)


def open_response(body_key: bytes, body_iv: bytes, v: int, data: bytes) -> bytes:
    """Decrypt and validate the 4-byte VMess response header.

    ``data`` is the raw response read from the wire (18-byte length block
    followed by ``n + 16`` bytes of sealed payload). Returns the plaintext
    ``[V, option, 0x00, 0x00]`` header; raises ``ValueError`` when the
    response is not authentic or does not echo ``v``.
    """
    resp_body_key = hashlib.sha256(body_key).digest()[:16]
    resp_body_iv = hashlib.sha256(body_iv).digest()[:16]

    length_key = _kdf16(resp_body_key, _SALT_RESP_LEN_KEY)
    length_nonce = _kdf(resp_body_iv, _SALT_RESP_LEN_IV)[:12]
    payload_key = _kdf16(resp_body_key, _SALT_RESP_KEY)
    payload_nonce = _kdf(resp_body_iv, _SALT_RESP_IV)[:12]

    try:
        n = struct.unpack(">H", AESGCM(length_key).decrypt(length_nonce, data[:18], None))[0]
        if n < 1 or n + 16 > len(data):
            raise ValueError("response length out of range")
        header = AESGCM(payload_key).decrypt(payload_nonce, data[18 : 18 + n + 16], None)
    except InvalidTag as exc:
        raise ValueError("inauthentic vmess response") from exc
    if not header or header[0] != v:
        raise ValueError("vmess response version mismatch")
    return header
