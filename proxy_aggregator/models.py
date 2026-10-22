"""Shared data models for proxy configurations and run results."""
from __future__ import annotations

import dataclasses
import enum
import time
from typing import Any, Dict, List, Optional


class Protocol(str, enum.Enum):
    VLESS = "vless"
    VMESS = "vmess"
    TROJAN = "trojan"
    SHADOWSOCKS = "shadowsocks"
    HYSTERIA2 = "hysteria2"
    SOCKS = "socks"
    UNKNOWN = "unknown"


@dataclasses.dataclass(frozen=True, eq=False, order=False)
class ConfigItem:
    """A single proxy configuration."""
    link: str
    protocol: Protocol
    fingerprint: str  # canonical hash for dedup

    # Optional metadata, populated by enrichment
    country_code: Optional[str] = None
    remark: str = ""

    # Verification results (populated by pipeline)
    verified_rounds: int = 0
    total_rounds: int = 0
    median_latency_ms: Optional[float] = None
    fast_threshold_ms: int = 800
    secure: bool = False

    def __eq__(self, other):
        if not isinstance(other, ConfigItem):
            return NotImplemented
        return self.fingerprint == other.fingerprint

    def __hash__(self):
        return hash(self.fingerprint)

    def __lt__(self, other):
        if not isinstance(other, ConfigItem):
            return NotImplemented
        return self.fingerprint < other.fingerprint

    # Allow field updates via object.__setattr__ for pipeline modifications
    def set_verified(self, rounds: int, total: int, latency_ms: Optional[float]) -> "ConfigItem":
        """Return a new instance with verification fields set."""
        return object.__setattr__(self, "verified_rounds", rounds) or self

    @property
    def is_verified(self) -> bool:
        return self.total_rounds > 0 and self.verified_rounds == self.total_rounds

    @property
    def is_fast(self) -> bool:
        return self.is_verified and self.median_latency_ms is not None \
            and self.median_latency_ms < self.fast_threshold_ms

    @property
    def category_tags(self) -> List[str]:
        tags = ["all"]
        if self.is_verified:
            tags.append("verified")
        if self.is_fast:
            tags.append("fast")
        if self.secure:
            tags.append("secure")
        return tags

    def to_link(self) -> str:
        return self.link

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class SourceResult:
    """Outcome of fetching one source URL."""
    url: str
    status: str = "ok"  # "ok" | "empty" | "fail"
    http_code: Optional[int] = None
    duration_sec: float = 0.0
    config_count: int = 0
    error: Optional[str] = None
    retry_count: int = 0


@dataclasses.dataclass
class RunSummary:
    """Overall pipeline run summary, written to health.json."""
    started_at: float = 0.0
    elapsed_sec: float = 0.0
    sources: List[SourceResult] = dataclasses.field(default_factory=list)
    total_configs: int = 0
    unique_configs: int = 0
    duplicates_removed: int = 0
    broken_removed: int = 0
    verified_count: int = 0
    fast_count: int = 0
    secure_count: int = 0
    top_count: int = 0
    cascade: Optional[Dict[str, Any]] = None
    runner_exit_country: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)
