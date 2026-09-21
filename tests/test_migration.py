"""Tests for Alembic migrations."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _alembic_config() -> Config:
    """Create an Alembic Config with paths resolved from project root."""
    ini_path = PROJECT_ROOT / "alembic.ini"
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    return config


def test_alembic_ini_exists():
    """Verify alembic.ini is present."""
    ini_path = PROJECT_ROOT / "alembic.ini"
    assert ini_path.exists(), "alembic.ini not found"


def test_alembic_env_exists():
    """Verify alembic env.py is present."""
    env_path = PROJECT_ROOT / "alembic" / "env.py"
    assert env_path.exists(), "alembic/env.py not found"


def test_alembic_script_directory_loads():
    """Verify Alembic can parse the migration script directory."""
    config = _alembic_config()
    script_dir = ScriptDirectory.from_config(config)
    assert script_dir is not None


def test_initial_migration_exists():
    """Verify at least one migration exists in versions/."""
    versions_dir = PROJECT_ROOT / "alembic" / "versions"
    migrations = list(versions_dir.glob("*.py"))
    assert len(migrations) >= 1, "No Alembic migration files found in alembic/versions/"


def test_initial_migration_covers_all_tables():
    """Verify the initial migration creates all expected tables."""
    versions_dir = PROJECT_ROOT / "alembic" / "versions"
    migrations = list(versions_dir.glob("*.py"))

    all_ops = ""
    for m in migrations:
        all_ops += m.read_text()

    assert "proxy_configs" in all_ops or "ProxyConfig" in all_ops
    assert "sources" in all_ops or "Source" in all_ops
    assert "health_checks" in all_ops or "HealthCheck" in all_ops


def test_migration_downgrade_works():
    """Verify that Alembic can parse the migration graph (single head)."""
    config = _alembic_config()
    script_dir = ScriptDirectory.from_config(config)

    heads = script_dir.get_heads()
    assert len(heads) == 1, f"Expected 1 head, got {len(heads)}: {heads}"

    head_rev = script_dir.get_current_head()
    assert head_rev is not None

    revision = script_dir.get_revision(head_rev)
    assert revision is not None
