"""Deduplication layer for proxy configurations -- Phase 4.

Provides deterministic deduplication via:
- Content-hash based dedup (SHA-256 fingerprint)
- Endpoint-based dedup (protocol/host/port)
- Fuzzy matching for near-duplicates

All mechanisms are explicit and separately testable.
"""
