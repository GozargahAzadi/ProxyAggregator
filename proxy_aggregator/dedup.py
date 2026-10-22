"""Deduplication — canonical-fingerprint based, preserving connection-relevant diffs."""
from __future__ import annotations

from typing import Dict, Iterable, List

from .models import ConfigItem


def deduplicate(configs: Iterable[ConfigItem]) -> List[ConfigItem]:
    """Remove exact duplicates based on fingerprint.

    Two ConfigItems with the same fingerprint are considered duplicates.
    Since ConfigItem is frozen and uses fingerprint in its equality,
    deduplication is simply: keep the first occurrence of each fingerprint.
    """
    seen: Dict[str, ConfigItem] = {}
    order: List[ConfigItem] = []
    for cfg in configs:
        if cfg.fingerprint not in seen:
            seen[cfg.fingerprint] = cfg
            order.append(cfg)
    return order


def dedup_stats(original: List[ConfigItem], deduped: List[ConfigItem]) -> Dict[str, int]:
    """Return counts of duplicates removed etc."""
    return {
        "original": len(original),
        "unique": len(deduped),
        "duplicates_removed": len(original) - len(deduped),
    }


def group_by_protocol(configs: List[ConfigItem]) -> Dict[str, List[ConfigItem]]:
    """Group configs by protocol for per-protocol feeds."""
    groups: Dict[str, List[ConfigItem]] = {}
    for cfg in configs:
        proto = cfg.protocol.value
        groups.setdefault(proto, []).append(cfg)
    # Sort each group by link for determinism
    for proto in groups:
        groups[proto].sort(key=lambda c: c.link)
    return groups


def filter_by_categories(configs: List[ConfigItem]) -> Dict[str, List[ConfigItem]]:
    """Partition configs into category buckets."""
    buckets: Dict[str, List[ConfigItem]] = {
        "all": [],
        "verified": [],
        "fast": [],
        "secure": [],
    }
    for cfg in configs:
        buckets["all"].append(cfg)
        if cfg.is_verified:
            buckets["verified"].append(cfg)
        if cfg.is_fast:
            buckets["fast"].append(cfg)
        if cfg.secure:
            buckets["secure"].append(cfg)
    return buckets
