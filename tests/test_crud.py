"""Tests for basic CRUD operations."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from proxyaggregator.db.base import Base
from proxyaggregator.db.crud import (
    create_health_check,
    create_proxy_config,
    create_source,
    delete_proxy_config,
    get_health_checks_for_config,
    get_proxy_config,
    get_source,
    list_proxy_configs,
    update_proxy_config,
)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class TestCRUDProxyConfig:
    """Tests for ProxyConfig CRUD operations."""

    def test_create_and_get(self, db_session: Session):
        config = create_proxy_config(
            db_session,
            protocol="vless",
            host="example.com",
            port=443,
            raw_uri="vless://user@example.com:443",
            content_hash="a" * 64,
        )
        assert config.id is not None

        retrieved = get_proxy_config(db_session, config.id)
        assert retrieved is not None
        assert retrieved.protocol == "vless"
        assert retrieved.host == "example.com"

    def test_list_proxy_configs(self, db_session: Session):
        for i in range(3):
            create_proxy_config(
                db_session,
                protocol="vless",
                host=f"host{i}.example.com",
                port=443,
                raw_uri=f"vless://user@host{i}.example.com:443",
                content_hash=f"{i:02x}" * 32,
            )

        configs = list_proxy_configs(db_session)
        assert len(configs) == 3

    def test_update_proxy_config(self, db_session: Session):
        config = create_proxy_config(
            db_session,
            protocol="vmess",
            host="1.2.3.4",
            port=8080,
            raw_uri="vmess://data",
            content_hash="b" * 64,
        )

        updated = update_proxy_config(
            db_session,
            config.id,
            country_code="US",
            city="San Francisco",
            is_alive=True,
            latency_ms=33.5,
        )
        assert updated.country_code == "US"
        assert updated.city == "San Francisco"
        assert updated.is_alive is True
        assert updated.latency_ms == 33.5

    def test_delete_proxy_config(self, db_session: Session):
        config = create_proxy_config(
            db_session,
            protocol="trojan",
            host="server.com",
            port=443,
            raw_uri="trojan://pass@server.com:443",
            content_hash="c" * 64,
        )
        config_id = config.id

        result = delete_proxy_config(db_session, config_id)
        assert result is True

        assert get_proxy_config(db_session, config_id) is None

    def test_delete_nonexistent_returns_false(self, db_session: Session):
        result = delete_proxy_config(db_session, 9999)
        assert result is False


class TestCRUDSource:
    """Tests for Source CRUD operations."""

    def test_create_and_get_source(self, db_session: Session):
        source = create_source(
            db_session,
            name="Telegram Channel",
            source_type="telegram",
            url="https://t.me/proxies",
        )
        assert source.id is not None

        retrieved = get_source(db_session, source.id)
        assert retrieved is not None
        assert retrieved.name == "Telegram Channel"


class TestCRUDHealthCheck:
    """Tests for HealthCheck CRUD operations."""

    def test_create_health_check_and_query(self, db_session: Session):
        config = create_proxy_config(
            db_session,
            protocol="vless",
            host="example.com",
            port=443,
            raw_uri="vless://user@example.com:443",
            content_hash="d" * 64,
        )

        check = create_health_check(
            db_session,
            proxy_config_id=config.id,
            is_alive=True,
            latency_ms=42.0,
        )
        assert check.id is not None

        checks = get_health_checks_for_config(db_session, config.id)
        assert len(checks) == 1
        assert checks[0].is_alive is True

    def test_health_check_history(self, db_session: Session):
        config = create_proxy_config(
            db_session,
            protocol="vmess",
            host="1.2.3.4",
            port=8080,
            raw_uri="vmess://data",
            content_hash="e" * 64,
        )

        for i in range(5):
            create_health_check(
                db_session,
                proxy_config_id=config.id,
                is_alive=i % 2 == 0,
                latency_ms=float(i * 10),
            )

        checks = get_health_checks_for_config(db_session, config.id)
        assert len(checks) == 5
