"""Phase 7 tests: deterministic proxy scoring and ranking.

Pure unit tests for the latency-only score model, eligibility gate, latest
health-row selection, deterministic ordering, and the Phase 6 contract.
No network access; DB-backed tests use the standard in-memory fixture.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from proxyaggregator.db.base import Base
from proxyaggregator.db.crud import create_proxy_config
from proxyaggregator.db.models import HealthCheckORM
from proxyaggregator.health.models import HealthStatus
from proxyaggregator.scoring.models import RankCandidate
from proxyaggregator.scoring.scorer import (
    MAX_LATENCY_MS,
    TAU_MS,
    build_rank_candidates,
    latency_score,
    latest_health_check,
    rank_proxies,
    score_proxy,
)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _candidate(
    proxy_config_id: int,
    content_hash: str,
    status: HealthStatus,
    latency_ms: float | None,
) -> RankCandidate:
    return RankCandidate(
        proxy_config_id=proxy_config_id,
        content_hash=content_hash,
        status=status,
        latency_ms=latency_ms,
    )


# A. Eligibility -------------------------------------------------------------


class TestEligibility:
    def test_ok_with_valid_latency_eligible(self):
        result = score_proxy(1, "a" * 64, HealthStatus.OK, 120.0)
        assert result.eligible is True
        assert result.score == latency_score(120.0)
        assert result.status is HealthStatus.OK

    @pytest.mark.parametrize(
        ("status",),
        [
            (HealthStatus.PROTOCOL_FAILURE,),
            (HealthStatus.UNSUPPORTED,),
            (HealthStatus.TLS_FAILURE,),
            (HealthStatus.TIMEOUT,),
            (HealthStatus.UNREACHABLE,),
            (HealthStatus.DNS_FAILURE,),
            (HealthStatus.DECLINED,),
            (HealthStatus.SKIPPED,),
        ],
    )
    def test_failed_statuses_are_ineligible(self, status):
        result = score_proxy(1, "a" * 64, status, 50.0)
        assert result.eligible is False
        assert result.score is None

    def test_ok_with_none_latency_ineligible(self):
        result = score_proxy(1, "a" * 64, HealthStatus.OK, None)
        assert result.eligible is False
        assert result.score is None

    def test_no_health_row_ineligible(self, db_session):
        config = create_proxy_config(
            db_session,
            protocol="http",
            host="unchecked.example.com",
            port=8080,
            raw_uri="http://unchecked.example.com:8080",
            content_hash="c" * 64,
        )
        candidates = build_rank_candidates([config], [])
        assert candidates == []
        assert rank_proxies(candidates) == []

    def test_rank_proxies_returns_only_eligible(self):
        candidates = [
            _candidate(1, "a" * 64, HealthStatus.OK, 100.0),
            _candidate(2, "b" * 64, HealthStatus.TIMEOUT, 50.0),
            _candidate(3, "c" * 64, HealthStatus.OK, None),
            _candidate(4, "d" * 64, HealthStatus.UNSUPPORTED, 10.0),
        ]
        ranked = rank_proxies(candidates)
        assert [r.proxy_config_id for r in ranked] == [1]
        assert all(r.eligible for r in ranked)


# B. Formula -----------------------------------------------------------------


class TestLatencyFormula:
    @pytest.mark.parametrize(
        ("latency", "expected"),
        [
            (0, 1.0),
            (100, 1000 / 1100),
            (500, 1000 / 1500),
            (1000, 0.5),
            (2000, 1000 / 3000),
            (3000, 0.25),
            (5000, 0.25),
        ],
    )
    def test_exact_values(self, latency, expected):
        assert latency_score(latency) == expected
        assert TAU_MS == 1000.0
        assert MAX_LATENCY_MS == 3000.0


# C. Monotonicity ------------------------------------------------------------


class TestMonotonicity:
    def test_lower_latency_higher_score(self):
        a = latency_score(50.0)
        b = latency_score(150.0)
        c = latency_score(250.0)
        assert a > b > c


# D. Cap behavior ------------------------------------------------------------


class TestCapBehavior:
    @pytest.mark.parametrize("latency", [3000.0, 3000.001, 5000.0, 100_000.0])
    def test_at_or_above_cap_is_exactly_quarter(self, latency):
        assert latency_score(latency) == 0.25


# E. Invalid latency ---------------------------------------------------------


class TestInvalidLatency:
    @pytest.mark.parametrize(
        "latency",
        [None, -1, -0.1, float("nan"), float("inf"), float("-inf")],
    )
    def test_invalid_latency_raises(self, latency):
        with pytest.raises(ValueError):
            latency_score(latency)

    def test_invalid_negative_never_yields_score(self):
        with pytest.raises(ValueError):
            score_proxy(1, "a" * 64, HealthStatus.OK, -5.0)


# F. Latest health row -------------------------------------------------------


class TestLatestHealthRow:
    def _make_check(self, session, config_id, *, status, latency_ms, checked_at):
        check = HealthCheckORM(
            proxy_config_id=config_id,
            status=status.value,
            is_alive=status is HealthStatus.OK,
            latency_ms=latency_ms,
            checked_at=checked_at,
        )
        session.add(check)
        session.commit()
        return check

    def test_latest_ok_eligible(self, db_session):
        config = create_proxy_config(
            db_session,
            protocol="http",
            host="latest.example.com",
            port=8080,
            raw_uri="http://latest.example.com:8080",
            content_hash="d" * 64,
        )
        self._make_check(
            db_session,
            config.id,
            status=HealthStatus.TIMEOUT,
            latency_ms=None,
            checked_at=datetime(2026, 9, 20),
        )
        self._make_check(
            db_session,
            config.id,
            status=HealthStatus.OK,
            latency_ms=90.0,
            checked_at=datetime(2026, 9, 21),
        )
        candidates = build_rank_candidates([config], db_session.query(HealthCheckORM).all())
        assert len(candidates) == 1
        assert candidates[0].status is HealthStatus.OK
        assert candidates[0].latency_ms == 90.0
        assert rank_proxies(candidates)[0].score == latency_score(90.0)

    def test_latest_failure_ineligible(self, db_session):
        config = create_proxy_config(
            db_session,
            protocol="http",
            host="nowdead.example.com",
            port=8080,
            raw_uri="http://nowdead.example.com:8080",
            content_hash="e" * 64,
        )
        self._make_check(
            db_session,
            config.id,
            status=HealthStatus.OK,
            latency_ms=40.0,
            checked_at=datetime(2026, 9, 20),
        )
        self._make_check(
            db_session,
            config.id,
            status=HealthStatus.PROTOCOL_FAILURE,
            latency_ms=None,
            checked_at=datetime(2026, 9, 21),
        )
        candidates = build_rank_candidates([config], db_session.query(HealthCheckORM).all())
        assert len(candidates) == 1
        assert candidates[0].status is HealthStatus.PROTOCOL_FAILURE
        assert rank_proxies(candidates) == []

    def test_identical_checked_at_falls_back_to_id(self, db_session):
        config = create_proxy_config(
            db_session,
            protocol="http",
            host="tie-clock.example.com",
            port=8080,
            raw_uri="http://tie-clock.example.com:8080",
            content_hash="f" * 64,
        )
        same = datetime(2026, 9, 22, tzinfo=UTC)
        old = self._make_check(
            db_session, config.id, status=HealthStatus.TIMEOUT, latency_ms=None, checked_at=same
        )
        new = self._make_check(
            db_session, config.id, status=HealthStatus.OK, latency_ms=60.0, checked_at=same
        )
        latest = latest_health_check([new, old])
        assert latest.id == new.id
        assert (latest.checked_at, latest.id) == (old.checked_at, old.id) or latest.id > old.id

    def test_latest_health_check_empty(self):
        assert latest_health_check([]) is None


# G. Ranking -----------------------------------------------------------------


class TestRanking:
    def test_lower_latency_ranks_higher(self):
        candidates = [
            _candidate(1, "a" * 64, HealthStatus.OK, 500.0),
            _candidate(2, "b" * 64, HealthStatus.OK, 100.0),
            _candidate(3, "c" * 64, HealthStatus.OK, 2000.0),
        ]
        ranked = rank_proxies(candidates)
        assert [r.proxy_config_id for r in ranked] == [2, 1, 3]
        scores = [r.score for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_scores_present_and_finite(self):
        ranked = rank_proxies([_candidate(7, "g" * 64, HealthStatus.OK, 123.0)])
        assert ranked[0].score == latency_score(123.0)
        assert ranked[0].status is HealthStatus.OK
        assert ranked[0].eligible is True
        assert ranked[0].latency_ms == 123.0


# H. Tie-breaking ------------------------------------------------------------


class TestTieBreaking:
    def test_equal_score_sorts_by_content_hash_asc(self):
        candidates = [
            _candidate(1, "b" * 64, HealthStatus.OK, 100.0),
            _candidate(2, "a" * 64, HealthStatus.OK, 100.0),
        ]
        ranked = rank_proxies(candidates)
        assert ranked[0].content_hash == "a" * 64
        assert ranked[1].content_hash == "b" * 64

    def test_equal_hash_sorts_by_proxy_config_id_asc(self):
        candidates = [
            _candidate(9, "x" * 64, HealthStatus.OK, 200.0),
            _candidate(3, "x" * 64, HealthStatus.OK, 200.0),
        ]
        ranked = rank_proxies(candidates)
        assert [r.proxy_config_id for r in ranked] == [3, 9]

    def test_full_ordering_keys(self):
        candidates = [
            _candidate(4, "z" * 64, HealthStatus.OK, 100.0),
            _candidate(1, "a" * 64, HealthStatus.OK, 50.0),
            _candidate(7, "m" * 64, HealthStatus.OK, 50.0),
            _candidate(2, "a" * 64, HealthStatus.OK, 50.0),
        ]
        # order: id1 (score highest, latency 50) then among {1,7}> tie: hash a<m then id 1<7>...
        ranked = [r.proxy_config_id for r in rank_proxies(candidates)]
        assert ranked == [1, 2, 7, 4]


# I. Determinism -------------------------------------------------------------


class TestDeterminism:
    def test_shuffled_input_produces_identical_order(self):
        candidates = [
            _candidate(1, "a" * 64, HealthStatus.OK, 90.0),
            _candidate(2, "b" * 64, HealthStatus.OK, 300.0),
            _candidate(3, "c" * 64, HealthStatus.OK, 60.0),
            _candidate(4, "d" * 64, HealthStatus.OK, 1500.0),
            _candidate(5, "e" * 64, HealthStatus.OK, 90.0),
        ]
        expected = [r.proxy_config_id for r in rank_proxies(candidates)]
        for seed in range(20):
            shuffled = candidates[:]
            random.Random(seed).shuffle(shuffled)
            assert [r.proxy_config_id for r in rank_proxies(shuffled)] == expected


# J. Phase 6 contract --------------------------------------------------------


class TestPhase6Contract:
    def test_unsupported_not_eligible(self):
        assert score_proxy(1, "a" * 64, HealthStatus.UNSUPPORTED, 1.0).eligible is False

    def test_protocol_failure_not_eligible(self):
        assert score_proxy(1, "a" * 64, HealthStatus.PROTOCOL_FAILURE, 1.0).eligible is False

    def test_ok_eligible(self):
        assert score_proxy(1, "a" * 64, HealthStatus.OK, 1.0).eligible is True


# K. No hidden scoring factors ------------------------------------------------


class TestNoHiddenFactors:
    def test_protocol_and_metadata_do_not_change_score(self, db_session):
        from proxyaggregator.db.models import SourceORM

        sources = []
        for name in ("feeds-a", "feeds-b"):
            source = SourceORM(
                name=name,
                source_type="http",
                url=f"https://example.com/{name}.txt",
            )
            db_session.add(source)
            db_session.flush()
            sources.append(source)

        configs = [
            create_proxy_config(
                db_session,
                protocol="vless",
                host="one.example.com",
                port=443,
                raw_uri=f"vless://u@one.example.com:443?hash={i}",
                content_hash=f"{i:02d}" * 32,
                source_id=sources[i].id,
                country_code="DE",
                city="Berlin",
            )
            for i in range(2)
        ]
        latest = []
        for i, config in enumerate(configs):
            check = HealthCheckORM(
                proxy_config_id=config.id,
                status="ok",
                is_alive=True,
                latency_ms=200.0,
                checked_at=datetime(2026, 9, 22, i, tzinfo=UTC),
            )
            db_session.add(check)
            latest.append(check)
        db_session.commit()
        # second proxy switches protocol/country/city/source and reverse hash
        configs[1].protocol = "trojan"
        configs[1].country_code = "US"
        configs[1].city = "New York"
        db_session.commit()

        candidates = build_rank_candidates(configs, latest)
        scores = [rank_proxies([c])[0].score for c in candidates]
        assert scores[0] == scores[1] == latency_score(200.0)

    def test_score_depends_only_on_status_and_latency(self):
        base = _candidate(1, "a" * 64, HealthStatus.OK, 250.0)
        same_score_other_identity = _candidate(2, "b" * 64, HealthStatus.OK, 250.0)
        assert rank_proxies([base])[0].score == rank_proxies([same_score_other_identity])[0].score
        assert rank_proxies([base])[0].score == latency_score(250.0)
