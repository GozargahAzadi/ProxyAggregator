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

### Phase 6.2 — Wire-level VLESS / Trojan / Shadowsocks

- [x] VLESS TCP CONNECT check (plain TCP and TLS transports; version `0x00`
      header, validated `0x54` response)
- [x] Trojan CONNECT check over TLS (SHA-224 credential, no-ack inference)
- [x] Shadowsocks AEAD TCP check (aes-128-gcm, aes-256-gcm,
      chacha20-ietf-poly1305; HKDF-SHA1 + EVP_BytesToKey)
- [x] Variant gate before dialing (unsupported variants never probed)
- [x] Known-answer AEAD regression vectors
- [ ] VLESS REALITY *(deferred: `tls.reality` → UNSUPPORTED)*
- [ ] VLESS WS / gRPC / httpupgrade / xhttp overlays *(deferred:
      `transport.ws` → UNSUPPORTED)*
- [ ] VMess check *(deferred: no success acknowledgement)*
- [ ] Shadowsocks 2022 (BLAKE3) ciphers *(deferred: `ss.cipher.unsupported`)*
- [ ] Hysteria / Hysteria2 wire checks *(deferred: QUIC transport)*

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
- [x] Production source seeding *(`seed-sources` loads the version-controlled `config/sources.json` into the `sources` table before the pipeline; validated, credential-free, url-keyed upsert, no network — see `docs/SOURCES.md`)*

## Phase 18 — 15-Minute Production Scheduling Reliability

- [x] `*/5` cron trigger (best-effort scheduling has more start opportunities)
- [x] Freshness gate (`freshness-gate` CLI + `output/published_at.json`) capping real publications at ~once per 15 minutes
- [x] `record-publish` writes the timestamp only after a successful output guard (failed runs never advance the gate)
- [x] `concurrency.group: publish` + `cancel-in-progress: false` kept so overlapping triggers serialize and never race
- [x] Deterministic freshness tests (threshold, UTC safety, failure semantics)
- [x] *Verified live*: a real run executed the gate (`Decision: RUN`), published, committed `output/published_at.json` (`2026-09-27T18:56:09Z`), and a request 95 s later correctly produced `Decision: SKIP` with every expensive step skipped
- [ ] *(a scheduled `*/5` run has still never been observed firing on time; GitHub's scheduler remains best-effort)*

## Phase 20 — GitHub-Native Trigger Reliability

- [x] Measured the real scheduler behaviour: the `*/5` cron produced only ~0.3 runs/hour (gaps of 2.3–5.8 h), so the 15-minute cadence degraded to hours
- [x] `publish-watchdog.yml`: a second scheduled entry point on a cron offset by 3 minutes from `*/5`, so a missed tick has an independent second chance
- [x] Watchdog only *requests* a run (`repository_dispatch` `publish-request`) and never publishes, so the 13-minute freshness gate still caps real publications
- [x] Watchdog skips its request while a `publish` run is `in_progress`/`queued`, so a request is never serialized behind a live publication (which would read a pre-publication `published_at.json`)
- [x] Least-privilege permissions (`contents: write` for the dispatch endpoint, `actions: read` for the active-run check); separate concurrency group with `cancel-in-progress: true` so production is never cancelled
- [x] Workflow contract tests pin the offset schedule, the repository-dispatch (never forced) path, the guard, and the isolation from the `publish` concurrency group
- [x] No application, parser, pipeline, health, GeoIP, database, or Phase 18 freshness logic changed
- [x] *Verified live*: GitHub registered the workflow as `active` and a real `repository_dispatch` request published end-to-end (run `36341771327`, bot commit `c37eade`), confirming the watchdog's exact API path works
- [x] *Verified live*: a watchdog-style request is **not** forced — it was gated (`SKIP`), so machine triggers can never bypass the cadence
- [ ] *(a watchdog-scheduled run has not yet been observed: GitHub has not started its first tick, 22 min after it was due — GitHub cron stays best-effort and no cadence is guaranteed)*

## Phase 21 — Publisher Push Resilience (identified, not started)

- [ ] **Blocking defect**: the commit step does a bare `git push`. Any commit landing during the ~11.5-minute run makes the push non-fast-forward and the whole publication is lost — reproduced twice (runs `36340267647`, `36340424631`, both `! [rejected] main -> main (fetch first)`), each after ~11 min of runner work
- [ ] Make the push resilient (fetch/rebase onto `origin/main` before pushing) so an unrelated commit cannot discard a successful publication
- [ ] The publication also *deletes* previously published files when a country has no eligible proxies (a publish commit removed ~28 tracked files); confirm that shrinkage is intended

## Phase 10 — API (Optional)

- [ ] FastAPI endpoints
- [ ] Real-time subscription API
- [ ] Statistics dashboard
