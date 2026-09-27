# Production Source Seeding

Phase 9.2 makes the `sources` table reproducible from version control. The
repository-controlled JSON file `config/sources.json` is the **authoritative
input**; the `seed-sources` command loads and validates it into the database
before the production pipeline runs. The seeder never contacts the network —
fetching is exclusively the collector's job (the `http` collector in Phase 2).

## The definition file

`config/sources.json` is a JSON **array** of source objects. Each object has
three fields:

```json
[
  {
    "name": "Example HTTP feed",
    "type": "http",
    "url": "https://cdn.example.com/proxies.txt"
  }
]
```

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `name` | string | yes | Human-readable source name (≤ 255 chars) |
| `type` | string | yes | Source type (≤ 50 chars); must be a registered collector type (currently `http`) |
| `url` | string | yes | Absolute `http`/`https` URL (≤ 2048 chars) |

The file currently contains an empty array (`[]`). Supplying real, trusted
production source URLs is an operator task and intentionally **not** part of
this codebase deliverable.

## The `seed-sources` command

```
python -m proxyaggregator seed-sources [--sources-file PATH]
```

- Default file: `$PA_SOURCES_FILE`, falling back to `config/sources.json`.
- Exit code `0` on success, `1` on any validation or database failure, with a
  stable reason token (never the offending URL).
- The summary line logs counts only: `defined`, `inserted`, `updated`,
  `unchanged`.

## Validation rules

Every definition is validated **before any database mutation**:

- Missing/empty `name`, `type`, or `url` → rejected
- `type` not in the collector registry allow-list (currently only `http`) → rejected
- URL scheme not `http`/`https` (e.g. `file://`) → rejected, so a definition
  can never steer the pipeline at local files
- Duplicate `url` within the file → rejected (deterministic failure)
- Column length overflows (name 255 / type 50 / url 2048) → rejected
- URL carrying userinfo/credentials (`https://user:pass@…`) → **rejected without
  echoing the URL** (`url_contains_credentials`)

The definition file itself must never contain secrets.

## Idempotency & lifecycle

The seeder upserts by **url** identity (`get_source_by_url`):

- First run inserts; a second run with identical definitions reports
  `inserted=0, unchanged=N` (equivalent table).
- Renamed/retyped rows are updated in place.
- Sources **absent** from the file are **retained**: `SourceORM` has no
  enabled/disabled/deleted field, so there is deliberately no stale-source
  deletion. Removing a source from `config/sources.json` does not delete its
  row; if you need removal, delete the row directly (one-off operator action).
- The seed file supersedes the pipeline's `_get_or_create_source` fallback:
  definitions land in the table *before* the pipeline runs, and duplicate
  rows are never created either by seeding or by the pipeline.

## Workflow order

`.github/workflows/publish.yml` runs:

```
checkout → uv sync → mkdir output → alembic upgrade head
  → seed-sources (reads config/sources.json)
  → pipeline (consumes the seeded sources table)
  → empty-output guard → commit & push
```

Seeding runs **before** the pipeline so the pipeline's `no_configured_sources`
fast-fail reflects the real, version-controlled definitions.

## Source content taxonomy

The `type: "http"` collector fetches whatever a URL returns; the pipeline then
feeds the response through the shared extractor (source text → per-node URIs).
Whether a URL can be added to `config/sources.json` today depends on the
**container format** of the payload it returns, not on the transport. Sources
are triaged into three tiers, and this triage is deliberate — it does **not**
copy whatever NiREvil's own source list looks like.

### Tier 1 — directly ingestible (no new code)

Feed lines are already `scheme://…` node URIs understood by the existing
extractor:

- VLESS, VMess, Trojan, Shadowsocks, Hysteria / Hysteria2
- SOCKS (SOCKS4 / SOCKS5)
- HTTP / HTTPS

These map directly onto the ten canonical protocols (`SUPPORTED_PROTOCOLS`) and
flow through parse → dedup → DNS/GeoIP → health → scoring → publishing with zero
changes.

### Tier 2 — requires a new parser

The source ships the *same* proxies inside a wrapper format that must first be
translated into per-node URIs:

- Clash / Mihomo YAML (`proxies:`)
- sing-box JSON (`outbounds` / `inbounds`)
- other subscription envelope formats (Base64-wrapped lists, etc.)

Adding one of these means writing a parser that emits the existing node model;
dedup, health, GeoIP, scoring, and publishing are then reused unchanged. None
is implemented yet — see `docs/SUBSCRIPTION.md`.

### Tier 3 — deliberately excluded for now

Sources whose content needs pipeline capability that does not exist yet, so
they are **not** added to `config/sources.json`:

- bare `IP:PORT` lines (e.g. `1.2.3.4:443`) — no scheme, no protocol identity,
  no auth, so a node cannot be built without per-endpoint probing /
  TLS-fingerprinting that is out of scope today
- ProxyIP-style geo-IP sweep services (bulk IP/port listings, not subscription
  payloads)
- Cloudflare IP ranges (raw CIDR lists, not proxy nodes)
- WireGuard configurations (`interface`/`peer` key material, not a single-node
  URI)
- raw HTML pages (no subscription payload; HTML scraping is explicitly out of
  scope)

Tier 1 entries are safe to add at any time; Tier 2 is tracked as a follow-up
feature; Tier 3 is a documented non-goal until the corresponding capability
(probing, WireGuard support, scraping) lands.

## Tests

`tests/test_seeding.py` covers definition loading/validation, credential
hygiene, idempotent seeding, CLI exit codes, and the offline
seed → pipeline integration path (injected collector + deterministic health
runner; no network).