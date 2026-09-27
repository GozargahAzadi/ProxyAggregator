"""Freshness gate for the scheduled production publisher (Phase 18).

The scheduled publish workflow triggers on a ``*/5`` cron but must *publish*
at most approximately once every 15 minutes. Every trigger first asks this
module how old the last *successful* publication is; when the previous
publication is younger than the configured threshold the expensive pipeline is
skipped entirely (the job still ends green).

Timestamps:

- The release ``manifest.json`` is deliberately timestamp-free (deterministic
  release contract), so the publication time is carried by a separate,
  workflow-written file: ``output/published_at.json``. The pipeline never
  writes it; only the successful-publish step of the workflow does, so a
  failed run can never advance the gate and scheduled runs keep retrying.
- ``now`` is always a tz-aware UTC ``datetime``; naive timestamps are treated
  as UTC, so decisions are timezone-safe.

The decision is a pure function of ``(published_at, now, threshold)`` and is
fully deterministic for tests; no wall clock is read during the decision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from proxyaggregator.publishing.publisher import write_artifact

#: Committed file that records the timestamp of the last successful
#: publication. It lives inside ``output/`` (already committed) and is written
#: only by the workflow's successful-publish step.
PUBLISHED_AT_FILENAME = "published_at.json"

#: Default gate threshold. Decisions run when ``age >= threshold``.
DEFAULT_FRESHNESS_THRESHOLD_MINUTES = 13


@dataclass(frozen=True)
class FreshnessDecision:
    """Outcome of one freshness gate evaluation (deterministic).

    ``run`` is the boolean that drives the workflow; ``decision`` is its
    SHOUTED form for logs and step outputs; ``reason`` is a stable token for
    diagnostics.
    """

    run: bool
    reason: str
    published_at: datetime | None
    now: datetime
    age_seconds: int | None

    @property
    def decision(self) -> str:
        return "RUN" if self.run else "SKIP"


def utc_now() -> datetime:
    """Return the current tz-aware UTC time (injected nowhere)."""
    return datetime.now(UTC)


def parse_published_at(text: str | None) -> datetime | None:
    """Parse ``{"published_at": "<RFC 3339 UTC>"}`` into a tz-aware datetime.

    ``None`` input, invalid JSON, a missing field, a non-string value, or an
    unparseable timestamp all return ``None`` (treated as "never published",
    which makes the gate run). Naive timestamps are interpreted as UTC.
    """
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    raw = payload.get("published_at")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value


def read_published_at(path: str | Path) -> datetime | None:
    """Read and parse the committed publication timestamp, or ``None``.

    Missing files, unreadable files, and malformed content all return
    ``None`` (safe: the gate will run).
    """
    try:
        return parse_published_at(Path(path).read_text(encoding="utf-8"))
    except OSError:
        return None


def serialize_published_at(value: datetime) -> str:
    """Format a timestamp as second-precision RFC 3339 UTC (``...Z``)."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def publish_decision(
    published_at: datetime | None,
    now: datetime,
    threshold_minutes: int = DEFAULT_FRESHNESS_THRESHOLD_MINUTES,
) -> FreshnessDecision:
    """Evaluate the freshness gate for one trigger.

    Rules:

    - no previous publication (``None``) -> RUN
    - age < threshold -> SKIP (a recent successful publication is still fresh)
    - age >= threshold -> RUN (a new publication is due)

    A timestamp in the future or a non-positive threshold is safe by
    construction: a future timestamp reads as "fresh" (SKIP) and the age is
    capped at the strict comparison, while ``threshold_minutes <= 0`` makes
    every run RUN (never used by the workflow; kept for explicit callers).
    """
    threshold_seconds = max(threshold_minutes * 60, 0)
    if published_at is None:
        return FreshnessDecision(
            run=True,
            reason="no_previous_publication",
            published_at=None,
            now=now,
            age_seconds=None,
        )
    age_seconds = max(int((now - published_at).total_seconds()), 0)
    run = age_seconds >= threshold_seconds
    reason = "threshold_met" if run else "fresh"
    return FreshnessDecision(
        run=run, reason=reason, published_at=published_at, now=now, age_seconds=age_seconds
    )


def format_age(seconds: int | None) -> str:
    """Render an age as ``10m 03s`` (or ``Xh Ym Zs`` past an hour)."""
    if seconds is None:
        return "n/a"
    hours, remainder = divmod(seconds, 3600)
    minutes, remaining = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {remaining:02d}s"
    return f"{minutes}m {remaining:02d}s"


def render_decision_log(decision: FreshnessDecision) -> str:
    """Render the compact, diagnosable gate log shown by the workflow."""
    published = (
        serialize_published_at(decision.published_at)
        if decision.published_at is not None
        else "not found"
    )
    lines = [
        "[Freshness Gate]",
        f"Last successful publication: {published}",
        f"Current time: {serialize_published_at(decision.now)}",
        f"Age: {format_age(decision.age_seconds)}",
        f"Threshold: {DEFAULT_FRESHNESS_THRESHOLD_MINUTES}m",
        f"Decision: {decision.decision}",
    ]
    if decision.reason == "no_previous_publication":
        lines.append("Reason: no previous successful publication found")
    elif decision.reason == "forced":
        lines.append("Reason: manual dispatch forces a run")
    return "\n".join(lines)


def record_published_at(path: str | Path, now: datetime) -> Path:
    """Persist ``now`` as the publication timestamp into ``path``.

    Written as a deterministic JSON document via the atomic artifact writer so
    a failed write can never leave a torn file. Only the workflow's
    successful-publish step calls this: failed runs never advance the gate.
    """
    target = Path(path)
    payload = json.dumps(
        {"published_at": serialize_published_at(now)}, ensure_ascii=False, sort_keys=True
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    return write_artifact(target.name, payload, target.parent)


def default_published_at_path() -> Path:
    """Default committed timestamp file relative to the working directory."""
    return Path("output") / PUBLISHED_AT_FILENAME
