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
