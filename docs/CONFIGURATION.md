# Configuration

ProxyAggregator is configured via environment variables with the `PA_` prefix.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PA_DATABASE_URL` | `sqlite:///proxyaggregator.db` | Database connection URL |
| `PA_GITHUB_TOKEN` | — | GitHub token for publishing |
| `PA_GITHUB_REPO` | — | GitHub repo (owner/name) |
| `PA_GEOIP_DB_PATH` | `GeoLite2-City.mmdb` | Path to MaxMind GeoLite2 City DB |
| `PA_HEALTH_CHECK_TIMEOUT` | `10` | Health check timeout in seconds |
| `PA_HEALTH_CHECK_CONCURRENCY` | `50` | Max concurrent health checks |
| `PA_LOG_LEVEL` | `INFO` | Logging level |

## .env File

Create a `.env` file in the project root (not committed to git):

```env
PA_DATABASE_URL=sqlite:///proxyaggregator.db
PA_GITHUB_TOKEN=ghp_xxxxxxxxxxxx
PA_GITHUB_REPO=your_username/ProxyAggregator
PA_GEOIP_DB_PATH=GeoLite2-City.mmdb
PA_HEALTH_CHECK_TIMEOUT=10
PA_HEALTH_CHECK_CONCURRENCY=50
PA_LOG_LEVEL=INFO
```

## GitHub Actions Secrets

When running in CI, use GitHub Actions secrets:

```yaml
env:
  PA_GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  PA_GITHUB_REPO: ${{ github.repository }}
  PA_GEOIP_DB_PATH: /path/to/GeoLite2-City.mmdb
```

## Configuration Validation

The `Settings` dataclass provides type-safe configuration with defaults. Invalid values will raise clear errors at startup.

## Security Notes

- Never commit `.env` to version control
- Use GitHub Actions secrets for CI
- Rotate tokens regularly
- GeoIP database requires a MaxMind license key (free tier available)
