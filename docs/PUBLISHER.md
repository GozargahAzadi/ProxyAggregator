# Phase 9 — GitHub Publisher & Release Automation

Phase 9 makes generated subscriptions publishable: a deterministic
**publisher library** writes Phase 8 feeds to disk, a **release manifest**
records their sizes and hashes, a **local dry-run** exercises the whole chain
without GitHub, and a **GitHub Actions workflow** runs migration, production
pipeline, and artifact commit on a schedule or manual dispatch.

## Scope

Phase 9 + Phase 9.1 covers all four ROADMAP items:

| ROADMAP item | Status | Location |
|---|---|---|
| Release automation | Done | `publishing/publisher.py` |
| Commit & push workflow | Done | `.github/workflows/publish.yml` |
| GitHub Actions orchestration | Done | `.github/workflows/publish.yml` |
| Full pipeline integration | Done | `pipeline.py` + `publish.yml` |

## Publisher library (`publishing/publisher.py`)

`build_subscription` (Phase 8) returns a `Subscription` (format, content,
count). The publisher turns that into artifacts:

- `write_artifact(filename, content, output_dir)` — atomic, traversal-safe
  single-file write. The final bytes are exactly UTF-8 of `content` (or the
  raw `bytes`); the file is staged under a sibling `.name.tmp`, fsynced, then
  `os.replace`d into place. No partial files survive a failure.
- `publish_subscriptions(names_to_feeds, output_dir)` — writes an ordered set
  of named feeds and returns one `SubscriptionRelease` each.
- `release_metadata(...)`, `build_release_manifest(entries)` /
  `write_release_manifest(...)` — deterministic JSON manifest.

### Determinism guarantees

- Byte-exact: `file_bytes == content.encode("utf-8")`. Publishing the same
  feeds twice yields identical files.
- No ephemeral state: no timestamps, random names, hostnames, run IDs,
  environment variables, or credentials in contents, filenames, or errors.
- Manifest is sorted by filename, compact JSON (`sort_keys`, no trailing
  newline), and contains only `filename`, `format`, `count`, `byte_size`,
  `sha256`.

### Artifact filenames

| Format | File |
|---|---|
| plain | `output/proxyaggregator.txt` |
| base64 | `output/proxyaggregator-base64.txt` |
| json | `output/proxyaggregator.json` |
| manifest | `output/manifest.json` |

Phase 9.3 adds protocol-separated feeds (plain + base64 per protocol) with
deterministic filenames derived from `DEFAULT_PROTOCOL_FILENAME_STEMS`
(`publishing/publisher.py`), e.g. `output/vless.txt`,
`output/vless-base64.txt`, `output/shadowsocks.txt`,
`output/shadowsocks-base64.txt`. Only the `ss` protocol renames its stem
(`shadowsocks`); all other stems equal their protocol id. The feed content
contracts are documented in `docs/SUBSCRIPTION.md` (filtering, no-empty,
global selection first, canonical ordering).

The default directory is `output/` (repo-relative). Error messages contain
only a sanitized filename and a stable reason token
(`PublishError.filename` / `PublishError.reason`); feed content is never
echoed.

### Security

- Filenames must be a single plain path component: empty names, NUL bytes,
  `"."`, `".."`, and anything with a path separator are rejected with a
  stable `PublishError` before any disk access.
- No `git add .` / `git commit -a` / force-push anywhere in Python or the
  workflow; git operations run only in the workflow with the stable message
  `chore: update generated subscriptions` and a `git diff --cached --quiet`
  no-op check.
- Secrets never enter code: the workflow uses only `${{ secrets.GITHUB_TOKEN }}`,
  never a PAT or hardcoded token.

## Local dry-run (no GitHub / no network)

```
python -m proxyaggregator sample-subscriptions            # writes output/
python -m proxyaggregator sample-subscriptions --output /tmp/out --max-items 5
```

Builds the canonical feeds from embedded **synthetic** example.com proxies
(RFC 6761; obviously fake credentials), publishes them via the real publisher,
writes `manifest.json`, and prints the manifest. The demo set covers every
serializable protocol, so the dry run exercises the combined *and*
protocol-separated artifact paths. Running it twice produces byte-identical
output — this validates the Phase 9 chain locally.

`python -m proxyaggregator` with no arguments still prints the version.

## GitHub Actions workflow (`.github/workflows/publish.yml`)

- Triggers: `workflow_dispatch` (manual), `repository_dispatch` (Phase 20
  watchdog request), and `schedule` every `5` minutes (Phase 18). The 5-minute
  trigger gives GitHub many opportunities to start a run, but real publications
  are capped at ~once per 15 minutes by the freshness gate below, so the
  cadence is a *reliability* improvement, never more frequent output.
- `permissions: contents: write` — least-privilege scope.
- `concurrency.group: publish` with `cancel-in-progress: false` so scheduled
  runs never race each other on the same branch: an overlapping trigger is
  queued until the active run finishes and then reads the committed state, so
  the freshness gate is always evaluated against the latest successful
  publication and the pipeline can never be killed by a newer run.
- Two jobs, `attempt-1` and `attempt-2`, both delegating the generation to the
  shared composite action `.github/actions/publish`. The retry is bounded to one
  extra attempt and only exists to recover from `main` moving underneath a
  running generation; see Phase 21 below.

### Phase 20 — publish watchdog (`.github/workflows/publish-watchdog.yml`)

GitHub's scheduler is best-effort: a `schedule` run may be delayed or dropped
when GitHub is under load, and the delay can be long. Measured on this
repository, the Phase 18 `*/5` cron produced only **~0.3 runs per hour** — the
gaps between scheduled runs were 2.3 to 5.8 hours — so the intended
15-minute cadence degraded to a multi-hour cadence even though twelve
opportunities per hour were nominally configured.

The watchdog is a second, independent scheduled entry point:

- `schedule: "3,8,13,18,23,28,33,38,43,48,53,58 * * * *"` — the 5-minute
  GitHub minimum, offset by three minutes from the production `*/5` cron so the
  two never target the same minute. Two workflows are two separate scheduling
  opportunities: a tick missed by one still has the other. `workflow_dispatch`
  is also accepted so the dispatch path can be verified by hand.
- It publishes nothing. Its single job checks whether a `publish.yml` run is
  already `in_progress` or `queued` and, only when none is, `POST`s a
  `repository_dispatch` event (`event_type: publish-request`) to start one.
- `permissions: contents: write` (required by GitHub for the repository
  dispatch endpoint) plus `actions: read` (the active-run check). The workflow
  has no checkout and never writes repository content.
- `concurrency.group: publish-watchdog` with `cancel-in-progress: true` — a
  superseded tick is a single API call that publishes nothing, and this
  guarantees at most one request at a time, so two requests can never queue
  behind each other.

Two safety properties are deliberate:

1. **A watchdog request stays gated.** The freshness step forces `RUN` only for
   `workflow_dispatch`, i.e. a human asking for an immediate publication. The
   watchdog therefore uses `repository_dispatch`, which the gate treats exactly
   like a scheduled run: it can add scheduling *opportunities* but can never
   publish outside the 13-minute cadence.
2. **No request is ever queued behind a live publication.** A queued run starts
   from the tree that was current when it was requested, which can predate the
   previous publication's commit, so its freshness gate could read a stale
   `output/published_at.json` and allow a second publication inside the
   threshold window. The active-run check skips such requests and the next tick
   asks again. Phase 21 removes the underlying hazard as well: a run that
   discovers `main` moved regenerates from the newest main and re-evaluates the
   gate there, so a stale-tree publication is no longer possible even if such a
   request is ever issued.

Honest limit: this multiplies the number of GitHub-native scheduling
opportunities; it does not make GitHub's scheduler reliable. Both crons remain
best-effort, so no cadence is guaranteed — the freshness gate remains the only
thing that actually caps how often output is published.

### Phase 21 — bounded regeneration when main moves (`.github/actions/publish/action.yml`)

A scheduled run starts from the commit that triggered it, which can predate a
publication that landed while the run was waiting in the `publish` concurrency
queue. If `origin/main` moves while the pipeline is running, the release on disk
is a mixture of two trees: files removed by the newer commit are still present
and files added by it are missing. Pushing that release would restore deleted
output and drop newly eligible proxies. The observed symptom of this defect was
a bare `git push` rejected with `! [rejected] main -> main (fetch first)`
*after* a full successful generation (~12 minutes of wasted work).

The generation sequence therefore lives in a shared composite action
(`.github/actions/publish/action.yml`) and the workflow runs **at most two
attempts**:

- **Attempt 1** checks out the triggering commit and runs the composite action.
  After the output guard passes, the action's *stale-tree guard* fetches
  `origin/main` and compares it with the commit the release was built from
  (`git rev-parse HEAD`). If they are equal, `record-publish` and the commit/push
  run and the publication lands.
- **If main moved**, the release is discarded *before* `record-publish` and
  before any commit, so no stale output is published and
  `output/published_at.json` is not advanced. The attempt exits green with
  `raced=true` and a `::warning::` annotation naming both commits.
- **Attempt 2** runs only when `needs.attempt-1.outputs.raced == 'true'`. It
  checks out `ref: main` on a fresh runner and reruns the *same* composite
  action, so the release is rebuilt from the newest tree, the output guard and
  the freshness gate both run again, and the push is an ordinary fast-forward.
- **If main moves again**, attempt 2's release is discarded and the job fails
  with a clear `::error::`. Nothing is published, the timestamp is untouched, and
  the next scheduled or watchdog trigger retries from scratch.

Deliberate non-solutions:

- **No rebase and no force push.** Rebasing a release that was generated from
  the older tree would not recreate the removed/added files (git does not
  replay working-tree content), and force-pushing would rewrite published
  history. Regenerating from the newest main is the only correct repair.
- **No self-dispatch.** Attempt 2 is a real dependent job, not a
  `repository_dispatch` back into the same workflow, so the bounded retry cannot
  loop and stays observable in one workflow run.
- **Bounded at two attempts.** A pathological push loop would otherwise keep
  regenerating; failing loudly lets the next trigger start from a clean state.

Because attempt 2 checks out the *current* main, its freshness gate reads the
newest `output/published_at.json`. If a publication landed while attempt 1 was
generating, the retry's gate correctly decides `SKIP`, which closes the
stale-timestamp window the Phase 20 watchdog had to work around by skipping
requests.

### Phase 18 — freshness gate

The scheduled workflow fires every 5 minutes, but before doing any expensive
work it evaluates how old the last *successful* publication is via the gate
step `python -m proxyaggregator freshness-gate`.

- The gate reads `output/published_at.json`, a small committed JSON document
  (`{"published_at": "<RFC 3339 UTC>"}`) produced **only** by the
  `record-publish` step that runs after a successful output guard. The release
  `manifest.json` is intentionally timestamp-free (deterministic contract), so
  this sidecar file is the sole publication-time source; the pipeline never
  writes it.
- Decision: no previous publication, or `age >= 13 minutes` → `RUN`; younger →
  `SKIP`. `workflow_dispatch` always forces `RUN`.
- Every expensive step (GeoIP provisioning/checksum/verify, migrations,
  seeding, pipeline, output guard, stale-tree guard, commit/push) is guarded with
  `if: steps.freshness.outputs.decision == 'RUN'`, so a `SKIP` finishes the
  job green without running the pipeline. The gate itself is unguarded, so it
  is also re-evaluated by the Phase 21 retry.
- Failure semantics: if the pipeline, the output guard, a detected race, or the
  push fails, the timestamp is **not** advanced — scheduled runs keep retrying
  until a genuinely successful publication lands.

Steps (when `RUN`): checkout → uv/Python 3.12 → `uv sync --all-extras` →
`mkdir output` → freshness gate → GeoIP provisioning + SHA-256 checksum +
`verify-geoip` → `alembic upgrade head` (SQLite at `output/proxyaggregator.db`,
gitignored via `*.db`) → **seed production sources** → **run production
pipeline** → empty-output guard → **stale-tree guard** → `record-publish` →
`git add output README.md` → commit & push
(`chore: update generated subscriptions`).

The empty-output guard fails the job when no artifacts were produced, so
stale or empty subscriptions are **never** published. The commit step exits
cleanly when `git diff --cached --quiet` shows no changes.

### Full pipeline integration (`pipeline.py`)

The step `uv run python -m proxyaggregator pipeline` is the workflow's
production entrypoint. The `pipeline` module (Phase 9.1) orchestrates the
existing phases in a single deterministic run:

    sources -> fetch -> parse -> dedup -> persist -> geoip -> health
             -> score -> rank -> subscribe -> publish into output/

It delegates to the Phase 2-9 modules and models and adds **no** new parsing,
dedup, scoring, or persistence logic. Key contracts:

- **Configured sources** are loaded from the `sources` table (id order) via
  `pipeline.load_configured_sources`. The pipeline never invents or hardcodes
  sources and never touches `publishing.samples` demo content. An empty table
  is a fatal `no_configured_sources` error.
- **Failure isolation**: one failing source does not block the others, and a
  per-entry parse failure is skipped (a `ParseError` is not fatal).
- **Empty-result policy**: if no proxy is eligible after health checks the run
  raises `PipelineError("no_eligible_proxies")`, exits non-zero, and writes
  **nothing** — stale or empty feeds are never published. The workflow's
  empty-output guard is a second, independent line of defense.
- **Determinism**: feeds + manifest are byte-identical for identical inputs
  (no timestamps, no random values); the step order is fixed.
- **Credential hygiene**: the pipeline logs stage counts only — never URLs,
  usernames, passwords, or raw URIs. The CLI also silences `httpx`/`httpcore`
  so fetched URLs do not reach the log stream.
- **Fail-fast exit codes**: fatal failures return exit code 1
  (`no_configured_sources`, `no_eligible_proxies`, scoring/subscription/
  publisher failures, or any unexpected exception).

**Production readiness (seeding).** The `sources` table is the only
production source configuration mechanism. Phase 9.2 added
`python -m proxyaggregator seed-sources`, which loads the version-controlled
`config/sources.json` definition file into the table (validated,
credential-free, url-keyed upsert) — see `docs/SOURCES.md`. The workflow runs
it **before** the pipeline. The file currently ships as an empty array: real,
trusted production source URLs are an operator input, so until one is supplied
the pipeline correctly fails on `no_configured_sources` rather than
fabricating feeds.