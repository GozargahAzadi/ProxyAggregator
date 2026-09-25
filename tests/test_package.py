"""Smoke tests for ProxyAggregator package."""

from proxyaggregator import __version__


def test_version_exists() -> None:
    """Verify package version is defined."""
    assert __version__ == "0.1.0"


def test_package_import() -> None:
    """Verify core package can be imported."""
    import proxyaggregator

    assert proxyaggregator is not None


def test_config_import() -> None:
    """Verify config module can be imported."""
    from proxyaggregator.config import settings

    assert settings is not None


def test_settings_defaults() -> None:
    """Verify Settings has correct default values."""
    from proxyaggregator.config.settings import Settings

    s = Settings()
    assert s.database_url == "sqlite:///proxyaggregator.db"
    assert s.health_check_timeout == 10
    assert s.health_check_concurrency == 50
    assert s.health_persist_batch_size == 1000
    assert s.dns_resolution_concurrency == 50
    assert s.source_collection_concurrency == 10
    assert s.log_level == "INFO"


def test_db_engine_import() -> None:
    """Verify database engine module can be imported."""
    from proxyaggregator.db.engine import Base, SessionLocal, engine

    assert Base is not None
    assert engine is not None
    assert SessionLocal is not None


def test_subpackage_imports() -> None:
    """Verify all subpackages can be imported."""
    import proxyaggregator.config
    import proxyaggregator.db
    import proxyaggregator.geoip
    import proxyaggregator.health
    import proxyaggregator.models
    import proxyaggregator.parsers
    import proxyaggregator.publishing
    import proxyaggregator.sources

    assert proxyaggregator.parsers is not None
    assert proxyaggregator.sources is not None
    assert proxyaggregator.geoip is not None
    assert proxyaggregator.health is not None
    assert proxyaggregator.publishing is not None
    assert proxyaggregator.db is not None
    assert proxyaggregator.config is not None
    assert proxyaggregator.models is not None
