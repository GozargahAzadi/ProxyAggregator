# Final Review & Commit Report — README Separation

Date: 2026-09-29
Status: **complete** — the change is committed locally and verified.
Commits: `57f9cea` (the README separation change), `5cd170a` (the separation
report), plus this report's own commit.
Local only — **nothing pushed**. No Phase 24 work, no Phase 24 tag.

Companion to `README_SEPARATION_REPORT.md`, which records the design, the
inspection and the per-file changes. This file records the final pre-commit
review, the commit itself, and the post-commit state.

## 1. Why this commit exists

The README separation work was implemented and verified in an earlier step but
had not yet been committed. This was the final review-and-commit pass: confirm
that only the intended changes were present, then commit exactly those.

## 2. Pre-commit state

```console
$ git status --short
 M README.md
 M src/proxyaggregator/pipeline.py
 M src/proxyaggregator/publishing/__init__.py
 M src/proxyaggregator/publishing/countries.py
 M tests/test_location_feeds.py
 M tests/test_pipeline.py
 M tests/test_protocol_feeds.py
 M tests/test_seeding.py
?? PHASE17_REPORT.md … PHASE23_REPORT.md          (untracked, not staged)
?? scripts/wait_*.py, scripts/watch_publish_run.py (untracked, not staged)

$ git diff --stat
 README.md                                   | 1521 +--------------------------
 src/proxyaggregator/pipeline.py             |   13 +-
 src/proxyaggregator/publishing/__init__.py  |   10 -
 src/proxyaggregator/publishing/countries.py |  170 +--
 tests/test_location_feeds.py                |  269 ++---
 tests/test_pipeline.py                      |    6 +-
 tests/test_protocol_feeds.py                |   27 +-
 tests/test_seeding.py                       |    4 +-
 8 files changed, 111 insertions(+), 1909 deletions(-)
```

Exactly eight tracked modifications, matching the expected scope one-for-one.

## 3. Scope review

| Check | Result |
| --- | --- |
| `output/` changes (generated subscriptions) | **none** |
| `.github/workflows/` changes (watchdog, scheduler, publish) | **none** |
| parsers / health / GeoIP / scoring / db / dedup / sources | **none** |
| `alembic/`, `config/`, `pyproject.toml` | **none** |
| `src/proxyaggregator/publishing/publisher.py` (pruning, stale removal) | **none** |
| `README.fa.md`, `docs/`, `ROADMAP.md` | **none** |
| Reports or helper scripts staged | **none** — only the 8 files were staged |
| Secrets, tokens or keys in added lines | **none** |

### Extra check on `tests/test_location_feeds.py`

This file was overwritten mid-implementation by a scripted edit and restored
from git, so it was re-verified rather than trusted:

- **File identity intact** — Phase 17 module docstring present, 13 classes.
- **Test-function diff** — only the 19 old root-index tests were removed and
  5 new contract tests added (62 → 48). Every removed test was one of
  `test_render_block_*`, `test_update_root_readme_*`,
  `test_root_list_matches_country_index_counts`, or
  `test_root_readme_country_index_generated_when_readme_present`. No unrelated
  test was lost.
- **No coverage gap** — the parity coverage dropped with
  `test_root_list_matches_country_index_counts` still exists as
  `test_index_count_matches_all_feed` and
  `test_index_protocol_files_exist_for_every_indexed_country`, now asserted
  against the live index at `output/countries/README.md`.

## 4. The commit

```text
57f9cea2eb6d6163bf17b358e56d389114cd89ee
docs(readme): keep the root README stable and the country index live

The root README carried a generated country block, so every successful
publication rewrote the front page. The live index already exists at
output/countries/README.md, and the per-country pages are richer than the
block, so nothing is lost by removing it.

Remove update_root_country_index() and its renderer, splicer and markers
rather than leaving unreachable code, and stop counting the root README as a
published artifact. publish.yml is untouched: with no writer, the existing
git add output README.md is a no-op for the README.
```

```
 README.md                                   | 1521 +--------------------------
 src/proxyaggregator/pipeline.py             |   13 +-
 src/proxyaggregator/publishing/__init__.py  |   10 -
 src/proxyaggregator/publishing/countries.py |  170 +--
 tests/test_location_feeds.py                |  269 ++---
 tests/test_pipeline.py                      |    6 +-
 tests/test_protocol_feeds.py                |   27 +-
 tests/test_seeding.py                       |    4 +-
 8 files changed, 111 insertions(+), 1909 deletions(-)
```

## 5. Verification already green before the commit

| Check | Result |
| --- | --- |
| Targeted tests (`test_location_feeds.py`, `test_protocol_feeds.py`) | **109 passed** |
| Full suite (`pytest`) | **1140 passed, 16 warnings** |
| `ruff check src/ tests/` | **passed** |
| `ruff format --check src/ tests/` | **passed** (90 files already formatted) |
| `git diff --check` | **clean** |
| `alembic heads` | **single head** `d4e5f6a7b8c9` |

No code was modified after these runs, and none after the commit. The
regression test was additionally mutation-verified earlier: restoring the
original source made `test_pipeline_does_not_modify_root_readme` fail with the
injected country block visible in the diff, then pass again once the new source
was restored — so the test is not vacuous.

## 6. Post-commit state

```console
$ git diff --stat          # EMPTY
$ git diff --cached --stat # EMPTY
$ git status --short
?? PHASE17_REPORT.md … PHASE23_REPORT.md
?? scripts/wait_*.py, scripts/watch_publish_run.py

$ git log -2 --oneline
5cd170a docs: add the README separation report
57f9cea docs(readme): keep the root README stable and the country index live
```

The tracked working tree is clean. The only remaining untracked files are the
seven historical Phase 17–23 reports and the three Phase 19–21 helper scripts —
pre-existing, outside this task's scope, and deliberately left alone.

## 7. Push and tag status

- **Nothing was pushed.** `origin/main` remains at `2d95caf`; local is
  `behind=0, ahead=2` (or 3 with this report). CI has not run against this
  change, so the green results in §5 are local only.
- **No Phase 24 tag** was created, and no tag points at these commits.

## 8. Known consequences

1. `published_artifacts` drops by 1 (e.g. 254 → 253 in the publish summary,
   20 → 19 in tests) because the root README is no longer a published
   artifact. This is correct, but it will be visible in the next summary.
2. The next successful publish will no longer stage a README change, so the
   publication commit will contain `output/` only.
3. A push and a CI run are still outstanding if this change is to be validated
   on GitHub.
