# Push Status Report — README Separation

Date: 2026-09-29
Status: **blocked on a decision** — nothing has been pushed.
Branch: `main`, local `ahead=4, behind=0` against `origin/main` (`2d95caf`).
No Phase 24 work, no Phase 24 tag, no files modified beyond this report.

Third companion document:

| File | Commit | Covers |
| --- | --- | --- |
| `README_SEPARATION_REPORT.md` | `5cd170a` | design, inspection, per-file changes |
| `README_SEPARATION_COMMIT_REPORT.md` | `4239ec7` | pre-commit review, the commit, post-commit state |
| this file | — | the outstanding push decision |

## 1. The request

Push commit `57f9cea` — `docs(readme): keep the root README stable and the
country index live` — to GitHub, using a normal fast-forward push, creating no
new commit, amending nothing, and excluding all untracked files and the
Phase 17–23 reports.

## 2. Verification result

| # | Check | Expected | Actual | |
| --- | --- | --- | --- | --- |
| 1 | `HEAD` | `57f9cea` | `4239ec7` | **FAIL** |
| 2 | working tree | clean | clean; nothing staged | pass |
| 3 | `origin/main` | `2d95caf` | `2d95caf` | pass |
| 3 | ahead of `origin/main` | exactly 1 | 3 at the time of the check | **FAIL** |
| 4 | untracked report/script staged | none | nothing staged | pass |

The push was **not** performed, because two preconditions did not hold and
executing it anyway would not have done what was asked.

## 3. Why `HEAD` is no longer `57f9cea`

`57f9cea` was made first, exactly as requested. `HEAD` then moved twice, each
time because a report was explicitly requested to be saved:

```
4239ec7 docs: add the README separation final review and commit report
5cd170a docs: add the README separation report
57f9cea docs(readme): keep the root README stable and the country index live   ← originally requested
```

- `5cd170a` came from "گزارش سیو کن" — the design/inspection report was written,
  then committed once the report itself was asked for.
- `4239ec7` came from "گزارش تو فایل جدید سیو کن" — a second, new report file
  for the final review and commit.

Nothing was amended, rebased, squashed or force-pushed at any point, so
`57f9cea` is intact and is still a direct descendant of `2d95caf`. Only the
branch tip moved.

## 4. Constraints that still hold

- The Phase 17–23 reports remain **untracked** and were never staged.
- `scripts/wait_and_extract_pipeline_log.py`, `scripts/wait_for_dispatch_run.py`
  and `scripts/watch_publish_run.py` remain **untracked**.
- The only report files ever committed are `README_SEPARATION_REPORT.md` and
  `README_SEPARATION_COMMIT_REPORT.md`, plus this one.
- `git diff` and `git diff --cached` are empty: the tracked working tree is
  clean.

## 5. Options for the push

### Option A — push all four commits *(recommended)*

```console
git push origin main
```

One normal fast-forward, `2d95caf` → the current tip. History stays linear,
local and remote stay in sync, and CI runs against the `57f9cea` code change.
The two report files also become public.

This is the only option that leaves the repository in a state that can be
worked on normally afterwards.

### Option B — push only `57f9cea`

```console
git push origin 57f9cea:main
```

Technically a valid fast-forward, because `57f9cea`'s parent is `2d95caf`, and
it rewrites nothing. But it leaves local `main` **diverged** — every remaining
local commit becomes unpushable, and the next `git push origin main` is
rejected as non-fast-forward. Recovering requires a merge or a reset, and the
instructions for this task forbid amending or rewriting history, so that
cleanup could not be done here without a further decision.

### Option C — leave everything local

No push. The change stays verified-but-unpublished, and CI does not run.

## 6. Recommendation

**Option A.** The divergence in Option B is not cosmetic: it would leave the
branch in a state where ordinary future work is blocked, in exchange for
keeping two documentation files off the remote. Splitting the reports from the
code change also has a documentation cost — the report that describes `57f9cea`
is itself committed after it.

## 7. Still outstanding after any push

1. CI has never run against `57f9cea`; all results so far (109 targeted tests,
   1140 full-suite tests, ruff, format, single alembic head `d4e5f6a7b8c9`) are
   local only.
2. `published_artifacts` will drop by 1 (e.g. 254 → 253) in the next publish
   summary, because the root README is no longer a published artifact.
3. The next successful publish will stage `output/` only — no README change.
