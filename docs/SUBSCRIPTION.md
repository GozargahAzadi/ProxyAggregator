# Subscription Generation (Phase 8)

Deterministic generation of subscription feeds from the Phase 7 ranked,
eligible proxies. Phase 8 is a pure layer: it performs no network I/O, no DNS,
no health checks, no database queries, and depends on no clock or random
values. Given identical inputs, the output is byte-for-byte identical.

## Input

`RankedProxy` per proxy:
- `proxy_config_id`, `protocol`, `host`, `port`, `raw_uri`, `content_hash`
- `score` (Phase 7 latency score) and `rank` (1-based position)

The producer passes the eligible output of Phase 7 ranking **in rank order
(best first)**. Phase 8 does not reinterpret health state: it never consults
`ProxyConfig.is_alive`, never re-reads `health_checks`, and never recalculates
a score. A candidate that Phase 7 excluded cannot appear, because the producer
only feeds ranked, eligible results.

`raw_uri` is the persisted source string and the only carrier of fields not
persisted in `proxy_configs` (UUID, password, TLS/SNI/network options, ...).
It is re-parsed with the Phase 3 parser and cross-checked against the
persisted identity fields (`protocol`, `host`, `port`) before serialization.

## Supported protocols

All 11 Phase 3 protocols are serializable: VLESS, VMess, Trojan, Shadowsocks,
Hysteria, Hysteria2, SOCKS4/SOCKS4a, SOCKS5, HTTP, HTTPS.

## Output formats

| Format | Content |
|--------|---------|
| `plain` | One canonical URI per line, each line terminated by `\n` (including the last). Empty input produces an empty string. |
| `base64` | Standard Base64 of the UTF-8 `plain` feed (single token, no newlines). |
| `json` | Compact deterministic JSON array; each item carries `uri`, `protocol`, `host`, `port`, `content_hash` (sorted keys, no scores/ids/ranks). |

Clash and sing-box config formats are **deferred** (see below); they are not
part of the Phase 8 output contract.

## Ordering

Output order is the input rank order: rank 1 is the first line, rank 2 the
second, and so on. Nothing is re-sorted after ranking.

## Limiting

`max_items = N` emits the first N **unique** proxies in rank order;
`max_items = None` emits all. `max_items` values below 1 (or non-integers)
raise `ValueError` deterministically instead of producing arbitrary output.

## Deduplication at the output boundary

Phase 4 owns canonical deduplication. Phase 8 only guarantees that one logical
proxy is not emitted twice: if the input contains two candidates with the same
`content_hash`, only the first (best-ranked) occurrence is emitted. No new
fuzzy matching is introduced.

## Determinism

- Canonical percent-encoding: each byte outside the unreserved set is encoded.
- Explicit, sorted query-parameter ordering per protocol.
- VMess JSON keys are emitted with `sort_keys=True`; the payload is re-encoded
  as standard Base64.
- No random values, timestamps, internal database ids, or scores appear in
  generated content.

## Error behavior

Invalid candidates fail deterministically via `SubscriptionError`, which
identifies `proxy_config_id`, `protocol`, and a stable, credential-free
`reason` (`unsupported_protocol`, `parse_failed`, `identity_mismatch`, or a
short serialization reason). Candidates are never dropped silently and never
emitted as malformed URIs.

## Credential handling

Credential material (UUIDs, passwords, auth tokens) appears only inside the
generated URI, exactly as required by the protocol format. Exception messages
never contain credentials or the raw URI string. Tests use synthetic
credentials.

## Relationship with Phase 7

Phase 7 ranks eligible proxies and produces `score`/`rank`; Phase 8 converts
those ranked results into feeds. Phase 8 does not change the score.

## Deferred items

- **Clash config format** — Clash loses fidelity for protocols whose fields are
  not captured by the Phase 3 parsers nor persisted (VMess `alterId`/`cipher`,
  Shadowsocks `plugin`). Emitting defaults would change semantics, so this is
  deferred rather than guessed.
- **Sing-box config format** — likewise deferred; Hysteria additionally
  requires `up`/`down` bandwidth values that are not persisted.
- **Signing** (e.g. Ed25519/PX25519) — not part of the Phase 8 contract
  (ROADMAP); deferred to its defined stage.
- **Phase 9 publishing** — writing feeds into git and GitHub Releases is the
  Phase 9 publisher's responsibility.