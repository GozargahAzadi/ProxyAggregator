"""Deterministic subscription feed generation (Phase 8).

Pure orchestration that:

1. consumes Phase 7 ranked, eligible candidates in authoritative order,
2. deduplicates at the output boundary using the existing canonical identity
   (``content_hash``), keeping the first (best-ranked) occurrence,
3. limits to the first N unique candidates when ``max_items`` is given,
4. re-parses each candidate's persisted ``raw_uri`` with the Phase 3 parser
   and cross-checks it against the persisted identity fields,
5. serializes each proxy to a canonical URI and joins it into a feed.

No network I/O, DNS, health checks, time, or random values are involved.
Given identical inputs the output is byte-for-byte identical.
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

from proxyaggregator.parsers.base import ParseError
from proxyaggregator.parsers.registry import get_registry
from proxyaggregator.publishing.errors import SubscriptionError
from proxyaggregator.publishing.models import RankedProxy, Subscription, SubscriptionFormat
from proxyaggregator.publishing.naming import build_remark
from proxyaggregator.publishing.serializer import SUPPORTED_PROTOCOLS, canonical_uri

if TYPE_CHECKING:
    from collections.abc import Sequence

    from proxyaggregator.parsers.base import ParseResult


def _validate_max_items(max_items: int | None) -> None:
    if max_items is None:
        return
    if not isinstance(max_items, int) or isinstance(max_items, bool) or max_items < 1:
        raise ValueError("max_items must be None or a positive integer")


def _select(candidates: Sequence[RankedProxy], max_items: int | None) -> list[RankedProxy]:
    seen: set[str] = set()
    selected: list[RankedProxy] = []
    for candidate in candidates:
        if candidate.content_hash in seen:
            continue
        seen.add(candidate.content_hash)
        selected.append(candidate)
        if max_items is not None and len(selected) >= max_items:
            break
    return selected


def _with_remark(parsed: ParseResult, candidate: RankedProxy) -> ParseResult:
    """Return a copy of ``parsed`` whose fragment is the Phase 10 Remark.

    Every canonical serializer renders the fragment as the node's public name
    (for VMess the fragment is emitted as the ``ps`` field), so swapping it in
    at the serialization boundary stamps every published URI with the
    deterministic Remark from :func:`build_remark`. The persisted ``raw_uri``,
    parsed identity, and ``content_hash`` are never mutated, which keeps dedup
    and scoring authoritative from earlier phases.
    """
    remark = build_remark(candidate.country_code, candidate.protocol, candidate.latency_ms)
    return parsed.model_copy(update={"fragment": remark})


def _serialize(candidate: RankedProxy) -> str:
    parser = get_registry().get(candidate.protocol)
    if parser is None:
        raise SubscriptionError(
            candidate.proxy_config_id, candidate.protocol, "unsupported_protocol"
        )
    parsed = parser.parse(candidate.raw_uri)
    if isinstance(parsed, ParseError):
        raise SubscriptionError(candidate.proxy_config_id, candidate.protocol, "parse_failed")
    if (
        parsed.protocol != candidate.protocol
        or parsed.host != candidate.host
        or parsed.port != candidate.port
    ):
        raise SubscriptionError(candidate.proxy_config_id, candidate.protocol, "identity_mismatch")
    try:
        return canonical_uri(_with_remark(parsed, candidate))
    except ValueError as exc:
        raise SubscriptionError(candidate.proxy_config_id, candidate.protocol, str(exc)) from exc


def _plain_feed(uris: list[str]) -> str:
    if not uris:
        return ""
    return "\n".join(uris) + "\n"


def _json_feed(items: list[dict]) -> str:
    return json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_subscription(
    candidates: Sequence[RankedProxy],
    *,
    format: SubscriptionFormat = SubscriptionFormat.PLAIN,
    max_items: int | None = None,
) -> Subscription:
    """Generate a deterministic subscription feed from ranked candidates.

    Args:
        candidates: Phase 7 ranked, eligible proxies in rank order (best first).
        format: Target feed encoding (plain, base64, or json).
        max_items: Emit at most this many unique proxies; ``None`` emits all.

    Raises:
        ValueError: ``max_items`` is not a positive integer or ``None``.
        SubscriptionError: a candidate cannot be serialized deterministically.
    """
    _validate_max_items(max_items)
    selected = _select(candidates, max_items)
    uris = [_serialize(candidate) for candidate in selected]

    if format is SubscriptionFormat.PLAIN:
        content = _plain_feed(uris)
    elif format is SubscriptionFormat.BASE64:
        content = base64.b64encode(_plain_feed(uris).encode("utf-8")).decode("ascii")
    elif format is SubscriptionFormat.JSON:
        items = [
            {
                "uri": uri,
                "protocol": candidate.protocol,
                "host": candidate.host,
                "port": candidate.port,
                "content_hash": candidate.content_hash,
            }
            for candidate, uri in zip(selected, uris, strict=True)
        ]
        content = _json_feed(items)
    else:
        raise ValueError(f"unsupported subscription format: {format!r}")

    return Subscription(format=format, content=content, count=len(selected))


def build_protocol_subscriptions(
    candidates: Sequence[RankedProxy],
    *,
    max_items: int | None = None,
) -> tuple[tuple[str, Subscription, Subscription], ...]:
    """Generate deterministic plain + base64 feeds per protocol (Phase 9.3).

    A single global selection (dedup by ``content_hash``, then the
    ``max_items`` cap) is applied **before** splitting by protocol, so every
    protocol feed is a subset of the combined feed produced by
    :func:`build_subscription` from the same inputs. Protocols with zero
    selected candidates emit no feed; empty protocol artifacts are never
    created.

    Returns ``(protocol, plain, base64)`` triples in the canonical protocol
    order (:data:`SUPPORTED_PROTOCOLS`).

    Raises:
        ValueError: ``max_items`` is not a positive integer or ``None``.
        SubscriptionError: a candidate cannot be serialized deterministically.
    """
    _validate_max_items(max_items)
    selected = _select(candidates, max_items)

    grouped: dict[str, list[RankedProxy]] = {}
    for candidate in selected:
        grouped.setdefault(candidate.protocol, []).append(candidate)

    feeds: list[tuple[str, Subscription, Subscription]] = []
    for protocol in SUPPORTED_PROTOCOLS:
        group = grouped.get(protocol)
        if not group:
            continue
        plain_content = _plain_feed([_serialize(candidate) for candidate in group])
        plain = Subscription(
            format=SubscriptionFormat.PLAIN, content=plain_content, count=len(group)
        )
        encoded = base64.b64encode(plain_content.encode("utf-8")).decode("ascii")
        feeds.append(
            (
                protocol,
                plain,
                Subscription(format=SubscriptionFormat.BASE64, content=encoded, count=len(group)),
            )
        )
    return tuple(feeds)
