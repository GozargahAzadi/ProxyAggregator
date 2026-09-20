# Database

## Overview

ProxyAggregator uses SQLAlchemy 2.x with SQLite as the default database. PostgreSQL support is planned via `DATABASE_URL`.

## Connection

The database URL is configured via the `PA_DATABASE_URL` environment variable:

```
# SQLite (default)
PA_DATABASE_URL=sqlite:///proxyaggregator.db

# PostgreSQL (future)
PA_DATABASE_URL=postgresql://user:pass@localhost/proxyaggregator
```

## Models

### ProxyConfig

Stores parsed and normalized proxy configurations.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer (PK) | Auto-increment ID |
| protocol | String | Protocol type (vless, vmess, etc.) |
| host | String | Server hostname/IP |
| port | Integer | Server port |
| raw_uri | Text | Original URI string |
| content_hash | String(64) | SHA-256 hash for dedup |
| country_code | String(2) | ISO 3166-1 alpha-2 |
| city | String | City name |
| latitude | Float | Latitude |
| longitude | Float | Longitude |
| is_alive | Boolean | Last health check result |
| latency_ms | Float | Last measured latency |
| created_at | DateTime | First seen timestamp |
| updated_at | DateTime | Last updated timestamp |

### Source

Tracks where configurations were collected from.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer (PK) | Auto-increment ID |
| name | String | Source name |
| source_type | String | Type (telegram, github, http, rss) |
| url | String | Source URL |
| last_fetched_at | DateTime | Last successful fetch |
| config_count | Integer | Number of configs from this source |

### HealthCheck

Stores health check history.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer (PK) | Auto-increment ID |
| proxy_config_id | Integer (FK) | Reference to ProxyConfig |
| checked_at | DateTime | Check timestamp |
| is_alive | Boolean | Result |
| latency_ms | Float | Latency in milliseconds |
| error_message | String | Error if failed |

## Migrations

Alembic is used for schema migrations:

```bash
# Generate a new migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Rollback
uv run alembic downgrade -1
```

## Future

- PostgreSQL via `DATABASE_URL` for production
- Connection pooling with `asyncpg`
- Read replicas for API
