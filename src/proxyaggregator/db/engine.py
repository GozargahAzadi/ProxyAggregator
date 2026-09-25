"""Database engine and session management."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# Import models so they register with Base.metadata
import proxyaggregator.db.models  # noqa: F401
from proxyaggregator.config.settings import Settings
from proxyaggregator.db.base import Base

settings = Settings()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=False,
)


def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    """Use synchronous=NORMAL instead of the default FULL.

    NORMAL still fsyncs at checkpoints, so durability is preserved without
    sacrificing the per-transaction commit cost.  OFF is deliberately not
    used.  Has no effect on non-SQLite engines.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


if "sqlite" in settings.database_url:
    event.listen(engine, "connect", _set_sqlite_pragma)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables (convenience for scripts / tests)."""
    Base.metadata.create_all(bind=engine)
