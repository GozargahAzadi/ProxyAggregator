"""Database engine and session management."""

from sqlalchemy import create_engine
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

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables (convenience for scripts / tests)."""
    Base.metadata.create_all(bind=engine)
