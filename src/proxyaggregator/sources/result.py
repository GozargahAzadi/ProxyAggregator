"""Source collection result representation."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum

from pydantic import BaseModel, Field


class SourceResultStatus(StrEnum):
    """Status of a source collection operation."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class SourceResult(BaseModel):
    """Result of collecting raw content from a single source.

    This carries the raw output of a fetch operation to the next pipeline
    stage.  It does NOT contain parsed proxy configurations.
    """

    source_name: str = Field(..., description="Human-readable source identifier")
    source_type: str = Field(..., description="Collector type that produced this result")
    source_url: str = Field(..., description="URL that was fetched")
    status: SourceResultStatus = Field(..., description="Outcome of the fetch")
    content: str = Field(default="", description="Raw fetched content")
    status_code: int | None = Field(default=None, description="HTTP status code when applicable")
    fetched_at: datetime = Field(..., description="When the fetch was performed")
    content_length: int = Field(default=-1, description="Byte length of content")
    error: str | None = Field(default=None, description="Error message when status is not SUCCESS")

    model_config = {"frozen": True}

    @property
    def is_success(self) -> bool:
        return self.status == SourceResultStatus.SUCCESS
