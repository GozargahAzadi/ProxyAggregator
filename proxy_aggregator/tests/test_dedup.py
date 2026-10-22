"""Tests for deduplication — fingerprint-based, preserves differences."""
from __future__ import annotations

import hashlib
import pytest
from proxy_aggregator.models import ConfigItem, Protocol
from proxy_aggregator.dedup import deduplicate, dedup_stats, group_by_protocol, filter_by_categories


def make_cfg(link: str, protocol: Protocol = Protocol.VLESS) -> ConfigItem:
    return ConfigItem(link=link, protocol=protocol, fingerprint=hashlib.md5(link.encode()).hexdigest()[:8])


class TestDeduplicate:
    def test_exact_duplicates_removed(self):
        cfg1 = make_cfg("vless://a@h1:443")
        cfg2 = make_cfg("vless://a@h1:443")  # Same link → same fingerprint
        result = deduplicate([cfg1, cfg2])
        assert len(result) == 1

    def test_different_links_kept(self):
        cfg1 = make_cfg("vless://a@h1:443")
        cfg2 = make_cfg("vless://b@h2:443")
        result = deduplicate([cfg1, cfg2])
        assert len(result) == 2

    def test_order_preserved(self):
        cfgs = [make_cfg(f"vless://c{i}@h:443") for i in range(5)]
        result = deduplicate(cfgs)
        assert [c.link for c in result] == [c.link for c in cfgs]

    def test_empty_input(self):
        assert deduplicate([]) == []


class TestDedupStats:
    def test_counts(self):
        orig = [make_cfg("vless://a@h:443"), make_cfg("vless://a@h:443")]
        deduped = deduplicate(orig)
        stats = dedup_stats(orig, deduped)
        assert stats["original"] == 2
        assert stats["unique"] == 1
        assert stats["duplicates_removed"] == 1


class TestGroupByProtocol:
    def test_groups_configs(self):
        cfgs = [
            make_cfg("vless://a@h:443", Protocol.VLESS),
            make_cfg("trojan://b@h:443", Protocol.TROJAN),
            make_cfg("vless://c@h:443", Protocol.VLESS),
        ]
        groups = group_by_protocol(cfgs)
        assert len(groups["vless"]) == 2
        assert len(groups["trojan"]) == 1

    def test_sorted_within_group(self):
        cfgs = [
            make_cfg("vless://z@h:443"),
            make_cfg("vless://a@h:443"),
        ]
        groups = group_by_protocol(cfgs)
        links = [c.link for c in groups["vless"]]
        assert links == sorted(links)


class TestFilterByCategories:
    def test_all_contains_everything(self):
        cfgs = [make_cfg("vless://a@h:443")]
        buckets = filter_by_categories(cfgs)
        assert len(buckets["all"]) == 1

    def test_verified_empty_without_verification(self):
        cfg = make_cfg("vless://a@h:443")
        buckets = filter_by_categories([cfg])
        assert len(buckets["verified"]) == 0

    def test_verified_populated(self):
        cfg = make_cfg("vless://a@h:443", Protocol.VLESS)
        object.__setattr__(cfg, "verified_rounds", 3)
        object.__setattr__(cfg, "total_rounds", 3)
        buckets = filter_by_categories([cfg])
        assert len(buckets["verified"]) == 1

    def test_fast_requires_verified(self):
        cfg = make_cfg("vless://a@h:443", Protocol.VLESS)
        object.__setattr__(cfg, "median_latency_ms", 100.0)
        buckets = filter_by_categories([cfg])
        assert len(buckets["fast"]) == 0  # not verified

    def test_fast_with_verification(self):
        cfg = make_cfg("vless://a@h:443", Protocol.VLESS)
        object.__setattr__(cfg, "verified_rounds", 3)
        object.__setattr__(cfg, "total_rounds", 3)
        object.__setattr__(cfg, "median_latency_ms", 100.0)
        buckets = filter_by_categories([cfg])
        assert len(buckets["fast"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
