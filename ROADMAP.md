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

- [ ] SQLAlchemy ORM models (ProxyConfig, Source, HealthCheck)
- [ ] Pydantic schemas for all protocols
- [ ] Database migration with Alembic
- [ ] CRUD operations
- [ ] Database tests

## Phase 2 — Source Collectors

- [ ] Base collector interface
- [ ] Telegram channel collector
- [ ] GitHub raw file collector
- [ ] HTTP subscription URL collector
- [ ] RSS feed collector
- [ ] Collector registry & plugin system

## Phase 3 — Protocol Parsers

- [ ] Base parser interface
- [ ] VLESS parser
- [ ] VMess parser
- [ ] Trojan parser
- [ ] Shadowsocks parser
- [ ] Hysteria / Hysteria2 parser
- [ ] SOCKS4/SOCKS5 parser
- [ ] HTTP/HTTPS proxy parser
- [ ] URI normalization

## Phase 4 — Deduplication

- [ ] Content-hash based dedup
- [ ] Endpoint-based dedup
- [ ] Fuzzy matching for near-duplicates

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
