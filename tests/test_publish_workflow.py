"""Contract tests for the Phase 21 publish workflow orchestration.

These tests pin the observable safety properties of
``.github/workflows/publish.yml`` and ``.github/actions/publish/action.yml``:
a bounded two-attempt publication flow that never publishes output generated
from a stale tree, never rebases or force-pushes, and never advances
``output/published_at.json`` unless a push genuinely succeeded.
"""

from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT_DIR / ".github" / "workflows" / "publish.yml"
WATCHDOG_PATH = ROOT_DIR / ".github" / "workflows" / "publish-watchdog.yml"
ACTION_PATH = ROOT_DIR / ".github" / "actions" / "publish" / "action.yml"

RUN_CONDITION = "steps.freshness.outputs.decision == 'RUN'"
NO_RACE_CONDITION = f"{RUN_CONDITION} && steps.race.outputs.raced == 'false'"

GATE_STEP = "Freshness gate"
BASE_STEP = "Record base commit"
PIPELINE_STEP = "Run production pipeline"
RACE_STEP = "Verify base commit is still origin/main"
GUARD_STEP = "Guard against empty or invalid output"
RECORD_STEP = "Record successful publication time"
COMMIT_STEP = "Commit & push generated subscriptions"
SUMMARY_STEP = "Write run summary"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def action() -> dict:
    return yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def action_text() -> str:
    return ACTION_PATH.read_text(encoding="utf-8")


def _step(action: dict, name: str) -> dict:
    for step in action["runs"]["steps"]:
        if step["name"] == name:
            return step
    raise AssertionError(f"step {name!r} not found in {ACTION_PATH}")


def _step_index(action: dict, name: str) -> int:
    return next(i for i, step in enumerate(action["runs"]["steps"]) if step["name"] == name)


def _job(workflow: dict, name: str) -> dict:
    assert name in workflow["jobs"], f"job {name!r} not found"
    return workflow["jobs"][name]


class TestExistingWorkflowIsIntact:
    def test_triggers_are_unchanged(self, workflow):
        triggers = workflow[True]
        assert triggers["schedule"] == [{"cron": "*/5 * * * *"}]
        assert "workflow_dispatch" in triggers
        assert triggers["repository_dispatch"] == {"types": ["publish-request"]}

    def test_permissions_remain_contents_write(self, workflow):
        assert workflow["permissions"] == {"contents": "write"}

    def test_concurrency_group_is_unchanged(self, workflow):
        assert workflow["concurrency"] == {
            "group": "publish",
            "cancel-in-progress": False,
        }

    def test_runtime_environment_is_unchanged(self, workflow):
        env = workflow["env"]
        assert env["PA_DATABASE_URL"] == "sqlite:///output/proxyaggregator.db"
        assert env["PA_SOURCES_FILE"] == "config/sources.json"
        assert env["PA_GEOIP_DB_PATH"] == (
            "${{ github.workspace }}/.runtime/geoip/user-country.mmdb"
        )

    def test_toolchain_steps_are_unchanged(self, workflow):
        for job_name in ("attempt-1", "attempt-2"):
            steps = _job(workflow, job_name)["steps"]
            assert steps[1]["uses"] == "astral-sh/setup-uv@v4"
            assert steps[1]["with"] == {"version": "0.12"}
            assert steps[2]["run"] == "uv python install 3.12"
            assert steps[3]["run"] == "uv sync --all-extras"

    def test_generation_sequence_is_preserved(self, action):
        steps = action["runs"]["steps"]
        names = [step["name"] for step in steps]
        assert names == [
            "Create output directory",
            BASE_STEP,
            GATE_STEP,
            "Provision GeoIP database",
            "Verify GeoIP database checksum",
            "Verify GeoIP database",
            "Apply database migrations",
            "Seed production sources",
            PIPELINE_STEP,
            GUARD_STEP,
            RACE_STEP,
            RECORD_STEP,
            COMMIT_STEP,
            SUMMARY_STEP,
        ]
        assert _step(action, "Apply database migrations")["run"] == ("uv run alembic upgrade head")
        assert _step(action, "Seed production sources")["run"] == (
            "uv run python -m proxyaggregator seed-sources"
        )
        pipeline_run = _step(action, PIPELINE_STEP)["run"]
        assert "uv run python -m proxyaggregator pipeline" in pipeline_run
        assert '--stats-file "${{ inputs.stats-file }}"' in pipeline_run
        assert _step(action, "Verify GeoIP database")["run"] == (
            "uv run python -m proxyaggregator verify-geoip"
        )

    def test_freshness_gate_runs_before_any_generation(self, action):
        steps = action["runs"]["steps"]
        gate_index = _step_index(action, GATE_STEP)
        for name in (
            "Provision GeoIP database",
            "Run production pipeline",
            GUARD_STEP,
            RACE_STEP,
        ):
            assert _step_index(action, name) > gate_index
        for name in (
            "Provision GeoIP database",
            "Verify GeoIP database checksum",
            "Verify GeoIP database",
            "Apply database migrations",
            "Seed production sources",
            "Run production pipeline",
            GUARD_STEP,
            RACE_STEP,
        ):
            assert steps[_step_index(action, name)]["if"] == RUN_CONDITION

    def test_freshness_threshold_is_thirteen_minutes(self, action_text):
        from proxyaggregator.publishing.freshness import (
            DEFAULT_FRESHNESS_THRESHOLD_MINUTES,
        )

        assert DEFAULT_FRESHNESS_THRESHOLD_MINUTES == 13
        assert "uv run python -m proxyaggregator freshness-gate $flag" in action_text

    def test_repository_dispatch_is_not_forced(self, action_text):
        # Only a manual dispatch may bypass the gate; the watchdog keeps the
        # 13-minute cadence intact.
        force_block = action_text.split('if [ "${{ github.event_name }}"')
        assert len(force_block) == 2
        assert '= "workflow_dispatch"' in force_block[1]
        assert 'flag="--force"' in force_block[1]

    def test_health_and_dns_concurrency_stay_within_limit(self):
        from proxyaggregator.config.settings import Settings

        settings = Settings()
        assert settings.health_check_concurrency <= 50
        assert settings.dns_resolution_concurrency <= 50

    def test_watchdog_workflow_is_unchanged(self):
        watchdog_text = WATCHDOG_PATH.read_text(encoding="utf-8")
        watchdog = yaml.safe_load(watchdog_text)
        # The watchdog stays on the 5-minute GitHub minimum, offset by three
        # minutes from the production cron so the two never fire together.
        assert watchdog[True]["schedule"] == [{"cron": "3,8,13,18,23,28,33,38,43,48,53,58 * * * *"}]
        assert "workflow_dispatch" in watchdog[True]
        # The watchdog *sends* repository_dispatch; it never receives one.
        assert watchdog[True].get("repository_dispatch") is None
        assert watchdog["concurrency"]["group"] == "publish-watchdog"
        assert watchdog["concurrency"]["cancel-in-progress"] is True
        # It must keep requesting publication instead of publishing anything.
        assert "event_type=publish-request" in watchdog_text
        watchdog_steps = [step for job in watchdog["jobs"].values() for step in job["steps"]]
        for step in watchdog_steps:
            assert "uses" not in step
            assert "git push" not in step.get("run", "")


class TestWatchdogRequestsAreReal:
    """Phase 23: a green watchdog run must not be mistaken for a triggered run.

    The watchdog was red for its whole life because ``gh api`` was passed
    ``--fail``, a flag that does not exist, so the step died before sending a
    request. Both of its green runs had skipped the dispatch entirely. These
    tests pin the dispatch to the documented GITHUB_TOKEN/repo_dispatch path
    and require the run to be *confirmed* rather than assumed.
    """

    @pytest.fixture(scope="class")
    def watchdog(self) -> dict:
        return yaml.safe_load(WATCHDOG_PATH.read_text(encoding="utf-8"))

    @pytest.fixture(scope="class")
    def steps(self, watchdog) -> list[dict]:
        return [s for job in watchdog["jobs"].values() for s in job["steps"]]

    def _step(self, steps: list[dict], name: str) -> dict:
        for step in steps:
            if step["name"] == name:
                return step
        raise AssertionError(f"watchdog step {name!r} not found")

    def test_dispatch_uses_no_unsupported_gh_flags(self, steps):
        request = self._step(steps, "Request publish run")
        # `gh api` has no --fail flag; passing it aborts the step before the
        # request is sent. `gh api` already exits non-zero on an HTTP error.
        assert "--fail" not in request["run"]
        assert "gh api --method POST" in request["run"]
        assert 'gh api --method POST "repos/$REPO/dispatches"' in request["run"]
        assert "-f event_type=publish-request" in request["run"]

    def test_dispatch_failure_still_fails_the_job(self, steps):
        request = self._step(steps, "Request publish run")
        # No unsupported flag, but error detection must not be lost with it.
        assert "set -euo pipefail" in request["run"]

    def test_watchdog_does_not_use_any_credential_but_the_default_token(self, watchdog):
        blob = yaml.safe_dump(watchdog)
        for forbidden in ("secrets.PAT", "secrets.TOKEN", "secrets.ACCESS", "PERSONAL"):
            assert forbidden not in blob
        # The only credential is the automatic per-run GITHUB_TOKEN.
        assert "secrets.GITHUB_TOKEN" in blob

    def test_requested_run_is_confirmed_not_assumed(self, steps):
        confirm = self._step(steps, "Confirm a publish run was created")
        script = confirm["run"]
        # The dispatch endpoint returns 204 with an empty body, so the only way
        # to know a run exists is to observe one.
        assert "repository_dispatch" in script
        assert "confirmed=true" in script
        assert "confirmed=false" in script
        # Bounded: it cannot poll forever.
        assert "for attempt in" in script
        assert "exit 1" in script
        # A missing epoch must fail loudly, not become a jq syntax error that
        # merely looks like "no run was created".
        assert "*[!0-9]*" in script
        # It runs only after an actual dispatch attempt.
        assert confirm["if"] == "steps.request.outcome == 'success'"

    def test_confirmation_cannot_dispatch_another_run(self, steps):
        confirm = self._step(steps, "Confirm a publish run was created")
        # Read-only by construction: no POST, no dispatch, no recursion.
        assert "dispatches" not in confirm["run"]
        assert "--method POST" not in confirm["run"]

    def test_watchdog_never_publishes_or_checks_out_code(self, steps):
        for step in steps:
            script = step.get("run", "")
            assert "git push" not in script
            assert "actions/checkout" not in script
            assert "record-publish" not in script

    def test_both_outcomes_are_reported_distinctly(self, steps):
        report = self._step(steps, "Report watchdog outcome")
        # A skipped request and a confirmed request must be told apart in the
        # job summary, so "no publication was triggered" is never ambiguous.
        assert report["if"] == "always()"
        assert "GITHUB_STEP_SUMMARY" in report["run"]
        assert "DISPATCH: ${{ steps.check.outputs.dispatch }}" in yaml.dump(report)
        assert "CONFIRMED: ${{ steps.confirm.outputs.confirmed }}" in yaml.dump(report)

    def test_active_run_check_rejects_unparseable_counts(self, steps):
        check = self._step(steps, "Check for an active publish run")
        # `gh api` does not apply --jq to an error body, so a failed call can
        # yield raw JSON. That must fail loudly rather than compare as zero and
        # dispatch on a guess.
        assert "*[!0-9]*" in check["run"]
        assert "exit 1" in check["run"]

    def test_watchdog_does_not_share_publish_concurrency(self, watchdog):
        assert watchdog["concurrency"]["group"] == "publish-watchdog"
        assert watchdog["concurrency"]["cancel-in-progress"] is True
        assert watchdog["permissions"] == {"contents": "write", "actions": "read"}


class TestNoForbiddenGitOperations:
    """Phase 23: no workflow may rewrite history or chain on run completion."""

    @pytest.fixture(scope="class")
    def all_workflow_files(self) -> list[Path]:
        return sorted((ROOT_DIR / ".github").rglob("*.yml"))

    def test_workflow_files_exist(self, all_workflow_files):
        assert all_workflow_files

    def test_no_history_rewriting(self, all_workflow_files):
        for path in all_workflow_files:
            text = path.read_text(encoding="utf-8")
            for forbidden in (
                "--force-with-lease",
                "push --force",
                "git rebase",
                "pull --rebase",
                "reset --hard",
            ):
                assert forbidden not in text, f"{forbidden!r} found in {path.name}"

    def test_no_workflow_run_chaining(self, all_workflow_files):
        # `workflow_run` as an event trigger would chain a workflow off another
        # workflow's completion. The API field `.workflow_runs[]` is unrelated
        # and must not trip this check, so match the trigger key only.
        for path in all_workflow_files:
            parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
            triggers = parsed.get(True, {}) if isinstance(parsed, dict) else {}
            assert "workflow_run" not in triggers, f"{path.name} chains on workflow_run"

    def test_release_verification_step_is_preserved(self, action):
        guard = _step(action, GUARD_STEP)
        script = guard["run"]
        assert "if [ ! -d output ]" in script
        assert "from proxyaggregator.publishing.publisher import verify_release" in script
        assert 'verify_release("output")' in script
        assert "Output guard passed" in script
        assert guard["if"] == RUN_CONDITION

    def test_base_commit_is_reported_before_generation(self, action):
        base = _step(action, BASE_STEP)
        assert base["id"] == "base"
        assert base.get("if") is None, "a freshness SKIP must still report the base commit"
        assert "git rev-parse HEAD" in base["run"]


class TestNoStalePublication:
    def test_base_commit_is_compared_against_origin_main(self, action):
        race = _step(action, RACE_STEP)
        assert race["if"] == RUN_CONDITION
        script = race["run"]
        assert 'base="$(git rev-parse HEAD)"' in script
        assert "git fetch --no-tags" in script
        assert "origin main" in script
        assert 'head_sha="$(git rev-parse FETCH_HEAD)"' in script
        assert 'if [ "$base" = "$head_sha" ]; then' in script
        assert 'echo "raced=true" >> "$GITHUB_OUTPUT"' in script
        assert 'echo "raced=false" >> "$GITHUB_OUTPUT"' in script

    def test_race_is_reported_before_the_publish_steps(self, action):
        steps = action["runs"]["steps"]
        race_index = _step_index(action, RACE_STEP)
        for name in (RECORD_STEP, COMMIT_STEP):
            step = _step(action, name)
            assert step["if"] == NO_RACE_CONDITION
            assert steps.index(step) > race_index

    def test_published_at_is_not_advanced_when_raced(self, action):
        record = _step(action, RECORD_STEP)
        assert "uv run python -m proxyaggregator record-publish" in record["run"]
        assert "raced == 'false'" in record["if"]

    def test_push_is_a_plain_fast_forward(self, action_text, workflow_text):
        combined = action_text + workflow_text
        for forbidden in (
            "--force-with-lease",
            "git push --force",
            "git push -f",
            "git rebase",
            "git pull --rebase",
            "git merge ",
            "reset --hard",
        ):
            assert forbidden not in combined, f"forbidden git operation: {forbidden}"
        assert "git push\n" in action_text

    def test_commit_step_configures_the_bot_and_adds_output(self, action):
        commit = _step(action, COMMIT_STEP)
        script = commit["run"]
        assert 'git config user.name "github-actions[bot]"' in script
        assert "git add output README.md" in script
        assert "git diff --cached --quiet" in script
        assert 'git commit -m "chore: update generated subscriptions"' in script
        assert commit["env"] == {"GITHUB_TOKEN": "${{ inputs.token }}"}
        # The commit is the last step that can touch the tree: the only step
        # after it is the read-only run summary, so nothing can be staged
        # between the race decision and the push.
        trailing = action["runs"]["steps"][_step_index(action, COMMIT_STEP) + 1 :]
        assert [step["name"] for step in trailing] == [SUMMARY_STEP]
        for step in trailing:
            for forbidden in ("git add", "git commit", "git push", "git checkout"):
                assert forbidden not in step["run"]


class TestBoundedRetries:
    def test_exactly_two_attempt_jobs_exist(self, workflow):
        assert list(workflow["jobs"]) == ["attempt-1", "attempt-2"]

    def test_attempt_2_runs_only_after_a_detected_race(self, workflow):
        first = _job(workflow, "attempt-1")
        second = _job(workflow, "attempt-2")
        assert first.get("needs") is None
        assert second["needs"] == "attempt-1"
        assert second["if"] == "needs.attempt-1.outputs.raced == 'true'"

    def test_attempt_1_exposes_the_race_output(self, workflow):
        first = _job(workflow, "attempt-1")
        assert first["outputs"] == {
            "decision": "${{ steps.publish.outputs.decision }}",
            "raced": "${{ steps.publish.outputs.raced }}",
            "published": "${{ steps.publish.outputs.published }}",
        }

    def test_attempt_1_uses_the_triggering_commit(self, workflow):
        first = _job(workflow, "attempt-1")
        checkout = first["steps"][0]
        assert checkout["uses"] == "actions/checkout@v4"
        assert "with" not in checkout

    def test_attempt_2_checks_out_latest_main(self, workflow):
        second = _job(workflow, "attempt-2")
        checkout = second["steps"][0]
        assert checkout["uses"] == "actions/checkout@v4"
        assert checkout["with"] == {"ref": "main"}

    def test_both_attempts_delegate_to_the_shared_action(self, workflow, action):
        for job_name in ("attempt-1", "attempt-2"):
            steps = _job(workflow, job_name)["steps"]
            publish = steps[4]
            assert publish["uses"] == "./.github/actions/publish"
            assert publish["id"] == "publish"
            assert publish["with"] == {
                "token": "${{ secrets.GITHUB_TOKEN }}",
                "attempt": "1" if job_name == "attempt-1" else "2",
            }
        # The shared action reruns the output guard and the freshness gate on
        # the retry, so a regenerated release is never published unguarded.
        assert _step(action, GUARD_STEP)["if"] == RUN_CONDITION
        assert _step(action, GATE_STEP).get("if") is None

    def test_exhausted_retries_fail_without_publishing(self, workflow):
        second = _job(workflow, "attempt-2")
        step = second["steps"][-1]
        assert step["name"] == "Report exhausted publication attempts"
        assert step["if"] == "steps.publish.outputs.raced == 'true'"
        assert "::error::" in step["run"]
        assert "exit 1" in step["run"]
        assert "published_at.json was not advanced" in step["run"]

    def test_no_self_dispatch_retrigger(self, workflow_text, action_text):
        for text in (workflow_text, action_text):
            for forbidden in ("/dispatches", "workflow_run", "github.run_id"):
                assert forbidden not in text

    def test_no_pat_dependency_is_introduced(self, workflow_text, action_text):
        combined = workflow_text + action_text
        for forbidden in ("secrets.PAT", "PERSONAL_ACCESS", "PAT:"):
            assert forbidden not in combined
        assert "secrets.GITHUB_TOKEN" in workflow_text


class TestProductionRunSummary:
    """Phase 22: every outcome is summarised, and none can publish falsely."""

    def test_summary_runs_for_every_outcome(self, action):
        step = _step(action, SUMMARY_STEP)
        assert step["if"] == "always()", (
            "a SKIP, a discarded race, and a failure must all be summarised"
        )
        assert step.get("continue-on-error") is None

    def test_summary_is_not_gated_on_the_freshness_decision(self, action):
        script = _step(action, SUMMARY_STEP)["run"]
        assert "publish-summary" in script
        # The freshness decision is passed *in*, not used as a guard.
        assert RUN_CONDITION not in script
        assert _step(action, SUMMARY_STEP)["if"] == "always()"

    def test_summary_reports_every_decision_input(self, action):
        step = _step(action, SUMMARY_STEP)
        env = step["env"]
        assert env == {
            "PA_DECISION": "${{ steps.freshness.outputs.decision }}",
            "PA_THRESHOLD": "${{ steps.freshness.outputs.threshold_minutes }}",
            "PA_PREVIOUS_PUBLISHED_AT": "${{ steps.freshness.outputs.published_at }}",
            "PA_AGE_SECONDS": "${{ steps.freshness.outputs.age_seconds }}",
            "PA_BASE_SHA": "${{ steps.base.outputs.sha }}",
            "PA_RACE": "${{ steps.race.outputs.raced }}",
            "PA_SANITY": "${{ steps.guard.outputs.sanity }}",
            "PA_PUBLISHED": "${{ steps.push.outputs.published }}",
        }
        for flag in (
            "--attempt",
            "--base-sha",
            "--decision",
            "--threshold-minutes",
            "--age-seconds",
            "--previous-published-at",
            "--race",
            "--sanity",
            "--published",
        ):
            assert flag in step["run"]

    def test_summary_reports_the_push_result(self, action):
        # A failed push must be summarised as FAILED, so the publication verdict
        # is taken from the push step's own output.
        step = _step(action, SUMMARY_STEP)
        assert step["env"]["PA_PUBLISHED"] == "${{ steps.push.outputs.published }}"
        assert '--published "$PA_PUBLISHED"' in step["run"]

    def test_summary_runs_after_the_publish_decision(self, action):
        assert _step_index(action, SUMMARY_STEP) > _step_index(action, COMMIT_STEP)
        assert _step_index(action, SUMMARY_STEP) > _step_index(action, GUARD_STEP)

    def test_summary_cannot_fail_a_run(self, action):
        script = _step(action, SUMMARY_STEP)["run"]
        assert "continue-on-error" not in script
        # The command itself always exits 0 (pinned in tests/test_summary.py), so
        # the only failure mode is a runner/interpreter crash.
        assert "|| true" not in script
        assert "exit 1" not in script

    def test_summary_does_not_write_the_publication_timestamp(self, action):
        script = _step(action, SUMMARY_STEP)["run"]
        assert "record-publish" not in script
        assert "published_at" not in script.replace("steps.push.outputs.published", "").replace(
            "PA_PUBLISHED", ""
        )

    def test_action_exposes_the_publication_and_sanity_results(self, action):
        assert set(action["outputs"]) == {"decision", "raced", "sanity", "published"}
        values = {name: spec["value"] for name, spec in action["outputs"].items()}
        assert values == {
            "decision": "${{ steps.freshness.outputs.decision }}",
            "raced": "${{ steps.race.outputs.raced }}",
            "sanity": "${{ steps.guard.outputs.sanity }}",
            "published": "${{ steps.push.outputs.published }}",
        }
        for name, spec in action["outputs"].items():
            assert spec["description"].strip(), f"{name} must document its value"

    def test_guard_reports_success_only_after_verification(self, action):
        guard = _step(action, GUARD_STEP)
        assert guard["id"] == "guard"
        assert guard["run"].index('verify_release("output")') < guard["run"].index(
            'echo "sanity=passed" >> "$GITHUB_OUTPUT"'
        )
        # A failing guard exits before exporting sanity, so the summary can only
        # ever report the guard's own verified outcome.
        assert 'echo "sanity=passed" >> "$GITHUB_OUTPUT"' in guard["run"]

    def test_push_reports_publication_only_after_a_successful_push(self, action):
        push = _step(action, COMMIT_STEP)
        assert push["id"] == "push"
        # The last statement, so a failed push can never report a publication.
        assert push["run"].rstrip().endswith('echo "published=true" >> "$GITHUB_OUTPUT"')
        # The idempotent "nothing to commit" path still means main already
        # carries this release.
        assert "No subscription changes to commit." in push["run"]

    def test_stats_file_stays_out_of_the_published_tree(self, action):
        stats = action["inputs"]["stats-file"]["default"]
        assert stats == ".runtime/pipeline_stats.json"
        assert not stats.startswith("output/")
        assert action["inputs"]["stats-file"]["required"] is False
        commit = _step(action, COMMIT_STEP)
        assert "git add output README.md" in commit["run"]
        assert ".runtime" not in commit["run"]

    def test_both_attempts_produce_a_summary(self, workflow, action):
        for job in ("attempt-1", "attempt-2"):
            steps = _job(workflow, job)["steps"]
            publish = next(s for s in steps if s.get("uses") == "./.github/actions/publish")
            assert publish["with"]["attempt"] in {"1", "2"}
        assert _step(action, SUMMARY_STEP)["if"] == "always()"

    def test_exhausted_retry_states_failure_in_the_job_summary(self, workflow):
        step = _job(workflow, "attempt-2")["steps"][-1]
        assert step["name"] == "Report exhausted publication attempts"
        assert "GITHUB_STEP_SUMMARY" in step["run"]
        assert "FAILED" in step["run"]
        assert "no output was committed" in step["run"].lower()

    def test_no_new_release_threshold_is_introduced(self, action_text, workflow_text):
        # Structural sanity only: no count, ratio, or percentage gate.
        combined = action_text + workflow_text
        for forbidden in (
            "0.5",
            "50%",
            "MIN_",
            "THRESHOLD_COUNT",
            "MIN_PROXIES",
            "assert_count",
        ):
            assert forbidden not in combined, f"arbitrary release threshold: {forbidden}"

    def test_sanity_still_runs_before_the_publish_steps(self, action):
        guard = _step_index(action, GUARD_STEP)
        assert guard < _step_index(action, RECORD_STEP) < _step_index(action, COMMIT_STEP)
        assert _step_index(action, PIPELINE_STEP) < guard

    def test_health_and_dns_concurrency_are_untouched(self, workflow):
        env = workflow["env"]
        assert "PA_HEALTH_CONCURRENCY" not in env
        assert "PA_DNS_CONCURRENCY" not in env


class TestRaceCheckScript:
    """Execute the real race-check shell script against throwaway git repos."""

    @pytest.fixture(scope="class")
    def race_script(self, action) -> str:
        return textwrap.dedent(_step(action, RACE_STEP)["run"])

    @staticmethod
    def _run(script: str, workdir: Path, output_file: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", script],
            cwd=workdir,
            env={"PATH": "/usr/bin:/bin", "GITHUB_OUTPUT": str(output_file)},
            capture_output=True,
            text=True,
        )

    @staticmethod
    def _make_remote(tmp_path: Path) -> tuple[Path, Path]:
        remote = tmp_path / "remote.git"
        seed = tmp_path / "seed"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True)
        subprocess.run(["git", "init", "-b", "main", str(seed)], check=True)
        (seed / "output.txt").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(seed), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(seed),
                "-c",
                "user.email=t@t",
                "-c",
                "user.name=t",
                "commit",
                "-m",
                "seed",
            ],
            check=True,
        )
        subprocess.run(["git", "-C", str(seed), "remote", "add", "origin", str(remote)], check=True)
        subprocess.run(["git", "-C", str(seed), "push", "origin", "main"], check=True)
        clone = tmp_path / "clone"
        subprocess.run(["git", "clone", str(remote), str(clone)], check=True)
        return remote, clone

    @pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
    def test_unchanged_main_is_not_a_race(self, race_script, tmp_path):
        _remote, clone = self._make_remote(tmp_path)
        out = tmp_path / "out1"
        out.write_text("", encoding="utf-8")
        result = self._run(race_script, clone, out)
        assert result.returncode == 0, result.stderr
        assert "raced=false" in out.read_text(encoding="utf-8")
        assert "::warning::" not in result.stdout

    @pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
    def test_moved_main_is_reported_as_a_race(self, race_script, tmp_path):
        remote, clone = self._make_remote(tmp_path)
        other = tmp_path / "other"
        subprocess.run(["git", "clone", str(remote), str(other)], check=True)
        (other / "output.txt").write_text("moved\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(other), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(other),
                "-c",
                "user.email=t@t",
                "-c",
                "user.name=t",
                "commit",
                "-m",
                "concurrent publication",
            ],
            check=True,
        )
        subprocess.run(["git", "-C", str(other), "push", "origin", "main"], check=True)
        # The clone is behind: it still holds the commit that triggered the run.
        assert (
            subprocess.run(
                ["git", "-C", str(clone), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            != subprocess.run(
                ["git", "-C", str(other), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )

        out = tmp_path / "out2"
        out.write_text("", encoding="utf-8")
        result = self._run(race_script, clone, out)
        assert result.returncode == 0, result.stderr
        written = out.read_text(encoding="utf-8")
        assert "raced=true" in written
        assert "raced=false" not in written
        assert "::warning::origin/main moved" in result.stdout
        assert "discarded" in result.stdout
        # The check reports the new tip so the caller can log what it regenerates.
        new_tip = subprocess.run(
            ["git", "-C", str(remote), "rev-parse", "main"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert new_tip in result.stdout
        # Detecting the race must not publish anything by itself.
        log = subprocess.run(
            ["git", "-C", str(remote), "log", "--oneline", "main"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "concurrent publication" in log
        assert len(log.strip().splitlines()) == 2
