"""Endpoint-based identity for proxy configurations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from proxyaggregator.parsers.base import ParseResult


class EndpointIdentity(BaseModel):
    """Normalized endpoint identity: protocol + host + port.

    This identifies the network endpoint, NOT the full configuration.
    Two configs on the same endpoint may have different credentials.
    """

    protocol: str = Field(..., min_length=1)
    host: str = Field(..., min_length=1)
    port: int = Field(..., ge=1, le=65535)

    model_config = {"frozen": True}


def endpoint_identity(config: ParseResult) -> EndpointIdentity:
    """Extract the normalized endpoint identity from a parsed config."""
    return EndpointIdentity(
        protocol=config.protocol,
        host=config.host.lower(),
        port=config.port,
    )
