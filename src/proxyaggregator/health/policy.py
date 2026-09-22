"""Target security policy for proxy health checks.

The policy is a defense-in-depth guard against SSRF and rebinding attacks.
It is evaluated BEFORE any connection is attempted and operates only on the
already-resolved, validated IP addresses produced by Phase 5 enrichment.

The production default rejects local, private, and non-routable destinations.
A permissive policy may be injected for tests that run local loopback servers;
the production policy is never silently bypassed.
"""

from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


def _blocked_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Return the networks that must never be dialed by a health check."""
    net = ipaddress.ip_network
    return [
        # --- loopback ---
        net("127.0.0.0/8"),
        net("::1/128"),
        # --- RFC1918 private ---
        net("10.0.0.0/8"),
        net("172.16.0.0/12"),
        net("192.168.0.0/16"),
        # --- link-local ---
        net("169.254.0.0/16"),
        net("fe80::/10"),
        # --- CGNAT ---
        net("100.64.0.0/10"),
        # --- unspecified / this network ---
        net("0.0.0.0/8"),
        net("::/128"),
        # --- multicast ---
        net("224.0.0.0/4"),
        net("ff00::/8"),
        # --- IPv6 unique-local ---
        net("fc00::/7"),
        # --- broadcast ---
        net("255.255.255.255/32"),
        # --- reserved / special-use ---
        net("192.0.0.0/24"),
        net("192.0.2.0/24"),  # TEST-NET-1 (documentation)
        net("198.18.0.0/15"),  # benchmarking
        net("198.51.100.0/24"),  # TEST-NET-2 (documentation)
        net("203.0.113.0/24"),  # TEST-NET-3 (documentation)
        net("240.0.0.0/4"),  # reserved
        net("2001:db8::/32"),  # documentation
        # --- IPv6 special-use (can embed or translate to IPv4 targets) ---
        net("2002::/16"),  # 6to4 (embeds IPv4 address)
        net("2001::/32"),  # Teredo
        net("64:ff9b::/96"),  # NAT64 well-known prefix
        net("64:ff9b:1::/48"),  # NAT64 direct / local-use
        net("2001:2::/48"),  # benchmarking
        net("2001:10::/28"),  # ORCHID
        net("2001:20::/28"),  # ORCHIDv2
        net("3fff::/20"),  # unassigned / not globally reachable
    ]


_BLOCKED: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = _blocked_networks()


def _is_blocked(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True when an address falls in any blocked network.

    IPv4-mapped IPv6 addresses are additionally checked against the blocked
    IPv4 ranges so that `::ffff:192.168.1.1` cannot slip past an IPv4 rule.
    """
    if any(addr in net for net in _BLOCKED):
        return True

    if isinstance(addr, ipaddress.IPv6Address):
        mapped = addr.ipv4_mapped
        if mapped is not None and any(mapped in net for net in _BLOCKED):
            return True

    return False


class TargetPolicy:
    """Checks whether a resolved IP address may be dialed.

    Production instances must always reject local/private/unsafe ranges.
    A permissive policy is only constructed explicitly for local tests.
    """

    def __init__(self, *, allow_private: bool = False) -> None:
        self._allow_private = allow_private

    def is_target_allowed(self, ip: str) -> bool:
        """Return True when the policy permits dialing this IP."""
        if self._allow_private:
            return True

        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False

        return not _is_blocked(addr)

    def split_allowed(self, ips: Iterable[str]) -> tuple[list[str], list[str]]:
        """Split candidate IPs into (allowed, rejected).

        Rejected IPs are excluded before any connection attempt, regardless of
        whether a hostname would otherwise resolve inside the blocked ranges.
        """
        allowed: list[str] = []
        rejected: list[str] = []
        for ip in ips:
            if self.is_target_allowed(ip):
                allowed.append(ip)
            else:
                rejected.append(ip)
        return allowed, rejected
