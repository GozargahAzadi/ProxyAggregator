"""Pydantic schema for data sources."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from pydantic import BaseModel, Field


class SourceSchema(BaseModel):
    """Domain model for a proxy data source."""

    name: str = Field(..., min_length=1, description="Source name")
    source_type: str = Field(
        ..., min_length=1, description="Type (telegram, github, http, rss)"
    )
    url: str = Field(..., min_length=1, description="Source URL")

    last_fetched_at: datetime | None = Field(
        default=None, description="Last successful fetch timestamp"
    )
    config_count: int = Field(default=0, ge=0, description="Number of configs from this source")

    model_config = {"frozen": True}
