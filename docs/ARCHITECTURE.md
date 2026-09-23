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
│       ├── scoring/             # Scoring & ranking (Phase 7)
│       │   ├── __init__.py
│       │   ├── models.py        # RankCandidate / ProxyScore
│       │   └── scorer.py        # latency score + deterministic ranking
│       └── publishing/          # Subscription generation (Phase 8) & publishing (Phase 9)
│           ├── __init__.py
│           ├── models.py        # RankedProxy / Subscription / formats
│           ├── errors.py        # SubscriptionError (credential-free)
│           ├── serializer.py    # canonical per-protocol URI serialization
│           ├── feeds.py         # feed assembly (order, dedup, max_items)
│           ├── publisher.py     # deterministic artifact writer + release manifest (Phase 9)
│           └── samples.py       # synthetic demo feeds for the local dry-run (Phase 9)
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

Phase 9 implements steps 8-9: `publishing/publisher.py` writes Phase 8
feeds byte-exactly into `output/` (deterministic filenames, atomic replace,
sha256 release manifest), and `.github/workflows/publish.yml` commits those
artifacts on a schedule or manual dispatch.

Phase 9.1 adds the shared orchestrator (`pipeline.py`) behind the single
`python -m proxyaggregator pipeline` command. It connects every stage in one
run — sources → fetch → parse → dedup → persist → geoip → health → score →
rank → subscribe → publish — delegating to the existing Phase 2-9 modules and
models. Each stage boundary is a pure function of the previous stage's output;
the orchestrator adds no new parsing, scoring, or persistence logic. It fails
fast (non-zero exit) with a stable reason token when no sources are configured
(`no_configured_sources`) or when no proxy survives health checks
(`no_eligible_proxies`), so the workflow never publishes empty/stale feeds.

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
