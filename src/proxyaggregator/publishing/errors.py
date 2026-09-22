"""Structured errors for subscription generation (Phase 8).

Messages are deliberately free of credentials and free of the raw URI string:
only the database id, the protocol identifier, and a short stable reason are
reported. This mirrors the sanitized-error convention used by the health
module.
"""

from __future__ import annotations


class SubscriptionError(Exception):
    """Raised when a candidate is not serializable.

    Attributes:
        proxy_config_id: Database identity of the offending proxy.
        protocol: Protocol identifier of the offending proxy.
        reason: Short, stable, credential-free reason token.
    """

    def __init__(self, proxy_config_id: int | None, protocol: str, reason: str) -> None:
        super().__init__(f"subscription error for proxy #{proxy_config_id} ({protocol}): {reason}")
        self.proxy_config_id = proxy_config_id
        self.protocol = protocol
        self.reason = reason
