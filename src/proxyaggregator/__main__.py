"""ProxyAggregator CLI entry point."""

from __future__ import annotations

import argparse
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
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run the CLI; bare `proxyaggregator` prints the version."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "sample-subscriptions":
        output_dir = Path(args.output) if args.output else Path(DEFAULT_OUTPUT_DIR)
        feeds = build_demo_subscriptions(max_items=args.max_items)
        entries = publish_subscriptions(feeds, output_dir)
        manifest = build_release_manifest(entries)
        write_release_manifest(manifest, output_dir)
        print(manifest)
        return

    print(f"ProxyAggregator v{__version__}")


if __name__ == "__main__":
    main()
