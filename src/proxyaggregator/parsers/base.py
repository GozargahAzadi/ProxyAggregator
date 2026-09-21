"""Base parser interface and result models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum

from pydantic import BaseModel, Field


class ParseStatus(StrEnum):
    """Status of a parse operation."""

    SUCCESS = "success"
    ERROR = "error"


class ParseResult(BaseModel):
    """Normalized result of parsing a single proxy URI."""

    protocol: str = Field(..., min_length=1)
    host: str = Field(..., min_length=1)
    port: int = Field(..., ge=1, le=65535)
    raw_uri: str = Field(..., min_length=1)

    user: str | None = Field(default=None)
    password: str | None = Field(default=None)
    sni: str | None = Field(default=None)
    network: str | None = Field(default=None)
    tls: str | None = Field(default=None)
    path: str | None = Field(default=None)
    host_header: str | None = Field(default=None)
    fragment: str | None = Field(default=None)
    service_name: str | None = Field(default=None)
    flow: str | None = Field(default=None)
    method: str | None = Field(default=None)
    obfs: str | None = Field(default=None)
    obfs_password: str | None = Field(default=None)

    model_config = {"frozen": True}


class ParseError(BaseModel):
    """Structured error from a failed parse attempt."""

    protocol: str = Field(..., min_length=1)
    error: str = Field(..., min_length=1)
    raw_uri: str = Field(..., min_length=1)

    model_config = {"frozen": True}


class BaseParser(ABC):
    """Contract that every protocol parser must satisfy."""

    @property
    @abstractmethod
    def supported_protocol(self) -> str:
        """Return the protocol string this parser handles."""

    @abstractmethod
    def parse(self, uri: str) -> ParseResult | ParseError:
        """Parse a single proxy URI and return a result or error."""
