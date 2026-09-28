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
- [x] *Verified live*: GitHub registered the workflow as `active` and a real `repository_dispatch` request published end-to-end (run `36341771327`, bot commit `c37eade`), confirming the repository-dispatch API path works
- [x] *Verified live*: a watchdog-style request is **not** forced — it was gated (`SKIP`), so machine triggers can never bypass the cadence
- [x] *Corrected in Phase 23*: this item previously claimed the watchdog's "exact API path works" on the strength of an **externally** dispatched run. The watchdog's own dispatch step had never executed successfully — see Phase 23
- [x] *(watchdog-scheduled runs have now been observed: `36352034796`, `36360360469`, `36380836546`, `36417639920` — two green, two red. GitHub cron stays best-effort and no cadence is guaranteed)*

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
- [x] *(watchdog-scheduled runs have now been observed — see Phase 20; GitHub cron stays best-effort and no cadence is guaranteed)*
- [ ] The publication also *deletes* previously published files when a country has no eligible proxies (a publish commit removed ~28 tracked files); confirm that shrinkage is intended

## Phase 22 — Production Run Summary & Release Sanity

- [x] Audited what already exists before changing anything: the pipeline computes and logs every counter (`PipelineStats`), the freshness gate already exports its decision/threshold/previous publication/age to `$GITHUB_OUTPUT`, the release manifest already records every artifact's filename, format, count, byte size, and SHA-256, and `verify_release` already enforces every structural invariant. The only real gap was machine readability: `run_pipeline_cli()` discarded the stats it had just computed, and no `GITHUB_STEP_SUMMARY` existed anywhere
- [x] `publishing/summary.py`: one pure renderer plus thin loaders. It reuses `verify_release` and `format_age` and derives nothing a caller has not already measured
- [x] `pipeline --stats-file <path>` serialises the *already computed* `PipelineStats` verbatim and writes only after a successful run, so a file that exists always describes a complete run; a write failure is logged and ignored and can never fail a publication
- [x] New `publish-summary` CLI command appends the report to `$GITHUB_STEP_SUMMARY` (stdout when unset) and **always exits 0**; every flag is coerced, so an empty step output becomes `unavailable` instead of a parse error
- [x] Wired as the composite action's last step with `if: always()`, fed only by the run's own step outputs (`decision`, `threshold_minutes`, `published_at`, `age_seconds`, `base_sha`, `raced`, guard `sanity`, push `published`), so a published, skipped, race-discarded, and failed run are all reported
- [x] Exactly one terminal status, derived in order: `SKIPPED` → `DISCARDED` (Phase 21 race) → `FAILED` (guard failure or no confirmed push) → `PUBLISHED` **only** when the commit/push step confirmed it. A skipped or raced attempt can never claim it published, and a lost step output can never manufacture a success
- [x] No fabricated numbers: an unavailable source of truth renders as `unavailable`, a skipped run shows no pipeline/output counts at all (the previous release is never presented as this run's output), a raced run labels its counts as the discarded release, and an unreported guard is shown as *not verified* rather than re-deriving a pass from the stale release still in `output/`
- [x] Release sanity is the existing Phase 19 structural guard (manifest valid, every artifact present with the recorded byte size and SHA-256, at least one non-empty feed), reported rather than duplicated. No new gate, because the audit found no invariant that was not already enforced
- [x] No arbitrary threshold added: the repository commits no per-release metric (the manifest is overwritten every run and no history file exists), so a comparative "count dropped X%" rule would be ungrounded — a relative comparison is out of scope until a versioned metric exists
- [x] Nothing published from the summary path: the stats file lives in `.runtime/` (now gitignored), outside `output/`, and `git add output README.md` is unchanged. The summary never writes `published_at.json`, never stages, and never runs before the guard
- [x] Safety invariants unchanged: `*/5` cron, gated `repository_dispatch`, `workflow_dispatch` force, 13-minute threshold, `concurrency.group: publish` + `cancel-in-progress: false`, `contents: write`, no PAT, no rebase, no force push, no self-dispatch, and no parser/protocol/health/GeoIP/dedup/scoring/serialization/publication-transaction change
- [x] Tests: new `tests/test_summary.py` (status matrix including a race and an unreported guard, rendered safety claims, no-URI guarantee, counter fidelity, manifest-derived output facts, protocol counts that never sum base64 mirrors, and CLI tests proving it exits 0 on broken input and never mutates `published_at.json`), five `PipelineStats`-handoff tests in `tests/test_pipeline.py`, and a `TestProductionRunSummary` contract class pinning the `if: always()` summary, its inputs, the guard-before-push ordering, and the absence of any new threshold
- [x] Verified locally: 1141 tests pass, `ruff check src/ tests/` and `ruff format --check src/ tests/` clean, `git diff --check` clean, single alembic head `d4e5f6a7b8c9`
- [x] Verified live: `repository_dispatch` run [`36420843610`](https://github.com/GozargahAzadi/ProxyAggregator/actions/runs/36420843610) reported `PUBLISHED` with `published=true` after a real push and advanced `published_at` to `2026-09-28T12:28:46Z`; its regenerate job published `ba869e3`; a follow-up dispatch [`36422697194`](https://github.com/GozargahAzadi/ProxyAggregator/actions/runs/36422697194) landed 5.8 minutes after that publication and reported `SKIPPED` with `published=false` — both wrote the report to the real `$GITHUB_STEP_SUMMARY`
- [ ] *Live verification pending*: normal publish + freshness `SKIP` on GitHub Actions (see `PHASE22_REPORT.md`)

## Phase 23 — GitHub Automation Reliability & Watchdog Audit

Status labels used below: **Implemented** (in the repo), **Verified locally** (tests/lint), **Verified live** (a real GitHub Actions run), **Best-effort** (works, but GitHub gives no cadence guarantee), **Platform constraint** (cannot be fixed under the project rules).

- [x] Audited the automation before changing anything: read both workflows, the composite action, the watchdog tests, the publisher docs, the roadmap, and every non-`push` run in the repository's Actions history
- [x] **Found (evidence)**: the watchdog had *never* dispatched. Both scheduled failures (`36380836546`, `36417639920`) failed with `gh: unknown flag: --fail` — `gh api` has no such flag, so the step died before sending anything; both scheduled successes (`36352034796`, `36360360469`) were green only because a Publish run was already active and the request step was skipped
- [x] **Found (evidence)**: the Phase 20 "verified live" line was satisfied by an *externally* dispatched run (`36341771327`), not by the watchdog. Corrected in place
- [x] **Platform constraint, corrected**: `GITHUB_TOKEN` *can* create a `repository_dispatch` run. GitHub documents `workflow_dispatch` and `repository_dispatch` as the explicit exceptions to the "`GITHUB_TOKEN` events do not start new runs" rule (changelog 2022-09-08). Phase 22's claim that the watchdog could never self-trigger was wrong; no PAT is required
- [x] Removed `--fail`; error detection is preserved because `gh api` already exits non-zero on an HTTP error status and `set -euo pipefail` propagates it
- [x] **No fake success**: a new *Confirm a publish run was created* step polls for a `repository_dispatch` run created after the request and **fails the job** if none appears within 60 s (the dispatch endpoint returns `204` with an empty body, so the request alone proves nothing)
- [x] The watchdog job summary now distinguishes *confirmed (run id)* / *skipped, a run was active* / *failed to confirm*, so "green" can never be misread as "a publication was triggered"
- [x] The active-run check now rejects a non-numeric count: `gh api` does not apply `--jq` to an error body, so a failed call could hand back raw JSON and compare as "nothing active"
- [x] **Security audit**: no PAT, no external credential, no new secret, no `workflow_run` chaining, no self-dispatch loop, no history rewriting. `permissions` remain `contents: write` + `actions: read`; the watchdog still has no checkout and never pushes
- [x] README/CI: the failing `test_readme_has_subscriptions_section` was **not** an accidental loss of content. Commit `c5f7fcc` deliberately restructured the README and retitled the section to `## 🔥 Ready-to-use Subscription Links`; the country-index markers the generator owns are intact. The test asserted a stale heading literal, so it was rewritten to assert the real contract — exactly one feed section, carrying the copyable links, above the generated country index
- [x] **Verified locally**: full suite, `ruff check`, `ruff format --check`, `git diff --check`, single alembic head `d4e5f6a7b8c9`
- [x] **Verified live**: a watchdog run created a real Publish run, which reported its terminal state through the Phase 22 summary — watchdog [`36467583194`](https://github.com/GozargahAzadi/ProxyAggregator/actions/runs/36467583194) (scheduled tick) confirmed Publish run [`36467600915`](https://github.com/GozargahAzadi/ProxyAggregator/actions/runs/36467600915) was created, which ran `Decision: RUN`, passed the output guard, recorded `2026-09-28T18:59:12Z`, and published. The first time in this repository's history a watchdog tick produced a publication; no PAT involved
- [x] **Verified live**: CI green on the Phase 23 commit (run [`36431955309`](https://github.com/GozargahAzadi/ProxyAggregator/actions/runs/36431955309)), the first green CI since the README upload `c5f7fcc`
- [x] **Best-effort, documented, not claimed otherwise**: GitHub delivered 0.19 runs/hour for `Publish` and 0.28/hour for the watchdog against 12/hour nominal. Schedule *opportunity* ≠ workflow *execution* ≠ *publication*. Under the no-external-scheduler / no-PAT rules no cron can deliver a 15-minute cadence here; that is a platform limit, not a configuration bug

## Phase 10 — API (Optional)

- [ ] FastAPI endpoints
- [ ] Real-time subscription API
- [ ] Statistics dashboard
