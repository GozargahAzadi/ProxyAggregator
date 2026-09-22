# Scoring & Ranking (Phase 7)

Deterministic, latency-only scoring. Output order is fully repeatable: the
same database state always produces the same ranking, anywhere (local dev or
GitHub Actions).

## Eligibility

A proxy is eligible for ranking **only** when its latest `health_checks` row
satisfies **both**:

- `status == OK` (equivalent to `is_alive == True`, per the Phase 6.1 contract)
- `latency_ms IS NOT NULL`

Ineligible and never ranked:

- no health check row at all
- `PROTOCOL_FAILURE`, `UNSUPPORTED`, `TLS_FAILURE`, `TIMEOUT`, `UNREACHABLE`,
  `DNS_FAILURE`, `DECLINED`, `SKIPPED`
- `OK` with `latency_ms = NULL`

The authoritative source is the **latest health check row**, selected by
`checked_at` descending with the row `id` as the deterministic fallback for
identical timestamps. The denormalized `proxy_configs.is_alive`,
`proxy_configs.latency_ms`, and `proxy_configs.working_ip` copies are **not**
independently scored.

## Score

Latency is the **only** score component in Phase 7:

```
tau            = 1000.0 ms
cap            = 3000.0 ms
score          = tau / (tau + min(latency_ms, cap))
```

Examples:

| latency | score |
|---------|-------|
| 0 ms    | 1.000 |
| 100 ms  | 0.909 |
| 500 ms  | 0.667 |
| 1000 ms | 0.500 |
| 2000 ms | 0.333 |
| >=3000 ms | 0.250 |

`latency_ms` must be finite and `>= 0`; `None` means ineligible; negative,
`NaN`, or infinite values are rejected deterministically and never produce a
valid score. Scores are not rounded internally; rounding happens only at
presentation time.

## Ranking order

Eligible proxies are sorted deterministically:

1. `score` **descending**
2. `latency_ms` **ascending**
3. `content_hash` **ascending**
4. `proxy_config_id` **ascending**

The final two keys are guaranteed unique, so the order is a total order.

## Excluded signals (by approved design)

- **No freshness/cross-run scoring** — scoring uses the latest result in the
  current database; there is no time-based decay.
- **No country/GeoIP weighting or filtering** — `country_code`, `city`, and
  location remain descriptive metadata.
- **No protocol weighting** — protocols are not ranked as inherently better.
- **No historical stability scoring** and no additional score components.
- **No score persistence** — scores are computed at runtime; there is no
  `score` column, no ranking table, and no migration.