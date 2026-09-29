# README Separation Report — Stable Root README vs. Live Country Feeds

Date: 2026-09-29
Status: **complete** — implemented, verified locally, and committed.
Commit: `57f9cea` — `docs(readme): keep the root README stable and the country index live`
Local only, **not pushed**. Deliberately **not** a Phase 24 commit or tag.

## 1. Objective

Separate the stable root `README.md` from the dynamic country-feed
information, so that a successful publication no longer rewrites the
repository's front page.

Before: every successful publish regenerated a marker-delimited country index
inside the root `README.md`, so the file changed on almost every publication
even though its content had nothing to do with the project documentation.

After: the root `README.md` is hand-maintained and changes only when a human
edits it. The live country index lives exclusively in
`output/countries/README.md`, and the per-country pages in
`output/countries/<ISO>/README.md`.

Explicitly out of scope, and untouched: the publishing pipeline, watchdog,
scheduler, parsers, health checks, GeoIP, deduplication, scoring, database,
subscriptions, and country-feed generation logic.

## 2. What the current README structure was

`README.md` was **1627 lines**, of which **lines 113–1627 (93%) were
generated**:

| Lines | Content | Nature |
| --- | --- | --- |
| 1–14 | Title, tagline, badges | hand-maintained |
| 15–51 | `## 🔥 Ready-to-use Subscription Links` — Recommended, By Protocol, By Country | hand-maintained |
| 52–112 | How to Use, Features, For Developers, Documentation, License | hand-maintained |
| **113–1627** | `<!-- PROXYAGGREGATOR: country index start -->` … `## 🌍 Proxies by Country`, a 250-entry ISO flag map, one collapsed `<details>` per available country … `<!-- PROXYAGGREGATOR: country index end -->` | **generated on every publish** |

Two findings from the inspection shaped the change:

1. **The stable pointer already existed.** `README.md:46-48` already carried

   ```markdown
   ### By Country

   🦋 **[View all countries with healthy proxies →](./output/countries/README.md)**
   ```

   So no new navigation had to be invented — only the dynamic block removed.

2. **The dynamic block was redundant *and* inferior.** The per-country pages
   carry strictly more: the healthy-proxy count, a GitHub "Open" link **and**
   a copyable raw subscription URL per protocol:

   ```markdown
   # 🇦🇪 United Arab Emirates
   3 healthy proxies.
   ## 📋 All Protocols
   | Format | GitHub | Raw subscription |
   |---|---|---|
   | Plain | [Open](./all.txt) | `https://raw.../countries/AE/all.txt` |
   ```

   The root block only emitted raw URLs inside ` ```text ` fences. Removing it
   therefore loses **no** information.

`README.fa.md` (111 lines) was inspected and required no change: it already has
no markers and no generated block, and the pipeline hard-codes `"README.md"`,
so it was never auto-written.

## 3. Which code path previously modified the root `README.md`

```
src/proxyaggregator/pipeline.py:585-588
    root_readme = Path(cfg.output_dir).parent / "README.md"
    entries = country_feed_entries(ranked_proxies, max_items=cfg.max_items)
    if update_root_country_index(root_readme, entries):
        logger.info("[PIPELINE] root README country index updated: %s", root_readme)
        |
        +-> countries.update_root_country_index()        (countries.py:382)
              |
              +-> render_root_country_index_block()     (countries.py:267)
              |     builds the marker-delimited block
              |
              +-> _splice_country_block()               (countries.py:363)
                    replaces the marker region, or INSERTS the block
                    before "## Quick Start" when the markers are absent
```

`.github/workflows/publish.yml` then staged and committed the result
(`git add output README.md` → commit & push), which is why the front page
changed on nearly every publication.

A second, less obvious effect: `published_artifacts=len(releases) + 1`
(`pipeline.py:594`). The `+1` **was** the root `README.md` — it was counted as
a published artifact on every run.

### Why the country feeds were never at risk

`output/countries/README.md` is rendered by `_index_readme()` from entries
computed **inside** `build_country_artifacts` (`countries.py:474`), and the
per-country pages by `_country_readme()`. Neither calls the root-README code
path, and the stale-artifact pruning lives in `publisher.py`
(`_prune_stale_artifacts` / `_prune_countries_subtree`). Inspection confirmed
`publisher.py` needs no change at all, so:

- the live country index keeps its exact generation behaviour, and
- ephemeral removal is unchanged — a country or protocol with no eligible
  healthy proxy in a successful publication still has its obsolete feed
  deleted, and **no stale-file retention was added**.

## 4. Exactly what was changed

| File | Change |
| --- | --- |
| `README.md` | **−1516 / +5.** Deleted the generated block; lines 1–111 are byte-identical to before (verified with `diff`). Added a three-line note under *By Country* explaining that country feeds are rebuilt on every publish and this README is hand-maintained. |
| `src/proxyaggregator/pipeline.py` | Removed the `update_root_country_index()` call and the two now-unused imports (`country_feed_entries`, `update_root_country_index`). `published_artifacts=len(releases) + 1` → `len(releases)`. |
| `src/proxyaggregator/publishing/countries.py` | Removed `update_root_country_index`, `_splice_country_block`, `render_root_country_index_block`, `country_index_entries`, `ROOT_README_COUNTRY_START_MARKER`, `ROOT_README_COUNTRY_END_MARKER` (−163 lines of dead code). Replaced the marker doc-comment with one stating the root README is hand-maintained. |
| `src/proxyaggregator/publishing/__init__.py` | Removed the five corresponding imports and `__all__` entries. |
| `tests/test_location_feeds.py` | New module docstring contract; replaced `test_root_readme_country_index_generated_when_readme_present` with `test_pipeline_does_not_modify_root_readme` + `test_country_index_and_country_pages_still_generated`; replaced the 18-test `TestRootReadmeCountryIndex` class with the 3-test `TestRootReadmeStability`; dropped the `_root_countries` helper and four dead imports. |
| `tests/test_protocol_feeds.py` | `test_readme_has_subscriptions_section` now bounds the section by the next `## ` heading instead of the deleted marker; added `test_readme_has_no_generated_country_index`; dropped the marker import. |
| `tests/test_pipeline.py`, `tests/test_seeding.py` | `published_artifacts` assertions adjusted for the removed artifact (20→19, 2→1, 16→15). |

Net: **8 files, +111 / −1909.**

`country_feed_entries` was deliberately **kept**: it is still the shared source
of truth that `build_country_artifacts` and the country index agree on.

## 5. Is the dynamic modification now disabled or removed?

**Removed entirely — not merely disabled.** There is no invocation left, and
the functions themselves were deleted rather than left unreachable.

```console
$ grep -rn "update_root_country_index\|render_root_country_index_block\|\
ROOT_README_COUNTRY\|country_index_entries" src/ tests/ --include=*.py
(no output)
```

`publish.yml` was intentionally **left untouched**. With no writer, the
`git add output README.md` step is now a harmless no-op for the README, and the
Phase 21 concern about README changes being swept into a publication commit
resolves itself without touching the workflow.

## 6. Resulting structure

### 1. `README.md` — stable, 116 lines

```markdown
# 🚀 ProxyAggregator
## 🔥 Ready-to-use Subscription Links     (Recommended / By Protocol / By Country)
## 📱 How to Use
## ✨ Features
## 🛠️ For Developers
### Documentation
## 📄 License
```

No markers, no generated country list, no per-country URLs — only the stable
pointer to `./output/countries/README.md`.

### 2. `output/countries/README.md` — the live index, unchanged

A Markdown table (Country / Code / Proxies) regenerated on every successful
publish, one row per country that has healthy proxies.

### 3. `output/countries/<ISO>/README.md` — per country, unchanged

Counts, all-protocol feeds and per-protocol feeds. Feed files remain ephemeral
live artifacts.

## 7. Tests

New contract tests:

| Test | Asserts |
| --- | --- |
| `TestRootReadmeStability::test_root_readme_has_no_generated_country_index` | No `PROXYAGGREGATOR` marker, no `## 🌍 Proxies by Country`, no per-country URLs |
| `TestRootReadmeStability::test_root_readme_links_to_live_country_index` | The stable pointer to `./output/countries/README.md` survives |
| `TestRootReadmeStability::test_root_readme_keeps_its_documentation` | All six documentation headings still present — separating the dynamic index must not drop useful docs |
| `TestPipelinePurity::test_pipeline_does_not_modify_root_readme` | **A full pipeline run leaves the root README byte-identical** |
| `TestPipelinePurity::test_country_index_and_country_pages_still_generated` | The index and per-country pages are still produced |
| `TestReadmeLinks::test_readme_has_no_generated_country_index` | Root-README contract, from the protocol-feeds side |

No test was deleted to make the suite pass. The 18 retired tests asserted the
*old* contract (a generated block in the root README); they were replaced by
tests of the new one. Notably, the three coverage guarantees that mattered most
were carried over to the live index instead of being lost: a URL is only ever
emitted for a feed that actually exists, every generated per-country feed
appears in the index, and the counts in the index match the per-country counts.

### Results

| Run | Result |
| --- | --- |
| `pytest tests/test_location_feeds.py tests/test_protocol_feeds.py` | **109 passed** |
| `pytest` (full suite) | **1140 passed, 16 warnings** |
| Before this change | 1153 passed — net −13 (18 retired, 5 added) |

### Mutation-verified

To prove the regression test is not vacuous, the original
`countries.py`, `__init__.py` and `pipeline.py` were temporarily restored and
the new tests run:

```
FAILED tests/test_location_feeds.py::TestPipelinePurity::test_pipeline_does_not_modify_root_readme
E   + <!-- PROXYAGGREGATOR: country index start -->
E   + ## 🌍 Proxies by Country
E   ...
1 failed, 4 passed
```

It fails on the old behaviour with a readable diff, then the implementation was
restored and 1140 tests re-confirmed green.

One assertion of mine was initially wrong and was corrected: I first asserted
`"<details>" not in readme`, which failed because the stable, hand-written
*By Protocol* section legitimately uses a `<details>` block. The assertion was
narrowed to per-country URLs, which is what the contract actually forbids.

## 8. Lint / format

| Check | Result |
| --- | --- |
| `ruff check src/ tests/` | **All checks passed** (3 orphaned imports fixed: `COUNTRY_UNKNOWN_BUCKET`, `pathlib.Path`, `country_feed_entries`) |
| `ruff format --check src/ tests/` | **90 files already formatted** |
| `git diff --check` | clean |
| `alembic heads` | `d4e5f6a7b8c9 (head)` — single, unchanged |

## 9. Final git diff summary

```console
 README.md                                   | 1521 +-----
 src/proxyaggregator/pipeline.py             |   13 +-
 src/proxyaggregator/publishing/__init__.py  |   10 -
 src/proxyaggregator/publishing/countries.py |  170 +--
 tests/test_location_feeds.py                |  269 ++---
 tests/test_pipeline.py                      |    6 +-
 tests/test_protocol_feeds.py                |   27 +-
 tests/test_seeding.py                       |    4 +-
 8 files changed, 111 insertions(+), 1909 deletions(-)
```

Verified untouched:

- `output/` — **zero diff**; no generated subscription output changed
- `alembic/`, `config/`, `pyproject.toml`
- `parsers/`, `health/`, `geoip/`, `scoring/`, `db/`, `sources/`
- `publisher.py` (so pruning and stale-file removal are untouched)
- `.github/workflows/` (watchdog, scheduler, publish)
- `README.fa.md`, `docs/`, `ROADMAP.md`

Documentation was audited rather than assumed: no doc claimed the root README
country index was auto-regenerated, so no stale claim needed correcting. The
only two `README.md` mentions in `docs/` are about the `git add output README.md`
staging step, which is accurate and unchanged.

## 10. Remaining issues

1. **`published_artifacts` drops by 1** (e.g. 254 → 253 in the publish
   summary, and 20 → 19 in tests). This is correct — the root README is no
   longer a published artifact — but it is a visible change in the next
   publish summary.
2. **Process note, not a code issue.** Mid-task a scripted edit overwrote
   `tests/test_location_feeds.py` with `tests/test_protocol_feeds.py`'s
   content. It was caught by a section-header sanity check, restored from git
   in full, and the edits were redone with the `Edit` tool. No other file was
   affected; all six edited files were verified afterwards and `src/` was never
   involved.
3. The next successful publish will no longer stage a README change, so the
   publication commit will contain `output/` only.
4. **Not pushed.** `origin/main` remains at `2d95caf`; the local branch is
   `ahead=1, behind=0`. CI has not run against this change.

## 11. The commit

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

Only these eight files were staged; the Phase 17–23 reports and the
`scripts/wait_*.py` helpers were left untracked and were not included.

## 12. Pre-commit review

| Check | Result |
| --- | --- |
| `output/` changes | none |
| `.github/workflows/` changes | none |
| parsers / health / GeoIP / scoring / db / sources / dedup | none |
| `alembic/`, `config/`, `pyproject.toml` | none |
| `publisher.py` (pruning / stale-removal) | none |
| `README.fa.md`, `docs/`, `ROADMAP.md` | none |
| Reports or scripts staged | none |
| Secrets or tokens in added lines | none |

Because `tests/test_location_feeds.py` was the file affected by the incident
in §10.2, it was re-checked explicitly: the file identity is intact (Phase 17
docstring, 13 classes) and a test-function diff shows only the 19 old
root-index tests removed and 5 new ones added (62 → 48) — no unrelated test
was lost. The index-parity coverage removed with
`test_root_list_matches_country_index_counts` was verified to still exist as
`test_index_count_matches_all_feed` and
`test_index_protocol_files_exist_for_every_indexed_country`, asserted against
the live index instead.
