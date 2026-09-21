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

- [ ] DNS resolver (endpoint -> real IP)
- [ ] MaxMind MMDB reader
- [ ] GeoIP enrichment pipeline
- [ ] IP-based dedup

## Phase 6 — Health Check

- [ ] TCP connectivity check
- [ ] TLS handshake check
- [ ] Protocol-specific health check
- [ ] Latency measurement
- [ ] Concurrent health checking

## Phase 7 — Scoring & Ranking

- [ ] Scoring algorithm
- [ ] Country/region filtering
- [ ] Protocol preference

## Phase 8 — Subscription Generation

- [ ] Base64 subscription format
- [ ] JSON subscription format
- [ ] Clash config format
- [ ] Sing-box config format

## Phase 9 — GitHub Publisher

- [ ] Release automation
- [ ] Commit & push workflow
- [ ] GitHub Actions orchestration
- [ ] Full pipeline integration

## Phase 10 — API (Optional)

- [ ] FastAPI endpoints
- [ ] Real-time subscription API
- [ ] Statistics dashboard
