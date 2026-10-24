# ProxyAggregator

A fully automated proxy configuration aggregator that runs on GitHub Actions — no VPS, no database, no permanently running server. Collects public proxy configs, deduplicates them by connection-relevant identity, verifies through-proxy connectivity using a pinned Xray-core binary, and publishes categorized feeds.

## Features

- **Collect** from multiple public HTTP/HTTPS feeds
- **Parse** VLESS, VMess, Trojan, Shadowsocks, Hysteria2 configs
- **Deduplicate** using CDN-aware fingerprints
- **Verify** with real through-proxy HTTP requests via Xray-core (3 rounds)
- **Categorize** into `all`, `verified`, `fast`, `secure` buckets
- **Export** to plain text, base64 subscriptions, JSON indexes
- **Publish** via rolling-squash commits (O(1) git history growth)

## Requirements

- Python 3.12+ (core logic uses only standard library; Xray-core binary for L3 verification)
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

- **GeoIP** — country classification requires an external MaxMind database (optional in future)
- **No Clash/Sing-box export** — YAML/JSON client configs need additional converters
- **Hysteria2 verification unsupported** — QUIC (UDP) cannot be tested via HTTP tunnel; configs are structurally checked but never marked as `verified`
- **Runner-dependent** — verification results reflect the network conditions of the GitHub Actions runner (US-based by default), not your local geography

## Project Structure

```
proxy_aggregator/
├── __init__.py          # Package marker
├── __main__.py          # Entry point
├── models.py            # Data models (ConfigItem, SourceResult, RunSummary)
├── parsers.py           # Protocol detection, parsing, normalization
├── sources.py           # Source fetching with retries
├── dedup.py             # Fingerprint-based deduplication
├── verification.py      # Through-proxy verification via Xray-core + stdlib fallback
├── ranking.py           # Latency-based ranking
├── exporters.py         # Output file generation
├── aggregate.py         # Main pipeline orchestration
└── tests/               # Test suite (100+ tests)
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
