"""Phase 6 tests: health check models, target policy, TCP/TLS primitives,
protocol checkers (HTTP CONNECT, SOCKS5, SOCKS4/4a), multi-IP runner,
concurrency, latency, sanitized errors, and DB persistence.

All network scenarios run against local, deterministic loopback servers.
No public proxies or external services are contacted. Loopback is permitted
only through the injected permissive test policy.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import ssl
import struct
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from proxyaggregator.config.settings import Settings
from proxyaggregator.db.base import Base
from proxyaggregator.db.crud import (
    create_proxy_config,
    get_health_checks_for_config,
    get_proxy_config,
    record_health_result,
)
from proxyaggregator.geoip.models import EnrichmentResult
from proxyaggregator.health import errors
from proxyaggregator.health import vmess as vmess_mod
from proxyaggregator.health.checks import CheckError, check_tcp, upgrade_tls
from proxyaggregator.health.models import (
    CheckStage,
    HealthCheckResult,
    HealthStatus,
)
from proxyaggregator.health.policy import TargetPolicy
from proxyaggregator.health.protocols import (
    _ss_chunk_cipher,
    _ss_decrypt_chunk,
    _ss_encrypt_chunk,
    _ss_evp_bytes_to_key,
    _ss_hkdf_sha1,
    check_http_connect,
    check_socks4,
    check_socks5,
    check_trojan,
    transport_gate,
)
from proxyaggregator.health.runner import (
    HealthEntry,
    HealthRunner,
    _Attempt,
    _select_best,
    build_health_runner,
    protocol_uses_tls,
)
from proxyaggregator.parsers.base import ParseResult
from proxyaggregator.parsers.vless import VlessParser

# ---------------------------------------------------------------------------
# Embedded TLS credentials (self-signed, test-only)
# ---------------------------------------------------------------------------

GOOD_CERT = """-----BEGIN CERTIFICATE-----
MIIDJTCCAg2gAwIBAgIUDdyGakCydCLtfr2YoNWbyX8OEGcwDQYJKoZIhvcNAQEL
BQAwFDESMBAGA1UEAwwJbG9jYWxob3N0MB4XDTI2MDkyMjE0MDYyMFoXDTM2MDkx
OTE0MDYyMFowFDESMBAGA1UEAwwJbG9jYWxob3N0MIIBIjANBgkqhkiG9w0BAQEF
AAOCAQ8AMIIBCgKCAQEAo7iOVqwxS7MT8UaYS4VaXccaRXAt/2HCTzygoaegX3Tn
ufavnlUMFXYm/zrg2g0+EgsWWusDG+B94qpyTaM+i6KzgyKAhG6vE8b7741KzDkH
+rq4RoHUoKZPpQ4av0IvyaSLy8CvRdDuUiGRrMYX9PR5R/SsuChtFblHE/ihQugF
OjAYm7DRBxDIiwOi+YPB1GrYeHBEhS2sS8G79+7qV/7IjaxMlT01WrgyGeUDWyBN
YLeob8NNIjcjfWVCPalfZoIrefQH3O/jifXhHGnDq5wTyaxesM8tIIZh91fMJnnT
FYrmRfxdscn+CN7IOMuUFVmKva/j5p7mSRUs487olQIDAQABo28wbTAdBgNVHQ4E
FgQUujdOISA3yIK6aGA/Rx5YYwMGdiswHwYDVR0jBBgwFoAUujdOISA3yIK6aGA/
Rx5YYwMGdiswDwYDVR0TAQH/BAUwAwEB/zAaBgNVHREEEzARgglsb2NhbGhvc3SH
BH8AAAEwDQYJKoZIhvcNAQELBQADggEBAHmDPu50z4EjGNXcghmGAAJRZv5+keHq
bI04GCLNTnJRQIqTMD5sxKXXDGAOSiA41k2J63jegtvhGrcIq4V9J1SkyEUGjawt
nNHW1ydp+oZ1mv4/8Sb0rchdTIeC3+NuH2XXUfz/iCKSmcMYK/DaK/7qFZ+Kl8cP
QS3dz5UEnSQql/peX9E4ZbtUjkJV9cUdilcawKiVTNJGbiKmVZ3KzqLS6Qgma+IB
1QCddr00Js9MgBh6okIeHuliLjX3UgSpRnze0F4V8XbDnO9w5V42Z3Xk5wQ1lfv1
Gd86kKEb7uU9MsvN7Kqmj+yVhJXlG05XsmllTEHqyHtgo/kU5bplqaU=
-----END CERTIFICATE-----
"""

GOOD_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCjuI5WrDFLsxPx
RphLhVpdxxpFcC3/YcJPPKChp6BfdOe59q+eVQwVdib/OuDaDT4SCxZa6wMb4H3i
qnJNoz6LorODIoCEbq8TxvvvjUrMOQf6urhGgdSgpk+lDhq/Qi/JpIvLwK9F0O5S
IZGsxhf09HlH9Ky4KG0VuUcT+KFC6AU6MBibsNEHEMiLA6L5g8HUath4cESFLaxL
wbv37upX/siNrEyVPTVauDIZ5QNbIE1gt6hvw00iNyN9ZUI9qV9mgit59Afc7+OJ
9eEcacOrnBPJrF6wzy0ghmH3V8wmedMViuZF/F2xyf4I3sg4y5QVWYq9r+PmnuZJ
FSzjzuiVAgMBAAECggEAIdav6L8fUzeYrBo8uQM/ebmAtxBoGWwxtqHfy3mzfndR
u9B+XNnULQ1mIwOe3MK27RDIlpMTaewc6L/07xIKB99hff2gFX8xBYPvp4QLDSnO
eeak1sHX2jp1pLZFFfnOmb0+Pac+Ms5rq6MPkmfBJNpwxMwP9OI6Ja7NP5X4crTg
TkOIhU4S3Olf+nRfQoHXAh9UFmhsXSHnmbAwMgVtzWH1PueUwsk0FAmOypbHqX+y
BmmoK3QuKzV/NxVrP78Xa8jvGxQvLy4L2eDgIZ3LBoZnm0yg/9rbqFjRpIgqzPqN
8Mn0QITxUV5kqQmLPs84/GBgsMkjam9RAQujvz29YwKBgQDTzmPD8jb7ZW16W10h
7o4rUU7uZlUZmCJCns6Is4ZZfoBH8QF3/nBkOptBot5wKbQt6HZvqx3ARZvgDiEm
+h0o2uf4zJ2D0Vczinf2nQpt30pzg88UBnS+aI5H1zW36N187N171M/uzIXz6sSl
mces5PW+qp/jZDOteuSGiYHfywKBgQDF4bHgNTJHWTr280n6if0luNe9n+g4Ngm1
HDkyJfDERy45r4XI5JcR6Fa3tSpFXFEiYzw/61/FlwkA4RzYsCVZxDVYFoQuT7R8
26eR3p3ewU1JRCsh0KLrnrhdTkd+Sof0iabKc2s9D9BAq+/thsSh2ILFlFieXTrq
oZgxgDaNHwKBgF0WUSx2EIoOer4S12ypTpxlIL6QBQi5nx0OdJEJ7Zr5iOGVX2Lg
VX8HbuK69O3wtjqS9zJ+zxWIwkgHjbR2qkghZWAodXXQlHWXfr/JJyNAxpTcMi+H
4tkoVJfoUrigRG+6HmFlF3nJM3oPDRwG6QXonsSMcrbafAfbggJK/uRfAoGBAKV0
15RPJqE93O3L81mHs6Gs8sddQ4BsvqUu2iwySST1F5OoTcbyS9bvXELzOksQq86D
B0ey+Ttv1Fll4QbWEgUC6E+lVBSdFJ8p0u1HJN2y53qRgzcdCnzVE/cAkwroKtGv
n0S8STifVlQc79q9ywBA1ud56LdR4Qd64pTRTculAoGACnBx3F6R335wwyml0dHI
FOZEP5UNso16hqiz8OBZX9u7VzyIuBhNL5488Q1ReqkJaLPm80Uz6gv2SbWxVyQ0
t1NDXXmx3AqaDtke1vNIft8DIuJRlpG37R6vD1W4PD8kYOzuh0YOcFPB0elbcdQK
2D6+1+aiXhr/kYk1l71qs5Q=
-----END PRIVATE KEY-----
"""

BAD_CERT = """-----BEGIN CERTIFICATE-----
MIIDNzCCAh+gAwIBAgIUZHWxialz2G2WSTdRP5jTa9z6NEQwDQYJKoZIhvcNAQEL
BQAwHDEaMBgGA1UEAwwRdW5yZWxhdGVkLmV4YW1wbGUwHhcNMjYwOTIyMTQwNjIw
WhcNMzYwOTE5MTQwNjIwWjAcMRowGAYDVQQDDBF1bnJlbGF0ZWQuZXhhbXBsZTCC
ASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBANkjIrlJ5086ElhxCwHCbr8t
D7xzZvni5dtK5uxbltanyvoQjMOxkH8DpxPETaDa1ahvA4PdU2w8vlF4mv61416d
T2WlTc3yCINUT+oLKy43N1NixYAdfb3ss7rRwBJLdNYKYjWmqCS/x1CGcs70fnsN
VSTz/shohyzGb95zBe5+dvWGtkzonLeAfFZKu/1JA6ORD8WC1yHdm4EIle6+sCcV
/eAg/mFTFmDYNeUVgJOIJg7hjo0ekPeIMeI7VF1DVXrhwe3RsoMv+ltJwk/JJKHq
jyrnah8ZKbQz9lfBnCTYZ3s+oDueM0ivVzDZMb+rt1CXFF/akHSi/wv7j/JaPV0C
AwEAAaNxMG8wHQYDVR0OBBYEFGllSMYYmwF065oUH0dmCTkZ0L7bMB8GA1UdIwQY
MBaAFGllSMYYmwF065oUH0dmCTkZ0L7bMA8GA1UdEwEB/wQFMAMBAf8wHAYDVR0R
BBUwE4IRdW5yZWxhdGVkLmV4YW1wbGUwDQYJKoZIhvcNAQELBQADggEBABe3Oll8
K0dJMyvz96Aiqc1lC7gYQDLYb5GU/aAa8IM6pDoS7N/ikZTCu7HTR4JdNKpPUq4L
PqCP7ifBoJ1rNwFAv5pAXpFhry0xvur9GYPZIgvx99uQLhCTthntxzzIJEw5K0Xr
8l1eImKVKKKiAg4c0yKKv3XlXJRTLvlh0zWz8PUt34rvTA3o7WvDfgmA/JTrO/51
wq4Y3PBE2xTVWI8MAeBdOMGQhR08o3pqed2hlLrKheqN4VWmc2i/65kwqrYcBrlH
mUX2RN9YSSGkXuV14DrlR9VP1v3/Y22xR+btblAYH1BEWwzT9AKaoCwKsuIZuJTM
229/Gn1R4DrvR9w=
-----END CERTIFICATE-----
"""

BAD_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDZIyK5SedPOhJY
cQsBwm6/LQ+8c2b54uXbSubsW5bWp8r6EIzDsZB/A6cTxE2g2tWobwOD3VNsPL5R
eJr+teNenU9lpU3N8giDVE/qCysuNzdTYsWAHX297LO60cASS3TWCmI1pqgkv8dQ
hnLO9H57DVUk8/7IaIcsxm/ecwXufnb1hrZM6Jy3gHxWSrv9SQOjkQ/Fgtch3ZuB
CJXuvrAnFf3gIP5hUxZg2DXlFYCTiCYO4Y6NHpD3iDHiO1RdQ1V64cHt0bKDL/pb
ScJPySSh6o8q52ofGSm0M/ZXwZwk2Gd7PqA7njNIr1cw2TG/q7dQlxRf2pB0ov8L
+4/yWj1dAgMBAAECggEACbEt5rUvFa28mn8DpA+QnIiMSCsJU/eC4nMPwLAYsqDC
iIvxkV1p9KMHzUDFy3uV7hLaeZ0I94iOLc1jQCHqGFPCpgGNagQDyXaB3kTWWuJz
EUFHTVmQcchQs3LGW7d+uEkckVMZjhGTYEhIDdQ2MXod+VLJmU3biGE18093p2mf
mkTDdngrWzEVPEtXakQe7Y7gMAgdAj8hrXGUa/hYeRSqHgeDkuQJ/LCqylOZ9Y4S
NVn7UjA/WLnESbH4hzRNx2yuEuI4aS20UJHg10w9aAtJnXGQhgDdF2mMN4UqZH9a
6Ua6HgDaZ+4NuILbxB4Priz55LF/97FJ5MafIng/8QKBgQD7Ur4/EvRvdjDSZdbo
epeASH3tplxqv4idWoKOPAg5Qr5DwV+t0XCUSoYSfRmCgEkkvzjY51rx+3jxA3zE
g1SJnzN4uHI3SucY0MmhTblfxFikfWkUQ918pUOW0l4hb+OtWWUyvw76bRvxh1Jt
22W8KNniwaFcSjKJSUG8scJG+QKBgQDdLYl0PUSJg5tt/sn7ORVmeEKCLLSnWnzD
2hXQ4n0WaEFt1gwPCoYG6TQWmEz4DKUgZMJV6VyJgK72W0uuryCwR85TDE3N5tOq
4g6oz9cEUDqwHJee3usjiOSOcHLK+fkKadDwhmPDO9oIXks5SG3Mpd2er/r1qkOD
zP1gBofOhQKBgQCg0UGLesWOzUJQX3o1KLzpCXoLJ/jbFdSFW/VOrntUqLC3CnX+
85XmTgmcqxA3wX8MVJA7u08mqJOrJWAhHyhpJ8X36Y6scvGNn4xl+yYzcaCHIPis
TwDbUaT+TX6ORtqZgiqPXlJnTIok80J7qXhf/oPt5ZkrRQ8xaf72j4iRgQKBgBe/
tPurPHm7jOvxqMR166tWDGYn4Ln7iFwLRb5pI19NkID3s9HFooCJd9NZRSJ5UR26
U/efmBUXoTHIucam/U6QV0Iplw0d1OqLXWGY95B6AOM6HrmrW/ozz77PqjPLRYdt
t0asV3f2LEIrxc3/zfJkePh6Eutf/eHgF/DAosJ1AoGBAIVziTvsViP3QHTUb00S
tqtKjWFN0wrtsLM/35NV9jjgre8NQZWvq0butDrC4IeWDcBeDM5ophgFZytMSmqO
Z9KmpLW/JdEP6v7opVLzWsChCieLtk/Q/XK4lkPgYTVgXgxUHQfdSZ8ltWJtY+TC
2Z0hXS9nIrnuAmhrGJV1+Hwa
-----END PRIVATE KEY-----
"""

ALLOWED_USER = "proxyuser"
ALLOWED_PASS = "proxypass"


# ---------------------------------------------------------------------------
# Local test servers
# ---------------------------------------------------------------------------


async def _read_http_request(reader) -> bytes:
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = await reader.read(1024)
        if not chunk:
            break
        buf += chunk
    return buf


async def _read_until_null(reader) -> bytes:
    out = bytearray()
    while True:
        b = await reader.readexactly(1)
        if b == b"\x00":
            return bytes(out)
        out += b


async def _tcp_accept_handler(reader, writer) -> None:
    try:
        await reader.read(1024)
    finally:
        writer.close()


def _http_handler(status: int = 200):
    async def handler(reader, writer) -> None:
        try:
            await _read_http_request(reader)
            if status == 200:
                writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            elif status == 407:
                writer.write(
                    b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                    b'Proxy-Authenticate: Basic realm="proxy"\r\n\r\n'
                )
            else:
                writer.write(f"HTTP/1.1 {status} Rejected\r\n\r\n".encode("ascii"))
            await writer.drain()
        finally:
            writer.close()

    return handler


async def _http_malformed_handler(reader, writer) -> None:
    try:
        await _read_http_request(reader)
        writer.write(b"NotAToken garbage\r\nConnection: nonsense\r\n\r\n")
        await writer.drain()
    finally:
        writer.close()


def _socks5_handler(
    require_auth: bool = False,
    reject_auth: bool = False,
    reject_connect: bool = False,
):
    async def handler(reader, writer) -> None:
        try:
            greeting = await reader.readexactly(2)
            methods = await reader.readexactly(greeting[1])
            if require_auth:
                if 0x02 not in methods:
                    writer.write(b"\x05\xff")
                    await writer.drain()
                    writer.close()
                    return
                writer.write(b"\x05\x02")
                await writer.drain()
                subneg = await reader.readexactly(2)
                uname = await reader.readexactly(subneg[1])
                plen = (await reader.readexactly(1))[0]
                pwd = await reader.readexactly(plen)
                if reject_auth or uname != ALLOWED_USER.encode() or pwd != ALLOWED_PASS.encode():
                    writer.write(b"\x01\x01")
                    await writer.drain()
                    writer.close()
                    return
                writer.write(b"\x01\x00")
                await writer.drain()
            else:
                writer.write(b"\x05\x00")
                await writer.drain()

            conn = await reader.readexactly(4)
            atyp = conn[3]
            if atyp == 0x01:
                await reader.readexactly(4)
            elif atyp == 0x04:
                await reader.readexactly(16)
            else:
                dom_len = (await reader.readexactly(1))[0]
                await reader.readexactly(dom_len)
            await reader.readexactly(2)

            rep = 0x05 if reject_connect else 0x00
            writer.write(bytes([0x05, rep, 0x00, 0x01]) + b"\x00\x00\x00\x00" + b"\x00\x00")
            await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()

    return handler


async def _socks4_handler(reader, writer) -> None:
    try:
        head = await reader.readexactly(8)
        await _read_until_null(reader)
        if head[4:7] == b"\x00\x00\x00" and head[7] != 0:
            await _read_until_null(reader)
        writer.write(b"\x00\x5a" + head[2:4] + head[4:8])
        await writer.drain()
    except asyncio.IncompleteReadError:
        pass
    finally:
        writer.close()


async def _silent_handler(reader, writer) -> None:
    try:
        await reader.readexactly(1)
        await asyncio.sleep(2.0)
    except asyncio.IncompleteReadError:
        pass
    finally:
        writer.close()


async def _read_vless_request(reader) -> bytes:
    await reader.readexactly(1)  # version
    uuid_bytes = await reader.readexactly(16)
    addons_len = (await reader.readexactly(1))[0]
    if addons_len:
        await reader.readexactly(addons_len)
    await reader.readexactly(1)  # command
    await reader.readexactly(2)  # port
    atyp = (await reader.readexactly(1))[0]
    if atyp == 0x02:
        n = (await reader.readexactly(1))[0]
        await reader.readexactly(n)
    elif atyp == 0x04:
        await reader.readexactly(16)
    else:
        await reader.readexactly(4)
    return uuid_bytes


def _vless_handler(
    expected_uuid: bytes,
    reply: bytes = b"\x00\x00",
    silent: bool = False,
):
    async def handler(reader, writer) -> None:
        try:
            uuid_bytes = await _read_vless_request(reader)
            if uuid_bytes != expected_uuid:
                return
            if silent:
                await reader.read()
                return
            writer.write(reply)
            await writer.drain()
            await reader.read()
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()

    return handler


async def _read_trojan_request(reader) -> bytes:
    digest = await reader.readexactly(56)
    await reader.readexactly(2)  # CRLF
    await reader.readexactly(1)  # command
    atyp = (await reader.readexactly(1))[0]
    if atyp == 0x03:
        n = (await reader.readexactly(1))[0]
        await reader.readexactly(n)
    elif atyp == 0x04:
        await reader.readexactly(16)
    else:
        await reader.readexactly(4)
    await reader.readexactly(2)  # DST.PORT
    await reader.readexactly(2)  # trailing CRLF
    return digest


def _trojan_handler(expected_password: str, reply: bytes | None = None):
    async def handler(reader, writer) -> None:
        try:
            digest = await _read_trojan_request(reader)
            key = hashlib.sha224(expected_password.encode("utf-8")).hexdigest().encode("ascii")
            if digest != key:
                return
            if reply is not None:
                writer.write(reply)
                await writer.drain()
                return
            await reader.read()
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()

    return handler


def _ss_password_handler(method: str, password: str):
    key_len = {"aes-128-gcm": 16, "aes-256-gcm": 32, "chacha20-ietf-poly1305": 32}[method]

    async def handler(reader, writer) -> None:
        try:
            salt = await reader.readexactly(key_len)
            master = _ss_evp_bytes_to_key(password.encode("utf-8"), key_len)
            session = _ss_hkdf_sha1(salt, master, b"ss-subkey", key_len)
            cipher = _ss_chunk_cipher(method, session)
            length = int.from_bytes(
                _ss_decrypt_chunk(cipher, 0, await reader.readexactly(2 + 16)), "big"
            )
            _ss_decrypt_chunk(cipher, 1, await reader.readexactly(length + 16))
            await reader.read()
        except (asyncio.IncompleteReadError, ValueError, InvalidTag):
            return
        finally:
            writer.close()

    return handler


_WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _ws_accept(client_key: bytes) -> bytes:
    """RFC 6455 Sec-WebSocket-Accept for a client key."""
    return base64.b64encode(hashlib.sha1(client_key + _WS_GUID).digest())


async def _ws_read_handshake_request(reader) -> tuple[str, bytes]:
    """Read the client's WS upgrade request, returning (path, client key)."""
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = await reader.read(1)
        if not chunk:
            raise asyncio.IncompleteReadError(buf, b"")
        buf += chunk
    path = buf.split(b" ", 2)[1].decode("ascii") if len(buf.split(b" ", 2)) > 1 else "/"
    client_key = b""
    for line in buf.split(b"\r\n")[1:]:
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"sec-websocket-key":
            client_key = value.strip()
    return path, client_key


async def _ws_answer_101(writer, client_key: bytes) -> None:
    """Reply with a valid 101 Switching Protocols response."""
    writer.write(
        b"HTTP/1.1 101 Switching Protocols\r\n"
        b"Upgrade: websocket\r\n"
        b"Connection: Upgrade\r\n"
        b"Sec-WebSocket-Accept: " + _ws_accept(client_key) + b"\r\n\r\n"
    )
    await writer.drain()


async def _ws_send_frame(writer, payload: bytes, opcode: int = 0x2) -> None:
    """Send one unmasked server WS frame (RFC 6455)."""
    header = bytearray([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header += struct.pack("!H", length)
    else:
        header.append(127)
        header += struct.pack("!Q", length)
    writer.write(bytes(header) + payload)
    await writer.drain()


async def _ws_read_message(reader) -> bytes:
    """Read one complete masked client WS message (binary or text)."""
    first = True
    message = bytearray()
    while True:
        head = await reader.readexactly(2)
        fin = bool(head[0] & 0x80)
        opcode = head[0] & 0x0F
        length = head[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", await reader.readexactly(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", await reader.readexactly(8))[0]
        mask = await reader.readexactly(4)
        payload = await reader.readexactly(length)
        payload = bytes(b ^ mask[index & 3] for index, b in enumerate(payload))
        if opcode in (0x9, 0xA):
            continue
        if first:
            if opcode not in (0x1, 0x2):
                raise asyncio.IncompleteReadError(b"", b"")
            first = False
        elif opcode != 0x0:
            raise asyncio.IncompleteReadError(b"", b"")
        message += payload
        if fin:
            return bytes(message)


async def _ws_accept_request(reader, writer) -> None:
    """Perform the server side of a WS upgrade handshake."""
    _, client_key = await _ws_read_handshake_request(reader)
    await _ws_answer_101(writer, client_key)


def _vless_ws_handler(
    expected_uuid: bytes,
    reply: bytes = b"\x00\x00",
    silent: bool = False,
):
    async def handler(reader, writer) -> None:
        try:
            await _ws_accept_request(reader, writer)
            request = await _ws_read_message(reader)
            uuid_bytes = request[1:17]
            if uuid_bytes != expected_uuid:
                await _ws_send_frame(writer, b"", opcode=0x8)
                return
            if silent:
                await reader.read()
                return
            await _ws_send_frame(writer, reply)
            await reader.read()
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()

    return handler


def _trojan_ws_handler(expected_password: str, reply: bytes | None = None):
    async def handler(reader, writer) -> None:
        try:
            await _ws_accept_request(reader, writer)
            request = await _ws_read_message(reader)
            digest = request[:56]
            key = hashlib.sha224(expected_password.encode("utf-8")).hexdigest().encode("ascii")
            if digest != key:
                await _ws_send_frame(writer, b"", opcode=0x8)
                return
            if reply is not None:
                await _ws_send_frame(writer, reply)
                return
            await reader.read()
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()

    return handler


async def _read_vmess_sealed_request(reader) -> tuple[bytes, bytes, bytes]:
    """Read the AEAD-authID/lenblock/nonce/header layout the client sends."""
    auth_id = await reader.readexactly(16)
    length_block = await reader.readexactly(18)
    nonce = await reader.readexactly(8)
    return auth_id, length_block, nonce


async def _vmess_response_for(
    key: bytes, auth_id: bytes, length_block: bytes, nonce: bytes, header_block: bytes
) -> bytes:
    """Decrypt a sealed VMess request with ``key`` and build the sealed 38-byte
    response header that the v2ray inbound would return."""
    length_nonce = vmess_mod._kdf(key, vmess_mod._SALT_LEN_IV, auth_id, nonce)[:12]
    length_key = vmess_mod._kdf16(key, vmess_mod._SALT_LEN_KEY, auth_id, nonce)
    header_nonce = vmess_mod._kdf(key, vmess_mod._SALT_HDR_IV, auth_id, nonce)[:12]
    header_key = vmess_mod._kdf16(key, vmess_mod._SALT_HDR_KEY, auth_id, nonce)
    try:
        AESGCM(length_key).decrypt(length_nonce, length_block, auth_id)
        record = AESGCM(header_key).decrypt(header_nonce, header_block, auth_id)
    except InvalidTag:
        raise
    body_iv = record[1:17]
    body_key = record[17:33]
    v = record[33]
    resp_body_key = hashlib.sha256(body_key).digest()[:16]
    resp_body_iv = hashlib.sha256(body_iv).digest()[:16]
    resp_len_nonce = vmess_mod._kdf(resp_body_iv, vmess_mod._SALT_RESP_LEN_IV)[:12]
    resp_len_key = vmess_mod._kdf16(resp_body_key, vmess_mod._SALT_RESP_LEN_KEY)
    resp_hdr_nonce = vmess_mod._kdf(resp_body_iv, vmess_mod._SALT_RESP_IV)[:12]
    resp_hdr_key = vmess_mod._kdf16(resp_body_key, vmess_mod._SALT_RESP_KEY)
    resp_len_block = AESGCM(resp_len_key).encrypt(resp_len_nonce, struct.pack("!H", 4), None)
    resp_hdr_block = AESGCM(resp_hdr_key).encrypt(resp_hdr_nonce, bytes([v, 0, 0, 0]), None)
    return resp_len_block + resp_hdr_block


def _vmess_handler(expected_uuid: bytes, silent: bool = False, bogus_response: bool = False):
    async def handler(reader, writer) -> None:
        try:
            command_key = vmess_mod.cmd_key(expected_uuid)
            auth_id, length_block, nonce = await asyncio.wait_for(
                _read_vmess_sealed_request(reader), 2.0
            )
            try:
                length_nonce = vmess_mod._kdf(command_key, vmess_mod._SALT_LEN_IV, auth_id, nonce)[
                    :12
                ]
                length_key = vmess_mod._kdf16(command_key, vmess_mod._SALT_LEN_KEY, auth_id, nonce)
                n = struct.unpack(
                    "!H", AESGCM(length_key).decrypt(length_nonce, length_block, auth_id)
                )[0]
                header_block = await reader.readexactly(n + 16)
                response = await _vmess_response_for(
                    command_key, auth_id, length_block, nonce, header_block
                )
            except (asyncio.IncompleteReadError, InvalidTag, TimeoutError):
                return
            if silent:
                await reader.read()
                return
            if bogus_response:
                response = b"\xff" * 38
            writer.write(response)
            await writer.drain()
            await reader.read()
        except (asyncio.IncompleteReadError, TimeoutError):
            pass
        finally:
            writer.close()

    return handler


def _vmess_ws_handler(expected_uuid: bytes, silent: bool = False):
    async def handler(reader, writer) -> None:
        try:
            await _ws_accept_request(reader, writer)
            request = await _ws_read_message(reader)
            command_key = vmess_mod.cmd_key(expected_uuid)
            auth_id = request[:16]
            length_block = request[16:34]
            nonce = request[34:42]
            header_block = request[42:]
            try:
                response = await _vmess_response_for(
                    command_key, auth_id, length_block, nonce, header_block
                )
            except InvalidTag:
                await _ws_send_frame(writer, b"", opcode=0x8)
                return
            if silent:
                await reader.read()
                return
            await _ws_send_frame(writer, response)
            await reader.read()
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()

    return handler


async def _tls_garbage_handler(reader, writer) -> None:
    """Plaintext responder: any TLS ClientHello is answered with garbage.

    The TLS client sees a non-record first byte and raises
    ``ssl.SSLError`` -> ``errors.TLS_HANDSHAKE`` deterministically.
    """

    try:
        await reader.read(1)
        writer.write(b"GET / HTTP/1.1\r\n\r\n")
        await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionError, OSError):
        pass
    finally:
        writer.close()


class _Activity:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.current = 0
        self.max_concurrent = 0


def _counting_http_handler(activity: _Activity):
    async def handler(reader, writer) -> None:
        async with activity.lock:
            activity.current += 1
            activity.max_concurrent = max(activity.max_concurrent, activity.current)
        try:
            await _read_http_request(reader)
            await asyncio.sleep(0.2)
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
        finally:
            async with activity.lock:
                activity.current -= 1
            writer.close()

    return handler


async def _start(handler) -> tuple[str, int, asyncio.Server]:
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return "127.0.0.1", port, server


async def _start_on(handler, ip: str, port: int = 0) -> tuple[int, asyncio.Server]:
    """Start a server on a specific loopback address."""
    server = await asyncio.start_server(handler, ip, port)
    port = server.sockets[0].getsockname()[1]
    return port, server


async def _second_loopback_same_port(handler, port: int) -> tuple[str, asyncio.Server]:
    """Bind a server on a second loopback address sharing ``port``.

    The primary server is bound to ``127.0.0.1`` only, so its port is
    otherwise closed on every other address. Picking another ``127.x.y.z``
    keeps the pair deterministic on Linux loopback.
    """
    for ip in ("127.0.0.2", "127.0.0.3", "127.0.1.1"):
        try:
            server = await asyncio.start_server(handler, ip, port)
            return ip, server
        except OSError:
            continue
    raise RuntimeError("no secondary loopback address available")


async def _start_tls(handler, cert: str, key: str) -> tuple[str, int, asyncio.Server]:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=cert, keyfile=key)
    server = await asyncio.start_server(handler, "127.0.0.1", 0, ssl=ctx)
    port = server.sockets[0].getsockname()[1]
    return "127.0.0.1", port, server


def _entry(
    protocol: str = "http",
    host: str = "127.0.0.1",
    port: int = 8080,
    enrichment: EnrichmentResult | None = None,
    **kwargs,
) -> HealthEntry:
    parsed = ParseResult(
        protocol=protocol,
        host=host,
        port=port,
        raw_uri=f"{protocol}://{host}:{port}",
        **kwargs,
    )
    return HealthEntry(parsed=parsed, enrichment=enrichment)


def _runner(**overrides) -> HealthRunner:
    kwargs: dict = {
        "policy": TargetPolicy(allow_private=True),
        "timeout": 2.0,
        "concurrency": 50,
    }
    kwargs.update(overrides)
    return HealthRunner(**kwargs)


def _write_pems(tmp_path) -> dict[str, str]:
    """Persist the embedded PEM blocks and return their file paths."""
    assets: dict[str, str] = {}
    for name, content in (
        ("good.crt", GOOD_CERT),
        ("good.key", GOOD_KEY),
        ("bad.crt", BAD_CERT),
        ("bad.key", BAD_KEY),
    ):
        path = tmp_path / name
        path.write_text(content)
        assets[name] = str(path)
    return assets


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


# ===========================================================================
# RESULT MODELS
# ===========================================================================


class TestHealthResultModels:
    def test_is_alive_only_for_ok(self):
        ok = HealthCheckResult(status=HealthStatus.OK, protocol="http", host="h", port=80)
        assert ok.is_alive is True

        for status in (
            HealthStatus.UNREACHABLE,
            HealthStatus.TIMEOUT,
            HealthStatus.DNS_FAILURE,
            HealthStatus.TLS_FAILURE,
            HealthStatus.PROTOCOL_FAILURE,
            HealthStatus.UNSUPPORTED,
            HealthStatus.DECLINED,
            HealthStatus.SKIPPED,
        ):
            res = HealthCheckResult(status=status, protocol="http", host="h", port=80)
            assert res.is_alive is False

    def test_model_is_frozen(self):
        res = HealthCheckResult(status=HealthStatus.OK, protocol="http", host="h", port=80)
        with pytest.raises(ValidationError):
            res.status = HealthStatus.TIMEOUT  # type: ignore[misc]

    def test_no_credentials_fields(self):
        res = HealthCheckResult(status=HealthStatus.UNSUPPORTED, protocol="ss", host="h", port=80)
        assert not hasattr(res, "user")
        assert not hasattr(res, "password")
        assert not hasattr(res, "raw_uri")

    def test_default_stage_is_tcp(self):
        res = HealthCheckResult(status=HealthStatus.UNREACHABLE, protocol="http", host="h", port=80)
        assert res.stage == CheckStage.TCP

    def test_attempted_ips_default_empty(self):
        res = HealthCheckResult(status=HealthStatus.OK, protocol="http", host="h", port=80)
        assert res.attempted_ips == []


# ===========================================================================
# TARGET SECURITY POLICY
# ===========================================================================


class TestTargetPolicy:
    def test_private_and_loopback_blocked(self):
        policy = TargetPolicy()
        for ip in [
            "127.0.0.1",
            "127.0.0.0",
            "10.0.0.1",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.1.1",
        ]:
            assert policy.is_target_allowed(ip) is False, ip

    def test_special_ranges_blocked(self):
        policy = TargetPolicy()
        for ip in [
            "0.0.0.0",
            "169.254.169.254",
            "100.64.0.1",
            "224.0.0.1",
            "255.255.255.255",
            "240.0.0.1",
            "192.0.2.1",
            "198.51.100.1",
            "203.0.113.1",
            "198.18.0.1",
        ]:
            assert policy.is_target_allowed(ip) is False, ip

    def test_ipv6_local_blocked(self):
        policy = TargetPolicy()
        for ip in [
            "::1",
            "fe80::1",
            "fc00::1",
            "fd12:3456::1",
            "ff00::1",
        ]:
            assert policy.is_target_allowed(ip) is False, ip

    def test_public_ips_allowed(self):
        policy = TargetPolicy()
        for ip in [
            "8.8.8.8",
            "1.1.1.1",
            "93.184.216.34",
            "2001:4860:4860::8888",
            "2606:4700:4700::1111",
        ]:
            assert policy.is_target_allowed(ip) is True, ip

    def test_ipv4_mapped_ipv6_blocked(self):
        policy = TargetPolicy()
        assert policy.is_target_allowed("::ffff:192.168.1.1") is False
        assert policy.is_target_allowed("::ffff:127.0.0.1") is False
        assert policy.is_target_allowed("::ffff:8.8.8.8") is True

    def test_ipv6_special_use_blocked(self):
        policy = TargetPolicy()
        for ip in [
            "2001::1",  # Teredo
            "2001:db8::1",  # documentation
            "2002:7f00:1::",  # 6to4 embedding 127.0.0.1
            "64:ff9b::7f00:1",  # NAT64 embedding 127.0.0.1
            "64:ff9b:1::7f00:1",  # NAT64 direct/local-use
            "2001:2::1",  # benchmarking
            "2001:10::1",  # ORCHID
            "2001:20::1",  # ORCHIDv2
            "3fff::1",  # unassigned
        ]:
            assert policy.is_target_allowed(ip) is False, ip

    def test_invalid_input_blocked(self):
        policy = TargetPolicy()
        assert policy.is_target_allowed("not-an-ip") is False
        assert policy.is_target_allowed("") is False

    def test_permissive_policy_allows_loopback(self):
        policy = TargetPolicy(allow_private=True)
        assert policy.is_target_allowed("127.0.0.1") is True
        assert policy.is_target_allowed("192.168.1.1") is True
        assert policy.is_target_allowed("::1") is True

    def test_split_allowed(self):
        policy = TargetPolicy()
        allowed, rejected = policy.split_allowed(["8.8.8.8", "192.168.1.1", "1.1.1.1", "127.0.0.1"])
        assert allowed == ["8.8.8.8", "1.1.1.1"]
        assert rejected == ["192.168.1.1", "127.0.0.1"]


# ===========================================================================
# TCP / TLS PRIMITIVES
# ===========================================================================


class TestTcpPrimitive:
    async def test_tcp_connect_success(self):
        host, port, server = await _start(_tcp_accept_handler)
        try:
            _reader, writer, connect_ms = await check_tcp(host, port, timeout=1.0)
            assert connect_ms >= 0.0
            writer.close()
            await writer.wait_closed()
        finally:
            server.close()

    async def test_tcp_connect_refused(self):
        with pytest.raises(CheckError) as excinfo:
            await check_tcp("127.0.0.1", 1, timeout=1.0)
        assert excinfo.value.code == errors.CONNECTION_REFUSED


class TestTlsPrimitive:
    async def test_tls_handshake_unverified_success(self, tmp_path):
        assets = _write_pems(tmp_path)
        host, port, server = await _start_tls(
            _tcp_accept_handler, assets["good.crt"], assets["good.key"]
        )
        try:
            reader, writer, _ms = await check_tcp(host, port, timeout=2.0)
            _r2, writer2, handshake_ms, verified = await upgrade_tls(
                reader,
                writer,
                server_hostname="localhost",
                verify_cert=False,
                timeout=2.0,
            )
            assert handshake_ms >= 0.0
            assert verified is False
            writer2.close()
            await writer2.wait_closed()
        finally:
            server.close()

    async def test_tls_handshake_verified_ok(self, tmp_path):
        assets = _write_pems(tmp_path)
        host, port, server = await _start_tls(
            _tcp_accept_handler, assets["good.crt"], assets["good.key"]
        )
        try:
            reader, writer, _ms = await check_tcp(host, port, timeout=2.0)
            _r2, writer2, _h, verified = await upgrade_tls(
                reader,
                writer,
                server_hostname="localhost",
                verify_cert=True,
                ca_file=assets["good.crt"],
                timeout=2.0,
            )
            assert verified is True
            writer2.close()
            await writer2.wait_closed()
        finally:
            server.close()

    async def test_tls_verification_failure_bad_cert(self, tmp_path):
        assets = _write_pems(tmp_path)
        host, port, server = await _start_tls(
            _tcp_accept_handler, assets["bad.crt"], assets["bad.key"]
        )
        try:
            reader, writer, _ms = await check_tcp(host, port, timeout=2.0)
            with pytest.raises(CheckError) as excinfo:
                await upgrade_tls(
                    reader,
                    writer,
                    server_hostname="localhost",
                    verify_cert=True,
                    ca_file=assets["good.crt"],
                    timeout=2.0,
                )
            assert excinfo.value.code == errors.TLS_CERTIFICATE
        finally:
            server.close()


# ===========================================================================
# PROTOCOL CHECKERS
# ===========================================================================


class TestHttpConnectChecker:
    async def _check(self, status: int, user=None, password=None):
        host, port, server = await _start(_http_handler(status))
        try:
            reader, writer, _ms = await check_tcp(host, port, timeout=2.0)
            outcome = await check_http_connect(
                reader,
                writer,
                target_host="target.invalid",
                target_port=443,
                user=user,
                password=password,
                timeout=2.0,
            )
            writer.close()
            await writer.wait_closed()
            return outcome
        finally:
            server.close()

    async def test_connect_200_ok(self):
        outcome = await self._check(200)
        assert outcome.ok is True
        assert outcome.proxy_ms >= 0.0
        assert outcome.error is None

    async def test_connect_407_auth_required(self):
        outcome = await self._check(407)
        assert outcome.ok is False
        assert outcome.error == errors.HTTP_STATUS_407

    async def test_connect_403_rejected(self):
        outcome = await self._check(403)
        assert outcome.ok is False
        assert outcome.error == errors.HTTP_REJECTED

    async def test_malformed_response(self):
        host, port, server = await _start(_http_malformed_handler)
        try:
            reader, writer, _ms = await check_tcp(host, port, timeout=2.0)
            outcome = await check_http_connect(
                reader,
                writer,
                target_host="target.invalid",
                target_port=443,
                user=None,
                password=None,
                timeout=2.0,
            )
            writer.close()
            await writer.wait_closed()
            assert outcome.ok is False
            assert outcome.error == errors.HTTP_MALFORMED
        finally:
            server.close()

    async def test_silent_server_times_out(self):
        host, port, server = await _start(_silent_handler)
        try:
            reader, writer, _ms = await check_tcp(host, port, timeout=2.0)
            outcome = await check_http_connect(
                reader,
                writer,
                target_host="target.invalid",
                target_port=443,
                user=None,
                password=None,
                timeout=0.3,
            )
            writer.close()
            await writer.wait_closed()
            assert outcome.ok is False
            assert outcome.error == errors.CONNECTION_TIMEOUT
        finally:
            server.close()


class TestSocks5Checker:
    async def _check(
        self,
        require_auth=False,
        reject_auth=False,
        reject_connect=False,
        user=None,
        password=None,
        target_host="target.invalid",
    ):
        handler = _socks5_handler(
            require_auth=require_auth, reject_auth=reject_auth, reject_connect=reject_connect
        )
        host, port, server = await _start(handler)
        try:
            reader, writer, _ms = await check_tcp(host, port, timeout=2.0)
            outcome = await check_socks5(
                reader,
                writer,
                target_host=target_host,
                target_port=443,
                user=user,
                password=password,
                timeout=2.0,
            )
            writer.close()
            await writer.wait_closed()
            return outcome
        finally:
            server.close()

    async def test_no_auth_success(self):
        outcome = await self._check(target_host="127.0.0.1")
        assert outcome.ok is True
        assert outcome.error is None

    async def test_userpass_auth_success(self):
        outcome = await self._check(
            require_auth=True,
            user=ALLOWED_USER,
            password=ALLOWED_PASS,
            target_host="127.0.0.1",
        )
        assert outcome.ok is True

    async def test_auth_failure(self):
        outcome = await self._check(
            require_auth=True,
            reject_auth=True,
            user=ALLOWED_USER,
            password="wrong",
            target_host="127.0.0.1",
        )
        assert outcome.ok is False
        assert outcome.error == errors.SOCKS_AUTH_FAILURE

    async def test_connect_rejected(self):
        outcome = await self._check(reject_connect=True, target_host="127.0.0.1")
        assert outcome.ok is False
        assert outcome.error == errors.SOCKS_REJECTED

    async def test_domain_target(self):
        outcome = await self._check(target_host="proxy.example.com")
        assert outcome.ok is True

    async def test_ipv6_target(self):
        outcome = await self._check(target_host="2001:db8::1")
        assert outcome.ok is True


class TestSocks4Checker:
    async def _check(self, target_host: str):
        host, port, server = await _start(_socks4_handler)
        try:
            reader, writer, _ms = await check_tcp(host, port, timeout=2.0)
            outcome = await check_socks4(
                reader,
                writer,
                target_host=target_host,
                target_port=1080,
                user="tester",
                timeout=2.0,
            )
            writer.close()
            await writer.wait_closed()
            return outcome
        finally:
            server.close()

    async def test_socks4_ipv4_target(self):
        outcome = await self._check("127.0.0.1")
        assert outcome.ok is True
        assert outcome.error is None

    async def test_socks4a_domain_target(self):
        outcome = await self._check("proxy.example.com")
        assert outcome.ok is True


# ===========================================================================
# FULL RUNNER
# ===========================================================================


class TestHealthRunner:
    async def test_http_proxy_ok_sets_alive(self):
        host, port, server = await _start(_http_handler(200))
        try:
            runner = _runner()
            result = await runner.check(_entry(protocol="http", host=host, port=port))
            assert result.status == HealthStatus.OK
            assert result.is_alive is True
            assert result.protocol_checked is True
            assert result.checked_ip == "127.0.0.1"
            assert result.error is None
            assert result.connect_ms >= 0.0
            assert result.proxy_ms >= 0.0
            assert result.latency_ms == pytest.approx(result.connect_ms + result.proxy_ms, abs=0.01)
            assert result.tls_used is False
        finally:
            server.close()

    async def test_http_proxy_407_protocol_failure(self):
        host, port, server = await _start(_http_handler(407))
        try:
            runner = _runner()
            result = await runner.check(_entry(protocol="http", host=host, port=port))
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.is_alive is False
            assert result.protocol_checked is True
            assert result.error == errors.HTTP_STATUS_407
        finally:
            server.close()

    async def test_ss_dial_rejected_by_closed_tcp_is_protocol_failure(self):
        host, port, server = await _start(_tcp_accept_handler)
        try:
            runner = _runner()
            result = await runner.check(
                _entry(
                    protocol="ss",
                    host=host,
                    port=port,
                    method="aes-256-gcm",
                    password="pw",
                )
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.is_alive is False
            assert result.protocol_checked is True
            assert result.checked_ip == "127.0.0.1"
            assert result.error == errors.PROTOCOL_AUTH
            assert result.connect_ms >= 0.0
        finally:
            server.close()

    async def test_vless_dial_rejected_by_closed_tcp_is_protocol_failure(self):
        host, port, server = await _start(_tcp_accept_handler)
        try:
            runner = _runner()
            result = await runner.check(
                _entry(protocol="vless", host=host, port=port, user=str(uuid.uuid4()))
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.protocol_checked is True
            assert result.error in (errors.PROTOCOL_MALFORMED, errors.PROTOCOL_REJECTED)
        finally:
            server.close()

    async def test_trojan_tls_closed_by_server_after_request_is_protocol_failure(self, tmp_path):
        assets = _write_pems(tmp_path)
        host, port, server = await _start_tls(
            _tcp_accept_handler, assets["good.crt"], assets["good.key"]
        )
        try:
            runner = _runner()
            result = await runner.check(
                _entry(
                    protocol="trojan",
                    host=host,
                    port=port,
                    sni="localhost",
                    password="pw",
                )
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.is_alive is False
            assert result.protocol_checked is True
            assert result.tls_used is True
            assert result.tls_ms >= 0.0
            assert result.error == errors.PROTOCOL_AUTH
        finally:
            server.close()

    async def test_https_proxy_tls_connect_ok(self, tmp_path):
        assets = _write_pems(tmp_path)
        host, port, server = await _start_tls(
            _http_handler(200), assets["good.crt"], assets["good.key"]
        )
        try:
            runner = _runner()
            result = await runner.check(
                _entry(protocol="https", host=host, port=port, sni="localhost")
            )
            assert result.status == HealthStatus.OK
            assert result.is_alive is True
            assert result.protocol_checked is True
            assert result.tls_used is True
            assert result.tls_verified is False  # verify_tls default off
            assert result.latency_ms == pytest.approx(
                result.connect_ms + result.tls_ms + result.proxy_ms, abs=0.01
            )
        finally:
            server.close()

    async def test_https_bad_cert_handshake_only_still_ok(self, tmp_path):
        assets = _write_pems(tmp_path)
        host, port, server = await _start_tls(
            _http_handler(200), assets["bad.crt"], assets["bad.key"]
        )
        try:
            runner = _runner()  # verify_tls=False default
            result = await runner.check(
                _entry(protocol="https", host=host, port=port, sni="localhost")
            )
            assert result.status == HealthStatus.OK
            assert result.is_alive is True
            assert result.tls_verified is False
        finally:
            server.close()

    async def test_https_bad_cert_verification_failure(self, tmp_path):
        assets = _write_pems(tmp_path)
        host, port, server = await _start_tls(
            _http_handler(200), assets["bad.crt"], assets["bad.key"]
        )
        try:
            runner = _runner(verify_tls=True)
            result = await runner.check(
                _entry(protocol="https", host=host, port=port, sni="localhost")
            )
            assert result.status == HealthStatus.TLS_FAILURE
            assert result.is_alive is False
            assert result.error == errors.TLS_CERTIFICATE
        finally:
            server.close()

    async def test_unreachable_port(self):
        runner = _runner()
        result = await runner.check(_entry(protocol="http", host="127.0.0.1", port=1))
        assert result.status == HealthStatus.UNREACHABLE
        assert result.is_alive is False
        assert result.error == errors.CONNECTION_REFUSED
        assert result.checked_ip == "127.0.0.1"

    async def test_timeout_bounded(self):
        host, port, server = await _start(_silent_handler)
        try:
            runner = _runner(timeout=0.4)
            start = asyncio.get_running_loop().time()
            result = await runner.check(_entry(protocol="http", host=host, port=port))
            elapsed = asyncio.get_running_loop().time() - start
            assert result.status == HealthStatus.TIMEOUT
            assert result.error == errors.CONNECTION_TIMEOUT
            assert elapsed <= 1.0
        finally:
            server.close()

    async def test_tls_timeout_bounded(self):
        host, port, server = await _start(_silent_handler)
        try:
            runner = _runner(timeout=0.4)
            start = asyncio.get_running_loop().time()
            result = await runner.check(
                _entry(protocol="https", host=host, port=port, sni="localhost")
            )
            elapsed = asyncio.get_running_loop().time() - start
            assert result.status in (HealthStatus.TLS_FAILURE, HealthStatus.TIMEOUT)
            assert result.error in (errors.TLS_TIMEOUT, errors.CONNECTION_TIMEOUT)
            assert result.is_alive is False
            assert elapsed <= 1.0
        finally:
            server.close()

    async def test_dns_failure(self):
        runner = _runner()
        with patch(
            "proxyaggregator.health.runner.resolve_host",
            return_value=type("R", (), {"resolved": False, "addresses": [], "error": "nxdomain"})(),
        ):
            result = await runner.check(
                _entry(protocol="http", host="no-such-host.invalid", port=80)
            )
        assert result.status == HealthStatus.DNS_FAILURE
        assert result.error == errors.DNS_FAILURE
        assert result.attempted_ips == []

    async def test_policy_declines_private_target(self):
        runner = HealthRunner()  # production policy: private/loopback blocked
        result = await runner.check(_entry(protocol="http", host="127.0.0.1", port=8080))
        assert result.status == HealthStatus.DECLINED
        assert result.error == errors.POLICY_DECLINED
        assert result.is_alive is False
        assert result.attempted_ips == []

    async def test_multi_ip_uses_working_ip(self):
        _host, port, server = await _start(_http_handler(200))
        try:
            enrichment = EnrichmentResult(
                original_host="multi.invalid",
                original_port=port,
                original_protocol="http",
                resolved_ip="127.0.0.2",
                all_resolved_ips=["127.0.0.2", "127.0.0.1"],
            )
            runner = _runner()
            result = await runner.check(
                _entry(protocol="http", host="multi.invalid", port=port, enrichment=enrichment)
            )
            # First candidate is refused, second answers: must converge on the working IP.
            assert result.status == HealthStatus.OK
            assert result.checked_ip == "127.0.0.1"
            assert result.attempted_ips == ["127.0.0.2", "127.0.0.1"]
        finally:
            server.close()

    async def test_max_ips_per_host_cap(self):
        _host, port, server = await _start(_http_handler(200))
        try:
            enrichment = EnrichmentResult(
                original_host="multi.invalid",
                original_port=port,
                original_protocol="http",
                resolved_ip="127.0.0.1",
                all_resolved_ips=["127.0.0.1", "127.0.0.2", "127.0.0.3"],
            )
            runner = _runner(max_ips_per_host=2)
            result = await runner.check(
                _entry(protocol="http", host="multi.invalid", port=port, enrichment=enrichment)
            )
            assert len(result.attempted_ips) <= 2
        finally:
            server.close()

    async def test_socks5_runner_ok(self):
        host, port, server = await _start(_socks5_handler())
        try:
            runner = _runner()
            result = await runner.check(_entry(protocol="socks5", host=host, port=port))
            assert result.status == HealthStatus.OK
            assert result.protocol_checked is True
        finally:
            server.close()

    async def test_socks4_runner_ok(self):
        host, port, server = await _start(_socks4_handler)
        try:
            runner = _runner()
            result = await runner.check(_entry(protocol="socks4", host=host, port=port))
            assert result.status == HealthStatus.OK
            assert result.protocol_checked is True
        finally:
            server.close()


class TestHealthRunnerConcurrency:
    async def test_check_all_bounded_concurrency(self):
        activity = _Activity()
        host, port, server = await _start(_counting_http_handler(activity))
        try:
            runner = _runner(concurrency=2, timeout=3.0)
            entries = [_entry(protocol="http", host=host, port=port) for _ in range(4)]
            results = await runner.check_all(entries)
            assert len(results) == 4
            assert all(r.status == HealthStatus.OK for r in results)
            assert activity.max_concurrent <= 2
        finally:
            server.close()

    async def test_check_all_result_order_preserved(self):
        activity = _Activity()
        host, port, server = await _start(_counting_http_handler(activity))
        try:
            runner = _runner(concurrency=2, timeout=3.0)
            ports = [port, port, port]
            entries = [_entry(protocol="http", host=host, port=p) for p in ports]
            results = await runner.check_all(entries)
            assert [r.port for r in results] == ports
        finally:
            server.close()

    async def test_check_all_isolates_unexpected_exception(self):
        """One entry raising unexpectedly must not abort the other checks.

        The affected entry degrades to a stable UNREACHABLE result and the
        remaining entries complete normally (Phase 16 reliability guard).
        """

        class ExplodingRunner(HealthRunner):
            async def check(self, entry):
                if entry.parsed.host == "boom.invalid":
                    raise RuntimeError("unexpected failure")
                return await super().check(entry)

        host, port, server = await _start(_http_handler(200))
        try:
            runner = ExplodingRunner(
                policy=TargetPolicy(allow_private=True), timeout=2.0, concurrency=4
            )
            entries = [
                _entry(protocol="http", host="boom.invalid", port=port),
                _entry(protocol="http", host=host, port=port),
            ]
            results = await runner.check_all(entries)
        finally:
            server.close()

        assert len(results) == 2
        assert results[0].status == HealthStatus.UNREACHABLE
        assert results[0].error == errors.CONNECTION_ERROR
        assert results[0].host == "boom.invalid"
        assert results[1].status == HealthStatus.OK
        assert results[1].is_alive is True


class TestSanitizedErrors:
    async def test_error_never_contains_credentials_or_uri(self):
        host, port, server = await _start(_socks5_handler(require_auth=True, reject_auth=True))
        try:
            runner = _runner()
            result = await runner.check(
                _entry(
                    protocol="socks5", host=host, port=port, user="secretuser", password="hunter2"
                )
            )
            assert result.error == errors.SOCKS_AUTH_FAILURE
            assert "secretuser" not in (result.error or "")
            assert "hunter2" not in (result.error or "")
        finally:
            server.close()

    async def test_http_reject_uses_stable_code(self):
        host, port, server = await _start(_http_handler(403))
        try:
            runner = _runner()
            result = await runner.check(_entry(protocol="http", host=host, port=port))
            assert result.error == errors.HTTP_REJECTED
        finally:
            server.close()


# ===========================================================================
# PROTOCOL_CHECKED CONTRACT
# ===========================================================================


class TestHealthCheckContract:
    """protocol_checked records that the wire-level protocol check ran.

    - OK: protocol_checked=True, is_alive=True
    - PROTOCOL_FAILURE: protocol_checked=True, is_alive=False
      (the wire-level check ran; its result was a failure)
    - UNSUPPORTED: protocol_checked=False, is_alive=False
    is_alive stays the single health signal: is_alive ⇔ status == OK.
    """

    async def test_protocol_checked_tri_state(self):
        ok_host, ok_port, ok_server = await _start(_http_handler(200))
        fail_host, fail_port, fail_server = await _start(_http_handler(407))
        sup_host, sup_port, sup_server = await _start(_tcp_accept_handler)
        try:
            runner = _runner()
            ok = await runner.check(_entry(protocol="http", host=ok_host, port=ok_port))
            fail = await runner.check(_entry(protocol="http", host=fail_host, port=fail_port))
            unsupported = await runner.check(
                _entry(protocol="hysteria2", host=sup_host, port=sup_port)
            )
        finally:
            ok_server.close()
            fail_server.close()
            sup_server.close()

        assert ok.status == HealthStatus.OK
        assert ok.protocol_checked is True
        assert ok.is_alive is True

        assert fail.status == HealthStatus.PROTOCOL_FAILURE
        assert fail.protocol_checked is True
        assert fail.is_alive is False

        assert unsupported.status == HealthStatus.UNSUPPORTED
        assert unsupported.protocol_checked is False
        assert unsupported.is_alive is False


# ===========================================================================
# AGGREGATION PRIORITY ACROSS MIXED IP RESULTS
# ===========================================================================


def _multi_ip_entry(protocol: str, host: str, port: int, ips: list[str], **kwargs) -> HealthEntry:
    enrichment = EnrichmentResult(
        original_host=host,
        original_port=port,
        original_protocol=protocol,
        resolved_ip=ips[0],
        all_resolved_ips=list(ips),
    )
    return _entry(protocol=protocol, host=host, port=port, enrichment=enrichment, **kwargs)


class TestAggregationPriority:
    async def test_tls_failure_beats_unreachable(self):
        port, tls_server = await _start_on(_tls_garbage_handler, "127.0.0.1")
        try:
            runner = _runner(timeout=2.0)
            result = await runner.check(
                _multi_ip_entry("https", "mix.invalid", port, ["127.0.0.2", "127.0.0.1"])
            )
        finally:
            tls_server.close()
        assert result.status == HealthStatus.TLS_FAILURE
        assert result.error == errors.TLS_HANDSHAKE
        assert result.checked_ip == "127.0.0.1"
        assert result.is_alive is False

    async def test_timeout_beats_unreachable(self):
        port, silent_server = await _start_on(_silent_handler, "127.0.0.1")
        try:
            runner = _runner(timeout=0.4)
            start = asyncio.get_running_loop().time()
            result = await runner.check(
                _multi_ip_entry("http", "mix.invalid", port, ["127.0.0.2", "127.0.0.1"])
            )
            elapsed = asyncio.get_running_loop().time() - start
        finally:
            silent_server.close()
        assert result.status == HealthStatus.TIMEOUT
        assert result.error == errors.CONNECTION_TIMEOUT
        assert result.checked_ip == "127.0.0.1"
        assert elapsed <= 1.0

    async def test_protocol_failure_beats_timeout(self):
        port, server_407 = await _start_on(_http_handler(407), "127.0.0.1")
        silent_ip, silent_server = await _second_loopback_same_port(_silent_handler, port)
        try:
            runner = _runner(timeout=0.4)
            start = asyncio.get_running_loop().time()
            result = await runner.check(
                _multi_ip_entry("http", "mix.invalid", port, ["127.0.0.1", silent_ip])
            )
            elapsed = asyncio.get_running_loop().time() - start
        finally:
            server_407.close()
            silent_server.close()
        assert result.status == HealthStatus.PROTOCOL_FAILURE
        assert result.error == errors.HTTP_STATUS_407
        assert result.checked_ip == "127.0.0.1"
        assert elapsed <= 1.0

    async def test_ok_beats_protocol_failure_even_when_completed_later(self):
        """A 407 finishes first; the slow 200 must still win (OK outranks)."""

        async def _slow_ok_handler(reader, writer) -> None:
            try:
                await _read_http_request(reader)
                await asyncio.sleep(0.2)
                writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                await writer.drain()
            finally:
                writer.close()

        port, server_407 = await _start_on(_http_handler(407), "127.0.0.1")
        ok_ip, ok_server = await _second_loopback_same_port(_slow_ok_handler, port)
        try:
            runner = _runner(timeout=2.0)
            start = asyncio.get_running_loop().time()
            result = await runner.check(
                _multi_ip_entry("http", "mix.invalid", port, ["127.0.0.1", ok_ip])
            )
            elapsed = asyncio.get_running_loop().time() - start
        finally:
            server_407.close()
            ok_server.close()
        assert result.status == HealthStatus.OK
        assert result.checked_ip == ok_ip
        assert result.is_alive is True
        assert elapsed >= 0.15  # proof the OK probe completed after the 407

    async def test_unsupported_early_stops(self):
        """An unsupported protocol needs no protocol exchange, so every
        TCP-successful IP is UNSUPPORTED; the runner must stop early and
        return promptly."""
        port, tcp_server = await _start_on(_tcp_accept_handler, "127.0.0.1")
        silent_ip, silent_server = await _second_loopback_same_port(_silent_handler, port)
        try:
            runner = _runner(timeout=2.0)
            start = asyncio.get_running_loop().time()
            result = await runner.check(
                _multi_ip_entry("hysteria2", "mix.invalid", port, ["127.0.0.1", silent_ip])
            )
            elapsed = asyncio.get_running_loop().time() - start
        finally:
            tcp_server.close()
            silent_server.close()
        assert result.status == HealthStatus.UNSUPPORTED
        assert result.checked_ip in ("127.0.0.1", silent_ip)
        assert result.is_alive is False
        assert elapsed <= 0.9

    def test_priority_order_contract(self):
        """Full documented order: OK > UNSUPPORTED > PROTOCOL_FAILURE >
        TLS_FAILURE > TIMEOUT > UNREACHABLE > DNS_FAILURE > DECLINED > SKIPPED.

        Pairs that cannot occur within one runner entry (one entry has one
        protocol, so e.g. TLS_FAILURE + PROTOCOL_FAILURE are unreachable
        together) are locked here at the selection level.
        """
        ordered = [
            HealthStatus.OK,
            HealthStatus.UNSUPPORTED,
            HealthStatus.PROTOCOL_FAILURE,
            HealthStatus.TLS_FAILURE,
            HealthStatus.TIMEOUT,
            HealthStatus.UNREACHABLE,
            HealthStatus.DNS_FAILURE,
            HealthStatus.DECLINED,
            HealthStatus.SKIPPED,
        ]
        attempts = [_Attempt(ip=f"ip{i}", status=status) for i, status in enumerate(ordered)]
        best = _select_best(attempts)
        assert best.status == HealthStatus.OK

        pairs = [
            (HealthStatus.UNSUPPORTED, HealthStatus.PROTOCOL_FAILURE),
            (HealthStatus.PROTOCOL_FAILURE, HealthStatus.TLS_FAILURE),
            (HealthStatus.TLS_FAILURE, HealthStatus.TIMEOUT),
            (HealthStatus.TIMEOUT, HealthStatus.UNREACHABLE),
            (HealthStatus.UNREACHABLE, HealthStatus.DNS_FAILURE),
            (HealthStatus.DNS_FAILURE, HealthStatus.DECLINED),
            (HealthStatus.DECLINED, HealthStatus.SKIPPED),
        ]
        for winner, loser in pairs:
            best = _select_best(
                [_Attempt(ip="first", status=loser), _Attempt(ip="second", status=winner)]
            )
            assert best.status is winner, f"{winner} must outrank {loser}"
            # tie-break: first completed attempt wins
            best = _select_best(
                [_Attempt(ip="first", status=winner), _Attempt(ip="second", status=winner)]
            )
            assert best.ip == "first"


class TestEarlyStopCancellation:
    async def test_ok_ip_cancels_hanging_probe(self):
        """First OK stops fan-out: the hanging IP must be cancelled+drained."""
        port, ok_server = await _start_on(_http_handler(200), "127.0.0.1")
        silent_ip, silent_server = await _second_loopback_same_port(_silent_handler, port)
        try:
            runner = _runner(timeout=1.0)
            start = asyncio.get_running_loop().time()
            result = await runner.check(
                _multi_ip_entry("http", "early.invalid", port, ["127.0.0.1", silent_ip])
            )
            elapsed = asyncio.get_running_loop().time() - start
        finally:
            ok_server.close()
            silent_server.close()
        assert result.status == HealthStatus.OK
        assert result.checked_ip == "127.0.0.1"
        assert result.attempted_ips == ["127.0.0.1", silent_ip]
        # Without cancellation this would wait for the silent probe (1.0s).
        assert elapsed <= 0.9


# ===========================================================================
# TLS VERIFY POLICY (IP LITERAL / NO SNI)
# ===========================================================================


class TestTlsVerifyIpLiteral:
    async def test_verify_tls_with_ip_literal_is_handshake_only(self, tmp_path):
        """verify_cert requires a hostname to verify against.

        With an IP-literal host (no SNI) verification cannot run, so the
        check intentionally degrades to handshake-only: tls_verified=False.
        No certificate-verification claim is made.
        """
        assets = _write_pems(tmp_path)
        host, port, server = await _start_tls(
            _http_handler(200), assets["good.crt"], assets["good.key"]
        )
        try:
            runner = _runner(verify_tls=True)
            result = await runner.check(_entry(protocol="https", host=host, port=port))
        finally:
            server.close()
        assert result.status == HealthStatus.OK
        assert result.tls_used is True
        assert result.tls_verified is False
        assert result.protocol_checked is True
        assert result.is_alive is True


# ===========================================================================
# protocol_uses_tls
# ===========================================================================


class TestProtocolUsesTls:
    def test_https_and_trojan_always_use_tls(self):
        assert protocol_uses_tls(_entry(protocol="https", host="h", port=443).parsed) is True
        assert protocol_uses_tls(_entry(protocol="trojan", host="h", port=443).parsed) is True

    def test_non_tls_protocols(self):
        assert protocol_uses_tls(_entry(protocol="http", host="h", port=80).parsed) is False
        assert protocol_uses_tls(_entry(protocol="ss", host="h", port=8388).parsed) is False
        assert protocol_uses_tls(_entry(protocol="socks5", host="h", port=1080).parsed) is False
        assert protocol_uses_tls(_entry(protocol="socks4", host="h", port=1080).parsed) is False

    def test_vless_security_variants(self):
        for tls in (None, "", "none"):
            assert (
                protocol_uses_tls(_entry(protocol="vless", host="h", port=443, tls=tls).parsed)
                is False
            )
        for tls in ("tls", "reality", "xtls"):
            assert (
                protocol_uses_tls(_entry(protocol="vless", host="h", port=443, tls=tls).parsed)
                is True
            )

    def test_vmess_security_variants(self):
        for tls in (None, "", "none"):
            assert (
                protocol_uses_tls(_entry(protocol="vmess", host="h", port=443, tls=tls).parsed)
                is False
            )
        for tls in ("tls", "reality", "xtls"):
            assert (
                protocol_uses_tls(_entry(protocol="vmess", host="h", port=443, tls=tls).parsed)
                is True
            )


# ===========================================================================
# SETTINGS -> HealthRunner WIRING
# ===========================================================================


class TestHealthSettingsWiring:
    def test_build_runner_uses_settings_defaults(self):
        settings = Settings()
        runner = build_health_runner(settings)
        assert runner.timeout == settings.health_check_timeout
        assert runner.concurrency == settings.health_check_concurrency
        assert runner.max_ips_per_host == settings.health_check_max_ips_per_host
        assert runner.verify_tls == settings.health_check_verify_tls

    def test_build_runner_reflects_env_overrides(self, monkeypatch):
        monkeypatch.setenv("PA_HEALTH_CHECK_TIMEOUT", "3")
        monkeypatch.setenv("PA_HEALTH_CHECK_CONCURRENCY", "7")
        monkeypatch.setenv("PA_HEALTH_CHECK_MAX_IPS_PER_HOST", "4")
        monkeypatch.setenv("PA_HEALTH_CHECK_VERIFY_TLS", "1")
        settings = Settings()
        runner = build_health_runner(settings)
        assert runner.timeout == 3
        assert runner.concurrency == 7
        assert runner.max_ips_per_host == 4
        assert runner.verify_tls is True

    def test_build_runner_keeps_self_tunnel_default(self):
        """No external health target: connect_target stays None (self-tunnel)."""
        runner = build_health_runner(Settings())
        assert runner.connect_target is None


# ===========================================================================
# DB PERSISTENCE + MIGRATION
# ===========================================================================


class TestHealthDbPersistence:
    def test_record_health_result_persists_columns(self, db_session):
        config = create_proxy_config(
            db_session,
            protocol="http",
            host="example.com",
            port=8080,
            raw_uri="http://example.com:8080",
            content_hash="f" * 64,
        )
        result = HealthCheckResult(
            proxy_config_id=config.id,
            protocol="http",
            host="example.com",
            port=8080,
            status=HealthStatus.OK,
            checked_ip="1.2.3.4",
            attempted_ips=["203.0.113.1", "1.2.3.4"],
            stage=CheckStage.PROTOCOL,
            connect_ms=10.5,
            proxy_ms=5.2,
            latency_ms=15.7,
            protocol_checked=True,
            tls_used=False,
        )
        record_health_result(db_session, result)

        refreshed = get_proxy_config(db_session, config.id)
        assert refreshed is not None
        assert refreshed.is_alive is True
        assert refreshed.latency_ms == 15.7
        assert refreshed.working_ip == "1.2.3.4"

        checks = get_health_checks_for_config(db_session, config.id)
        assert len(checks) == 1
        check = checks[0]
        assert check.status == HealthStatus.OK.value
        assert check.checked_ip == "1.2.3.4"
        assert check.protocol_checked is True
        assert json.loads(check.attempted_ips) == ["203.0.113.1", "1.2.3.4"]

    def test_record_dead_result(self, db_session):
        config = create_proxy_config(
            db_session,
            protocol="ss",
            host="dead.example.com",
            port=8388,
            raw_uri="ss://x@dead.example.com:8388",
            content_hash="a1" * 32,
        )
        result = HealthCheckResult(
            proxy_config_id=config.id,
            protocol="ss",
            host="dead.example.com",
            port=8388,
            status=HealthStatus.TIMEOUT,
            error=errors.CONNECTION_TIMEOUT,
        )
        record_health_result(db_session, result)
        refreshed = get_proxy_config(db_session, config.id)
        assert refreshed.is_alive is False
        assert refreshed.working_ip is None
        assert refreshed.latency_ms is None


class TestPhase6Migration:
    def _alembic_config(self):
        from alembic.config import Config

        root = Path(__file__).resolve().parent.parent
        cfg = Config(str(root / "alembic.ini"))
        cfg.set_main_option("script_location", str(root / "alembic"))
        return cfg

    def test_round_trip_adds_detail_columns(self, tmp_path, monkeypatch):
        from alembic import command

        url = f"sqlite:///{tmp_path / 'mig.db'}"
        monkeypatch.setenv("PA_DATABASE_URL", url)
        cfg = self._alembic_config()

        command.upgrade(cfg, "head")
        engine = create_engine(url)
        insp = inspect(engine)
        hc = {c["name"] for c in insp.get_columns("health_checks")}
        pc = {c["name"] for c in insp.get_columns("proxy_configs")}
        required = {
            "status",
            "checked_ip",
            "attempted_ips",
            "connect_ms",
            "tls_ms",
            "proxy_ms",
            "tls_used",
            "protocol_checked",
        }
        assert required <= hc
        assert "working_ip" in pc

        command.downgrade(cfg, "c2f13f33da92")
        insp2 = inspect(engine)
        hc2 = {c["name"] for c in insp2.get_columns("health_checks")}
        pc2 = {c["name"] for c in insp2.get_columns("proxy_configs")}
        assert not (required & hc2)
        assert "working_ip" not in pc2

        command.upgrade(cfg, "head")
        insp3 = inspect(engine)
        hc3 = {c["name"] for c in insp3.get_columns("health_checks")}
        assert required <= hc3

    def test_data_survives_round_trip(self, tmp_path, monkeypatch):
        from alembic import command
        from sqlalchemy import text

        url = f"sqlite:///{tmp_path / 'mig2.db'}"
        monkeypatch.setenv("PA_DATABASE_URL", url)
        cfg = self._alembic_config()
        command.upgrade(cfg, "head")

        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO proxy_configs "
                    "(protocol, host, port, raw_uri, content_hash, is_alive, "
                    " created_at, updated_at)"
                    " VALUES (:p, :h, :pt, :ru, :ch, :al, :ca, :ua)"
                ),
                {
                    "p": "http",
                    "h": "keep.example.com",
                    "pt": 8080,
                    "ru": "http://keep.example.com:8080",
                    "ch": "b2" * 32,
                    "al": 0,
                    "ca": datetime(2024, 1, 2, 3, 4, 5),
                    "ua": datetime(2024, 1, 2, 3, 4, 5),
                },
            )
            config_id = conn.execute(text("SELECT id FROM proxy_configs")).scalar()

        command.downgrade(cfg, "c2f13f33da92")
        command.upgrade(cfg, "head")

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT host, port FROM proxy_configs WHERE id = :id"),
                {"id": config_id},
            ).one()
        assert row[0] == "keep.example.com"
        assert row[1] == 8080


# ===========================================================================
# PHASE 6.2: VLESS / TROJAN / SHADOWSOCKS
# ===========================================================================


class TestPhase62VariantGate:
    def _parsed(self, protocol: str, **kwargs) -> ParseResult:
        return _entry(protocol=protocol, host="127.0.0.1", port=443, **kwargs).parsed

    def test_vless_reality_unsupported(self):
        assert transport_gate(self._parsed("vless", tls="reality")) == errors.TLS_REALITY

    def test_vless_overlay_networks_unsupported(self):
        for network in ("httpupgrade", "xhttp", "kcp", "quic"):
            assert (
                transport_gate(self._parsed("vless", network=network)) == errors.TRANSPORT_OVERLAY
            )

    def test_vless_ws_networks_supported(self):
        for network in ("ws",):
            assert transport_gate(self._parsed("vless", network=network)) is None

    def test_vless_grpc_network_gated(self):
        assert transport_gate(self._parsed("vless", network="grpc")) == errors.TRANSPORT_GRPC

    def test_vless_tcp_networks_supported(self):
        for network in (None, "", "tcp", "raw"):
            assert transport_gate(self._parsed("vless", network=network)) is None

    def test_trojan_overlay_unsupported(self):
        for network in ("httpupgrade", "xhttp", "kcp", "quic"):
            assert (
                transport_gate(self._parsed("trojan", network=network)) == errors.TRANSPORT_OVERLAY
            )

    def test_trojan_ws_supported(self):
        for network in ("ws", None, "", "tcp"):
            assert transport_gate(self._parsed("trojan", network=network)) is None

    def test_trojan_grpc_network_gated(self):
        assert transport_gate(self._parsed("trojan", network="grpc")) == errors.TRANSPORT_GRPC

    def test_ss_methods_gate(self):
        for method in ("aes-128-gcm", "aes-256-gcm", "chacha20-ietf-poly1305"):
            assert transport_gate(self._parsed("ss", method=method)) is None, method
        for method in ("2022-blake3-aes-128-gcm", "aes-192-gcm", "rc4-md5"):
            assert (
                transport_gate(self._parsed("ss", method=method)) == errors.SS_CIPHER_UNSUPPORTED
            ), method

    def test_other_protocols_pass_through(self):
        assert transport_gate(self._parsed("http")) is None
        assert transport_gate(self._parsed("socks5")) is None

    def test_vmess_reality_unsupported(self):
        assert transport_gate(self._parsed("vmess", tls="reality")) == errors.TLS_REALITY

    def test_vmess_ws_and_tcp_supported(self):
        for network in ("ws", None, "", "tcp"):
            assert transport_gate(self._parsed("vmess", network=network)) is None

    def test_vmess_overlay_networks_unsupported(self):
        for network in ("httpupgrade", "xhttp", "kcp", "quic"):
            assert (
                transport_gate(self._parsed("vmess", network=network)) == errors.TRANSPORT_OVERLAY
            )

    def test_vmess_grpc_network_gated(self):
        assert transport_gate(self._parsed("vmess", network="grpc")) == errors.TRANSPORT_GRPC

    def test_hysteria_protocols_unsupported(self):
        for protocol in ("hysteria", "hysteria2"):
            assert transport_gate(self._parsed(protocol)) == errors.UNSUPPORTED_PROTOCOL


class TestPhase62GateBeforeDialing:
    async def test_vless_reality_never_dials(self):
        runner = _runner()
        result = await runner.check(
            _entry(protocol="vless", host="127.0.0.1", port=1, tls="reality")
        )
        assert result.status == HealthStatus.UNSUPPORTED
        assert result.error == errors.TLS_REALITY
        assert result.connect_ms is None
        assert result.protocol_checked is False

    async def test_vless_ws_reaches_wire(self):
        """WS news now dials: a refused port must surface as unreachable, not
        as a pre-dial unsupported transport."""
        runner = _runner(timeout=0.4)
        result = await runner.check(
            _entry(protocol="vless", host="127.0.0.1", port=1, network="ws")
        )
        assert result.status == HealthStatus.UNREACHABLE
        assert result.error == errors.CONNECTION_REFUSED
        assert result.protocol_checked is False

    async def test_ss_2022_never_dials(self):
        runner = _runner()
        result = await runner.check(
            _entry(
                protocol="ss",
                host="127.0.0.1",
                port=1,
                method="2022-blake3-aes-128-gcm",
            )
        )
        assert result.status == HealthStatus.UNSUPPORTED
        assert result.error == errors.SS_CIPHER_UNSUPPORTED
        assert result.connect_ms is None


class TestPhase62VlessChecker:
    async def test_plain_tcp_ok(self):
        uuid_str = str(uuid.uuid4())
        host, port, server = await _start(_vless_handler(uuid.UUID(uuid_str).bytes))
        try:
            runner = _runner()
            result = await runner.check(
                _entry(protocol="vless", host=host, port=port, user=uuid_str)
            )
            assert result.status == HealthStatus.OK
            assert result.is_alive is True
            assert result.protocol_checked is True
            assert result.proxy_ms >= 0.0
        finally:
            server.close()

    async def test_tls_ok(self, tmp_path):
        assets = _write_pems(tmp_path)
        uid = uuid.uuid4()
        host, port, server = await _start_tls(
            _vless_handler(uid.bytes), assets["good.crt"], assets["good.key"]
        )
        try:
            runner = _runner()
            result = await runner.check(
                _entry(
                    protocol="vless",
                    host=host,
                    port=port,
                    user=str(uid),
                    tls="tls",
                    sni="localhost",
                )
            )
            assert result.status == HealthStatus.OK
            assert result.is_alive is True
            assert result.tls_used is True
        finally:
            server.close()

    async def test_malformed_reply_is_protocol_failure(self):
        uid = uuid.uuid4()
        host, port, server = await _start(_vless_handler(uid.bytes, reply=b"\x00\x01"))
        try:
            runner = _runner()
            result = await runner.check(
                _entry(protocol="vless", host=host, port=port, user=str(uid))
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.error == errors.PROTOCOL_MALFORMED
            assert result.protocol_checked is True
            assert result.is_alive is False
        finally:
            server.close()

    async def test_invalid_uuid_rejected(self):
        host, port, server = await _start(_vless_handler(uuid.uuid4().bytes))
        try:
            runner = _runner()
            result = await runner.check(
                _entry(protocol="vless", host=host, port=port, user=str(uuid.uuid4()))
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.error == errors.PROTOCOL_MALFORMED
        finally:
            server.close()

    async def test_silent_server_is_timeout(self):
        uid = uuid.uuid4()
        host, port, server = await _start(_vless_handler(uid.bytes, silent=True))
        try:
            runner = _runner(timeout=0.4)
            result = await runner.check(
                _entry(protocol="vless", host=host, port=port, user=str(uid))
            )
            assert result.status == HealthStatus.TIMEOUT
            assert result.error == errors.CONNECTION_TIMEOUT
        finally:
            server.close()

    async def test_credential_never_leaks_into_error(self):
        host, port, server = await _start(_vless_handler(uuid.uuid4().bytes))
        try:
            runner = _runner()
            secret = str(uuid.uuid4())
            result = await runner.check(_entry(protocol="vless", host=host, port=port, user=secret))
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert secret not in (result.error or "")
        finally:
            server.close()


class TestPhase62TrojanChecker:
    async def test_tls_ok(self, tmp_path):
        assets = _write_pems(tmp_path)
        host, port, server = await _start_tls(
            _trojan_handler("proxypw"), assets["good.crt"], assets["good.key"]
        )
        try:
            runner = _runner()
            result = await runner.check(
                _entry(
                    protocol="trojan",
                    host=host,
                    port=port,
                    sni="localhost",
                    password="proxypw",
                )
            )
            assert result.status == HealthStatus.OK
            assert result.is_alive is True
            assert result.protocol_checked is True
            assert result.tls_used is True
            assert result.proxy_ms >= 0.0
        finally:
            server.close()

    async def test_wrong_password_auth_failure(self, tmp_path):
        assets = _write_pems(tmp_path)
        host, port, server = await _start_tls(
            _trojan_handler("rightpw"), assets["good.crt"], assets["good.key"]
        )
        try:
            runner = _runner()
            result = await runner.check(
                _entry(
                    protocol="trojan",
                    host=host,
                    port=port,
                    sni="localhost",
                    password="wrongpw",
                )
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.error == errors.PROTOCOL_AUTH
            assert result.protocol_checked is True
            assert "wrongpw" not in (result.error or "")
        finally:
            server.close()

    async def test_error_reply_is_protocol_failure(self, tmp_path):
        assets = _write_pems(tmp_path)
        host, port, server = await _start_tls(
            _trojan_handler("proxypw", reply=b"\x00"), assets["good.crt"], assets["good.key"]
        )
        try:
            runner = _runner()
            result = await runner.check(
                _entry(
                    protocol="trojan",
                    host=host,
                    port=port,
                    sni="localhost",
                    password="proxypw",
                )
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.error == errors.PROTOCOL_MALFORMED
        finally:
            server.close()

    async def test_wire_request_byte_layout(self, tmp_path):
        """Independently pin the serialized Trojan request layout.

        The expected bytes are written here by hand against the documented
        Trojan protocol order (CMD | ATYP | DST.ADDR | DST.PORT | CRLF) and use
        a hard-coded sha224(password) value, so the assertion is independent of
        the production serializer and of the reference-server parser.
        """
        assets = _write_pems(tmp_path)
        received: list[bytes] = []

        async def recording_handler(reader, writer) -> None:
            try:
                received.append(await reader.readexactly(68))
            except asyncio.IncompleteReadError:
                pass
            finally:
                writer.close()

        host, port, server = await _start_tls(
            recording_handler, assets["good.crt"], assets["good.key"]
        )
        try:
            client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            client_ctx.check_hostname = False
            client_ctx.verify_mode = ssl.CERT_NONE
            reader, writer = await asyncio.open_connection(
                host, port, ssl=client_ctx, server_hostname="localhost"
            )
            await check_trojan(
                reader,
                writer,
                target_host="1.2.3.4",
                target_port=443,
                password="pw123456",
                timeout=2.0,
            )
            writer.close()
        finally:
            server.close()

        assert received, "reference server received nothing"
        first = received[0]
        expected = (
            # hex(SHA224("pw123456"))
            "078ab6beac38f5b3beba8b8ad13a6fcde36da3e4653cb301798cb8f9".encode("ascii")
            + b"\r\n"
            + b"\x01"  # CMD CONNECT
            + b"\x01"  # ATYP IPv4
            + b"\x01\x02\x03\x04"  # DST.ADDR = 1.2.3.4
            + b"\x01\xbb"  # DST.PORT = 443
            + b"\r\n"
        )
        assert first == expected
        assert expected.index(b"\x01\xbb") > expected.rfind(b"\x01\x02\x03\x04")


class TestPhase62ShadowsocksChecker:
    @pytest.mark.parametrize("method", ["aes-128-gcm", "aes-256-gcm", "chacha20-ietf-poly1305"])
    async def test_ok(self, method):
        host, port, server = await _start(_ss_password_handler(method, "secret"))
        try:
            runner = _runner()
            result = await runner.check(
                _entry(protocol="ss", host=host, port=port, method=method, password="secret")
            )
            assert result.status == HealthStatus.OK
            assert result.is_alive is True
            assert result.protocol_checked is True
            assert result.proxy_ms >= 0.0
        finally:
            server.close()

    async def test_wrong_password_auth_failure(self):
        host, port, server = await _start(_ss_password_handler("aes-256-gcm", "server-secret"))
        try:
            runner = _runner()
            result = await runner.check(
                _entry(
                    protocol="ss",
                    host=host,
                    port=port,
                    method="aes-256-gcm",
                    password="client-wrong",
                )
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.error == errors.PROTOCOL_AUTH
            assert "client-wrong" not in (result.error or "")
        finally:
            server.close()


class TestPhase14VlessWsChecker:
    UUID = "11111111-2222-4333-8444-555555555555"

    async def test_ws_ok(self):
        uid = uuid.UUID(self.UUID)
        host, port, server = await _start(_vless_ws_handler(uid.bytes))
        try:
            runner = _runner()
            result = await runner.check(
                _entry(protocol="vless", host=host, port=port, user=self.UUID, network="ws")
            )
            assert result.status == HealthStatus.OK
            assert result.is_alive is True
            assert result.protocol_checked is True
            assert result.proxy_ms >= 0.0
        finally:
            server.close()

    async def test_ws_over_tls_ok(self, tmp_path):
        assets = _write_pems(tmp_path)
        uid = uuid.UUID(self.UUID)
        host, port, server = await _start_tls(
            _vless_ws_handler(uid.bytes), assets["good.crt"], assets["good.key"]
        )
        try:
            runner = _runner()
            result = await runner.check(
                _entry(
                    protocol="vless",
                    host=host,
                    port=port,
                    user=self.UUID,
                    network="ws",
                    tls="tls",
                    sni="localhost",
                )
            )
            assert result.status == HealthStatus.OK
            assert result.tls_used is True
        finally:
            server.close()

    async def test_malformed_reply_is_protocol_failure(self):
        uid = uuid.UUID(self.UUID)
        host, port, server = await _start(_vless_ws_handler(uid.bytes, reply=b"\x00\x01"))
        try:
            runner = _runner()
            result = await runner.check(
                _entry(protocol="vless", host=host, port=port, user=self.UUID, network="ws")
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.error == errors.PROTOCOL_MALFORMED
            assert result.protocol_checked is True
        finally:
            server.close()

    async def test_wrong_uuid_close_is_ws_handshake(self):
        host, port, server = await _start(_vless_ws_handler(uuid.uuid4().bytes))
        try:
            runner = _runner()
            result = await runner.check(
                _entry(protocol="vless", host=host, port=port, user=self.UUID, network="ws")
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.error == errors.WS_HANDSHAKE
        finally:
            server.close()

    async def test_silent_ws_server_is_timeout(self):
        uid = uuid.UUID(self.UUID)
        host, port, server = await _start(_vless_ws_handler(uid.bytes, silent=True))
        try:
            runner = _runner(timeout=0.4)
            result = await runner.check(
                _entry(protocol="vless", host=host, port=port, user=self.UUID, network="ws")
            )
            assert result.status == HealthStatus.TIMEOUT
            assert result.error == errors.CONNECTION_TIMEOUT
        finally:
            server.close()

    async def test_plain_server_is_not_ws(self):
        host, port, server = await _start(_http_handler(200))
        try:
            runner = _runner()
            result = await runner.check(
                _entry(protocol="vless", host=host, port=port, user=self.UUID, network="ws")
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.error == errors.WS_HANDSHAKE
        finally:
            server.close()

    async def test_credential_never_leaks(self):
        host, port, server = await _start(_vless_ws_handler(uuid.uuid4().bytes))
        try:
            runner = _runner()
            secret = str(uuid.uuid4())
            result = await runner.check(
                _entry(protocol="vless", host=host, port=port, user=secret, network="ws")
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert secret not in (result.error or "")
        finally:
            server.close()


class TestPhase14TrojanWsChecker:
    async def test_wss_ok(self, tmp_path):
        assets = _write_pems(tmp_path)
        host, port, server = await _start_tls(
            _trojan_ws_handler("proxypw"), assets["good.crt"], assets["good.key"]
        )
        try:
            runner = _runner()
            result = await runner.check(
                _entry(
                    protocol="trojan",
                    host=host,
                    port=port,
                    sni="localhost",
                    password="proxypw",
                    network="ws",
                )
            )
            assert result.status == HealthStatus.OK
            assert result.is_alive is True
            assert result.protocol_checked is True
            assert result.tls_used is True
        finally:
            server.close()

    async def test_wrong_password_close_is_auth(self, tmp_path):
        assets = _write_pems(tmp_path)
        host, port, server = await _start_tls(
            _trojan_ws_handler("rightpw"), assets["good.crt"], assets["good.key"]
        )
        try:
            runner = _runner()
            result = await runner.check(
                _entry(
                    protocol="trojan",
                    host=host,
                    port=port,
                    sni="localhost",
                    password="wrongpw",
                    network="ws",
                )
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.error == errors.PROTOCOL_AUTH
            assert "wrongpw" not in (result.error or "")
        finally:
            server.close()

    async def test_ws_data_is_malformed(self, tmp_path):
        assets = _write_pems(tmp_path)
        host, port, server = await _start_tls(
            _trojan_ws_handler("proxypw", reply=b"\x01"), assets["good.crt"], assets["good.key"]
        )
        try:
            runner = _runner()
            result = await runner.check(
                _entry(
                    protocol="trojan",
                    host=host,
                    port=port,
                    sni="localhost",
                    password="proxypw",
                    network="ws",
                )
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.error == errors.PROTOCOL_MALFORMED
        finally:
            server.close()

    async def test_plain_server_is_not_ws(self, tmp_path):
        assets = _write_pems(tmp_path)
        host, port, server = await _start_tls(
            _http_handler(200), assets["good.crt"], assets["good.key"]
        )
        try:
            runner = _runner()
            result = await runner.check(
                _entry(
                    protocol="trojan",
                    host=host,
                    port=port,
                    sni="localhost",
                    password="proxypw",
                    network="ws",
                )
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.error == errors.WS_HANDSHAKE
        finally:
            server.close()


class TestPhase14VmessChecker:
    UUID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeffff0000"

    async def test_tcp_ok(self):
        host, port, server = await _start(_vmess_handler(uuid.UUID(self.UUID).bytes))
        try:
            runner = _runner()
            result = await runner.check(
                _entry(protocol="vmess", host=host, port=port, user=self.UUID)
            )
            assert result.status == HealthStatus.OK
            assert result.is_alive is True
            assert result.protocol_checked is True
            assert result.proxy_ms >= 0.0
        finally:
            server.close()

    async def test_ws_ok(self, tmp_path):
        host, port, server = await _start(_vmess_ws_handler(uuid.UUID(self.UUID).bytes))
        try:
            runner = _runner()
            result = await runner.check(
                _entry(protocol="vmess", host=host, port=port, user=self.UUID, network="ws")
            )
            assert result.status == HealthStatus.OK
            assert result.tls_used is False
        finally:
            server.close()

    async def test_wss_ok(self, tmp_path):
        assets = _write_pems(tmp_path)
        host, port, server = await _start_tls(
            _vmess_ws_handler(uuid.UUID(self.UUID).bytes), assets["good.crt"], assets["good.key"]
        )
        try:
            runner = _runner()
            result = await runner.check(
                _entry(
                    protocol="vmess",
                    host=host,
                    port=port,
                    user=self.UUID,
                    network="ws",
                    tls="tls",
                    sni="localhost",
                )
            )
            assert result.status == HealthStatus.OK
            assert result.tls_used is True
        finally:
            server.close()

    async def test_wrong_uuid_is_auth_failure(self):
        host, port, server = await _start(_vmess_handler(uuid.uuid4().bytes))
        try:
            runner = _runner()
            result = await runner.check(
                _entry(protocol="vmess", host=host, port=port, user=self.UUID)
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.error == errors.PROTOCOL_AUTH
            assert self.UUID not in (result.error or "")
        finally:
            server.close()

    async def test_wrong_uuid_ws_close_is_ws_handshake(self):
        host, port, server = await _start(_vmess_ws_handler(uuid.uuid4().bytes))
        try:
            runner = _runner()
            result = await runner.check(
                _entry(protocol="vmess", host=host, port=port, user=self.UUID, network="ws")
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.error == errors.WS_HANDSHAKE
        finally:
            server.close()

    async def test_invalid_uuid_is_malformed(self):
        host, port, server = await _start(_vmess_handler(uuid.UUID(self.UUID).bytes))
        try:
            runner = _runner()
            result = await runner.check(
                _entry(protocol="vmess", host=host, port=port, user="not-a-uuid")
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.error == errors.PROTOCOL_MALFORMED
        finally:
            server.close()

    async def test_bogus_response_is_auth_failure(self):
        host, port, server = await _start(
            _vmess_handler(uuid.UUID(self.UUID).bytes, bogus_response=True)
        )
        try:
            runner = _runner()
            result = await runner.check(
                _entry(protocol="vmess", host=host, port=port, user=self.UUID)
            )
            assert result.status == HealthStatus.PROTOCOL_FAILURE
            assert result.error == errors.PROTOCOL_AUTH
        finally:
            server.close()

    async def test_silent_server_is_timeout(self):
        host, port, server = await _start(_vmess_handler(uuid.UUID(self.UUID).bytes, silent=True))
        try:
            runner = _runner(timeout=0.4)
            result = await runner.check(
                _entry(protocol="vmess", host=host, port=port, user=self.UUID)
            )
            assert result.status == HealthStatus.TIMEOUT
            assert result.error == errors.CONNECTION_TIMEOUT
        finally:
            server.close()


class TestPhase62SsKnownAnswer:
    def test_evp_bytes_to_key_aes128(self):
        assert _ss_evp_bytes_to_key(b"123456", 16).hex() == "e10adc3949ba59abbe56e057f20f883e"

    def test_evp_bytes_to_key_aes256(self):
        assert (
            _ss_evp_bytes_to_key(b"123456", 32).hex()
            == "e10adc3949ba59abbe56e057f20f883e65b4ad270b3b98098d256ab32f5b8fba"
        )

    def test_hkdf_sha1_pinned(self):
        master = _ss_evp_bytes_to_key(b"123456", 32)
        salt = bytes(range(32))
        assert (
            _ss_hkdf_sha1(salt, master, b"ss-subkey", 32).hex()
            == "070ae8f62685b1b45351d4e628ebcead3902408ba45cb7f045bd17e5d109efa7"
        )

    def test_chunk_round_trip_and_tag_size(self):
        master = _ss_evp_bytes_to_key(b"123456", 32)
        salt = bytes(range(32))
        session = _ss_hkdf_sha1(salt, master, b"ss-subkey", 32)
        cipher = _ss_chunk_cipher("aes-256-gcm", session)
        ct = _ss_encrypt_chunk(cipher, 0, b"\x00\x18")
        assert len(ct) == 18
        assert _ss_decrypt_chunk(cipher, 0, ct) == b"\x00\x18"

    def test_tampered_chunk_rejected(self):
        master = _ss_evp_bytes_to_key(b"123456", 32)
        salt = bytes(range(32))
        session = _ss_hkdf_sha1(salt, master, b"ss-subkey", 32)
        cipher = _ss_chunk_cipher("aes-256-gcm", session)
        ct = bytearray(_ss_encrypt_chunk(cipher, 0, b"\x00\x18"))
        ct[-1] ^= 0x01
        with pytest.raises((InvalidTag, ValueError)):
            _ss_decrypt_chunk(cipher, 0, bytes(ct))


class TestPhase14VmessKnownAnswer:
    """Pin the serialized VMess AEAD wire layout and KDF outputs by hand.

    The length/header blocks are random (session keys and nonces come from
    ``os.urandom``), so the layout is asserted structurally while the KDF and
    the seal/open round trip are asserted against independently chosen values.
    """

    UUID = "11111111-2222-4333-8444-555555555555"

    def test_kdf_golden_vector(self):
        got = vmess_mod._kdf(
            b"Demo Key for KDF Value Test",
            b"Demo Path for KDF Value Test",
            b"Demo Path for KDF Value Test2",
            b"Demo Path for KDF Value Test3",
        )
        assert got.hex() == "53e9d7e1bd7bd25022b71ead07d8a596efc8a845c7888652fd684b4903dc8892"

    def test_cmd_key_known(self):
        assert vmess_mod.cmd_key("11111111-2222-4333-8444-555555555555").hex() == (
            "21fb68641c5a02b1cf67dd3b6bd1e58d"
        )

    def test_fnv1a32_known_vectors(self):
        assert vmess_mod.fnv1a32(b"") == 0x811C9DC5
        assert vmess_mod.fnv1a32(b"a") == 0xE40C292C
        assert vmess_mod.fnv1a32(b"foobar") == 0xBF9CF968

    def test_sealed_request_layout(self):
        uid = uuid.UUID(self.UUID)
        sealed = vmess_mod.seal_request(uid.bytes, "www.example.com", 443)
        stream = sealed.stream
        # authID(16) + lenblk(18) + connNonce(8) + record(n=61) + GCM tag(16)
        assert len(stream) == 16 + 18 + 8 + 61 + 16
        assert stream[34:42]  # connNonce sits between len block and header block

    def test_seal_open_round_trip(self):
        uid = uuid.UUID(self.UUID)
        body_key = bytes(range(0xA0, 0xB0))
        body_iv = bytes(range(0xB0, 0xC0))
        sealed = vmess_mod.seal_request(
            uid.bytes,
            "www.example.com",
            443,
            timestamp=1628342914,
            rand4=bytes.fromhex("11223344"),
            conn_nonce=bytes.fromhex("0011223344556677"),
            body_key=body_key,
            body_iv=body_iv,
            v=0x01,
        )
        assert sealed.v == 0x01
        resp_body_key = hashlib.sha256(body_key).digest()[:16]
        resp_body_iv = hashlib.sha256(body_iv).digest()[:16]
        len_nonce = vmess_mod._kdf(resp_body_iv, vmess_mod._SALT_RESP_LEN_IV)[:12]
        len_key = vmess_mod._kdf16(resp_body_key, vmess_mod._SALT_RESP_LEN_KEY)
        hdr_nonce = vmess_mod._kdf(resp_body_iv, vmess_mod._SALT_RESP_IV)[:12]
        hdr_key = vmess_mod._kdf16(resp_body_key, vmess_mod._SALT_RESP_KEY)
        resp = AESGCM(len_key).encrypt(len_nonce, struct.pack("!H", 4), None)
        resp += AESGCM(hdr_key).encrypt(hdr_nonce, b"\x01\x00\x00\x00", None)
        assert vmess_mod.open_response(body_key, body_iv, 0x01, resp) == b"\x01\x00\x00\x00"

    def test_open_response_rejects_tamper(self):
        uid = uuid.UUID(self.UUID)
        body_key = bytes(range(0x20, 0x30))
        body_iv = bytes(range(0x30, 0x40))
        sealed = vmess_mod.seal_request(uid.bytes, "x.test", 80, body_key=body_key, body_iv=body_iv)
        resp_body_key = hashlib.sha256(body_key).digest()[:16]
        resp_body_iv = hashlib.sha256(body_iv).digest()[:16]
        len_nonce = vmess_mod._kdf(resp_body_iv, vmess_mod._SALT_RESP_LEN_IV)[:12]
        len_key = vmess_mod._kdf16(resp_body_key, vmess_mod._SALT_RESP_LEN_KEY)
        hdr_nonce = vmess_mod._kdf(resp_body_iv, vmess_mod._SALT_RESP_IV)[:12]
        hdr_key = vmess_mod._kdf16(resp_body_key, vmess_mod._SALT_RESP_KEY)
        resp = bytearray(AESGCM(len_key).encrypt(len_nonce, struct.pack("!H", 4), None))
        resp += AESGCM(hdr_key).encrypt(hdr_nonce, bytes([sealed.v, 0, 0, 0]), None)
        resp[-1] ^= 0x01
        with pytest.raises(ValueError):
            vmess_mod.open_response(body_key, body_iv, sealed.v, bytes(resp))

    def test_open_response_rejects_version_mismatch(self):
        uid = uuid.UUID(self.UUID)
        body_key = bytes(range(0x40, 0x50))
        body_iv = bytes(range(0x50, 0x60))
        vmess_mod.seal_request(uid.bytes, "y.test", 80, body_key=body_key, body_iv=body_iv)
        resp_body_key = hashlib.sha256(body_key).digest()[:16]
        resp_body_iv = hashlib.sha256(body_iv).digest()[:16]
        len_nonce = vmess_mod._kdf(resp_body_iv, vmess_mod._SALT_RESP_LEN_IV)[:12]
        len_key = vmess_mod._kdf16(resp_body_key, vmess_mod._SALT_RESP_LEN_KEY)
        hdr_nonce = vmess_mod._kdf(resp_body_iv, vmess_mod._SALT_RESP_IV)[:12]
        hdr_key = vmess_mod._kdf16(resp_body_key, vmess_mod._SALT_RESP_KEY)
        resp = AESGCM(len_key).encrypt(len_nonce, struct.pack("!H", 4), None)
        resp += AESGCM(hdr_key).encrypt(hdr_nonce, b"\x02\x00\x00\x00", None)
        with pytest.raises(ValueError):
            vmess_mod.open_response(body_key, body_iv, 0x01, resp)

    UUID = "11111111-2222-4333-8444-555555555555"

    def _parsed(self, uri: str) -> ParseResult:
        result = VlessParser().parse(uri)
        assert isinstance(result, ParseResult), result
        return result

    def test_type_ws_parses_into_network(self):
        parsed = self._parsed(f"vless://{self.UUID}@example.com:443?security=tls&type=ws")
        assert parsed.network == "ws"
        assert transport_gate(parsed) is None

    def test_type_grpc_parses_into_network(self):
        parsed = self._parsed(
            f"vless://{self.UUID}@example.com:443?security=tls&type=grpc&serviceName=x"
        )
        assert parsed.network == "grpc"
        assert transport_gate(parsed) == errors.TRANSPORT_GRPC

    def test_type_httpupgrade_and_xhttp_parses_into_network(self):
        for alias in ("httpupgrade", "xhttp"):
            parsed = self._parsed(f"vless://{self.UUID}@example.com:443?security=tls&type={alias}")
            assert parsed.network == alias
            assert transport_gate(parsed) == errors.TRANSPORT_OVERLAY

    def test_type_tcp_is_not_gated(self):
        parsed = self._parsed(f"vless://{self.UUID}@example.com:443?type=tcp")
        assert parsed.network == "tcp"
        assert transport_gate(parsed) is None

    def test_legacy_network_param_still_parses(self):
        parsed = self._parsed(f"vless://{self.UUID}@example.com:443?security=tls&network=ws")
        assert parsed.network == "ws"
        assert transport_gate(parsed) is None

    async def test_type_ws_share_link_reaches_wire(self):
        """A WS type share-link now dials; an unreachable port proves it."""
        parsed = self._parsed(f"vless://{self.UUID}@127.0.0.1:1?security=tls&type=ws")
        runner = _runner(timeout=0.4)
        result = await runner.check(HealthEntry(parsed=parsed))
        assert result.status == HealthStatus.UNREACHABLE
        assert result.error == errors.CONNECTION_REFUSED
        assert result.protocol_checked is False
