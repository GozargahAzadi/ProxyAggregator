# Phase 4 Report — Deduplication

## 1. Files Created/Changed

### New Files
| File | Purpose |
|------|---------|
| `src/proxyaggregator/dedup/__init__.py` | Module docstring |
| `src/proxyaggregator/dedup/models.py` | `DedupMatchType` enum, `DedupResult` Pydantic model |
| `src/proxyaggregator/dedup/canonical.py` | `canonicalize()` and `compute_content_hash()` |
| `src/proxyaggregator/dedup/endpoint.py` | `EndpointIdentity` model and `endpoint_identity()` |
| `src/proxyaggregator/dedup/fuzzy.py` | `fuzzy_match()` structured field comparison |
| `src/proxyaggregator/dedup/deduplicator.py` | `Deduplicator` main class |
| `tests/test_dedup.py` | 71 tests covering all mechanisms |

### Changed Files
| File | Change |
|------|--------|
| `ROADMAP.md` | Marked Phase 3 and Phase 4 items complete |

## 2. Deduplication Architecture

```
ParseResult list
      |
      v
+-----------------+
| Deduplicator    |
|                 |
| For each item:  |
|  1. Compute     |
|     content hash|
|  2. Check       |
|     exact match |
|  3. Check       |
|     endpoint    |
|  4. Check       |
|     fuzzy match |
+-----------------+
      |
      v
DedupResult list (one per input, ordered)
```

Three independent mechanisms, evaluated in priority order:
1. **Exact** (highest priority) — same content hash
2. **Endpoint** — same protocol/host/port, different config
3. **Fuzzy** — structured field comparison ignoring non-essential fields

## 3. Canonical Fingerprint Rules

**Fields included in canonical form (identity fields):**
- `protocol`, `host` (lowercased), `port`
- `user`, `password` (credentials are included in hash but never exposed)
- `sni`, `network`, `tls`, `path`, `host_header`
- `service_name`, `flow`, `method`, `obfs`, `obfs_password`

**Fields excluded (non-identity):**
- `raw_uri` — original presentation, not identity
- `fragment` — cosmetic naming only
- Host header — not part of endpoint identity

**Normalization:**
- Host lowercased
- `None`/empty values normalized to empty string
- Deterministic sorted JSON serialization
- SHA-256 hash (64-char hex)

**Security:**
- Credentials are hashed, never exposed in `DedupResult.match_reason`
- `match_reason` strings never contain passwords, UUIDs, or secrets

## 4. Endpoint Identity Rules

Endpoint = `(protocol, host_lowercased, port)`

- Same endpoint does NOT imply same configuration
- Different credentials on same endpoint → `ENDPOINT` collision (not `EXACT`)
- Different protocols → different endpoints
- Endpoint identity is hashable (usable in dicts/sets)

## 5. Fuzzy Matching Rules

**Fields compared (must match exactly):**
- protocol, host, port, user, password
- sni, network, tls, path
- service_name, flow, method
- obfs, obfs_password

**Fields ignored (non-essential):**
- fragment, host_header, raw_uri

**Conservative behavior:**
- Any difference in identity fields → no match
- Only cosmetic/presentation differences → fuzzy match
- When ambiguous, prefer keeping nodes separate

## 6. Survivor Policy

- **First occurrence survives**: Items processed in input order
- **Exact duplicates**: Later items classified as `EXACT`, referencing first occurrence index
- **Endpoint collisions**: Later items classified as `ENDPOINT`, referencing first occurrence index
- **Fuzzy matches**: Later items classified as `FUZZY`, referencing first occurrence index
- **Deterministic**: Same input → same output across runs

## 7. False-Positive Protections

- Same host+port does NOT auto-merge different credentials
- Different protocols always produce different hashes
- Different Shadowsocks methods produce different hashes
- Different transport/TLS settings produce different hashes
- Fragment differences are fuzzy, not exact
- No arbitrary thresholds on string similarity

## 8. Security Considerations

- SHA-256 is used as identity fingerprint, not encryption
- Passwords/UUIDs never appear in `match_reason` strings
- `match_reason` uses generic descriptions ("Same endpoint, different configuration")
- No logging of raw URIs or credentials in the dedup layer

## 9. Tests Added

**71 tests** across 8 test classes:

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestCanonicalization` | 16 | Determinism, field ordering, host normalization, meaningful vs excluded fields |
| `TestComputeContentHash` | 8 | Determinism, hex format, length, cross-protocol, credential handling |
| `TestEndpointIdentity` | 8 | Basic identity, host lowercasing, hashability, same-endpoint-different-creds |
| `TestFuzzyMatch` | 18 | Identity matching, non-essential ignored, all identity fields tested |
| `TestDeduplicatorOrdering` | 5 | First survivor, determinism, all-dupes, no-dupes, mixed |
| `TestDeduplicatorEndpoint` | 3 | Endpoint collision detection |
| `TestDeduplicatorFuzzy` | 2 | Fuzzy detection in Deduplicator |
| `TestSecurity` | 3 | No credential leakage in fingerprints or reasons |
| `TestEdgeCases` | 10 | Empty, single, mixed, hash/endpoint fields |

## 10. Full Pytest Result

```
250 passed, 2 warnings in 3.41s
```

All Phase 0–3 tests continue to pass. No regressions.

## 11. Ruff Result

```
All checks passed!
```

## 12. Alembic Result

```
No new upgrade operations detected.
```

No database migration needed — dedup layer is pure Python.

## 13. Git Status

```
Untracked files:
  PHASE4_REPORT.md
  src/proxyaggregator/dedup/__init__.py
  src/proxyaggregator/dedup/canonical.py
  src/proxyaggregator/dedup/deduplicator.py
  src/proxyaggregator/dedup/endpoint.py
  src/proxyaggregator/dedup/fuzzy.py
  src/proxyaggregator/dedup/models.py
  tests/test_dedup.py

Modified files:
  ROADMAP.md
```

## 14. Commit Hash

Pending — will be committed after report review.

## 15. Unresolved Issues / Architectural Concerns

None. The dedup layer is complete, self-contained, and ready for Phase 5 integration.
