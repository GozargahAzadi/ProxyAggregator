# ProxyAggregator

A fully automated, stdlib-only proxy configuration aggregator that runs on GitHub Actions — no VPS, no database, no external dependencies.

Inspired by [0xRadikal/Free-v2ray-Configs](https://github.com/0xRadikal/Free-v2ray-Configs) but built from scratch with zero external packages.

## Features

- **Collect** from multiple public HTTP/HTTPS feeds
- **Parse** VLESS, VMess, Trojan, Shadowsocks, Hysteria2 configs
- **Deduplicate** using CDN-aware fingerprints
- **Verify** with real TCP/TLS connectivity checks (3 rounds)
- **Categorize** into `all`, `verified`, `fast`, `secure` buckets
- **Export** to plain text, base64 subscriptions, JSON indexes
- **Publish** via rolling-squash commits (O(1) git history growth)

## Requirements

- Python 3.12+ (uses only standard library)
- Git
- GitHub repository with push access

## Quick Start

```bash
# Run locally (dry-run mode)
python -m proxy_aggregator.aggregate --dry-run

# Run full pipeline
python -m proxy_aggregator.aggregate --out .

# Run tests
python -m pytest proxy_aggregator/tests/ -v
```

## GitHub Actions

Push to `main` triggers the workflow automatically. Schedule runs every 15 minutes.

```yaml
.on:
  schedule:
    - cron: '*/15 * * * *'
  workflow_dispatch:
    inputs:
      force:
        description: 'Force run'
        required: false
        default: 'false'
```

## Output Structure

```
all/           Full deduplicated collection
verified/      Passed all 3 verification rounds
fast/          Verified with median latency < 800ms
secure/        Verified with forward secrecy
protocols/     Split by protocol type
top100.txt     Fastest 100 verified configs
index.json     Machine-readable metadata
health.json    Source health and cascade statistics
state.json     Rolling yield history
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGG_CONN_TIMEOUT` | 10 | Source connection timeout (seconds) |
| `AGG_READ_TIMEOUT` | 30 | Source read timeout (seconds) |
| `AGG_MAX_SIZE` | 10000000 | Max response size (bytes) |
| `VERIFY_CONNECT_TIMEOUT_MS` | 5000 | Verify connect timeout (ms) |
| `VERIFY_REQUEST_TIMEOUT_MS` | 8000 | Verify request timeout (ms) |
| `VERIFY_ROUNDS` | 3 | Number of verification rounds |
| `VERIFY_FAST_MS` | 800 | Fast threshold (ms) |

## Limitations

- **L3 verification** uses direct TCP/TLS checks, not full proxy tunneling (would require xray-core binary)
- **No GeoIP** — country classification requires external database (optional in future)
- **No Clash/Sing-box export** — YAML/JSON client configs need additional converters

These are v1 tradeoffs for a stdlib-only, zero-dependency design.

## Project Structure

```
proxy_aggregator/
├── __init__.py          # Package marker
├── __main__.py          # Entry point
├── models.py            # Data models (ConfigItem, SourceResult, RunSummary)
├── parsers.py           # Protocol detection, parsing, normalization
├── sources.py           # Source fetching with retries
├── dedup.py             # Fingerprint-based deduplication
├── verification.py      # TCP/TLS verification
├── ranking.py           # Latency-based ranking
├── exporters.py         # Output file generation
├── aggregate.py         # Main pipeline orchestration
└── tests/               # Test suite (89 tests)
    ├── test_models.py
    ├── test_parsers.py
    ├── test_sources.py
    ├── test_dedup.py
    ├── test_verification.py
    ├── test_ranking.py
    └── test_exporters.py
```

## License

MIT
