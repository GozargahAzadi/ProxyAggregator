# ProxyAggregator

Public V2Ray/Proxy Config Aggregator that collects, parses, normalizes, deduplicates, and health-checks public proxy configurations, then publishes them as subscription files via GitHub.

## Features

- **Multi-protocol support**: VLESS, VMess, Trojan, Shadowsocks, Hysteria, Hysteria2, SOCKS4, SOCKS5, HTTP, HTTPS
- **Real IP resolution**: Resolves actual endpoint IPs for accurate GeoIP lookup
- **GeoIP enrichment**: MaxMind GeoLite2-based geolocation
- **Health checking**: Latency and connectivity verification
- **Deduplication**: Removes duplicate configurations
- **Subscription output**: Standard proxy subscription formats
- **GitHub Actions native**: Designed to run entirely in CI/CD

## Quick Start

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/ProxyAggregator.git
cd ProxyAggregator

# Install dependencies
uv sync

# Run tests
uv run pytest

# Run linter
uv run ruff check src/ tests/
```

## Configuration

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for all available settings.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architectural overview.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the development plan.

## License

MIT
