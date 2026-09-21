"""Main deduplicator class.

Processes a list of ParseResult items and classifies each as:
- NONE: first occurrence, survivor
- EXACT: exact duplicate (same content hash AND same non-essential fields)
- ENDPOINT: same endpoint but different configuration
- FUZZY: near-duplicate differing only in non-essential fields (fragment,
  host_header, raw_uri) or matching all identity fields

Survivor policy: first occurrence wins. Later duplicates reference
the index of the first survivor that matched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from proxyaggregator.dedup.canonical import compute_content_hash
from proxyaggregator.dedup.endpoint import EndpointIdentity, endpoint_identity
from proxyaggregator.dedup.fuzzy import fuzzy_match
from proxyaggregator.dedup.models import DedupMatchType, DedupResult

if TYPE_CHECKING:
    from proxyaggregator.parsers.base import ParseResult

# Non-essential fields: excluded from content hash but checked for EXACT vs FUZZY.
_NON_ESSENTIAL_FIELDS = ("fragment", "host_header", "raw_uri")


def _non_essential_equal(a: ParseResult, b: ParseResult) -> bool:
    """Return True if all non-essential fields match."""
    for field in _NON_ESSENTIAL_FIELDS:
        val_a = getattr(a, field) or ""
        val_b = getattr(b, field) or ""
        if val_a != val_b:
            return False
    return True


class Deduplicator:
    """Deterministic deduplication of parsed proxy configurations.

    Processing order is preserved. First occurrence survives.
    All three mechanisms (exact, endpoint, fuzzy) are evaluated
    for each item against previously seen survivors.
    """

    def deduplicate(self, items: list[ParseResult]) -> list[DedupResult]:
        """Deduplicate a list of parsed configs.

        Returns one DedupResult per input item, preserving order.
        """
        # Maps for O(1) lookups of seen items
        seen_by_hash: dict[str, int] = {}  # content_hash -> index of first survivor
        seen_by_endpoint: dict[EndpointIdentity, int] = {}  # endpoint -> index
        seen_items: list[ParseResult] = []  # all survivors in order

        results: list[DedupResult] = []

        for _idx, item in enumerate(items):
            h = compute_content_hash(item)
            ep = endpoint_identity(item)

            # 1. Exact match check
            if h in seen_by_hash:
                orig_idx = seen_by_hash[h]
                orig_item = seen_items[orig_idx]
                # Same hash but non-essential fields differ -> FUZZY
                if not _non_essential_equal(item, orig_item):
                    results.append(DedupResult(
                        content_hash=h,
                        endpoint=ep,
                        match_type=DedupMatchType.FUZZY,
                        match_index=orig_idx,
                        match_reason="Near-duplicate (non-essential field differences)",
                    ))
                else:
                    results.append(DedupResult(
                        content_hash=h,
                        endpoint=ep,
                        match_type=DedupMatchType.EXACT,
                        match_index=orig_idx,
                        match_reason="Exact duplicate (identical content hash)",
                    ))
                continue

            # 2. Endpoint match check
            if ep in seen_by_endpoint:
                orig_idx = seen_by_endpoint[ep]
                results.append(DedupResult(
                    content_hash=h,
                    endpoint=ep,
                    match_type=DedupMatchType.ENDPOINT,
                    match_index=orig_idx,
                    match_reason="Same endpoint, different configuration",
                ))
                # Register as survivor: hash for exact matching, item for fuzzy.
                # Do NOT overwrite seen_by_endpoint — first occurrence stays.
                new_idx = len(seen_items)
                seen_items.append(item)
                seen_by_hash[h] = new_idx
                continue

            # 3. Fuzzy match check against all seen items
            fuzzy_matched = False
            fuzzy_orig_idx = None
            for si, seen_item in enumerate(seen_items):
                if fuzzy_match(item, seen_item):
                    fuzzy_orig_idx = si
                    fuzzy_matched = True
                    break

            if fuzzy_matched and fuzzy_orig_idx is not None:
                results.append(DedupResult(
                    content_hash=h,
                    endpoint=ep,
                    match_type=DedupMatchType.FUZZY,
                    match_index=fuzzy_orig_idx,
                    match_reason="Near-duplicate (non-essential field differences)",
                ))
            else:
                results.append(DedupResult(
                    content_hash=h,
                    endpoint=ep,
                    match_type=DedupMatchType.NONE,
                    match_index=None,
                    match_reason=None,
                ))

            # Register as survivor
            new_idx = len(seen_items)
            seen_items.append(item)
            seen_by_hash[h] = new_idx
            seen_by_endpoint[ep] = new_idx

        return results
