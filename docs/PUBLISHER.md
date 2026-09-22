# Phase 9 — GitHub Publisher & Release Automation

Phase 9 makes generated subscriptions publishable: a deterministic
**publisher library** writes Phase 8 feeds to disk, a **release manifest**
records their sizes and hashes, a **local dry-run** exercises the whole chain
without GitHub, and a **GitHub Actions workflow** runs migration, production
pipeline, and artifact commit on a schedule or manual dispatch.

## Scope

Phase 9 covers three ROADMAP items and **deliberately stops** on the fourth:

| ROADMAP item | Status | Location |
|---|---|---|
| Release automation | Done | `publishing/publisher.py` |
| Commit & push workflow | Done | `.github/workflows/publish.yml` |
| GitHub Actions orchestration | Done | `.github/workflows/publish.yml` |
| Full pipeline integration | **Blocked / reported** | see below |

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

Builds the three canonical feeds from embedded **synthetic** example.com
proxies (RFC 6761; obviously fake credentials), publishes them via the real
publisher, writes `manifest.json`, and prints the manifest. Running it twice
produces byte-identical output — this validates the Phase 9 chain locally.

`python -m proxyaggregator` with no arguments still prints the version.

## GitHub Actions workflow (`.github/workflows/publish.yml`)

- Triggers: `workflow_dispatch` (manual) and `schedule` daily at `00:00 UTC`
  (pre-existing contract, kept unchanged).
- `permissions: contents: write` — least-privilege scope.
- `concurrency.group: publish` with `cancel-in-progress: false` so scheduled
  runs never race each other on the same branch.
- Steps: checkout → uv/Python 3.12 → `uv sync --all-extras` → `mkdir output`
  → `alembic upgrade head` (SQLite at `output/proxyaggregator.db`, gitignored
  via `*.db`) → **run production pipeline** → empty-output guard → commit &
  push.

The empty-output guard fails the job when no artifacts were produced, so
stale or empty subscriptions are **never** published. The commit step exits
cleanly when `git diff --cached --quiet` shows no changes.

### Full pipeline integration — STOP point

The step `uv run python -m proxyaggregator pipeline` is the workflow's
production entrypoint. It does **not exist yet**: the CLI exposes only
`sample-subscriptions`, and no orchestrator connects sources → parse →
dedup → geoip → health → scoring → subscription. Per the Phase 9 contract the
workflow ships this step in place and **fails at it** (as it should — a
missing pipeline must not produce empty/stale artifacts), rather than invent
a parallel architecture. The exact missing piece: a single command (e.g.
`proxyaggregator pipeline`) that fetches sources, persists parsed configs,
runs Phase 4-7 enrichment/scoring, calls `build_subscription`, and writes via
`publish_subscriptions` into `output/`. See `PHASE9_REPORT.md`.