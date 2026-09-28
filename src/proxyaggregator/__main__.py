"""ProxyAggregator CLI entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from proxyaggregator import __version__
from proxyaggregator.publishing import (
    DEFAULT_OUTPUT_DIR,
    build_demo_subscriptions,
    build_release_manifest,
    publish_subscriptions,
    write_release_manifest,
)
from proxyaggregator.publishing.summary import (
    SANITY_FAILED,
    SANITY_PASSED,
    SANITY_SKIPPED,
    build_run_summary,
    parse_optional_bool,
    parse_optional_int,
    write_run_summary,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proxyaggregator",
        description="ProxyAggregator - public V2Ray/proxy config aggregator.",
    )
    subparsers = parser.add_subparsers(dest="command")

    cmd_pipeline = subparsers.add_parser(
        "pipeline",
        help="Run the end-to-end production pipeline over configured sources.",
    )
    cmd_pipeline.add_argument(
        "--stats-file",
        default=None,
        help=(
            "Write the run's measured PipelineStats to this JSON file "
            "(used by the Phase 22 run summary; keep it outside output/)."
        ),
    )
    cmd_pipeline.set_defaults(handler=_cmd_pipeline)

    cmd_seed_sources = subparsers.add_parser(
        "seed-sources",
        help="Seed the sources table from the repository-controlled definition file.",
    )
    cmd_seed_sources.add_argument(
        "--sources-file",
        default=None,
        help="Source definition file (default: $PA_SOURCES_FILE, i.e. config/sources.json).",
    )
    cmd_seed_sources.set_defaults(handler=_cmd_seed_sources)

    sample = subparsers.add_parser(
        "sample-subscriptions",
        help="Generate demo subscription artifacts locally (no GitHub/network needed).",
    )
    sample.add_argument(
        "--output",
        default=None,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR!r}, relative to cwd).",
    )
    sample.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Emit at most this many unique proxies per feed (None = all).",
    )
    sample.set_defaults(handler=_cmd_sample_subscriptions)

    cmd_verify_geoip = subparsers.add_parser(
        "verify-geoip",
        help="Validate the GeoIP MMDB database used by the pipeline.",
    )
    cmd_verify_geoip.add_argument(
        "--path",
        default=None,
        help="Path to the MMDB file (default: $PA_GEOIP_DB_PATH).",
    )
    cmd_verify_geoip.set_defaults(handler=_cmd_verify_geoip)

    cmd_freshness = subparsers.add_parser(
        "freshness-gate",
        help="Decide whether a scheduled publish should run (Phase 18).",
    )
    cmd_freshness.add_argument(
        "--file",
        default=None,
        help="Path to the committed publication timestamp file (default: output/published_at.json).",
    )
    cmd_freshness.add_argument(
        "--threshold-minutes",
        type=int,
        default=13,
        help="Minimum age of the last publication before a run is due (default: 13).",
    )
    cmd_freshness.add_argument(
        "--force",
        action="store_true",
        help="Force Decision RUN (used by workflow_dispatch).",
    )
    cmd_freshness.set_defaults(handler=_cmd_freshness_gate)

    cmd_record = subparsers.add_parser(
        "record-publish",
        help="Record a successful publication timestamp (Phase 18).",
    )
    cmd_record.add_argument(
        "--file",
        default=None,
        help="Path to the committed publication timestamp file (default: output/published_at.json).",
    )
    cmd_record.set_defaults(handler=_cmd_record_publish)

    cmd_summary = subparsers.add_parser(
        "publish-summary",
        help="Render the production run summary into $GITHUB_STEP_SUMMARY (Phase 22).",
    )
    cmd_summary.add_argument(
        "--event",
        default=None,
        help="Trigger that started the run (default: $GITHUB_EVENT_NAME).",
    )
    cmd_summary.add_argument(
        "--attempt",
        default=None,
        help="1-based publication attempt number, when the caller knows it.",
    )
    cmd_summary.add_argument(
        "--base-sha",
        default=None,
        help="Commit the release was built from.",
    )
    cmd_summary.add_argument(
        "--decision",
        default=None,
        help="Freshness gate decision (RUN or SKIP); any other value is treated as unknown.",
    )
    cmd_summary.add_argument(
        "--threshold-minutes",
        default=None,
        help="Freshness threshold in minutes.",
    )
    cmd_summary.add_argument(
        "--age-seconds",
        default=None,
        help="Age of the previous successful publication in seconds.",
    )
    cmd_summary.add_argument(
        "--previous-published-at",
        default=None,
        help="Previous successful publication time (RFC 3339 UTC).",
    )
    cmd_summary.add_argument(
        "--race",
        default=None,
        help="Phase 21 stale-tree result: 'yes' raced, 'no' did not, blank unknown.",
    )
    cmd_summary.add_argument(
        "--sanity",
        default="auto",
        help=(
            f"Output-guard outcome ({SANITY_PASSED}, {SANITY_FAILED}, or "
            f"{SANITY_SKIPPED}). 'auto' (default) re-verifies the release; a "
            "blank or unrecognised value is reported as unavailable rather "
            "than re-deriving it."
        ),
    )
    cmd_summary.add_argument(
        "--published",
        default=None,
        help=(
            "Whether the commit/push step published to main: 'yes' confirmed, "
            "'no' not published, blank unknown. A run is only reported as "
            "PUBLISHED when this is 'yes'."
        ),
    )
    cmd_summary.add_argument(
        "--output",
        default=None,
        help=f"Output directory to read (default: {DEFAULT_OUTPUT_DIR!r}, relative to cwd).",
    )
    cmd_summary.add_argument(
        "--stats-file",
        default=None,
        help="Pipeline stats JSON written by `pipeline --stats-file`.",
    )
    cmd_summary.set_defaults(handler=_cmd_publish_summary)
    return parser


def _cmd_sample_subscriptions(args: argparse.Namespace) -> int:
    """Generate demo artifacts (no GitHub/network needed)."""
    output_dir = Path(args.output) if args.output else Path(DEFAULT_OUTPUT_DIR)
    feeds = build_demo_subscriptions(max_items=args.max_items)
    entries = publish_subscriptions(feeds, output_dir)
    manifest = build_release_manifest(entries)
    write_release_manifest(manifest, output_dir)
    print(manifest)
    return 0


def _cmd_pipeline(args: argparse.Namespace) -> int:
    """Run the production pipeline; non-zero exit on fatal failures."""
    from proxyaggregator.config.settings import Settings
    from proxyaggregator.pipeline import run_pipeline_cli

    settings = Settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )
    # Never leak fetched URLs/credentials from third-party network loggers.
    for logger_name in ("httpx", "httpcore", "h11", "http.client", "anyio"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    return run_pipeline_cli(stats_path=args.stats_file)


def _cmd_seed_sources(args: argparse.Namespace) -> int:
    """Seed the sources table; non-zero exit on validation/database failures."""
    from proxyaggregator.config.settings import Settings
    from proxyaggregator.seeding import run_seed_cli

    settings = Settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )
    return run_seed_cli(args.sources_file or settings.sources_file)


def _cmd_verify_geoip(args: argparse.Namespace) -> int:
    """Validate the GeoIP MMDB; non-zero with a clear error when unusable."""
    from proxyaggregator.config.settings import Settings
    from proxyaggregator.geoip.mmdb import GeoIpDatabaseError, validate_mmdb

    path = args.path or Settings().geoip_db_path
    try:
        database_type = validate_mmdb(path)
    except GeoIpDatabaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"GeoIP database OK: {database_type} ({path})")
    return 0


def _cmd_freshness_gate(args: argparse.Namespace) -> int:
    """Evaluate the freshness gate and print the decision (always exit 0).

    The decision is exposed to the workflow through ``$GITHUB_OUTPUT`` when the
    step runs in GitHub Actions (``decision=RUN``/``decision=SKIP``); every
    expensive downstream step is guarded with ``if: steps.freshness.outputs.
    decision == 'RUN'``, so a SKIP finishes the job green without running the
    pipeline.
    """
    import os

    from proxyaggregator.publishing.freshness import (
        DEFAULT_FRESHNESS_THRESHOLD_MINUTES,
        FreshnessDecision,
        default_published_at_path,
        publish_decision,
        read_published_at,
        render_decision_log,
        serialize_published_at,
        utc_now,
    )

    threshold = args.threshold_minutes or DEFAULT_FRESHNESS_THRESHOLD_MINUTES
    path = Path(args.file) if args.file else default_published_at_path()
    now = utc_now()
    published_at = None if args.force else read_published_at(path)
    if args.force:
        decision = FreshnessDecision(
            run=True,
            reason="forced",
            published_at=published_at,
            now=now,
            age_seconds=publish_decision(published_at, now, threshold).age_seconds,
        )
    else:
        decision = publish_decision(published_at, now, threshold)

    print(render_decision_log(decision), flush=True)

    outputs = os.environ.get("GITHUB_OUTPUT", "")
    if outputs:
        with open(outputs, "a", encoding="utf-8") as handle:
            handle.write(f"decision={decision.decision}\n")
            handle.write(
                f"published_at={(published_at and serialize_published_at(published_at)) or 'none'}\n"
            )
            handle.write(
                f"age_seconds={decision.age_seconds if decision.age_seconds is not None else 'n/a'}\n"
            )
            handle.write(f"threshold_minutes={threshold}\n")
    return 0


def _cmd_record_publish(args: argparse.Namespace) -> int:
    """Record the current UTC time as a successful publication timestamp."""
    from proxyaggregator.publishing.freshness import (
        PUBLISHED_AT_FILENAME,
        default_published_at_path,
        record_published_at,
        serialize_published_at,
        utc_now,
    )

    path = Path(args.file) if args.file else default_published_at_path()
    now = utc_now()
    record_published_at(path, now)
    print(
        f"[Publish] recorded successful publication at {serialize_published_at(now)} "
        f"into {path} ({PUBLISHED_AT_FILENAME})"
    )
    return 0


def _cmd_publish_summary(args: argparse.Namespace) -> int:
    """Render the Phase 22 run summary into ``$GITHUB_STEP_SUMMARY``.

    Always returns 0: the summary is observability only and must never fail a
    run that already published (or deliberately skipped, or discarded a race).
    """
    target = os.environ.get("GITHUB_STEP_SUMMARY", "") or None
    # Step outputs are empty when a step did not run, so every flag is coerced
    # rather than validated: a blank or unrecognised value becomes "unknown"
    # and is reported as unavailable, never as a failure of the summary itself.
    try:
        summary = build_run_summary(
            event=args.event or os.environ.get("GITHUB_EVENT_NAME", "") or "unknown",
            output_dir=Path(args.output) if args.output else Path(DEFAULT_OUTPUT_DIR),
            stats_path=args.stats_file,
            attempt=parse_optional_int(args.attempt),
            base_sha=args.base_sha or None,
            decision=args.decision if args.decision in ("RUN", "SKIP") else None,
            threshold_minutes=parse_optional_int(args.threshold_minutes),
            age_seconds=parse_optional_int(args.age_seconds),
            previous_published_at=args.previous_published_at or None,
            race=parse_optional_bool(args.race),
            sanity=None if args.sanity == "auto" else args.sanity,
            published=parse_optional_bool(args.published),
        )
        markdown = write_run_summary(summary, target)
    except Exception as exc:  # observability must never fail a run
        print(f"[Summary] could not render run summary: {exc.__class__.__name__}", file=sys.stderr)
        return 0
    if target is None:
        print(markdown)
    else:
        print(
            f"[Summary] {summary.status}: appended run summary to {target} "
            f"(published={str(summary.did_publish).lower()})"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the CLI; bare `proxyaggregator` prints the version."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    handler = getattr(args, "handler", None)
    if handler is not None:
        return handler(args)

    print(f"ProxyAggregator v{__version__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
