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

## Subscriptions

Generated subscription feeds are published to the `output/` directory as
plain (newline-delimited URIs), base64 (standard Base64 of the plain feed),
and per-protocol feeds. All files are deterministic and re-generated on every
pipeline run.

### Combined feeds

- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator-base64.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/proxyaggregator.json
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/manifest.json

### Protocol feeds

Each protocol below ships a plain feed and its base64 variant.

VLESS:
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vless.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vless-base64.txt

VMess:
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vmess.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/vmess-base64.txt

Trojan:
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/trojan.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/trojan-base64.txt

Shadowsocks:
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/shadowsocks.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/shadowsocks-base64.txt

Hysteria:
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria-base64.txt

Hysteria2:
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria2.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/hysteria2-base64.txt

SOCKS4:
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks4.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks4-base64.txt

SOCKS5:
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks5.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/socks5-base64.txt

HTTP:
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/http.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/http-base64.txt

HTTPS:
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/https.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/https-base64.txt

### Proxies by country

Browse the auto-generated country index:
- [output/countries/README.md](https://github.com/GozargahAzadi/ProxyAggregator/blob/main/output/countries/README.md)

It is a Markdown table — flag, country name, ISO code, proxy count, and a
clickable link to each country's directory — and is **regenerated automatically
by every Publish run**, so it always reflects the current healthy-proxy
distribution. Do not edit it by hand.

Start at the index, click a country (e.g. 🇺🇸 United States), and each country
page (`output/countries/{CC}/README.md`) exposes copyable raw subscription URLs
for its `all` feed and every available protocol feed.

Country feeds are generated from the same deduplicated and health-checked
proxy set, so they contain only verified proxies. Each non-empty country gets
its own directory under `output/countries/{CC}/` (uppercase ISO 3166-1
alpha-2), containing:

- `README.md` — a human-readable country page with raw subscription links
- `all.txt` / `all-base64.txt` — every protocol of that country, plain and base64
- `{protocol}.txt` / `{protocol}-base64.txt` — per-protocol feeds, only when
  that protocol has healthy proxies from that country

Unknown or unrecognized countries are grouped under `XX` (`🌐`) when non-empty;
otherwise that group is omitted.

Stable examples (a directory per country; plain and base64 variants exist for each):
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/README.md
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/all.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/all-base64.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/vless.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/DE/vless-base64.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/US/all.txt
- https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/countries/US/vmess.txt

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
