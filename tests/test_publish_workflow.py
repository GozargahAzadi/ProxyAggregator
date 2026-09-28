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
RACE_STEP = "Verify base commit is still origin/main"
GUARD_STEP = "Guard against empty or invalid output"
RECORD_STEP = "Record successful publication time"
COMMIT_STEP = "Commit & push generated subscriptions"


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
            GATE_STEP,
            "Provision GeoIP database",
            "Verify GeoIP database checksum",
            "Verify GeoIP database",
            "Apply database migrations",
            "Seed production sources",
            "Run production pipeline",
            GUARD_STEP,
            RACE_STEP,
            RECORD_STEP,
            COMMIT_STEP,
        ]
        assert _step(action, "Apply database migrations")["run"] == ("uv run alembic upgrade head")
        assert _step(action, "Seed production sources")["run"] == (
            "uv run python -m proxyaggregator seed-sources"
        )
        assert _step(action, "Run production pipeline")["run"] == (
            "uv run python -m proxyaggregator pipeline"
        )
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

    def test_release_verification_step_is_preserved(self, action):
        guard = _step(action, GUARD_STEP)
        script = guard["run"]
        assert "if [ ! -d output ]" in script
        assert "from proxyaggregator.publishing.publisher import verify_release" in script
        assert 'verify_release("output")' in script
        assert "Output guard passed" in script
        assert guard["if"] == RUN_CONDITION


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
        # The commit is the last step in the action, so nothing can be staged
        # between the race decision and the push.
        assert action["runs"]["steps"][-1]["name"] == COMMIT_STEP


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
            assert publish["with"] == {"token": "${{ secrets.GITHUB_TOKEN }}"}
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
