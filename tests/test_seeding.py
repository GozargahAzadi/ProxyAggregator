"""Phase 9.2 tests: production source seeding.

The repository-controlled ``config/sources.json`` definition file is the
authoritative input for the ``sources`` table. These tests exercise
definition validation, url-keyed upsert idempotency, credential hygiene,
CLI exit codes, and the offline seed -> pipeline integration path.  No test
performs network I/O: validation is pure parsing, collection is injected,
and health checks use a deterministic stub.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from proxyaggregator import pipeline, seeding
from proxyaggregator.config.settings import Settings
from proxyaggregator.db.crud import list_sources
from proxyaggregator.db.models import SourceORM
from proxyaggregator.geoip.models import EnrichmentResult
from proxyaggregator.health.models import (
    CheckStage,
    HealthCheckResult,
    HealthStatus,
)
from proxyaggregator.parsers.base import ParseError, ParseResult
from proxyaggregator.sources.result import SourceResult, SourceResultStatus

if TYPE_CHECKING:
    from proxyaggregator.models.source import SourceSchema

ROOT_DIR = Path(__file__).resolve().parents[1]

DEFINITION_A = {
    "name": "alpha",
    "type": "http",
    "url": "https://cdn.invalid/one.txt",
}
DEFINITION_B = {
    "name": "beta",
    "type": "http",
    "url": "https://cdn.invalid/two.txt",
}

CONTENT_A = "http://203.0.113.10:8080\nsocks5://user:secretpass@203.0.113.11:1080\n"
CONTENT_B = (
    "vless://11111111-2222-3333-4444-555555555555@203.0.113.12:443?security=none\n"
    "http://203.0.113.10:8080\n"
    "vmess://!!!notbase64!!!\n"
)

URI_HTTP = "http://203.0.113.10:8080"


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _source_result(source: SourceSchema, content: str) -> SourceResult:
    return SourceResult(
        source_name=source.name,
        source_type=source.source_type,
        source_url=source.url,
        status=SourceResultStatus.SUCCESS,
        content=content,
        fetched_at=_utcnow(),
        content_length=len(content),
    )


def _parse(uri: str) -> ParseResult:
    from proxyaggregator.parsers.detect import detect_protocol
    from proxyaggregator.parsers.registry import get_registry

    parser = get_registry().get(detect_protocol(uri))
    assert parser is not None, (uri, detect_protocol(uri))
    result = parser.parse(uri)
    assert not isinstance(result, ParseError), result
    assert isinstance(result, ParseResult)
    return result


def _enricher(parsed: ParseResult) -> EnrichmentResult:
    return EnrichmentResult(
        original_host=parsed.host,
        original_port=parsed.port,
        original_protocol=parsed.protocol,
        resolved_ip=parsed.host,
        all_resolved_ips=[parsed.host],
        country_code="US",
        country_name="United States",
        city="Testville",
        latitude=1.0,
        longitude=2.0,
    )


class DeterministicHealthRunner:
    """Async ``check_all`` stub: stable status and per-config latency."""

    def __init__(self, status: HealthStatus = HealthStatus.OK, latency_ms: float = 120.0) -> None:
        self.status = status
        self.latency_ms = latency_ms

    async def check_all(self, entries):
        results = []
        for entry in entries:
            ip = entry.parsed.host
            latency = 80.0 + (entry.proxy_config_id or 0) % 50
            results.append(
                HealthCheckResult(
                    proxy_config_id=entry.proxy_config_id,
                    protocol=entry.parsed.protocol,
                    host=entry.parsed.host,
                    port=entry.parsed.port,
                    status=self.status,
                    checked_ip=ip,
                    attempted_ips=[ip],
                    stage=CheckStage.PROTOCOL,
                    connect_ms=10.0,
                    tls_ms=0.0,
                    proxy_ms=latency,
                    latency_ms=latency if self.status is HealthStatus.OK else None,
                    tls_used=entry.parsed.protocol in ("https", "trojan"),
                    protocol_checked=True,
                )
            )
        return results


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from proxyaggregator.db.base import Base

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def sources_file(tmp_path):
    """Write a definition file containing two http sources."""

    def _write(definitions) -> Path:
        path = tmp_path / "sources.json"
        path.write_text(json.dumps(definitions), encoding="utf-8")
        return path

    return _write


# A. Definition loading & validation ------------------------------------------


class TestLoadDefinitions:
    def test_valid_file_loads_schemas(self, sources_file):
        path = sources_file([DEFINITION_A, DEFINITION_B])
        schemas = seeding.load_defined_sources(path)
        assert [s.name for s in schemas] == ["alpha", "beta"]
        assert [s.source_type for s in schemas] == ["http", "http"]
        assert schemas[0].url == DEFINITION_A["url"]
        assert schemas[1].url == DEFINITION_B["url"]

    @pytest.mark.parametrize(
        ("mutate", "expected"),
        [
            (lambda d: d.pop("name"), "missing_source_name"),
            (lambda d: d.pop("type"), "missing_source_type"),
            (lambda d: d.pop("url"), "missing_source_url"),
        ],
    )
    def test_missing_required_field_rejected(self, sources_file, mutate, expected):
        definition = dict(DEFINITION_A)
        mutate(definition)
        path = sources_file([definition])
        with pytest.raises(seeding.SeedError) as excinfo:
            seeding.load_defined_sources(path)
        assert excinfo.value.reason == expected

    @pytest.mark.parametrize(
        "value",
        ["", "   "],
    )
    def test_empty_url_rejected(self, sources_file, value):
        definition = dict(DEFINITION_A, url=value)
        path = sources_file([definition])
        with pytest.raises(seeding.SeedError) as excinfo:
            seeding.load_defined_sources(path)
        assert excinfo.value.reason == "missing_source_url"

    def test_missing_file_rejected(self):
        with pytest.raises(seeding.SeedError) as excinfo:
            seeding.load_defined_sources("/nonexistent/sources.json")
        assert excinfo.value.reason == "sources_file_not_found"

    def test_malformed_json_rejected(self, tmp_path):
        path = tmp_path / "sources.json"
        path.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(seeding.SeedError) as excinfo:
            seeding.load_defined_sources(path)
        assert excinfo.value.reason == "invalid_sources_file"

    def test_non_list_root_rejected(self, sources_file):
        path = sources_file({"name": "alpha", "type": "http", "url": "https://cdn.invalid/x"})
        with pytest.raises(seeding.SeedError) as excinfo:
            seeding.load_defined_sources(path)
        assert excinfo.value.reason == "invalid_sources_file"

    def test_non_object_entry_rejected(self, sources_file):
        path = sources_file(["alpha", DEFINITION_A])
        with pytest.raises(seeding.SeedError) as excinfo:
            seeding.load_defined_sources(path)
        assert excinfo.value.reason == "invalid_source_entry"

    def test_unsupported_source_type_rejected(self, sources_file):
        definition = dict(DEFINITION_A, type="telegram")
        path = sources_file([definition])
        with pytest.raises(seeding.SeedError) as excinfo:
            seeding.load_defined_sources(path)
        assert excinfo.value.reason == "unsupported_source_type"

    def test_unsupported_url_scheme_rejected(self, sources_file):
        definition = dict(DEFINITION_A, url="file:///etc/passwd")
        path = sources_file([definition])
        with pytest.raises(seeding.SeedError) as excinfo:
            seeding.load_defined_sources(path)
        assert excinfo.value.reason == "unsupported_url_scheme"

    def test_duplicate_definition_rejected(self, sources_file):
        path = sources_file([DEFINITION_A, DEFINITION_A])
        with pytest.raises(seeding.SeedError) as excinfo:
            seeding.load_defined_sources(path)
        assert excinfo.value.reason == "duplicate_source_definition"

    @pytest.mark.parametrize(
        ("field", "value", "expected"),
        [
            ("name", "n" * 256, "source_name_too_long"),
            ("type", "t" * 51, "source_type_too_long"),
            ("url", "https://" + "u" * 2042, "source_url_too_long"),
        ],
    )
    def test_length_limits_rejected(self, sources_file, field, value, expected):
        definition = dict(DEFINITION_A, **{field: value})
        path = sources_file([definition])
        with pytest.raises(seeding.SeedError) as excinfo:
            seeding.load_defined_sources(path)
        assert excinfo.value.reason == expected

    def test_empty_file_is_valid_and_empty(self, sources_file):
        path = sources_file([])
        assert seeding.load_defined_sources(path) == []


# B. Credential hygiene --------------------------------------------------------


class TestCredentialHygiene:
    def test_url_with_credentials_rejected_without_leak(self, sources_file):
        sneaky = "https://alice:s3cret@cdn.invalid/one.txt"
        definition = dict(DEFINITION_A, url=sneaky)
        path = sources_file([definition])
        with pytest.raises(seeding.SeedError) as excinfo:
            seeding.load_defined_sources(path)
        assert excinfo.value.reason == "url_contains_credentials"
        assert "s3cret" not in str(excinfo.value)
        assert "alice" not in str(excinfo.value)
        assert sneaky not in str(excinfo.value)

    def test_username_only_url_rejected(self, sources_file):
        definition = dict(DEFINITION_A, url="https://alice@cdn.invalid/one.txt")
        path = sources_file([definition])
        with pytest.raises(seeding.SeedError) as excinfo:
            seeding.load_defined_sources(path)
        assert excinfo.value.reason == "url_contains_credentials"


# C. Seeding behavior ----------------------------------------------------------


class TestSeedBehavior:
    def test_seed_inserts_sources(self, db_session, sources_file):
        path = sources_file([DEFINITION_A, DEFINITION_B])
        stats = seeding.seed_sources(db_session, seeding.load_defined_sources(path))
        assert stats.defined == 2
        assert stats.inserted == 2
        assert stats.updated == 0
        assert stats.unchanged == 0

        rows = list_sources(db_session)
        assert len(rows) == 2
        assert {row.name for row in rows} == {"alpha", "beta"}
        assert all(row.source_type == "http" for row in rows)

    def test_seed_is_idempotent(self, db_session, sources_file):
        path = sources_file([DEFINITION_A, DEFINITION_B])
        schemas = seeding.load_defined_sources(path)
        seeding.seed_sources(db_session, schemas)
        stats = seeding.seed_sources(db_session, schemas)

        assert stats.inserted == 0
        assert stats.updated == 0
        assert stats.unchanged == 2
        rows = list_sources(db_session)
        assert len(rows) == 2
        assert {row.name for row in rows} == {"alpha", "beta"}
        assert stats.defined == 2

    def test_seed_updates_changed_fields(self, db_session, sources_file):
        path = sources_file([DEFINITION_A])
        seeding.seed_sources(db_session, seeding.load_defined_sources(path))

        renamed = dict(DEFINITION_A, name="alpha-renamed")
        rename_path = sources_file([renamed])
        stats = seeding.seed_sources(db_session, seeding.load_defined_sources(rename_path))
        assert stats.updated == 1
        assert stats.unchanged == 0

        rows = list_sources(db_session)
        assert len(rows) == 1
        assert rows[0].name == "alpha-renamed"
        assert rows[0].url == DEFINITION_A["url"]

    def test_sources_absent_from_file_are_retained(self, db_session, sources_file):
        path = sources_file([DEFINITION_A, DEFINITION_B])
        schemas = seeding.load_defined_sources(path)
        seeding.seed_sources(db_session, schemas)

        only_a = sources_file([DEFINITION_A])
        stats = seeding.seed_sources(db_session, seeding.load_defined_sources(only_a))
        assert stats.unchanged == 1
        assert len(list_sources(db_session)) == 2  # beta retained, never deleted

    def test_empty_definitions_leave_table_untouched(self, db_session, sources_file):
        path = sources_file([])
        stats = seeding.seed_sources(db_session, seeding.load_defined_sources(path))
        assert stats.defined == 0
        assert stats.inserted == 0
        assert list_sources(db_session) == []

    def test_seed_performs_no_network(self, db_session, sources_file):
        definitions = [
            dict(DEFINITION_A),
            dict(DEFINITION_B),
        ]
        path = sources_file(definitions)
        stats = seeding.seed_sources(db_session, seeding.load_defined_sources(path))
        assert stats.inserted == 2  # .invalid hosts; validation/seed never fetch


# D. CLI -----------------------------------------------------------------------


class TestCli:
    def test_parser_recognizes_seed_sources_command(self):
        from proxyaggregator.__main__ import _build_parser

        namespace = _build_parser().parse_args(["seed-sources"])
        assert namespace.command == "seed-sources"
        assert namespace.sources_file is None
        assert callable(namespace.handler)

    def test_parser_accepts_sources_file_override(self):
        from proxyaggregator.__main__ import _build_parser

        namespace = _build_parser().parse_args(
            ["seed-sources", "--sources-file", "/tmp/custom.json"]
        )
        assert namespace.sources_file == "/tmp/custom.json"

    def test_cli_seed_valid_file_exits_zero(self, tmp_path):
        db_path = tmp_path / "cli.db"
        sources_file = tmp_path / "sources.json"
        sources_file.write_text(json.dumps([DEFINITION_A, DEFINITION_B]), encoding="utf-8")
        from sqlalchemy import create_engine

        from proxyaggregator.db.base import Base

        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        engine.dispose()

        env = dict(os.environ)
        env["PA_DATABASE_URL"] = f"sqlite:///{db_path}"
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT_DIR / "src"), env.get("PYTHONPATH", "")])
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "proxyaggregator",
                "seed-sources",
                "--sources-file",
                str(sources_file),
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=ROOT_DIR,
            timeout=120,
        )
        assert result.returncode == 0
        assert "seed-sources complete: defined=2, inserted=2" in result.stderr

    def test_cli_seed_missing_file_exits_one(self, tmp_path):
        db_path = tmp_path / "cli.db"
        from sqlalchemy import create_engine

        from proxyaggregator.db.base import Base

        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        engine.dispose()

        env = dict(os.environ)
        env["PA_DATABASE_URL"] = f"sqlite:///{db_path}"
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT_DIR / "src"), env.get("PYTHONPATH", "")])
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "proxyaggregator",
                "seed-sources",
                "--sources-file",
                "/nonexistent/sources.json",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=ROOT_DIR,
            timeout=120,
        )
        assert result.returncode == 1
        assert "seed-sources failed: sources_file_not_found" in result.stderr

    def test_cli_seed_credentials_rejected_without_leak(self, tmp_path):
        db_path = tmp_path / "cli.db"
        sources_file = tmp_path / "sources.json"
        sources_file.write_text(
            json.dumps(
                [{"name": "bad", "type": "http", "url": "https://alice:s3cret@cdn.invalid/x"}]
            ),
            encoding="utf-8",
        )
        from sqlalchemy import create_engine

        from proxyaggregator.db.base import Base

        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        engine.dispose()

        env = dict(os.environ)
        env["PA_DATABASE_URL"] = f"sqlite:///{db_path}"
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT_DIR / "src"), env.get("PYTHONPATH", "")])
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "proxyaggregator",
                "seed-sources",
                "--sources-file",
                str(sources_file),
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=ROOT_DIR,
            timeout=120,
        )
        assert result.returncode == 1
        assert "seed-sources failed: url_contains_credentials" in result.stderr
        assert "s3cret" not in result.stderr
        assert "alice" not in result.stderr


# E. Repository contract -------------------------------------------------------


class TestRepositoryContract:
    def test_config_sources_file_contains_single_verified_source(self):
        path = ROOT_DIR / "config" / "sources.json"
        assert path.exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, list)
        assert len(payload) == 1  # exactly one production source registered so far
        definition = payload[0]
        assert definition == {
            "name": "0xRadikal-verified",
            "type": "http",
            "url": (
                "https://raw.githubusercontent.com/0xRadikal/Free-v2ray-Configs/"
                "main/verified/configs_base64.txt"
            ),
        }

    def test_config_source_passes_definition_validation(self):
        path = ROOT_DIR / "config" / "sources.json"
        schemas = seeding.load_defined_sources(path)
        assert len(schemas) == 1
        assert schemas[0].name == "0xRadikal-verified"
        assert schemas[0].source_type == "http"

    def test_default_sources_file_setting_matches_workflow(self):
        from proxyaggregator.__main__ import _build_parser

        parser = _build_parser()
        assert Settings().sources_file == "config/sources.json"
        assert parser.parse_args(["seed-sources"]).sources_file is None

    def test_workflow_seeds_before_pipeline(self):
        text = (ROOT_DIR / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
        seed_pos = text.index("Seed production sources")
        pipeline_pos = text.index("Run production pipeline")
        assert seed_pos < pipeline_pos
        assert "PA_SOURCES_FILE: config/sources.json" in text


# F. Offline integration: seed -> pipeline -------------------------------------


class TestSeedToPipeline:
    @staticmethod
    async def _fake_collect(sources, registry=None):
        results = []
        for source in sources:
            content = CONTENT_A if "one" in source.url else CONTENT_B
            results.append(_source_result(source, content))
        return results

    def test_seeded_definitions_flow_into_pipeline(
        self, db_session, sources_file, tmp_path, monkeypatch
    ):
        path = sources_file([DEFINITION_A, DEFINITION_B])
        schemas = seeding.load_defined_sources(path)
        stats1 = seeding.seed_sources(db_session, schemas)
        stats2 = seeding.seed_sources(db_session, schemas)
        assert (stats1.inserted, stats2.inserted) == (2, 0)

        rows = list_sources(db_session)
        assert len(rows) == 2
        assert isinstance(rows[0], SourceORM)

        cfg = pipeline.PipelineConfig(
            settings=Settings(),
            sources=tuple(pipeline.load_configured_sources(db_session)),
            output_dir=tmp_path / "out",
            enricher=_enricher,
            health_runner=DeterministicHealthRunner(),
        )
        with mock.patch.object(pipeline, "_collect_sources", self._fake_collect):
            stats = asyncio.run(pipeline.run_pipeline(db_session, cfg))

        assert stats.sources_discovered == 2
        assert stats.sources_fetched == 2
        assert stats.published_artifacts == 10

        out = tmp_path / "out"
        assert (out / "proxyaggregator.txt").exists()
        assert (out / "manifest.json").exists()

        # Pipeline attributes configs to the seeded sources; no duplicate rows.
        rows_after = list_sources(db_session)
        assert len(rows_after) == 2
        assert {row.name for row in rows_after} == {"alpha", "beta"}

    def test_seed_twice_then_pipeline_is_deterministic(self, db_session, sources_file, tmp_path):
        path = sources_file([DEFINITION_A, DEFINITION_B])
        schemas = seeding.load_defined_sources(path)
        seeding.seed_sources(db_session, schemas)
        seeding.seed_sources(db_session, schemas)

        out = tmp_path / "out"
        with mock.patch.object(pipeline, "_collect_sources", self._fake_collect):
            first = asyncio.run(
                pipeline.run_pipeline(
                    db_session,
                    pipeline.PipelineConfig(
                        settings=Settings(),
                        sources=tuple(pipeline.load_configured_sources(db_session)),
                        output_dir=out,
                        enricher=_enricher,
                        health_runner=DeterministicHealthRunner(),
                    ),
                )
            )
        first_bytes = {p.name: p.read_bytes() for p in out.iterdir()}

        with mock.patch.object(pipeline, "_collect_sources", self._fake_collect):
            second = asyncio.run(
                pipeline.run_pipeline(
                    db_session,
                    pipeline.PipelineConfig(
                        settings=Settings(),
                        sources=tuple(pipeline.load_configured_sources(db_session)),
                        output_dir=out,
                        enricher=_enricher,
                        health_runner=DeterministicHealthRunner(),
                    ),
                )
            )
        second_bytes = {p.name: p.read_bytes() for p in out.iterdir()}

        assert sorted(first_bytes) == sorted(second_bytes)
        for name, data in first_bytes.items():
            assert data == second_bytes[name]
        assert first.published_artifacts == second.published_artifacts == 10
