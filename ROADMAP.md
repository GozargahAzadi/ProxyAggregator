# Roadmap

## Phase 0 — Bootstrap & Architecture

- [x] Project scaffolding
- [x] uv + Python 3.12 setup
- [x] pyproject.toml with core dependencies
- [x] Package structure
- [x] Documentation skeleton
- [x] CI skeleton (GitHub Actions)
- [x] Smoke test
- [x] Linting setup (ruff)
- [x] Alembic skeleton

## Phase 1 — Data Models & Database

- [x] SQLAlchemy ORM models (ProxyConfig, Source, HealthCheck)
- [x] Pydantic schemas for all protocols
- [x] Database migration with Alembic
- [x] CRUD operations
- [x] Database tests

## Phase 2 — Source Collectors

- [x] Base collector interface
- [x] HTTP source collector
- [x] Collector registry & plugin system

## Phase 3 — Protocol Parsers

- [x] Base parser interface
- [x] VLESS parser
- [x] VMess parser
- [x] Trojan parser
- [x] Shadowsocks parser
- [x] Hysteria / Hysteria2 parser
- [x] SOCKS4/SOCKS5 parser
- [x] HTTP/HTTPS proxy parser
- [x] URI normalization

## Phase 4 — Deduplication

- [x] Content-hash based dedup
- [x] Endpoint-based dedup
- [x] Fuzzy matching for near-duplicates

## Phase 5 — GeoIP & IP Resolution

- [x] DNS resolver (endpoint -> real IP)
- [x] MaxMind MMDB reader
- [x] GeoIP enrichment pipeline
- [x] IP-based dedup

## Phase 6 — Health Check

- [x] TCP connectivity check
- [x] TLS handshake check
- [x] Protocol-specific health check (HTTP CONNECT, SOCKS5, SOCKS4/4a)
- [x] Latency measurement (connect / TLS / proxy stages)
- [x] Multi-IP probing with bounded concurrency
- [x] Target security policy (rejects private/loopback/local networks)
- [x] Sanitized stable error codes
- [x] Health result persistence + Alembic migration

## Phase 7 — Scoring & Ranking

- [x] Scoring algorithm
- [ ] Country/region filtering *(deferred: metadata only per Phase 7 design decisions)*
- [ ] Protocol preference *(deferred: metadata only per Phase 7 design decisions)*

## Phase 8 — Subscription Generation

- [x] Plain URI list (canonical one-per-line serialization)
- [x] Base64 subscription format
- [x] JSON subscription format
- [ ] Clash config format *(deferred — fields lost by Phase 3/persistence: VMess `alterId`/`cipher`, SS `plugin`, Hysteria bandwidth; lossless conversion impossible without a schema change)*
- [ ] Sing-box config format *(deferred — same reason)*

## Phase 9 — GitHub Publisher

- [x] Release automation (deterministic publisher + release manifest)
- [x] Commit & push workflow (GitHub Actions, stable commit message)
- [x] GitHub Actions orchestration (schedule + manual dispatch, migrations, empty-output guard)
- [x] Full pipeline integration *(end-to-end orchestrator `python -m proxyaggregator pipeline` wires sources → parse → dedup → geoip → health → scoring → subscription → publish; fails fast when no sources are configured or no proxy is eligible)*

## Phase 10 — API (Optional)

- [ ] FastAPI endpoints
- [ ] Real-time subscription API
- [ ] Statistics dashboard
