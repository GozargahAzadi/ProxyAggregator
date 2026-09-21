"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from proxyaggregator.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class SourceORM(Base):
    """Tracks where proxy configurations were collected from."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    config_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    configs: Mapped[list[ProxyConfigORM]] = relationship(
        "ProxyConfigORM", back_populates="source", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<SourceORM(id={self.id}, name='{self.name}', type='{self.source_type}')>"


class ProxyConfigORM(Base):
    """Stores parsed and normalized proxy configurations."""

    __tablename__ = "proxy_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    protocol: Mapped[str] = mapped_column(String(50), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_uri: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )

    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    is_alive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sources.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    source: Mapped[SourceORM | None] = relationship(
        "SourceORM", back_populates="configs", lazy="select"
    )
    health_checks: Mapped[list[HealthCheckORM]] = relationship(
        "HealthCheckORM", back_populates="proxy_config", lazy="select",
        order_by="HealthCheckORM.checked_at.desc()",
    )

    def __repr__(self) -> str:
        return (
            f"<ProxyConfigORM(id={self.id}, protocol='{self.protocol}', "
            f"host='{self.host}:{self.port}')>"
        )


class HealthCheckORM(Base):
    """Stores health check history for proxy configs."""

    __tablename__ = "health_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proxy_config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("proxy_configs.id"), nullable=False
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    is_alive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    proxy_config: Mapped[ProxyConfigORM] = relationship(
        "ProxyConfigORM", back_populates="health_checks", lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<HealthCheckORM(id={self.id}, config_id={self.proxy_config_id}, "
            f"alive={self.is_alive})>"
        )
