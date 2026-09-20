"""Application settings loaded from environment / .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(key: str, default: str = "") -> str:
    """Read an environment variable."""
    return os.environ.get(f"PA_{key}", default)


@dataclass(frozen=True)
class Settings:
    """Application settings.

    All values are read from environment variables with the PA_ prefix.
    Example: PA_DATABASE_URL, PA_GITHUB_TOKEN, etc.
    """

    database_url: str = field(
        default_factory=lambda: _env("DATABASE_URL", "sqlite:///proxyaggregator.db")
    )
    github_token: str = field(default_factory=lambda: _env("GITHUB_TOKEN"))
    github_repo: str = field(default_factory=lambda: _env("GITHUB_REPO"))
    geoip_db_path: str = field(default_factory=lambda: _env("GEOIP_DB_PATH", "GeoLite2-City.mmdb"))
    health_check_timeout: int = field(
        default_factory=lambda: int(_env("HEALTH_CHECK_TIMEOUT", "10"))
    )
    health_check_concurrency: int = field(
        default_factory=lambda: int(_env("HEALTH_CHECK_CONCURRENCY", "50"))
    )
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
