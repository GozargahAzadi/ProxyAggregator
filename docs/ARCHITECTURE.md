# Architecture

## Overview

ProxyAggregator is designed as a modular pipeline that runs entirely on GitHub Actions. There are no daemons, no persistent processes, and no dependency on a VPS.

```
Source Collectors -> Protocol Parsers -> Deduplication -> IP Resolution -> GeoIP -> Health Check -> Scoring -> Publisher
```

## Design Principles

### 1. GitHub Actions First

The entire system is designed to run in ephemeral CI environments:

- **No persistent state**: All state is stored in SQLite or committed to git
- **Time-boxed execution**: Each step has timeouts
- **Network-aware**: Handles failures, rate limits, and retries
- **No daemons**: Every run is self-contained

### 2. Modularity

Each component is independent and replaceable:

| Component | Interface | Purpose |
|-----------|-----------|---------|
| Source Collector | `BaseCollector` | Fetches raw proxy URLs |
| Protocol Parser | `BaseParser` | Parses URIs into structured data |
| Deduplicator | `Deduplicator` | Removes duplicate configs |
| IP Resolver | `IPResolver` | Resolves endpoint to real IP |
| GeoIP | `GeoIPProvider` | Enriches with geolocation |
| Health Checker | `BaseHealthChecker` | Tests connectivity & latency |
| Publisher | `BasePublisher` | Outputs subscription files |

### 3. Security

All inputs are treated as untrusted:

- Malformed URL handling
- Invalid base64 rejection
- Input size limits
- SSRF prevention
- No credential leakage in logs

### 4. Test First

Every feature follows: Test -> Red -> Implementation -> Green -> Refactor

## Directory Structure

```
ProxyAggregator/
├── src/
│   └── proxyaggregator/
│       ├── __init__.py          # Package version
│       ├── __main__.py          # CLI entry point
│       ├── config/              # Settings & configuration
│       │   ├── __init__.py
│       │   └── settings.py
│       ├── models/              # Pydantic schemas
│       │   └── __init__.py
│       ├── db/                  # SQLAlchemy models & engine
│       │   ├── __init__.py
│       │   └── engine.py
│       ├── parsers/             # Protocol parsers
│       │   └── __init__.py
│       ├── sources/             # Source collectors
│       │   └── __init__.py
│       ├── geoip/               # GeoIP lookup
│       │   └── __init__.py
│       ├── health/              # Health checking
│       │   └── __init__.py
│       └── publishing/          # Subscription publishers
│           └── __init__.py
├── tests/
│   └── test_package.py          # Smoke tests
├── alembic/                     # Database migrations
│   └── versions/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DATABASE.md
│   └── CONFIGURATION.md
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── publish.yml
├── pyproject.toml
├── README.md
├── ROADMAP.md
├── .gitignore
└── .env.example
```

## Pipeline Flow

```
1. Source Collectors     Fetch raw URLs/text from public sources
         |
2. Protocol Parsers     Parse each URL into a structured ProxyConfig
         |
3. Deduplication        Remove exact and near-duplicates
         |
4. IP Resolution        Resolve DNS to get real endpoint IPs
         |
5. GeoIP Lookup         Enrich with country/city from MaxMind MMDB
         |
6. Health Check         Verify connectivity, measure latency
         |
7. Scoring              Rank proxies by quality metrics
         |
8. Publisher            Generate subscription files (base64, Clash, etc.)
         |
9. GitHub Release       Commit and publish via GitHub Actions
```

## Data Flow

All intermediate data flows through SQLAlchemy models in SQLite:

- `sources` — collected source metadata
- `proxy_configs` — parsed and normalized proxy configurations
- `health_checks` — health check results with latency
- `geo_data` — geolocation data for each endpoint

## Concurrency Model

On GitHub Actions:

- Parallel fetching with bounded concurrency (httpx.AsyncClient)
- Rate limiting per source
- Timeouts on all network operations
- Graceful degradation on failures
