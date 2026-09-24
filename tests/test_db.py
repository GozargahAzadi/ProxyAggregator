"""Tests for SQLAlchemy ORM models and database initialization."""

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from proxyaggregator.db.base import Base
from proxyaggregator.db.models import HealthCheckORM, ProxyConfigORM, SourceORM


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


class TestProxyConfigORM:
    """Tests for ProxyConfig ORM model."""

    def test_create_proxy_config(self, db_session: Session):
        config = ProxyConfigORM(
            protocol="vless",
            host="example.com",
            port=443,
            raw_uri="vless://user@example.com:443?security=tls",
            content_hash="a" * 64,
        )
        db_session.add(config)
        db_session.commit()

        assert config.id is not None
        assert config.created_at is not None
        assert config.updated_at is not None

    def test_proxy_config_defaults(self, db_session: Session):
        config = ProxyConfigORM(
            protocol="vmess",
            host="1.2.3.4",
            port=8080,
            raw_uri="vmess://data",
            content_hash="b" * 64,
        )
        db_session.add(config)
        db_session.commit()

        assert config.is_alive is False
        assert config.latency_ms is None
        assert config.country_code is None
        assert config.city is None
        assert config.latitude is None
        assert config.longitude is None
        assert config.source_id is None

    def test_proxy_config_with_source_relationship(self, db_session: Session):
        source = SourceORM(
            name="Test Source",
            source_type="telegram",
            url="https://t.me/test",
        )
        db_session.add(source)
        db_session.flush()

        config = ProxyConfigORM(
            protocol="trojan",
            host="server.com",
            port=443,
            raw_uri="trojan://pass@server.com:443",
            content_hash="c" * 64,
            source_id=source.id,
        )
        db_session.add(config)
        db_session.commit()

        assert config.source_id == source.id
        assert config.source is source

    def test_proxy_config_unique_content_hash(self, db_session: Session):
        from sqlalchemy.exc import IntegrityError

        config1 = ProxyConfigORM(
            protocol="vless",
            host="example.com",
            port=443,
            raw_uri="vless://user@example.com:443",
            content_hash="d" * 64,
        )
        db_session.add(config1)
        db_session.commit()

        config2 = ProxyConfigORM(
            protocol="vmess",
            host="other.com",
            port=80,
            raw_uri="vmess://other",
            content_hash="d" * 64,
        )
        db_session.add(config2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_proxy_config_read(self, db_session: Session):
        config = ProxyConfigORM(
            protocol="hysteria2",
            host="hy2.example.com",
            port=8443,
            raw_uri="hysteria2://pass@hy2.example.com:8443",
            content_hash="e" * 64,
            country_code="DE",
            city="Berlin",
            latitude=52.52,
            longitude=13.405,
        )
        db_session.add(config)
        db_session.commit()

        retrieved = db_session.query(ProxyConfigORM).filter_by(id=config.id).one()
        assert retrieved.protocol == "hysteria2"
        assert retrieved.country_code == "DE"
        assert retrieved.city == "Berlin"

    def test_proxy_config_update(self, db_session: Session):
        config = ProxyConfigORM(
            protocol="vless",
            host="example.com",
            port=443,
            raw_uri="vless://user@example.com:443",
            content_hash="f" * 64,
        )
        db_session.add(config)
        db_session.commit()

        config.is_alive = True
        config.latency_ms = 45.2
        config.country_code = "JP"
        db_session.commit()

        retrieved = db_session.query(ProxyConfigORM).filter_by(id=config.id).one()
        assert retrieved.is_alive is True
        assert retrieved.latency_ms == 45.2
        assert retrieved.country_code == "JP"

    def test_proxy_config_delete(self, db_session: Session):
        config = ProxyConfigORM(
            protocol="vless",
            host="example.com",
            port=443,
            raw_uri="vless://user@example.com:443",
            content_hash="1a" * 32,
        )
        db_session.add(config)
        db_session.commit()
        config_id = config.id

        db_session.delete(config)
        db_session.commit()

        assert db_session.query(ProxyConfigORM).filter_by(id=config_id).first() is None

    def test_proxy_config_bulk_create(self, db_session: Session):
        configs = [
            ProxyConfigORM(
                protocol="vless",
                host=f"host{i}.example.com",
                port=443,
                raw_uri=f"vless://user@host{i}.example.com:443",
                content_hash=f"{i:02x}" * 32,
            )
            for i in range(5)
        ]
        db_session.add_all(configs)
        db_session.commit()

        count = db_session.query(ProxyConfigORM).count()
        assert count == 5


class TestSourceORM:
    """Tests for Source ORM model."""

    def test_create_source(self, db_session: Session):
        source = SourceORM(
            name="GitHub Raw",
            source_type="github",
            url="https://github.com/user/proxies/raw/main/proxies.txt",
        )
        db_session.add(source)
        db_session.commit()

        assert source.id is not None

    def test_source_defaults(self, db_session: Session):
        source = SourceORM(
            name="Test",
            source_type="http",
            url="https://example.com/proxies",
        )
        db_session.add(source)
        db_session.commit()

        assert source.config_count == 0
        assert source.last_fetched_at is None

    def test_source_configs_relationship(self, db_session: Session):
        source = SourceORM(
            name="Telegram",
            source_type="telegram",
            url="https://t.me/proxies",
        )
        db_session.add(source)
        db_session.flush()

        config = ProxyConfigORM(
            protocol="vless",
            host="example.com",
            port=443,
            raw_uri="vless://user@example.com:443",
            content_hash="aa" * 32,
            source_id=source.id,
        )
        db_session.add(config)
        db_session.commit()

        assert len(source.configs) == 1
        assert source.configs[0].protocol == "vless"

    def test_source_read(self, db_session: Session):
        source = SourceORM(
            name="RSS Feed",
            source_type="rss",
            url="https://example.com/feed.xml",
        )
        db_session.add(source)
        db_session.commit()

        retrieved = db_session.query(SourceORM).filter_by(id=source.id).one()
        assert retrieved.source_type == "rss"
        assert retrieved.url == "https://example.com/feed.xml"


class TestHealthCheckORM:
    """Tests for HealthCheck ORM model."""

    def test_create_health_check(self, db_session: Session):
        config = ProxyConfigORM(
            protocol="vless",
            host="example.com",
            port=443,
            raw_uri="vless://user@example.com:443",
            content_hash="bb" * 32,
        )
        db_session.add(config)
        db_session.flush()

        check = HealthCheckORM(
            proxy_config_id=config.id,
            is_alive=True,
            latency_ms=123.45,
        )
        db_session.add(check)
        db_session.commit()

        assert check.id is not None
        assert check.checked_at is not None

    def test_health_check_defaults(self, db_session: Session):
        config = ProxyConfigORM(
            protocol="vmess",
            host="1.2.3.4",
            port=8080,
            raw_uri="vmess://data",
            content_hash="cc" * 32,
        )
        db_session.add(config)
        db_session.flush()

        check = HealthCheckORM(
            proxy_config_id=config.id,
            is_alive=False,
        )
        db_session.add(check)
        db_session.commit()

        assert check.latency_ms is None
        assert check.error_message is None

    def test_health_check_proxy_config_relationship(self, db_session: Session):
        config = ProxyConfigORM(
            protocol="trojan",
            host="server.com",
            port=443,
            raw_uri="trojan://pass@server.com:443",
            content_hash="dd" * 32,
        )
        db_session.add(config)
        db_session.flush()

        check = HealthCheckORM(
            proxy_config_id=config.id,
            is_alive=True,
            latency_ms=50.0,
        )
        db_session.add(check)
        db_session.commit()

        assert check.proxy_config is config
        assert check in config.health_checks

    def test_health_check_history(self, db_session: Session):
        config = ProxyConfigORM(
            protocol="vless",
            host="example.com",
            port=443,
            raw_uri="vless://user@example.com:443",
            content_hash="ee" * 32,
        )
        db_session.add(config)
        db_session.flush()

        for i in range(3):
            check = HealthCheckORM(
                proxy_config_id=config.id,
                is_alive=i % 2 == 0,
                latency_ms=float(i * 100),
            )
            db_session.add(check)
        db_session.commit()

        checks = db_session.query(HealthCheckORM).filter_by(proxy_config_id=config.id).all()
        assert len(checks) == 3


class TestDatabaseSchema:
    """Tests for database schema validation."""

    def test_tables_created(self, db_engine):
        inspector = inspect(db_engine)
        tables = inspector.get_table_names()
        assert "proxy_configs" in tables
        assert "sources" in tables
        assert "health_checks" in tables

    def test_proxy_config_columns(self, db_engine):
        inspector = inspect(db_engine)
        columns = {col["name"] for col in inspector.get_columns("proxy_configs")}
        expected = {
            "id",
            "protocol",
            "host",
            "port",
            "raw_uri",
            "content_hash",
            "country_code",
            "city",
            "latitude",
            "longitude",
            "is_alive",
            "latency_ms",
            "source_id",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(columns)

    def test_source_columns(self, db_engine):
        inspector = inspect(db_engine)
        columns = {col["name"] for col in inspector.get_columns("sources")}
        expected = {"id", "name", "source_type", "url", "last_fetched_at", "config_count"}
        assert expected.issubset(columns)

    def test_health_check_columns(self, db_engine):
        inspector = inspect(db_engine)
        columns = {col["name"] for col in inspector.get_columns("health_checks")}
        expected = {
            "id",
            "proxy_config_id",
            "checked_at",
            "is_alive",
            "latency_ms",
            "error_message",
        }
        assert expected.issubset(columns)

    def test_foreign_keys(self, db_engine):
        inspector = inspect(db_engine)
        fks = inspector.get_foreign_keys("proxy_configs")
        assert any(fk["referred_table"] == "sources" for fk in fks)

        fks = inspector.get_foreign_keys("health_checks")
        assert any(fk["referred_table"] == "proxy_configs" for fk in fks)
