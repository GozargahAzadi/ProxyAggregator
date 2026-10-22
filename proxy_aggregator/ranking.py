"""Ranking — deterministic ordering by median latency with stable tie-breaking."""
from __future__ import annotations

from typing import List

from .models import ConfigItem


def rank_by_latency(configs: List[ConfigItem],
                    top_n: int = 100) -> List[ConfigItem]:
    """Return the top-N fastest verified configs.

    Sorting key: (median_latency_ms is not None, median_latency_ms asc).
    Tie-break: by fingerprint (alphabetical) for determinism.
    """
    eligible = [c for c in configs if c.median_latency_ms is not None]
    eligible.sort(key=lambda c: (
        0 if c.median_latency_ms is not None else 1,
        c.median_latency_ms if c.median_latency_ms is not None else float("inf"),
        c.fingerprint,
    ))
    return eligible[:top_n]


def compute_statistics(configs: List[ConfigItem]) -> dict:
    """Compute latency statistics for verified configs."""
    latencies = [c.median_latency_ms for c in configs
                 if c.median_latency_ms is not None]
    if not latencies:
        return {"count": 0, "min": None, "median": None, "max": None}
    latencies.sort()
    n = len(latencies)
    return {
        "count": n,
        "min": round(latencies[0], 1),
        "median": round(latencies[n // 2], 1),
        "max": round(latencies[-1], 1),
    }
