"""Phase 22 production run summary tests.

The summary is observability only, so these tests pin three properties above
everything else:

1. It never claims a run published when it did not - a freshness ``SKIP``, a
   Phase 21 race discard, and a failed structural guard all render as
   non-publish outcomes.
2. It never fabricates a metric: an unavailable source of truth renders as
   ``unavailable``/``not run``, and the release is validated through the
   existing ``verify_release`` guard rather than a second rule set.
3. It cannot fail a run or mutate state: the CLI always exits 0 and never
   touches ``output/published_at.json`` or any published artifact.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from proxyaggregator.publishing.freshness import (
    DEFAULT_FRESHNESS_THRESHOLD_MINUTES,
    PUBLISHED_AT_FILENAME,
    record_published_at,
    serialize_published_at,
)
from proxyaggregator.publishing.models import Subscription, SubscriptionFormat
from proxyaggregator.publishing.publisher import (
    DEFAULT_PROTOCOL_FILENAME_STEMS,
    publish_release,
)
from proxyaggregator.publishing.samples import build_demo_subscriptions
from proxyaggregator.publishing.summary import (
    SANITY_FAILED,
    SANITY_PASSED,
    SANITY_SKIPPED,
    SANITY_UNKNOWN,
    STATUS_DISCARDED,
    STATUS_FAILED,
    STATUS_PUBLISHED,
    STATUS_SKIPPED,
    UNAVAILABLE,
    RunSummary,
    build_run_summary,
    country_codes,
    load_pipeline_stats,
    parse_optional_bool,
    parse_optional_int,
    protocol_counts,
    render_run_summary,
    total_published_proxies,
    write_run_summary,
)

NOW = datetime(2026, 9, 28, 10, 41, 0, tzinfo=UTC)
PREVIOUS = "2026-09-28T10:20:00Z"

STATS = {
    "sources_discovered": 6,
    "sources_fetched": 6,
    "parse_candidates": 12934,
    "parsed_proxies": 12555,
    "deduplicated_proxies": 7457,
    "dns_attempts": 7457,
    "dns_successes": 6773,
    "dns_failures": 684,
    "health_checks_completed": 7457,
    "healthy_proxies": 1657,
    "ranked_proxies": 1657,
    "subscription_count": 253,
    "published_artifacts": 254,
    "collection_seconds": 12.0,
    "parsing_seconds": 4.0,
    "dedup_seconds": 2.0,
    "persist_enrich_seconds": 300.0,
    "health_seconds": 380.0,
    "scoring_seconds": 1.0,
    "subscriptions_seconds": 2.0,
    "publish_seconds": 5.0,
    "total_seconds": 706.4,
}


def _feed(content: str, count: int = 1):
    return Subscription(format=SubscriptionFormat.PLAIN, content=content, count=count)


def _release(tmp_path, *, countries: bool = True):
    """Publish a small but structurally valid release and return its dir."""
    feeds = list(build_demo_subscriptions())
    if countries:
        feeds.append(("countries/README.md", _feed("| Country | Feeds |\n| AE | 1 |\n", 0)))
        feeds.append(("countries/AE/README.md", _feed("| Protocol | Count |\n| vless | 1 |\n", 0)))
        feeds.append(("countries/AE/all.txt", _feed("vless://demo-one\n")))
        feeds.append(("countries/AE/vless.txt", _feed("vless://demo-one\n")))
    publish_release(feeds, tmp_path)
    return tmp_path


def _stats_file(tmp_path, payload=None):
    path = tmp_path / "stats.json"
    path.write_text(json.dumps(STATS if payload is None else payload), encoding="utf-8")
    return path


def _summary(**overrides) -> RunSummary:
    base = {
        "event": "schedule",
        "attempt": 1,
        "base_sha": "7a8cf30abcdef1234",
        "decision": "RUN",
        "threshold_minutes": DEFAULT_FRESHNESS_THRESHOLD_MINUTES,
        "age_seconds": 1024,
        "previous_published_at": PREVIOUS,
        "race": False,
        "sanity": SANITY_PASSED,
        "published": True,
        "published_at": PREVIOUS,
        "release": None,
        "release_error": None,
        "stats": STATS,
    }
    base.update(overrides)
    return RunSummary(**base)


class TestStatusDerivation:
    def test_freshness_skip_is_never_a_publication(self):
        summary = _summary(decision="SKIP", race=None, sanity=SANITY_SKIPPED)
        assert summary.status == STATUS_SKIPPED
        assert summary.did_publish is False
        assert summary.pipeline_ran is False

    def test_detected_race_is_discarded_not_published(self):
        summary = _summary(race=True)
        assert summary.status == STATUS_DISCARDED
        assert summary.did_publish is False

    def test_failed_sanity_is_failed_not_published(self):
        summary = _summary(sanity=SANITY_FAILED)
        assert summary.status == STATUS_FAILED
        assert summary.did_publish is False

    def test_confirmed_push_is_published(self):
        summary = _summary()
        assert summary.status == STATUS_PUBLISHED
        assert summary.did_publish is True

    @pytest.mark.parametrize("published", [False, None])
    def test_run_without_a_confirmed_push_never_claims_success(self, published):
        # The push step reported no publication (or never ran): the release is
        # not on main, so the run is a failure, not a publication.
        assert _summary(published=published).status == STATUS_FAILED
        assert _summary(published=published).did_publish is False

    def test_a_confirmed_push_outranks_a_lost_sanity_output(self):
        # Only the commit/push step can prove a publication reached main; a
        # missing guard output must not rewrite that verdict.
        assert _summary(sanity=SANITY_UNKNOWN).status == STATUS_PUBLISHED

    def test_an_unreported_guard_is_never_treated_as_verified(self, tmp_path):
        # After a failed pipeline the guard never ran and output/ still holds
        # the previous release. Re-verifying that would prove nothing about this
        # run, so the summary must report the sanity result as unknown.
        summary = build_run_summary(
            event="schedule",
            output_dir=_release(tmp_path),
            decision="RUN",
            sanity="",
            published=False,
        )
        assert summary.sanity == SANITY_UNKNOWN
        assert summary.release is None
        assert summary.status == STATUS_FAILED
        markdown = render_run_summary(summary)
        assert f"| Structural verification | {UNAVAILABLE} |" in markdown
        assert "not reported" in markdown
        assert "Not verified" in markdown
        assert "Artifacts" not in markdown

    @pytest.mark.parametrize("published", [False, None])
    def test_unknown_decision_without_a_confirmed_push_fails(self, published):
        assert _summary(decision=None, published=published).status == STATUS_FAILED

    def test_a_skip_outranks_a_race_flag(self):
        # A stale `race` output from an earlier step must not turn a freshness
        # skip into a discard; the gate decided first.
        assert _summary(decision="SKIP", race=True, sanity=SANITY_SKIPPED).status == STATUS_SKIPPED

    @pytest.mark.parametrize("sanity", [SANITY_PASSED, SANITY_FAILED, SANITY_SKIPPED, "unknown"])
    def test_a_detected_race_is_never_a_publication(self, sanity):
        # A stale-tree discard outranks every guard outcome, including a
        # verified release: the generated tree was never publishable.
        summary = _summary(race=True, sanity=sanity)
        assert summary.did_publish is False
        assert summary.status == STATUS_DISCARDED


class TestRenderedSafetyClaims:
    def test_race_markdown_never_claims_a_publication(self):
        markdown = render_run_summary(_summary(race=True))
        assert STATUS_DISCARDED in markdown
        assert "**PUBLISHED**" not in markdown
        assert "Published this run | no" in markdown
        assert "discarded" in markdown

    def test_skip_markdown_never_shows_pipeline_or_output_counts(self):
        markdown = render_run_summary(
            _summary(decision="SKIP", race=None, sanity=SANITY_SKIPPED, stats=None)
        )
        assert STATUS_SKIPPED in markdown
        assert "**PUBLISHED**" not in markdown
        assert "Not executed" in markdown
        assert "Not generated" in markdown
        assert "12,934" not in markdown
        assert "1,657" not in markdown

    def test_failed_sanity_is_reported_as_failed(self):
        markdown = render_run_summary(_summary(sanity=SANITY_FAILED))
        assert f"**{STATUS_FAILED}**" in markdown
        assert "Published this run | no" in markdown

    def test_published_run_reports_the_advanced_timestamp(self):
        markdown = render_run_summary(_summary(published_at="2026-09-28T10:41:00Z"))
        assert "2026-09-28T10:41:00Z (advanced by this run)" in markdown
        assert "Published this run | yes" in markdown

    def test_push_failure_is_reported_as_failed_with_its_reason(self):
        markdown = render_run_summary(_summary(published=False))
        assert f"**{STATUS_FAILED}**" in markdown
        assert "Published this run | no" in markdown
        assert "| Push result | not published by the commit/push step |" in markdown
        assert f"{PREVIOUS} (unchanged by this run)" in markdown

    def test_unknown_push_result_is_reported_as_unavailable(self):
        markdown = render_run_summary(_summary(published=None))
        assert f"**{STATUS_FAILED}**" in markdown
        assert f"| Push result | {UNAVAILABLE} |" in markdown

    def test_confirmed_push_is_reported_as_such(self):
        markdown = render_run_summary(_summary())
        assert "| Push result | confirmed by the commit/push step |" in markdown

    def test_non_published_run_marks_the_timestamp_unchanged(self):
        markdown = render_run_summary(_summary(decision="SKIP", sanity=SANITY_SKIPPED))
        assert f"{PREVIOUS} (unchanged by this run)" in markdown

    def test_summary_contains_no_proxy_uris(self):
        markdown = render_run_summary(_summary())
        for forbidden in ("vless://", "vmess://", "ss://", "trojan://", "hysteria2://"):
            assert forbidden not in markdown


class TestPipelineSection:
    def test_measured_counters_are_reported(self):
        markdown = render_run_summary(_summary())
        assert "| Raw candidates | 12,934 |" in markdown
        assert "| Parsed | 12,555 |" in markdown
        assert "| Deduplicated | 7,457 |" in markdown
        assert "| DNS resolved | 6,773 / 7,457 |" in markdown
        assert "| Healthy | 1,657 |" in markdown
        assert "| Ranked | 1,657 |" in markdown
        assert "| Feeds built | 253 |" in markdown
        assert "Total pipeline duration: 706.4s" in markdown
        assert "health 380.0s" in markdown

    def test_missing_stats_file_is_reported_as_unavailable(self):
        markdown = render_run_summary(_summary(stats=None))
        assert "unavailable" in markdown
        assert "12,934" not in markdown

    def test_partial_stats_do_not_fabricate_missing_counters(self):
        markdown = render_run_summary(_summary(stats={"parsed_proxies": 10}))
        assert "| Parsed | 10 |" in markdown
        assert "| Raw candidates | unavailable |" in markdown

    def test_no_counters_are_zero_filled(self):
        markdown = render_run_summary(_summary(stats={}))
        assert "| Parsed | unavailable |" in markdown
        assert "| Parsed | 0 |" not in markdown


class TestOutputSection:
    def test_derived_output_facts_match_the_manifest(self, tmp_path):
        summary = build_run_summary(
            event="schedule", output_dir=_release(tmp_path), decision="RUN", published=True
        )
        assert summary.release is not None
        markdown = render_run_summary(summary)
        assert f"| Artifacts | {len(summary.release):,} |" in markdown
        assert f"| Countries | {len(country_codes(summary.release)):,} |" in markdown
        assert total_published_proxies(summary.release) is not None
        assert "**PUBLISHED**" in markdown

    def test_country_index_is_not_counted_as_a_country(self, tmp_path):
        entries = build_run_summary(
            event="schedule", output_dir=_release(tmp_path), decision="RUN"
        ).release
        assert country_codes(entries) == ("AE",)

    def test_protocol_counts_come_from_the_plain_feeds(self, tmp_path):
        entries = build_run_summary(
            event="schedule", output_dir=_release(tmp_path), decision="RUN"
        ).release
        by_name = {entry.filename: entry for entry in entries}
        counts = dict(protocol_counts(entries))
        assert counts, "the demo release contains per-protocol feeds"
        assert set(counts) <= set(DEFAULT_PROTOCOL_FILENAME_STEMS)
        for protocol, count in counts.items():
            stem = DEFAULT_PROTOCOL_FILENAME_STEMS[protocol]
            assert by_name[f"{stem}.txt"].count == count

    def test_protocol_counts_never_sum_base64_mirrors(self, tmp_path):
        entries = build_run_summary(
            event="schedule", output_dir=_release(tmp_path), decision="RUN"
        ).release
        assert all(not name.endswith("-base64.txt") for name, _ in protocol_counts(entries))

    def test_only_published_protocols_are_reported(self, tmp_path):
        publish_release([("vless.txt", _feed("vless://demo-one\n"))], tmp_path)
        entries = build_run_summary(
            event="schedule", output_dir=tmp_path, decision="RUN", published=True
        ).release
        assert [name for name, _ in protocol_counts(entries)] == ["vless"]

    def test_combined_feed_count_is_unavailable_when_absent(self, tmp_path):
        publish_release([("vless.txt", _feed("vless://demo-one\n"))], tmp_path)
        entries = build_run_summary(
            event="schedule", output_dir=tmp_path, decision="RUN", published=True
        ).release
        assert total_published_proxies(entries) is None
        assert f"| Published proxies | {UNAVAILABLE} |" in render_run_summary(
            build_run_summary(event="schedule", output_dir=tmp_path, decision="RUN", published=True)
        )

    def test_unverifiable_release_reports_no_numbers(self, tmp_path):
        broken = tmp_path / "output"
        broken.mkdir()
        summary = build_run_summary(event="schedule", output_dir=broken, decision="RUN")
        assert summary.release is None
        assert summary.release_error
        assert summary.sanity == SANITY_FAILED
        markdown = render_run_summary(summary)
        assert "Release could not be validated" in markdown
        assert f"**{STATUS_FAILED}**" in markdown

    def test_missing_output_directory_is_reported_not_raised(self, tmp_path):
        summary = build_run_summary(event="schedule", output_dir=tmp_path / "nope", decision="RUN")
        assert summary.status == STATUS_FAILED
        assert summary.release_error


class TestFreshnessSection:
    def test_threshold_decision_and_age_are_reported(self):
        markdown = render_run_summary(_summary())
        assert "| Threshold | 13m |" in markdown
        assert "| Decision | RUN |" in markdown
        assert f"| Previous publication | {PREVIOUS} |" in markdown
        assert "| Previous age | 17m 04s |" in markdown

    def test_unknown_age_is_unavailable(self):
        markdown = render_run_summary(_summary(age_seconds=None))
        assert f"| Previous age | {UNAVAILABLE} |" in markdown

    def test_no_previous_publication_is_stated_plainly(self):
        markdown = render_run_summary(_summary(previous_published_at=None))
        assert "none (no previous publication)" in markdown

    def test_unknown_race_result_is_not_invented(self):
        markdown = render_run_summary(_summary(race=None, decision="RUN"))
        assert f"| Race (Phase 21) | {UNAVAILABLE} |" in markdown


class TestStatsLoading:
    def test_missing_path_returns_none(self):
        assert load_pipeline_stats(None) is None

    def test_missing_file_returns_none(self, tmp_path):
        assert load_pipeline_stats(tmp_path / "absent.json") is None

    def test_invalid_json_returns_none(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        assert load_pipeline_stats(path) is None

    def test_non_object_payload_returns_none(self, tmp_path):
        path = tmp_path / "list.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        assert load_pipeline_stats(path) is None

    def test_valid_payload_is_returned(self, tmp_path):
        assert load_pipeline_stats(_stats_file(tmp_path)) == STATS


class TestOutputCoercion:
    @pytest.mark.parametrize("raw", ["", "  ", "none", "n/a", "N/A", "null", None])
    def test_blank_tokens_become_none(self, raw):
        assert parse_optional_int(raw) is None
        assert parse_optional_bool(raw) is None

    @pytest.mark.parametrize(("raw", "expected"), [("13", 13), (" 0 ", 0), ("-1", -1)])
    def test_integers_are_parsed(self, raw, expected):
        assert parse_optional_int(raw) == expected

    def test_invalid_integer_is_none(self):
        assert parse_optional_int("not a number") is None

    @pytest.mark.parametrize(("raw", "expected"), [("yes", True), ("true", True), ("1", True)])
    def test_true_tokens(self, raw, expected):
        assert parse_optional_bool(raw) is expected

    @pytest.mark.parametrize(("raw", "expected"), [("no", False), ("false", False), ("0", False)])
    def test_false_tokens(self, raw, expected):
        assert parse_optional_bool(raw) is expected

    def test_bools_pass_through(self):
        assert parse_optional_bool(True) is True
        assert parse_optional_bool(False) is False
        assert parse_optional_int(7) == 7


class TestBuildRunSummary:
    def test_skip_does_not_read_the_release(self, tmp_path):
        summary = build_run_summary(event="schedule", output_dir=tmp_path, decision="SKIP")
        assert summary.release is None
        assert summary.release_error is None
        assert summary.stats is None
        assert summary.sanity == SANITY_SKIPPED

    def test_stats_are_ignored_when_the_pipeline_did_not_run(self, tmp_path):
        stats = _stats_file(tmp_path)
        summary = build_run_summary(
            event="schedule", output_dir=tmp_path, stats_path=stats, decision="SKIP"
        )
        assert summary.stats is None

    def test_run_reads_stats_and_release(self, tmp_path):
        summary = build_run_summary(
            event="schedule",
            output_dir=_release(tmp_path),
            stats_path=_stats_file(tmp_path),
            decision="RUN",
        )
        assert summary.stats == STATS
        assert summary.release is not None
        assert summary.sanity == SANITY_PASSED

    def test_published_at_is_read_from_disk(self, tmp_path):
        out = _release(tmp_path)
        record_published_at(out / PUBLISHED_AT_FILENAME, NOW)
        summary = build_run_summary(event="schedule", output_dir=out, decision="RUN")
        assert summary.published_at == serialize_published_at(NOW)

    def test_missing_published_at_is_none(self, tmp_path):
        summary = build_run_summary(
            event="schedule", output_dir=_release(tmp_path), decision="RUN", published=True
        )
        assert summary.published_at is None


class TestWriteRunSummary:
    def test_none_target_only_returns_markdown(self, tmp_path):
        markdown = write_run_summary(_summary(), None)
        assert markdown.startswith("## Production Run")
        assert not list(tmp_path.iterdir())

    def test_target_is_appended_not_truncated(self, tmp_path):
        target = tmp_path / "nested" / "step-summary.md"
        target.parent.mkdir(parents=True)
        target.write_text("earlier content\n", encoding="utf-8")
        write_run_summary(_summary(), target)
        body = target.read_text(encoding="utf-8")
        assert body.startswith("earlier content")
        assert "## Production Run" in body
        write_run_summary(_summary(decision="SKIP", sanity=SANITY_SKIPPED), target)
        assert target.read_text(encoding="utf-8").count("## Production Run") == 2


class TestSummaryCli:
    def _argv(self, output, **kwargs):
        argv = ["publish-summary", "--event", "schedule", "--output", str(output)]
        for flag, value in kwargs.items():
            argv.extend([f"--{flag.replace('_', '-')}", str(value)])
        return argv

    def test_writes_to_step_summary_file(self, tmp_path, monkeypatch):
        from proxyaggregator.__main__ import main

        target = tmp_path / "step-summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(target))
        code = main(
            self._argv(_release(tmp_path), decision="RUN", attempt=1, race="no", published="yes")
        )
        assert code == 0
        body = target.read_text(encoding="utf-8")
        assert "## Production Run" in body
        assert f"**{STATUS_PUBLISHED}**" in body

    def test_prints_to_stdout_without_a_step_summary_target(self, tmp_path, monkeypatch, capsys):
        from proxyaggregator.__main__ import main

        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        code = main(self._argv(tmp_path, decision="SKIP", attempt=2, threshold_minutes=13))
        assert code == 0
        out = capsys.readouterr().out
        assert f"## Production Run — {STATUS_SKIPPED}" in out
        assert "Attempt | 2" in out

    def test_defaults_to_the_github_event_name(self, tmp_path, monkeypatch, capsys):
        from proxyaggregator.__main__ import main

        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        monkeypatch.setenv("GITHUB_EVENT_NAME", "repository_dispatch")
        assert main(["publish-summary", "--output", str(tmp_path), "--decision", "SKIP"]) == 0
        assert "| Trigger | `repository_dispatch` |" in capsys.readouterr().out

    def test_never_fails_on_a_broken_release(self, tmp_path, monkeypatch, capsys):
        from proxyaggregator.__main__ import main

        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        code = main(self._argv(tmp_path / "absent", decision="RUN", attempt=1))
        assert code == 0
        assert f"**{STATUS_FAILED}**" in capsys.readouterr().out

    def test_never_fails_on_empty_step_outputs(self, tmp_path, monkeypatch, capsys):
        from proxyaggregator.__main__ import main

        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        # Exactly what the action passes when the guard, race, and push steps
        # did not run: every derived flag is an empty string.
        argv = [
            "publish-summary",
            "--output",
            str(tmp_path),
            "--attempt",
            "",
            "--base-sha",
            "",
            "--decision",
            "RUN",
            "--threshold-minutes",
            "13",
            "--age-seconds",
            "n/a",
            "--previous-published-at",
            "",
            "--race",
            "",
            "--sanity",
            "",
        ]
        assert main(argv) == 0
        out = capsys.readouterr().out
        assert f"| Previous age | {UNAVAILABLE} |" in out
        assert f"| Race (Phase 21) | {UNAVAILABLE} |" in out
        assert f"| Base commit | `{UNAVAILABLE}` |" in out
        assert f"| Attempt | {UNAVAILABLE} |" in out

    def test_unrecognised_values_are_treated_as_unknown(self, tmp_path, monkeypatch, capsys):
        from proxyaggregator.__main__ import main

        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        argv = [
            "publish-summary",
            "--output",
            str(tmp_path),
            "--decision",
            "MAYBE",
            "--sanity",
            "who-knows",
        ]
        assert main(argv) == 0
        assert f"**{STATUS_FAILED}**" in capsys.readouterr().out

    def test_does_not_advance_the_publication_timestamp(self, tmp_path, monkeypatch):
        from proxyaggregator.__main__ import main

        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        out = _release(tmp_path)
        stamp = out / PUBLISHED_AT_FILENAME
        record_published_at(stamp, NOW)
        before = stamp.read_bytes()
        manifest_before = (out / "manifest.json").read_bytes()
        for decision in ("RUN", "SKIP"):
            assert main(self._argv(out, decision=decision, attempt=1, race="no")) == 0
        assert stamp.read_bytes() == before
        assert (out / "manifest.json").read_bytes() == manifest_before
        assert json.loads(stamp.read_text(encoding="utf-8")) == {
            "published_at": serialize_published_at(NOW)
        }
