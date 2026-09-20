"""ProxyAggregator main entry point."""

from proxyaggregator import __version__


def main() -> None:
    """Run ProxyAggregator."""
    print(f"ProxyAggregator v{__version__}")


if __name__ == "__main__":
    main()
