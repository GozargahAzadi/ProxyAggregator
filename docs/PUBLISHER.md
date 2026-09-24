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

- Triggers: `workflow_dispatch` (manual) and `schedule` daily at `00:00 UTC`
  (pre-existing contract, kept unchanged).
- `permissions: contents: write` — least-privilege scope.
- `concurrency.group: publish` with `cancel-in-progress: false` so scheduled
  runs never race each other on the same branch.
- Steps: checkout → uv/Python 3.12 → `uv sync --all-extras` → `mkdir output`
  → `alembic upgrade head` (SQLite at `output/proxyaggregator.db`, gitignored
  via `*.db`) → **seed production sources** → **run production pipeline** →
  empty-output guard → commit & push.

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