# Configuration

ProxyAggregator is configured via environment variables with the `PA_` prefix.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PA_DATABASE_URL` | `sqlite:///proxyaggregator.db` | Database connection URL |
| `PA_GITHUB_TOKEN` | — | GitHub token for publishing |
| `PA_GITHUB_REPO` | — | GitHub repo (owner/name) |
| `PA_GEOIP_DB_PATH` | `GeoLite2-City.mmdb` | Path to a country-level MMDB database (`country ipvAll` or GeoLite2-City). In CI this is provisioned automatically and requires no credentials |
| `PA_HEALTH_CHECK_TIMEOUT` | `10` | Health check timeout in seconds |
| `PA_HEALTH_CHECK_CONCURRENCY` | `50` | Max concurrent health checks |
| `PA_HEALTH_CHECK_MAX_IPS_PER_HOST` | `8` | Max candidate IPs probed per host |
| `PA_HEALTH_CHECK_VERIFY_TLS` | `false` | Verify TLS certificate chains. Defaults to handshake-only |
| `PA_FETCH_TIMEOUT` | `30` | Source fetch timeout in seconds |
| `PA_MAX_RESPONSE_BYTES` | `10485760` | Maximum accepted source response size |
| `PA_SOURCES_FILE` | `config/sources.json` | Path to the version-controlled source definition file for `seed-sources` (see `docs/SOURCES.md`) |
| `PA_LOG_LEVEL` | `INFO` | Logging level |

## .env File

Create a `.env` file in the project root (not committed to git):

```env
PA_DATABASE_URL=sqlite:///proxyaggregator.db
PA_GITHUB_TOKEN=ghp_xxxxxxxxxxxx
PA_GITHUB_REPO=your_username/ProxyAggregator
PA_GEOIP_DB_PATH=user-country.mmdb
PA_HEALTH_CHECK_TIMEOUT=10
PA_HEALTH_CHECK_CONCURRENCY=50
PA_HEALTH_CHECK_MAX_IPS_PER_HOST=8
PA_HEALTH_CHECK_VERIFY_TLS=false
PA_FETCH_TIMEOUT=30
PA_MAX_RESPONSE_BYTES=10485760
PA_SOURCES_FILE=config/sources.json
PA_LOG_LEVEL=INFO
```

## GitHub Actions Secrets

CI uses no GeoIP credentials; the country-level MMDB is downloaded from the
ip-location-db releases (no MaxMind account/license key needed). Tokens:

```yaml
env:
  PA_GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  PA_GITHUB_REPO: ${{ github.repository }}
  # PA_GEOIP_DB_PATH is set by the workflow (downloaded user-country.mmdb)
```

## Configuration Validation

The `Settings` dataclass provides type-safe configuration with defaults. Invalid values will raise clear errors at startup.

## Security Notes

- Never commit `.env` to version control
- Use GitHub Actions secrets for CI
- Rotate tokens regularly
- GeoIP uses a free country-level MMDB (`country ipvAll` from
  ip-location-db); no license key is required. GeoLite2-City databases
  remain supported but are not used by CI
- Health-check protocol handshakes (HTTP CONNECT / SOCKS / VLESS /
  Trojan / Shadowsocks) target the proxy's own advertised endpoint
  (self-tunnel) by default, so no external service is configured or
  contacted. VLESS is checked over its plain TCP and TLS transports only;
  REALITY, WS/gRPC overlays, Shadowsocks 2022 (BLAKE3) ciphers, VMess, and
  Hysteria are reported `unsupported` and are never probed. There is
  intentionally no configurable external health-check target;
  `PA_HEALTH_CHECK_*` only controls timeout, concurrency, per-host IP cap,
  and TLS verification.
