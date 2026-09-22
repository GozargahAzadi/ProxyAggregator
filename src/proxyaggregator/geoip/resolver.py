"""DNS resolver for proxy endpoints.

Resolves hostnames to IPv4/IPv6 addresses using socket.getaddrinfo.
Literal IP addresses are returned directly without DNS lookup.

All addresses are normalized and sorted deterministically.
"""

from __future__ import annotations

import ipaddress
import math
import socket

from pydantic import BaseModel, Field


class ResolveResult(BaseModel):
    """Structured result of DNS resolution."""

    host: str = Field(..., description="Original hostname or IP")
    resolved: bool = Field(..., description="Whether resolution succeeded")
    addresses: list[str] = Field(default_factory=list, description="Resolved IP addresses, sorted")
    is_ipv4: bool = Field(default=False)
    is_ipv6: bool = Field(default=False)
    error: str | None = Field(default=None, description="Error message if resolution failed")

    model_config = {"frozen": True}


def _normalize_ip(addr: str) -> str:
    """Normalize an IP address string."""
    try:
        ip = ipaddress.ip_address(addr)
        return str(ip)
    except ValueError:
        return addr


def _ip_sort_key(addr: str) -> tuple[int, int, str]:
    """Sort key for IP addresses: IPv4 first, then by integer value."""
    try:
        ip = ipaddress.ip_address(addr)
        return (0 if ip.version == 4 else 1, int(ip), "")
    except ValueError:
        return (2, 0, addr)


def resolve_host(host: str | None, timeout: float = 5.0) -> ResolveResult:
    """Resolve a hostname to IP address(es).

    Args:
        host: Hostname or literal IP address. None or empty/whitespace produces an error.
        timeout: DNS lookup timeout in seconds. Must be a finite positive number.
            The timeout is enforced by temporarily setting the process-wide
            socket default timeout, then restoring the previous value.

    Returns:
        ResolveResult with resolved addresses or error information.
    """
    if host is None:
        return ResolveResult(host="", resolved=False, error="None hostname")

    host = host.strip()
    if not host:
        return ResolveResult(host="", resolved=False, error="Empty hostname")

    # Literal IP: skip DNS
    try:
        ip = ipaddress.ip_address(host)
        normalized = str(ip)
        return ResolveResult(
            host=host,
            resolved=True,
            addresses=[normalized],
            is_ipv4=ip.version == 4,
            is_ipv6=ip.version == 6,
        )
    except ValueError:
        pass

    # Validate timeout before touching DNS
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        return ResolveResult(
            host=host, resolved=False, error=f"Invalid timeout value: {timeout!r}"
        )

    # Hostname: resolve via socket with bounded timeout
    previous_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(float(timeout))
        infos = socket.getaddrinfo(
            host, None, socket.AF_UNSPEC, socket.SOCK_STREAM, 0, socket.AI_ADDRCONFIG
        )
    except (socket.gaierror, OSError, TimeoutError) as exc:
        return ResolveResult(host=host, resolved=False, error=str(exc))
    finally:
        socket.setdefaulttimeout(previous_timeout)

    if not infos:
        return ResolveResult(host=host, resolved=False, error="No addresses returned")

    # Extract and normalize IPs
    addresses: list[str] = []
    has_ipv4 = False
    has_ipv6 = False

    for family, _socktype, _proto, _canonname, sockaddr in infos:
        ip_str = sockaddr[0]
        normalized = _normalize_ip(ip_str)
        addresses.append(normalized)
        if family == socket.AF_INET:
            has_ipv4 = True
        elif family == socket.AF_INET6:
            has_ipv6 = True

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for addr in addresses:
        if addr not in seen:
            seen.add(addr)
            unique.append(addr)

    # Sort deterministically: IPv4 first, then by integer value
    unique.sort(key=_ip_sort_key)

    return ResolveResult(
        host=host,
        resolved=True,
        addresses=unique,
        is_ipv4=has_ipv4,
        is_ipv6=has_ipv6,
    )
