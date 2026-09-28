"""Phase 22 production run summary.

Renders one production publication run as a compact, credential-free GitHub
Actions job summary. This module is **observability only**: it never changes
collection, parsing, deduplication, health checking, scoring, GeoIP enrichment,
or publication behaviour, and it can never fail a publication.

Every number rendered here comes from a source of truth that already exists:

- the freshness gate's decision, threshold, previous publication time, and age
  (the gate already writes these to ``$GITHUB_OUTPUT``; see
  :mod:`proxyaggregator.publishing.freshness`),
- :class:`proxyaggregator.pipeline.PipelineStats`, which the pipeline already
  computes and logs. The Phase 22 wiring serialises that same object to a JSON
  file (outside ``output/``, so it is never published) instead of recomputing
  anything,
- the release manifest, read through the existing
  :func:`proxyaggregator.publishing.publisher.verify_release` — the same call
  the workflow's output guard already makes. No release rule is duplicated here.

Nothing is estimated. A value that is unavailable is rendered as
:data:`UNAVAILABLE` rather than guessed, and a run that did not execute the
pipeline reports ``not run`` instead of showing counts from a previous release.

No proxy URI, host, credential, or source URL is ever included: only counters
and artifact names already present in the deterministic manifest.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from proxyaggregator.publishing.freshness import (
    PUBLISHED_AT_FILENAME,
    format_age,
    read_published_at,
    serialize_published_at,
)
from proxyaggregator.publishing.models import SubscriptionFormat
from proxyaggregator.publishing.publisher import (
    COUNTRIES_DIR,
    DEFAULT_FILENAMES,
    ReleaseVerificationError,
    SubscriptionRelease,
    default_protocol_filename,
    verify_release,
)
from proxyaggregator.publishing.serializer import SUPPORTED_PROTOCOLS

if TYPE_CHECKING:
    from collections.abc import Mapping

#: Rendered in place of any value whose source of truth is unavailable.
UNAVAILABLE = "unavailable"

#: Terminal run states, deliberately distinct so a skip can never be mistaken
#: for a failure and a discarded attempt can never be mistaken for a publish.
STATUS_SKIPPED = "SKIPPED"
STATUS_PUBLISHED = "PUBLISHED"
STATUS_DISCARDED = "DISCARDED"
STATUS_FAILED = "FAILED"

#: Sanity outcomes, mirroring the workflow's output-guard step.
SANITY_PASSED = "passed"
SANITY_FAILED = "failed"
SANITY_SKIPPED = "skipped"
#: The output guard produced no result (it never ran, or its output was lost).
#: Distinct from a derived value on purpose: after a failed pipeline ``output/``
#: still holds the *previous* release, so re-verifying it would prove nothing
#: about the release this run was supposed to produce.
SANITY_UNKNOWN = "unknown"

_SANITY_REPORTED = (SANITY_PASSED, SANITY_FAILED, SANITY_SKIPPED)

#: Counter name -> (label, stage-seconds key or None) in display order. The
#: keys are the existing ``PipelineStats`` field names; nothing is renamed or
#: derived. ``None`` means the row has no timing counterpart.
_COUNTER_ROWS: tuple[tuple[str, str, str | None], ...] = (
    ("sources_discovered", "Sources discovered", None),
    ("sources_fetched", "Sources fetched", None),
    ("parse_candidates", "Raw candidates", None),
    ("parsed_proxies", "Parsed", None),
    ("deduplicated_proxies", "Deduplicated", None),
    ("dns_successes", "DNS resolved", None),
    ("deduplicated_proxies", "Health checked", "health_seconds"),
    ("healthy_proxies", "Healthy", None),
    ("ranked_proxies", "Ranked", None),
    ("subscription_count", "Feeds built", None),
    ("published_artifacts", "Artifacts written", None),
)

_TIMING_ROWS: tuple[tuple[str, str], ...] = (
    ("collection_seconds", "collect"),
    ("parsing_seconds", "parse"),
    ("dedup_seconds", "dedup"),
    ("persist_enrich_seconds", "persist+geoip"),
    ("health_seconds", "health"),
    ("scoring_seconds", "score"),
    ("subscriptions_seconds", "feeds"),
    ("publish_seconds", "publish"),
)


@dataclass(frozen=True)
class RunSummary:
    """Everything one production run's summary is rendered from.

    Each field is supplied by the caller from an existing source of truth.
    ``None``/empty means "unknown", which is rendered as
    :data:`UNAVAILABLE`; it is never replaced with a guess.
    """

    #: Trigger that started the run (``schedule``, ``repository_dispatch``, ...).
    event: str
    #: 1-based publication attempt, or ``None`` when the caller cannot tell.
    attempt: int | None
    #: Commit the release was built from.
    base_sha: str | None
    #: Freshness gate decision: ``RUN``, ``SKIP``, or ``None`` when unknown.
    decision: str | None
    #: Freshness threshold in minutes.
    threshold_minutes: int | None
    #: Age of the previous successful publication in seconds.
    age_seconds: int | None
    #: Previous successful publication time (RFC 3339 UTC), if any.
    previous_published_at: str | None
    #: Phase 21 stale-tree result: ``True`` raced, ``False`` did not, ``None``
    #: unknown (e.g. the gate skipped before the check).
    race: bool | None
    #: Output-guard outcome: ``passed``, ``failed``, or ``skipped``.
    sanity: str
    #: Whether the commit/push step reported that it published to ``main``.
    #: ``True`` published, ``False`` did not, ``None`` unknown (e.g. a step that
    #: never ran). A run is only PUBLISHED when this is ``True``.
    published: bool | None
    #: Current on-disk ``output/published_at.json`` value, i.e. what a reader
    #: of ``main`` would see. ``None`` when the file is absent or malformed.
    published_at: str | None
    #: Validated release entries, or ``None`` when the release is unreadable.
    release: tuple[SubscriptionRelease, ...] | None
    #: Reason the release could not be read (never an exception traceback).
    release_error: str | None
    #: Serialised :class:`~proxyaggregator.pipeline.PipelineStats`, or ``None``
    #: when the pipeline did not run or wrote no stats file.
    stats: Mapping[str, Any] | None

    @property
    def status(self) -> str:
        """Terminal state of the run.

        The freshness ``SKIP`` is decided first, then a Phase 21 race, then an
        explicit guard failure, and only a *confirmed* push may report a
        publication. A run that reached ``RUN`` without a publication the push
        step confirmed is a failure: a run must never silently end without
        publishing, and must never claim a publication it cannot prove.
        """
        if self.decision == "SKIP":
            return STATUS_SKIPPED
        if self.race:
            return STATUS_DISCARDED
        if self.sanity == SANITY_FAILED:
            return STATUS_FAILED
        if self.published is True:
            return STATUS_PUBLISHED
        return STATUS_FAILED

    @property
    def did_publish(self) -> bool:
        """Whether this attempt published a release.

        Derived from :attr:`status` rather than from a step output, so a
        skipped or raced attempt can never report that it published.
        """
        return self.status == STATUS_PUBLISHED

    @property
    def pipeline_ran(self) -> bool:
        """Whether the pipeline actually executed in this attempt."""
        return self.decision == "RUN"


def load_pipeline_stats(path: str | Path | None) -> dict[str, Any] | None:
    """Read a serialised :class:`~proxyaggregator.pipeline.PipelineStats`.

    Returns ``None`` for a missing path, a missing file, unreadable bytes,
    invalid JSON, or a payload that is not a JSON object. Never raises, and
    never invents values.
    """
    if path is None:
        return None
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def read_release(
    output_dir: str | Path,
) -> tuple[tuple[SubscriptionRelease, ...] | None, str | None]:
    """Validate a release with the existing ``verify_release`` guard.

    Returns ``(entries, None)`` when the release is valid and
    ``(None, reason)`` when it is not. ``reason`` is the guard's own stable
    message, so the summary reports exactly what the output guard would have
    reported instead of re-implementing any release rule.
    """
    try:
        entries = tuple(verify_release(output_dir))
    except ReleaseVerificationError as exc:
        return None, str(exc)
    except OSError as exc:
        return None, exc.__class__.__name__
    return entries, None


def _short(sha: str | None, length: int = 8) -> str:
    if not sha:
        return UNAVAILABLE
    return sha[:length]


#: Tokens the workflow uses for "no value" when a step output is empty.
_BLANK_TOKENS = frozenset({"", "none", "n/a", "null", "unknown", "skipped"})


def parse_optional_int(raw: str | int | None) -> int | None:
    """Coerce a step-output string to ``int``, or ``None`` when blank.

    Accepts the gate's own ``n/a``/``none`` tokens so an absent freshness age
    is reported as unknown rather than as zero.
    """
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    if raw is None or raw.strip().lower() in _BLANK_TOKENS:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def parse_optional_bool(raw: str | bool | None) -> bool | None:
    """Coerce a step-output string to ``bool``, or ``None`` when unknown.

    ``yes``/``true``/``1`` are ``True``; ``no``/``false``/``0`` are ``False``;
    an empty, ``none``, ``n/a``, or unrecognised value is ``None`` so the
    Phase 21 race result is never invented.
    """
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return None
    token = raw.strip().lower()
    if token in {"yes", "true", "1"}:
        return True
    if token in {"no", "false", "0"}:
        return False
    return None


def _number(value: Any) -> str:
    """Render one counter, or ``unavailable`` when it is missing/invalid."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return UNAVAILABLE
    return f"{value:,}"


def _seconds(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return UNAVAILABLE
    return f"{value:.1f}s"


def country_codes(entries: tuple[SubscriptionRelease, ...]) -> tuple[str, ...]:
    """Country codes that have at least one published feed.

    Derived from the manifest's ``countries/<CC>/<file>`` shape. The generated
    ``countries/README.md`` index has no country segment and is excluded.
    """
    codes = {
        entry.filename.split("/")[1]
        for entry in entries
        if len(entry.filename.split("/")) == 3 and entry.filename.split("/")[0] == COUNTRIES_DIR
    }
    return tuple(sorted(codes))


def protocol_counts(entries: tuple[SubscriptionRelease, ...]) -> tuple[tuple[str, int], ...]:
    """Per-protocol published proxy counts.

    Read from the root-level plain protocol feeds (``vless.txt``,
    ``shadowsocks.txt``, ...), which is the deterministic published count for
    each protocol. The combined feed and the base64 mirrors of the same
    protocol are intentionally not summed: they are the same proxies in a
    different encoding.
    """
    by_name = {entry.filename: entry for entry in entries}
    counts: list[tuple[str, int]] = []
    for protocol in SUPPORTED_PROTOCOLS:
        entry = by_name.get(default_protocol_filename(protocol, SubscriptionFormat.PLAIN))
        if entry is not None:
            counts.append((protocol, entry.count))
    return tuple(counts)


def total_published_proxies(entries: tuple[SubscriptionRelease, ...]) -> int | None:
    """Proxy count of the combined feed, or ``None`` when it is absent."""
    for entry in entries:
        if entry.filename == DEFAULT_FILENAMES[SubscriptionFormat.JSON]:
            return entry.count
    return None


def _table(rows: list[tuple[str, str]], *, right_align: bool = False) -> list[str]:
    if not rows:
        return []
    separator = "| --- | ---: |" if right_align else "| --- | --- |"
    lines = [f"| {rows[0][0]} | {rows[0][1]} |", separator]
    lines.extend(f"| {label} | {value} |" for label, value in rows[1:])
    return lines


def render_run_summary(summary: RunSummary) -> str:
    """Render one run as GitHub-flavoured markdown.

    Section order is fixed so consecutive runs are visually comparable. A
    section is omitted when the run did not produce the data for it, rather
    than being filled with zeros.
    """
    status = summary.status
    lines: list[str] = [f"## Production Run — {status}", ""]
    lines.extend(
        _table(
            [
                ("Trigger", f"`{summary.event}`" if summary.event else UNAVAILABLE),
                (
                    "Attempt",
                    str(summary.attempt) if summary.attempt is not None else UNAVAILABLE,
                ),
                ("Base commit", f"`{_short(summary.base_sha)}`"),
                ("Status", f"**{status}**"),
            ]
        )
    )
    lines.append("")

    threshold = (
        f"{summary.threshold_minutes}m" if summary.threshold_minutes is not None else UNAVAILABLE
    )
    age = format_age(summary.age_seconds) if summary.age_seconds is not None else UNAVAILABLE
    previous = summary.previous_published_at or "none (no previous publication)"
    lines.append("### Freshness")
    lines.append("")
    lines.extend(
        _table(
            [
                ("Threshold", threshold),
                ("Decision", summary.decision or UNAVAILABLE),
                ("Previous publication", previous),
                ("Previous age", age),
            ]
        )
    )
    lines.append("")

    if not summary.pipeline_ran:
        lines.append("### Pipeline")
        lines.append("")
        lines.append(
            f"Not executed — freshness decision was "
            f"{summary.decision or UNAVAILABLE}, so no pipeline metrics exist for this run."
        )
        lines.append("")
    else:
        lines.append("### Pipeline")
        lines.append("")
        if summary.stats is None:
            lines.append("Pipeline statistics unavailable (no stats file was written).")
        else:
            dns_ok = _number(summary.stats.get("dns_successes"))
            dns_attempts = _number(summary.stats.get("dns_attempts"))
            rows = [
                (label, _number(summary.stats.get(key))) for key, label, _timing in _COUNTER_ROWS
            ]
            dns_row = next(
                (i for i, (_k, label, _t) in enumerate(_COUNTER_ROWS) if label == "DNS resolved"),
                None,
            )
            if dns_row is not None:
                rows[dns_row] = ("DNS resolved", f"{dns_ok} / {dns_attempts}")
            lines.extend(_table([("Metric", "Value"), *rows], right_align=True))
            total = summary.stats.get("total_seconds")
            if isinstance(total, (int, float)) and not isinstance(total, bool):
                lines.append("")
                lines.append(f"Total pipeline duration: {total:.1f}s ({format_age(int(total))}).")
            stages = [
                f"{label} {_seconds(summary.stats.get(key))}"
                for key, label in _TIMING_ROWS
                if summary.stats.get(key) is not None
            ]
            if stages:
                lines.append("")
                lines.append("Stage durations: " + " · ".join(stages) + ".")
        lines.append("")

    lines.append("### Output")
    lines.append("")
    if summary.status == STATUS_SKIPPED:
        lines.append("Not generated — the previous committed release is unchanged by this run.")
        lines.append("")
    elif summary.sanity == SANITY_UNKNOWN:
        lines.append(
            "Not verified — the output guard produced no result for this attempt, and "
            "the previous release is not this run's output."
        )
        lines.append("")
    elif summary.release is None:
        lines.append(f"Release could not be validated: {summary.release_error or UNAVAILABLE}.")
        lines.append("")
    else:
        if summary.status == STATUS_DISCARDED:
            lines.append(
                "> These figures describe the **discarded** release built from a stale "
                "tree. It was not published."
            )
            lines.append("")
        entries = summary.release
        protocols = protocol_counts(entries)
        protocol_text = (
            ", ".join(f"{name} {count}" for name, count in protocols) if protocols else UNAVAILABLE
        )
        total = total_published_proxies(entries)
        lines.extend(
            _table(
                [
                    ("Artifacts", f"{len(entries):,}"),
                    ("Countries", f"{len(country_codes(entries)):,}"),
                    (
                        "Published proxies",
                        f"{total:,}" if total is not None else UNAVAILABLE,
                    ),
                    ("Protocols", protocol_text),
                ]
            )
        )
        lines.append("")

    lines.append("### Release sanity")
    lines.append("")
    if summary.sanity == SANITY_SKIPPED:
        checks = "not executed — the freshness gate skipped the publication pipeline"
    elif summary.sanity == SANITY_UNKNOWN:
        checks = "not reported — the output guard produced no result for this attempt"
    else:
        checks = (
            "manifest valid; every listed artifact present with the recorded "
            "byte size and SHA-256; at least one non-empty feed"
        )
    lines.extend(
        _table(
            [
                (
                    "Structural verification",
                    UNAVAILABLE if summary.sanity == SANITY_UNKNOWN else summary.sanity,
                ),
                ("Checks", checks),
            ]
        )
    )
    lines.append("")

    if summary.race is True:
        race_text = "yes — release discarded, nothing published, timestamp not advanced"
    elif summary.race is False:
        race_text = "no — base commit was still origin/main"
    else:
        race_text = UNAVAILABLE
    if summary.published_at is None:
        published_at = UNAVAILABLE
    elif summary.did_publish:
        published_at = f"{summary.published_at} (advanced by this run)"
    else:
        published_at = f"{summary.published_at} (unchanged by this run)"
    if summary.published is True:
        confirmation = "confirmed by the commit/push step"
    elif summary.published is False:
        confirmation = "not published by the commit/push step"
    else:
        confirmation = UNAVAILABLE
    lines.append("### Publication")
    lines.append("")
    lines.extend(
        _table(
            [
                ("Race (Phase 21)", race_text),
                ("Published this run", "yes" if summary.did_publish else "no"),
                ("Push result", confirmation),
                ("published_at.json", published_at),
            ]
        )
    )
    lines.append("")
    return "\n".join(lines)


def build_run_summary(
    *,
    event: str,
    output_dir: str | Path,
    stats_path: str | Path | None = None,
    attempt: int | None = None,
    base_sha: str | None = None,
    decision: str | None = None,
    threshold_minutes: int | None = None,
    age_seconds: int | None = None,
    previous_published_at: str | None = None,
    race: bool | None = None,
    sanity: str | None = None,
    published: bool | None = None,
) -> RunSummary:
    """Assemble a :class:`RunSummary` from the existing sources of truth.

    The release is read with :func:`read_release` (the same ``verify_release``
    call the workflow's output guard makes) only when the pipeline actually
    ran, so a freshness ``SKIP`` never presents the previous release as this
    run's output. ``output/published_at.json`` is read from disk, so the
    reported timestamp is exactly what a reader of ``main`` would see.
    """
    ran = decision == "RUN"
    if not ran:
        resolved_sanity = SANITY_SKIPPED
    elif sanity in _SANITY_REPORTED:
        resolved_sanity = sanity
    elif sanity is not None:
        # The caller reported that the guard produced no result. ``output/``
        # then still holds the previous release, so it is neither verified nor
        # reported: a stale release must never be presented as this run's.
        resolved_sanity = SANITY_UNKNOWN
    else:
        resolved_sanity = None
    verified = ran and resolved_sanity is not SANITY_UNKNOWN
    entries, error = read_release(output_dir) if verified else (None, None)
    if resolved_sanity is None:
        resolved_sanity = SANITY_PASSED if entries is not None else SANITY_FAILED
    recorded = read_published_at(Path(output_dir) / PUBLISHED_AT_FILENAME)
    return RunSummary(
        event=event,
        attempt=attempt,
        base_sha=base_sha,
        decision=decision,
        threshold_minutes=threshold_minutes,
        age_seconds=age_seconds,
        previous_published_at=previous_published_at,
        race=race,
        sanity=resolved_sanity,
        published=published,
        published_at=None if recorded is None else serialize_published_at(recorded),
        release=entries,
        release_error=error,
        stats=load_pipeline_stats(stats_path) if ran else None,
    )


def write_run_summary(summary: RunSummary, target: str | Path | None) -> str:
    """Render the summary and append it to ``target`` (or return it).

    ``target`` is the GitHub Actions ``$GITHUB_STEP_SUMMARY`` path. When it is
    ``None`` the markdown is only returned, so a local run is unaffected.
    """
    markdown = render_run_summary(summary)
    if target is None:
        return markdown
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(markdown + "\n")
    return markdown


__all__ = [
    "SANITY_FAILED",
    "SANITY_PASSED",
    "SANITY_SKIPPED",
    "SANITY_UNKNOWN",
    "STATUS_DISCARDED",
    "STATUS_FAILED",
    "STATUS_PUBLISHED",
    "STATUS_SKIPPED",
    "UNAVAILABLE",
    "RunSummary",
    "build_run_summary",
    "country_codes",
    "load_pipeline_stats",
    "parse_optional_bool",
    "parse_optional_int",
    "protocol_counts",
    "read_release",
    "render_run_summary",
    "total_published_proxies",
    "write_run_summary",
]
