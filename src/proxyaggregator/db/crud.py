"""Basic CRUD operations for database models."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from proxyaggregator.db.models import HealthCheckORM, ProxyConfigORM, SourceORM

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from proxyaggregator.health.models import HealthCheckResult


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
    status: str | None = None,
    checked_ip: str | None = None,
    attempted_ips: list[str] | None = None,
    connect_ms: float | None = None,
    tls_ms: float | None = None,
    proxy_ms: float | None = None,
    tls_used: bool = False,
    protocol_checked: bool = False,
) -> HealthCheckORM:
    check = HealthCheckORM(
        proxy_config_id=proxy_config_id,
        is_alive=is_alive,
        latency_ms=latency_ms,
        error_message=error_message,
        status=status,
        checked_ip=checked_ip,
        attempted_ips=json.dumps(attempted_ips) if attempted_ips else None,
        connect_ms=connect_ms,
        tls_ms=tls_ms,
        proxy_ms=proxy_ms,
        tls_used=tls_used,
        protocol_checked=protocol_checked,
    )
    session.add(check)
    session.commit()
    return check


def record_health_result(session: Session, result: HealthCheckResult) -> HealthCheckORM:
    """Persist a runner result and refresh the proxied config's denormalized state."""
    if result.proxy_config_id is None:
        raise ValueError("proxy_config_id is required to persist a health result")

    config = session.get(ProxyConfigORM, result.proxy_config_id)
    if config is None:
        raise ValueError(f"proxy config {result.proxy_config_id} not found")

    config.is_alive = result.is_alive
    config.latency_ms = result.latency_ms
    config.working_ip = result.checked_ip
    config.updated_at = _utcnow()

    check = create_health_check(
        session,
        proxy_config_id=result.proxy_config_id,
        is_alive=result.is_alive,
        latency_ms=result.latency_ms,
        error_message=result.error,
        status=result.status.value,
        checked_ip=result.checked_ip,
        attempted_ips=result.attempted_ips or None,
        connect_ms=result.connect_ms,
        tls_ms=result.tls_ms,
        proxy_ms=result.proxy_ms,
        tls_used=result.tls_used,
        protocol_checked=result.protocol_checked,
    )
    return check


def get_health_checks_for_config(session: Session, proxy_config_id: int) -> list[HealthCheckORM]:
    stmt = (
        select(HealthCheckORM)
        .where(HealthCheckORM.proxy_config_id == proxy_config_id)
        .order_by(HealthCheckORM.checked_at.desc())
    )
    return list(session.scalars(stmt))


def list_health_checks(session: Session) -> list[HealthCheckORM]:
    """Return all health check rows in a single bounded query.

    Bulk retrieval for Phase 7 ranking: the scorer selects the latest row per
    proxy in memory (``scoring.scorer.latest_health_check``), so a per-proxy
    query is unnecessary. Returns every row; callers group/order as needed.
    """
    stmt = select(HealthCheckORM)
    return list(session.scalars(stmt))
