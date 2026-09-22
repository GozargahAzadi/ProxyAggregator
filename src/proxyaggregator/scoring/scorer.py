"""Deterministic, latency-only proxy scoring and ranking (Phase 7).

Approved Phase 7 contract (see ``docs/SCORING.md``):

- Eligibility: latest health ``status == OK`` AND a non-null ``latency_ms``.
- Score: the ONLY component is the latency score
  ``tau / (tau + min(latency_ms, MAX_LATENCY_MS))``.
- Ranking order: ``score DESC``, ``latency_ms ASC``, ``content_hash ASC``,
  ``proxy_config_id ASC`` — a total, repeatable order.
- No freshness/decay, no historical stability, no protocol/country/GeoIP
  weighting, and no score persistence.

This module is pure: it performs no network I/O and no database access.
DB-shaped rows may be passed into :func:`latest_health_check` /
:func:`build_rank_candidates`; the data is read, never queried here.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from proxyaggregator.health.models import HealthStatus
from proxyaggregator.scoring.models import ProxyScore, RankCandidate

if TYPE_CHECKING:
    from collections.abc import Sequence

    from proxyaggregator.db.models import HealthCheckORM, ProxyConfigORM

# Approved fixed constants (not configurable in Phase 7).
TAU_MS = 1000.0
MAX_LATENCY_MS = 3000.0


def latency_score(latency_ms: float) -> float:
    """Convert a measured latency into the Phase 7 score.

    ``tau / (tau + min(latency_ms, MAX_LATENCY_MS))`` with ``tau = 1000.0`` and
    a hard cap of ``3000.0`` ms. The result range is ``(0.0, 1.0]``: 0 ms → 1.0,
    >= 3000 ms → 0.25.

    Raises:
        ValueError: for a non-finite, negative, or None latency. Invalid input
            never produces a valid score.
    """
    if latency_ms is None:
        raise ValueError("latency_ms must be a finite number >= 0")
    if not isinstance(latency_ms, (int, float)) or not math.isfinite(latency_ms):
        raise ValueError(f"latency_ms must be finite, got {latency_ms!r}")
    if latency_ms < 0:
        raise ValueError(f"latency_ms must be >= 0, got {latency_ms!r}")
    capped = min(latency_ms, MAX_LATENCY_MS)
    return TAU_MS / (TAU_MS + capped)


def latest_health_check(checks: Sequence) -> HealthCheckORM | None:
    """Return the newest health check using ``(checked_at, id)`` ordering.

    ``checked_at`` descending with ``id`` as the deterministic fallback for
    identical timestamps — the same semantics the repository applies when
    querying health history. ``None`` when the sequence is empty.
    """
    if not checks:
        return None
    return max(checks, key=lambda check: (check.checked_at, check.id))


def build_rank_candidates(
    proxy_configs: Sequence[ProxyConfigORM],
    health_checks: Sequence[HealthCheckORM],
) -> list[RankCandidate]:
    """Join proxy configs with their latest health check into candidates.

    A proxy with no health check is skipped (no evidence → not rankable).
    Rows whose ``status`` is missing are skipped rather than guessed. All
    selection is in-memory over data already provided by the caller.
    """
    latest: dict[int, HealthCheckORM] = {}
    for check in health_checks:
        current = latest.get(check.proxy_config_id)
        if check.status is None:
            continue
        if current is None or (check.checked_at, check.id) > (current.checked_at, current.id):
            latest[check.proxy_config_id] = check

    candidates: list[RankCandidate] = []
    for config in proxy_configs:
        check = latest.get(config.id)
        if check is None or check.status is None:
            continue
        candidates.append(
            RankCandidate(
                proxy_config_id=config.id,
                content_hash=config.content_hash,
                status=HealthStatus(check.status),
                latency_ms=check.latency_ms,
            )
        )
    return candidates


def score_proxy(
    proxy_config_id: int,
    content_hash: str,
    status: HealthStatus,
    latency_ms: float | None,
) -> ProxyScore:
    """Score one proxy endpoint from its latest health outcome.

    Only ``status == OK`` with a non-null, valid latency yields an eligible,
    scored result. Any other outcome is ineligible with no score.
    """
    if status is not HealthStatus.OK or latency_ms is None:
        return ProxyScore(
            proxy_config_id=proxy_config_id,
            content_hash=content_hash,
            status=status,
            eligible=False,
        )
    return ProxyScore(
        proxy_config_id=proxy_config_id,
        content_hash=content_hash,
        status=status,
        eligible=True,
        score=latency_score(latency_ms),
        latency_ms=latency_ms,
    )


def rank_proxies(candidates: Sequence[RankCandidate]) -> list[ProxyScore]:
    """Rank eligible proxies deterministically, lowest latency first.

    Order: ``score DESC`` → ``latency_ms ASC`` → ``content_hash ASC`` →
    ``proxy_config_id ASC``. Only eligible proxies are returned. The input
    order never affects the output order.
    """
    scored = [
        score_proxy(
            proxy_config_id=c.proxy_config_id,
            content_hash=c.content_hash,
            status=c.status,
            latency_ms=c.latency_ms,
        )
        for c in candidates
    ]
    eligible = [result for result in scored if result.eligible]
    eligible.sort(key=lambda r: (-r.score, r.latency_ms, r.content_hash, r.proxy_config_id))
    return eligible
