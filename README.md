# ProxyAggregator

**English** | [فارسی](./README.fa.md)

Public V2Ray/Proxy Config Aggregator that collects, parses, normalizes,
deduplicates, and health-checks public proxy configurations, then publishes
them as subscription files via GitHub.

## Features

- **Multi-protocol support**: VLESS, VMess, Trojan, Shadowsocks, Hysteria, Hysteria2, SOCKS4, SOCKS5, HTTP, HTTPS
- **Real IP resolution**: Resolves actual endpoint IPs for accurate GeoIP lookup
- **GeoIP enrichment**: MaxMind GeoLite2-based geolocation
- **Health checking**: Latency and connectivity verification
- **Deduplication**: Removes duplicate configurations
- **Subscription output**: Standard proxy subscription formats
- **GitHub Actions native**: Designed to run entirely in CI/CD

## Subscriptions

Generated subscription feeds are published to the `output/` directory as plain
(newline-delimited URIs), base64 (standard Base64 of the plain feed), and
per-protocol feeds. All files are deterministic and re-generated on every
pipeline run. Every usable URL below sits in its own fenced code block, so
GitHub shows a native Copy button next to it.

### Combined feeds

ProxyAggregator — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator.txt
```

ProxyAggregator — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator-base64.txt
```

ProxyAggregator — JSON

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator.json
```

Manifest — JSON

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/manifest.json
```

### Protocol feeds

Each protocol below ships a plain feed and its base64 variant.

VLESS — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vless.txt
```

VLESS — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vless-base64.txt
```

VMess — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vmess.txt
```

VMess — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vmess-base64.txt
```

Trojan — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/trojan.txt
```

Trojan — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/trojan-base64.txt
```

Shadowsocks — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/shadowsocks.txt
```

Shadowsocks — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/shadowsocks-base64.txt
```

Hysteria — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria.txt
```

Hysteria — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria-base64.txt
```

Hysteria2 — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria2.txt
```

Hysteria2 — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria2-base64.txt
```

SOCKS4 — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks4.txt
```

SOCKS4 — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks4-base64.txt
```

SOCKS5 — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks5.txt
```

SOCKS5 — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks5-base64.txt
```

HTTP — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/http.txt
```

HTTP — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/http-base64.txt
```

HTTPS — Plain

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/https.txt
```

HTTPS — Base64

```text
https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/https-base64.txt
```

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

## License

MIT