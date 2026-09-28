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
- [x] *Verified live (2026-09-28)*: the `*/5` cron did fire on its own — scheduled runs `36360194767`, `36371053260`, and `36400609363` all started and completed without any manual request. Gaps between firings are still 1–4 h rather than 5 min, so the scheduler is *better* than the Phase 20 measurement suggested but still far coarser than configured; the freshness gate remains the only cap that is actually enforced

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

## Phase 21 — Publisher Push Resilience

- [x] Root-caused the blocking defect: a run publishes from the commit that triggered it, so a commit landing during the ~11.5-minute run leaves the release as a mixture of two trees (removed files still present, added files missing) and a bare `git push` is rejected — reproduced twice (runs `36340267647`, `36340424631`, both `! [rejected] main -> main (fetch first)`), each after ~11 min of runner work
- [x] Generation sequence moved verbatim into a shared composite action `.github/actions/publish/action.yml` so a retry can rerun it unchanged
- [x] Stale-tree guard: after the output guard, fetch `origin/main` and compare it with the release's base commit; on a mismatch the release is discarded **before** `record-publish` and before any commit, so no stale output is published and `published_at.json` is not advanced
- [x] Bounded regeneration: a single dependent retry job checks out `ref: main` on a fresh runner and reruns the same action (freshness gate, GeoIP, pipeline, output guard, push all run again)
- [x] Retries are exhausted after two attempts — the second attempt fails loudly with `::error::`, publishes nothing, and lets the next scheduled/watchdog trigger retry from a clean state
- [x] No rebase and no force push: a rebase cannot recreate working-tree content, and force-pushing would rewrite published history, so regeneration is the only correct repair
- [x] No self-dispatch and no `workflow_run` retrigger: the retry is a real dependent job, so it cannot loop and stays visible in a single workflow run
- [x] All Phase 18/20 invariants preserved: `*/5` cron, gated `repository_dispatch`, `workflow_dispatch` force, 13-minute threshold, `concurrency.group: publish` + `cancel-in-progress: false`, `contents: write`, `cancel-in-progress: true` on the watchdog
- [x] Side benefit: the retry checks out current `main`, so its freshness gate reads the newest `published_at.json` and correctly `SKIP`s if a publication landed meanwhile — closing the stale-timestamp window the watchdog had to work around
- [x] No application, parser, pipeline, health, GeoIP, database, or publishing Python logic changed (`git diff` over `src/`, `scripts/`, `alembic/`, `config/` is empty)
- [x] Contract tests pin the triggers, env, toolchain, step order, `verify_release` guard, race decision, timestamp/push guards, job graph, retry bound, and the absence of force/rebase/self-dispatch; a functional test executes the real race-check script against throwaway git repos (unchanged main → `raced=false`, moved main → `raced=true`)
- [x] Verified locally: 1042 tests pass, `ruff check src/ tests/` and `ruff format --check src/ tests/` clean, `git diff --check` clean, single alembic head
- [x] *Verified live (2026-09-28)*: three production runs on the Phase 21 two-job workflow (`36366848328` via `repository_dispatch`, `36371053260` and `36400609363` via `schedule`) published end-to-end. The composite action's stale-tree guard reported `generated_from == origin_main` (`raced=false`) in each, and the bounded retry job was correctly `skipped` because no race occurred
- [x] *Verified live (2026-09-28)*: **a real race was provoked on purpose and recovered** (run `36408757722`). A commit pushed 28 s into a running generation moved `main` from `24275780` to `f135f88c`; attempt 1 detected it (`generated_from != origin_main`), skipped `record-publish` and the commit/push, and exited green without advancing `published_at.json`; attempt 2 checked out `f135f88c`, regenerated, re-verified, and published (`a275057`, `published_at.json` = `2026-09-28T10:41:00Z`). The Phase 20 defect that lost a publication twice now costs ~12 min of discarded work instead
- [ ] *(the `workflow_dispatch` force path is still unexercised live: this environment's credential gets HTTP 403 for workflow_dispatch; the code path is unchanged and pinned by contract test)*
- [ ] *(a watchdog-scheduled run has not yet been observed: GitHub has not started its first tick, 22 min after it was due — GitHub cron stays best-effort and no cadence is guaranteed)*
- [ ] The publication also *deletes* previously published files when a country has no eligible proxies (a publish commit removed ~28 tracked files); confirm that shrinkage is intended

## Phase 10 — API (Optional)

- [ ] FastAPI endpoints
- [ ] Real-time subscription API
- [ ] Statistics dashboard
