"""Stable, sanitized health check error codes.

Every value in this module is a short, stable token. They are intentionally
free of free-form exception text so that credentials, hostnames, or raw URIs
never leak into stored error messages or logs.
"""

# --- Connection level ---
CONNECTION_REFUSED = "connection.refused"
CONNECTION_TIMEOUT = "connection.timeout"
CONNECTION_UNREACHABLE = "connection.unreachable"
CONNECTION_ERROR = "connection.error"

# --- Resolution ---
DNS_FAILURE = "dns.failure"

# --- TLS ---
TLS_HANDSHAKE = "tls.handshake"
TLS_CERTIFICATE = "tls.certificate"
TLS_TIMEOUT = "tls.timeout"

# --- SOCKS ---
SOCKS_AUTH_FAILURE = "socks.auth"
SOCKS_REJECTED = "socks.rejected"
SOCKS_MALFORMED = "socks.malformed"

# --- HTTP proxy ---
HTTP_STATUS_407 = "http.status.407"
HTTP_REJECTED = "http.rejected"
HTTP_MALFORMED = "http.malformed"

# --- Policy / input ---
POLICY_DECLINED = "policy.declined"
DNS_UNAVAILABLE = "dns.unavailable"
UNSUPPORTED_PROTOCOL = "protocol.unsupported"
SKIPPED_INPUT = "skipped.input"
