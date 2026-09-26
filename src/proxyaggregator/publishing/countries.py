"""Deterministic per-country subscription directories (Phase 17).

Pure orchestration that groups Phase 7 ranked, eligible candidates into
``output/countries/{CC}/`` directories:

- one generated index README (``countries/README.md``) listing every country
  directory that actually contains proxies this run, deterministically
  ordered by ISO code;
- per non-empty directory: ``README.md``, an all-protocol plain + base64 feed
  (``all.txt`` / ``all-base64.txt``), and a plain + base64 feed per protocol
  only when that protocol has candidates. Empty countries or empty protocols
  never produce artifacts.

The generated READMEs are GitHub-facing: the index is a Markdown table
(sorted by ISO code) whose rows link relative-directory links ``./{CC}/``
plus copyable raw subscription URLs from
:data:`COUNTRY_RAW_SUBSCRIPTIONS_BASE_URL`. Nothing above is hard-coded from
live countries — every entry is derived from the actual country buckets.

A single global selection (dedup by ``content_hash``, then the ``max_items``
cap) is applied exactly once and serialization is cached per unique proxy, so
the combined, protocol, and country feeds from the same inputs are mutually
consistent. No network I/O, DNS, health checks, time, or random values are
involved; given identical inputs the artifacts are byte-for-byte identical.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from proxyaggregator.publishing.feeds import (
    _plain_feed,
    _select,
    _serialize,
    _validate_max_items,
)
from proxyaggregator.publishing.models import Subscription, SubscriptionFormat
from proxyaggregator.publishing.naming import (
    country_bucket,
    country_code_to_flag,
    country_code_to_name,
)
from proxyaggregator.publishing.publisher import (
    DEFAULT_PROTOCOL_FILENAME_STEMS,
    country_all_path,
    country_index_path,
    country_protocol_path,
    country_readme_path,
)
from proxyaggregator.publishing.serializer import SUPPORTED_PROTOCOLS

if TYPE_CHECKING:
    from collections.abc import Sequence

    from proxyaggregator.publishing.models import RankedProxy

#: README files carry content but no proxies, so they are emitted as plain
#: artifacts with ``count=0`` (matching their manifest representation).
_COUNTRY_README_FORMAT = SubscriptionFormat.PLAIN
_COUNTRY_README_COUNT = 0

#: Protocol label map used in the country README's ``## 🔌 Protocols`` table.
#: Keys are canonical serializer protocol ids; the on-disk stems come from the
#: publisher's ``DEFAULT_PROTOCOL_FILENAME_STEMS``.
_COUNTRY_PROTOCOL_DISPLAY: dict[str, str] = {
    "vless": "VLESS",
    "vmess": "VMess",
    "trojan": "Trojan",
    "ss": "Shadowsocks",
    "hysteria": "Hysteria",
    "hysteria2": "Hysteria2",
    "socks4": "Socks4",
    "socks5": "Socks5",
    "http": "HTTP",
    "https": "HTTPS",
}

_INDEX_HEADING = "# 🌍 ProxyAggregator — Proxies by Country"

#: Base URL for copyable raw subscription links in the country READMEs
#: (the generated country index lives at ``countries/README.md`` next to
#: ``countries/{CC}/`` on the ``main`` branch).
COUNTRY_RAW_SUBSCRIPTIONS_BASE_URL = (
    "https://raw.githubusercontent.com/GozargahAzadi/ProxyAggregator/main/output/"
)


def _doc(content: str) -> Subscription:
    """Wrap generated markdown as a count-zero plain feed."""
    return Subscription(format=_COUNTRY_README_FORMAT, content=content, count=_COUNTRY_README_COUNT)


def _proxy_or_proxies(count: int) -> str:
    return "proxy" if count == 1 else "proxies"


def _raw_subscription_url(code: str, *parts: str) -> str:
    """Join the raw base URL with a country-directory artifact path."""
    return f"{COUNTRY_RAW_SUBSCRIPTIONS_BASE_URL}countries/{code}/{'/'.join(parts)}"


def _country_readme(bucket: str, count: int, protocols: Sequence[str]) -> Subscription:
    """Generate the deterministic ``countries/{CC}/README.md`` content.

    The page shows the flag + English country name, the healthy-proxy count,
    the all-protocol feeds, and a ``## 🔌 Protocols`` table containing only the
    protocols that actually produced files this run. Every subscription link is
    a copyable raw URL wrapped in a Markdown code span.
    """
    code = bucket.upper()
    flag = country_code_to_flag(bucket)
    name = country_code_to_name(bucket)
    lines = [
        f"# {flag} {name}",
        "",
        f"{count} healthy {_proxy_or_proxies(count)}.",
        "",
        "## 📋 All Protocols",
        "",
        "| Format | GitHub | Raw subscription |",
        "|---|---|---|",
        f"| Plain | [Open](./all.txt) | `{_raw_subscription_url(code, 'all.txt')}` |",
        f"| Base64 | [Open](./all-base64.txt) | `{_raw_subscription_url(code, 'all-base64.txt')}` |",
    ]
    if protocols:
        lines += [
            "",
            "## 🔌 Protocols",
            "",
            "| Protocol | GitHub | Raw |",
            "|---|---|---|",
        ]
        for protocol in protocols:
            stem = DEFAULT_PROTOCOL_FILENAME_STEMS[protocol]
            display = _COUNTRY_PROTOCOL_DISPLAY[protocol]
            lines.append(
                f"| {display} | [Open](./{stem}.txt) | "
                f"`{_raw_subscription_url(code, stem + '.txt')}` |"
            )
            lines.append(
                f"| {display} Base64 | [Open](./{stem}-base64.txt) | "
                f"`{_raw_subscription_url(code, stem + '-base64.txt')}` |"
            )
    return _doc("\n".join(lines) + "\n")


def _index_readme(entries: Sequence[tuple[str, int]]) -> Subscription:
    """Generate the deterministic ``countries/README.md`` country index.

    A Markdown table with one row per non-empty country bucket: a clickable
    flag + name (relative link ``./{CC}/``), the ISO alpha-2 code, the healthy
    proxy count, and an open-directory link. Rows are ordered by ISO code; the
    live country list is never hard-coded.
    """
    lines = [
        _INDEX_HEADING,
        "",
        "Click a country to open its subscriptions.",
        "",
        "| Country | Code | Proxies | Links |",
        "| --- | --- | ---: | --- |",
    ]
    for bucket, count in entries:
        code = bucket.upper()
        flag = country_code_to_flag(bucket)
        name = country_code_to_name(bucket)
        lines.append(
            f"| [{flag} {name}](./{code}/) | {code} | {count} | [Open {flag}](./{code}/) |"
        )
    return _doc("\n".join(lines) + "\n")


def build_country_artifacts(
    candidates: Sequence[RankedProxy],
    *,
    max_items: int | None = None,
) -> tuple[tuple[str, Subscription], ...]:
    """Generate deterministic ``(artifact_path, feed)`` pairs for countries.

    A single global selection is applied (dedup by ``content_hash``, then the
    ``max_items`` cap) before grouping by the normalized lowercase country
    bucket, so every selected proxy lands in exactly one country directory (in
    addition to the combined and its protocol feed). Rank order is preserved
    within each group. The returned sequence places the generated index README
    first, then one directory per non-empty bucket in ISO-code order; within a
    directory the all-protocol plain/base64 feeds come first, then each
    non-empty protocol's feeds, then the directory README.

    Country codes are taken purely from ``RankedProxy.country_code``; no
    GeoIP, DNS, health checks, or network I/O happens here. Unknown/invalid
    codes group under the ``XX`` bucket.

    Raises:
        ValueError: ``max_items`` is not a positive integer or ``None``.
        SubscriptionError: a candidate cannot be serialized deterministically.
    """
    _validate_max_items(max_items)
    selected = _select(candidates, max_items)

    uri_cache: dict[str, str] = {}
    grouped: dict[str, list[tuple[str, int, str]]] = {}
    protocol_counts: dict[str, dict[str, int]] = {}

    for candidate in selected:
        if candidate.content_hash not in uri_cache:
            uri_cache[candidate.content_hash] = _serialize(candidate)
        bucket = country_bucket(candidate.country_code)
        grouped.setdefault(bucket, []).append(
            (candidate.content_hash, candidate.protocol, uri_cache[candidate.content_hash])
        )
        per_protocol = protocol_counts.setdefault(bucket, {})
        per_protocol[candidate.protocol] = per_protocol.get(candidate.protocol, 0) + 1

    artifacts: list[tuple[str, Subscription]] = []
    index_entries: list[tuple[str, int]] = []
    for bucket in sorted(grouped):
        group = grouped[bucket]
        count = len(group)
        index_entries.append((bucket, count))

        plain_all = _plain_feed([_uri for _hash, _protocol, _uri in group])
        encoded_all = base64.b64encode(plain_all.encode("utf-8")).decode("ascii")
        artifacts.append(
            (
                country_all_path(bucket, SubscriptionFormat.PLAIN),
                Subscription(format=SubscriptionFormat.PLAIN, content=plain_all, count=count),
            )
        )
        artifacts.append(
            (
                country_all_path(bucket, SubscriptionFormat.BASE64),
                Subscription(format=SubscriptionFormat.BASE64, content=encoded_all, count=count),
            )
        )

        protocols = [
            protocol
            for protocol in SUPPORTED_PROTOCOLS
            if protocol_counts[bucket].get(protocol, 0) > 0
        ]
        for protocol in protocols:
            uris = [_uri for _hash, _protocol, _uri in group if _protocol == protocol]
            plain = _plain_feed(uris)
            encoded = base64.b64encode(plain.encode("utf-8")).decode("ascii")
            artifacts.append(
                (
                    country_protocol_path(protocol, bucket, SubscriptionFormat.PLAIN),
                    Subscription(format=SubscriptionFormat.PLAIN, content=plain, count=len(uris)),
                )
            )
            artifacts.append(
                (
                    country_protocol_path(protocol, bucket, SubscriptionFormat.BASE64),
                    Subscription(
                        format=SubscriptionFormat.BASE64, content=encoded, count=len(uris)
                    ),
                )
            )
        artifacts.append((country_readme_path(bucket), _country_readme(bucket, count, protocols)))

    artifacts.insert(0, (country_index_path(), _index_readme(index_entries)))
    return tuple(artifacts)
