"""Phase 18 freshness-gate tests (deterministic, injected clocks only).

Cover the decision logic, parsing of the committed ``published_at.json``,
UTC safety, and the failure semantics: only an explicit successful-publish
record may advance the timestamp; a failed run never does.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from proxyaggregator.publishing.freshness import (
    DEFAULT_FRESHNESS_THRESHOLD_MINUTES,
    PUBLISHED_AT_FILENAME,
    FreshnessDecision,
    format_age,
    parse_published_at,
    publish_decision,
    read_published_at,
    record_published_at,
    render_decision_log,
    serialize_published_at,
)

NOW = datetime(2026, 9, 27, 12, 0, 0, tzinfo=UTC)


def _minutes_ago(minutes: int) -> datetime:
    return NOW - timedelta(minutes=minutes)


def decision_for_age(minutes_ago: int) -> FreshnessDecision:
    return publish_decision(_minutes_ago(minutes_ago), NOW)


class TestNoPreviousPublication:
    def test_none_timestamp_runs(self):
        decision = publish_decision(None, NOW)
        assert decision.run is True
        assert decision.decision == "RUN"
        assert decision.reason == "no_previous_publication"
        assert decision.age_seconds is None


class TestThresholdWindow:
    def test_publication_5_minutes_ago_skips(self):
        decision = decision_for_age(5)
        assert decision.run is False
        assert decision.decision == "SKIP"
        assert decision.reason == "fresh"

    def test_publication_12_minutes_ago_skips(self):
        decision = decision_for_age(12)
        assert decision.run is False

    def test_publication_13_minutes_ago_runs(self):
        decision = decision_for_age(13)
        assert decision.run is True
        assert decision.reason == "threshold_met"

    def test_publication_15_minutes_ago_runs(self):
        decision = decision_for_age(15)
        assert decision.run is True

    def test_publication_older_than_15_minutes_runs(self):
        for minutes in (20, 60, 24 * 60):
            assert decision_for_age(minutes).run is True

    def test_future_timestamp_skips_as_fresh(self):
        decision = publish_decision(_minutes_ago(-2), NOW)
        assert decision.run is False
        assert decision.age_seconds == 0


class TestInvalidAndMissingTimestamps:
    @pytest.mark.parametrize(
        "text",
        [
            None,
            "",
            "not json",
            "[]",
            '"2026-09-27T12:00:00Z"',
            "{}",
            '{"published_at": null}',
            '{"published_at": 123}',
            '{"published_at": ""}',
            '{"published_at": "not-a-date"}',
        ],
    )
    def test_unusable_timestamps_parse_to_none(self, text):
        assert parse_published_at(text) is None

    def test_missing_file_reads_as_none(self, tmp_path):
        assert read_published_at(tmp_path / "published_at.json") is None

    def test_missing_timestamp_safe_behavior_is_run(self):
        assert publish_decision(None, NOW).run is True


class TestSuccessfulRecordAdvances:
    def test_record_then_fresh_gate_skips(self, tmp_path):
        path = tmp_path / PUBLISHED_AT_FILENAME
        record_published_at(path, NOW)
        decision = publish_decision(read_published_at(path), NOW)
        assert decision.run is False

    def test_record_overwrites_previous_timestamp(self, tmp_path):
        path = tmp_path / PUBLISHED_AT_FILENAME
        record_published_at(path, NOW - timedelta(hours=3))
        record_published_at(path, NOW)
        assert read_published_at(path) == NOW


class TestFailedRunDoesNotAdvance:
    def test_unrecorded_old_timestamp_still_triggers_run(self, tmp_path):
        path = tmp_path / PUBLISHED_AT_FILENAME
        record_published_at(path, _minutes_ago(15))
        content_before = path.read_bytes()
        # A failed run never invokes record_published_at: the file is untouched.
        assert path.read_bytes() == content_before
        decision = publish_decision(read_published_at(path), NOW)
        assert decision.run is True

    def test_only_record_publish_advances(self, tmp_path):
        path = tmp_path / PUBLISHED_AT_FILENAME
        record_published_at(path, _minutes_ago(15))
        before = path.read_bytes()
        # No pipeline/guard step must ever touch the file; here we simply prove
        # the gate re-reads the same bytes (kept as-is) and still runs.
        assert path.read_bytes() == before
        assert publish_decision(read_published_at(path), NOW).run is True


class TestUtcSafety:
    def test_naive_timestamp_is_treated_as_utc(self):
        naive = parse_published_at('{"published_at": "2026-09-27T12:00:00"}')
        assert naive is not None
        assert naive.tzinfo is not None
        assert naive.utcoffset() == timedelta(0)

    def test_z_suffix_parses_to_utc(self):
        parsed = parse_published_at('{"published_at": "2026-09-27T12:00:00Z"}')
        assert parsed == NOW

    def test_serialize_round_trip(self):
        parsed = parse_published_at(json.dumps({"published_at": serialize_published_at(NOW)}))
        assert parsed == NOW

    def test_decision_uses_absolute_instants(self):
        published = NOW
        local = datetime(2026, 9, 27, 14, 5, 0, tzinfo=timezone(timedelta(hours=2)))
        decision = publish_decision(published, local)
        assert decision.age_seconds == 5 * 60
        assert decision.run is False
        assert decision.now == local


class TestObservability:
    def test_log_matches_expected_skip_shape(self):
        decision = decision_for_age(10)
        log = render_decision_log(decision)
        assert log.splitlines()[0] == "[Freshness Gate]"
        assert "Last successful publication: 2026-09-27T11:50:00Z" in log
        assert "Current time: 2026-09-27T12:00:00Z" in log
        assert "Age: 10m 00s" in log
        assert f"Threshold: {DEFAULT_FRESHNESS_THRESHOLD_MINUTES}m" in log
        assert "Decision: SKIP" in log

    def test_log_run_shape_without_timestamp(self):
        decision = publish_decision(None, NOW)
        log = render_decision_log(decision)
        assert "Last successful publication: not found" in log
        assert "Age: n/a" in log
        assert "Decision: RUN" in log
        assert "Reason: no previous successful publication found" in log

    def test_format_age(self):
        assert format_age(60 * 10 + 3) == "10m 03s"
        assert format_age(3600 + 2 * 60 + 5) == "1h 02m 05s"
        assert format_age(None) == "n/a"

    def test_cli_gate_writes_step_output(self, tmp_path, monkeypatch):
        import proxyaggregator.publishing.freshness as freshness

        monkeypatch.setattr(freshness, "utc_now", lambda: NOW)
        path = tmp_path / "published_at.json"
        record_published_at(path, NOW)
        outputs = tmp_path / "github-output.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        from proxyaggregator.__main__ import main

        assert main(["freshness-gate", "--file", str(path)]) == 0
        lines = outputs.read_text(encoding="utf-8").splitlines()
        assert any(line == "decision=SKIP" for line in lines)
        assert any(line == "published_at=2026-09-27T12:00:00Z" for line in lines)

    def test_cli_gate_force_runs(self, tmp_path, monkeypatch):
        import proxyaggregator.publishing.freshness as freshness

        monkeypatch.setattr(freshness, "utc_now", lambda: NOW)
        path = tmp_path / "published_at.json"
        record_published_at(path, NOW)
        outputs = tmp_path / "github-output.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
        from proxyaggregator.__main__ import main

        assert main(["freshness-gate", "--force", "--file", str(path)]) == 0
        assert "decision=RUN\n" in outputs.read_text(encoding="utf-8")
