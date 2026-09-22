"""Health check modules for proxy endpoints."""

from proxyaggregator.health.errors import (
    CONNECTION_ERROR,
    CONNECTION_REFUSED,
    CONNECTION_TIMEOUT,
    CONNECTION_UNREACHABLE,
    DNS_FAILURE,
    DNS_UNAVAILABLE,
    HTTP_MALFORMED,
    HTTP_REJECTED,
    HTTP_STATUS_407,
    POLICY_DECLINED,
    SKIPPED_INPUT,
    SOCKS_AUTH_FAILURE,
    SOCKS_MALFORMED,
    SOCKS_REJECTED,
    TLS_CERTIFICATE,
    TLS_HANDSHAKE,
    TLS_TIMEOUT,
    UNSUPPORTED_PROTOCOL,
)
from proxyaggregator.health.models import (
    CheckStage,
    HealthCheckResult,
    HealthStatus,
)
from proxyaggregator.health.policy import TargetPolicy
from proxyaggregator.health.runner import (
    HealthEntry,
    HealthRunner,
    protocol_uses_tls,
)

__all__ = [
    "CONNECTION_ERROR",
    "CONNECTION_REFUSED",
    "CONNECTION_TIMEOUT",
    "CONNECTION_UNREACHABLE",
    "DNS_FAILURE",
    "DNS_UNAVAILABLE",
    "HTTP_MALFORMED",
    "HTTP_REJECTED",
    "HTTP_STATUS_407",
    "POLICY_DECLINED",
    "SKIPPED_INPUT",
    "SOCKS_AUTH_FAILURE",
    "SOCKS_MALFORMED",
    "SOCKS_REJECTED",
    "TLS_CERTIFICATE",
    "TLS_HANDSHAKE",
    "TLS_TIMEOUT",
    "UNSUPPORTED_PROTOCOL",
    "CheckStage",
    "HealthCheckResult",
    "HealthEntry",
    "HealthRunner",
    "HealthStatus",
    "TargetPolicy",
    "protocol_uses_tls",
]
