"""Basic CRUD operations for database models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from proxyaggregator.db.models import HealthCheckORM, ProxyConfigORM, SourceORM

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


# --- ProxyConfig CRUD ---


def create_proxy_config(
    session: Session,
    *,
    protocol: str,
    host: str,
    port: int,
    raw_uri: str,
    content_hash: str,
    source_id: int | None = None,
    country_code: str | None = None,
    city: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> ProxyConfigORM:
    config = ProxyConfigORM(
        protocol=protocol,
        host=host,
        port=port,
        raw_uri=raw_uri,
        content_hash=content_hash,
        source_id=source_id,
        country_code=country_code,
        city=city,
        latitude=latitude,
        longitude=longitude,
    )
    session.add(config)
    session.commit()
    return config


def get_proxy_config(session: Session, config_id: int) -> ProxyConfigORM | None:
    return session.get(ProxyConfigORM, config_id)


def list_proxy_configs(
    session: Session, *, limit: int = 100, offset: int = 0
) -> list[ProxyConfigORM]:
    stmt = select(ProxyConfigORM).offset(offset).limit(limit)
    return list(session.scalars(stmt))


def update_proxy_config(
    session: Session,
    config_id: int,
    **kwargs,
) -> ProxyConfigORM | None:
    config = session.get(ProxyConfigORM, config_id)
    if config is None:
        return None
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
    config.updated_at = _utcnow()
    session.commit()
    return config


def delete_proxy_config(session: Session, config_id: int) -> bool:
    config = session.get(ProxyConfigORM, config_id)
    if config is None:
        return False
    session.delete(config)
    session.commit()
    return True


# --- Source CRUD ---


def create_source(
    session: Session,
    *,
    name: str,
    source_type: str,
    url: str,
) -> SourceORM:
    source = SourceORM(name=name, source_type=source_type, url=url)
    session.add(source)
    session.commit()
    return source


def get_source(session: Session, source_id: int) -> SourceORM | None:
    return session.get(SourceORM, source_id)


# --- HealthCheck CRUD ---


def create_health_check(
    session: Session,
    *,
    proxy_config_id: int,
    is_alive: bool,
    latency_ms: float | None = None,
    error_message: str | None = None,
) -> HealthCheckORM:
    check = HealthCheckORM(
        proxy_config_id=proxy_config_id,
        is_alive=is_alive,
        latency_ms=latency_ms,
        error_message=error_message,
    )
    session.add(check)
    session.commit()
    return check


def get_health_checks_for_config(
    session: Session, proxy_config_id: int
) -> list[HealthCheckORM]:
    stmt = (
        select(HealthCheckORM)
        .where(HealthCheckORM.proxy_config_id == proxy_config_id)
        .order_by(HealthCheckORM.checked_at.desc())
    )
    return list(session.scalars(stmt))
