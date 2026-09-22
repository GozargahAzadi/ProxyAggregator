"""Asynchronous TCP and TLS check primitives.

Every network operation is bounded by an explicit timeout, uses only
asyncio (no blocking sockets), and is measured with a monotonic clock.
Connections are always closed, including on failure paths.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import ssl
import time
from typing import TYPE_CHECKING

from proxyaggregator.health import errors

if TYPE_CHECKING:
    from asyncio import StreamReader, StreamWriter

# Sensible upper bound when a caller does not provide an explicit timeout.
DEFAULT_TIMEOUT = 10.0


class CheckError(Exception):
    """A check failed with a stable, sanitized error code.

    The message is always one of the codes from :mod:`proxyaggregator.health.errors`;
    no free-form exception text, credentials, or URIs are ever placed here.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def monotonic_ms() -> float:
    """Return monotonic time in milliseconds."""
    return time.monotonic() * 1000.0


def _classify_os_error(exc: OSError) -> str:
    """Map an OSError to a stable connection error code."""
    if isinstance(exc, ConnectionRefusedError):
        return errors.CONNECTION_REFUSED
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return errors.CONNECTION_TIMEOUT

    eno = getattr(exc, "errno", None)
    if eno in (errno.EHOSTUNREACH, errno.ENETUNREACH, errno.EHOSTDOWN, errno.ENETDOWN):
        return errors.CONNECTION_UNREACHABLE
    if eno in (errno.ETIMEDOUT,):
        return errors.CONNECTION_TIMEOUT
    return errors.CONNECTION_ERROR


async def check_tcp(
    ip: str,
    port: int,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[StreamReader, StreamWriter, float]:
    """Open a TCP connection to a single IP:port.

    Args:
        ip: Already-resolved, policy-validated IP address (never a hostname).
        port: Destination port.
        timeout: Hard upper bound in seconds for this operation.

    Returns:
        ``(reader, writer, connect_ms)`` on success, where ``connect_ms`` is
        the measured TCP connect duration.

    Raises:
        CheckError: With a stable error code when the connection fails,
            times out, or is otherwise refused/unreachable.
    """
    start = monotonic_ms()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise CheckError(errors.CONNECTION_TIMEOUT) from exc
    except OSError as exc:
        raise CheckError(_classify_os_error(exc)) from exc

    connect_ms = monotonic_ms() - start
    return reader, writer, connect_ms


async def check_tls(
    ip: str,
    port: int,
    *,
    server_hostname: str | None,
    verify_cert: bool,
    ca_file: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[StreamReader, StreamWriter, float, bool]:
    """Open a TCP connection and complete a TLS handshake.

    The TLS handshake is performed against the already-resolved ``ip``, while
    ``server_hostname`` is used only for SNI and certificate verification.
    This keeps hostname rebinding out of the picture: the socket is never
    dialed by name.

    Args:
        ip: Already-resolved, policy-validated IP address.
        port: Destination port.
        server_hostname: SNI / verification hostname. Pass ``None`` to send
            no SNI and skip hostname verification.
        verify_cert: When True, verify the certificate chain (producing a
            :data:`errors.TLS_CERTIFICATE` failure on mismatch). When False,
            accept self-signed or mismatched certificates as long as the
            handshake itself completes.
        ca_file: Optional path to a PEM file whose certificates are trusted
            in addition to the system store (for self-signed / private-CA
            proxies).
        timeout: Hard upper bound in seconds for connect + handshake.

    Returns:
        ``(reader, writer, tls_ms, tls_verified)`` on success, where
        ``tls_ms`` covers the full connect + handshake duration and
        ``tls_verified`` reflects whether certificate verification ran.

    Raises:
        CheckError: With a stable error code on failure.
    """
    start = monotonic_ms()
    if verify_cert and server_hostname is not None:
        context = ssl.create_default_context(cafile=ca_file)
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        tls_verified = True
    else:
        # Handshake-only: accept any cert but do not treat it as verified.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        tls_verified = False

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                ip,
                port,
                ssl=context,
                server_hostname=server_hostname,
            ),
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise CheckError(errors.TLS_TIMEOUT) from exc
    except ssl.SSLCertVerificationError as exc:
        raise CheckError(errors.TLS_CERTIFICATE) from exc
    except ssl.SSLError as exc:
        raise CheckError(errors.TLS_HANDSHAKE) from exc
    except OSError as exc:
        raise CheckError(_classify_os_error(exc)) from exc

    tls_ms = monotonic_ms() - start
    return reader, writer, tls_ms, tls_verified


async def upgrade_tls(
    reader: StreamReader,
    writer: StreamWriter,
    *,
    server_hostname: str | None,
    verify_cert: bool,
    ca_file: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[StreamReader, StreamWriter, float, bool]:
    """Upgrade an existing plaintext stream to TLS via ``start_tls``.

    The connection was already established against the validated IP; this
    performs only the handshake against that same socket. ``server_hostname``
    carries SNI and, when ``verify_cert`` is True, the verification identity.

    Args:
        ca_file: Optional path to a PEM file whose certificates are trusted
            in addition to the system store. Useful for proxies that present
            self-signed or private-CA certificates.

    Returns:
        ``(reader, writer, tls_ms, tls_verified)`` where ``tls_ms`` is the
        handshake duration only (no TCP connect time).

    Raises:
        CheckError: With a stable error code on failure.
    """
    if verify_cert and server_hostname is not None:
        context = ssl.create_default_context(cafile=ca_file)
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        tls_verified = True
    else:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        tls_verified = False

    start = monotonic_ms()
    try:
        result = await asyncio.wait_for(
            writer.start_tls(context, server_hostname=server_hostname),
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise CheckError(errors.TLS_TIMEOUT) from exc
    except ssl.SSLCertVerificationError as exc:
        raise CheckError(errors.TLS_CERTIFICATE) from exc
    except ssl.SSLError as exc:
        raise CheckError(errors.TLS_HANDSHAKE) from exc
    except OSError as exc:
        raise CheckError(_classify_os_error(exc)) from exc

    # Python 3.11+ returns ``None`` and swaps the transport in place on the
    # original reader/writer; 3.10 returned a fresh ``(reader, writer)`` tuple.
    if isinstance(result, tuple) and len(result) == 2:
        reader, writer = result
    elif reader is not None:
        new_transport = getattr(writer, "_transport", None)
        old_transport = getattr(reader, "_transport", None)
        if new_transport is not None and new_transport is not old_transport:
            with contextlib.suppress(AttributeError):
                reader._transport = new_transport

    tls_ms = monotonic_ms() - start
    return reader, writer, tls_ms, tls_verified


async def close_quietly(writer: StreamWriter | None) -> None:
    """Close a writer, swallowing any teardown error.

    ``wait_closed`` is time-bound so a stuck TLS shutdown can never stall a
    cancelled task's unwinding; when the current task is already being
    cancelled we skip the wait entirely (asyncio ``wait_for`` waits for a
    cancelled task's ``finally`` blocks to run, so a quick cleanup keeps the
    overall probe deadline honest).
    """
    if writer is None:
        return
    task = asyncio.current_task()
    if task is not None and task.cancelling() > 0:
        writer.close()
        return
    try:
        writer.close()
        await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
    except Exception:
        pass
