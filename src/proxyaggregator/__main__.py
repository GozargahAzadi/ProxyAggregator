"""ProxyAggregator CLI entry point."""

from __future__ import annotations

import argparse
import logging
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
        help="Path to the MMDB file (default: $PA_GEOIP_DB_PATH, i.e. GeoLite2-City.mmdb).",
    )
    cmd_verify_geoip.set_defaults(handler=_cmd_verify_geoip)
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


def _cmd_pipeline(_args: argparse.Namespace) -> int:
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
    return run_pipeline_cli()


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
