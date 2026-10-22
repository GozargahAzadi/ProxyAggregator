"""Tests for ranking module."""
from __future__ import annotations

import pytest
from proxy_aggregator.models import ConfigItem, Protocol
from proxy_aggregator.ranking import rank_by_latency, compute_statistics


class TestRankByLatency:
    def test_sorts_by_latency(self):
        cfgs = [
            ConfigItem(link="vless://slow@h:443", protocol=Protocol.VLESS,
                       fingerprint="slow", median_latency_ms=500.0),
            ConfigItem(link="vless://fast@h:443", protocol=Protocol.VLESS,
                       fingerprint="fast", median_latency_ms=100.0),
            ConfigItem(link="vless://mid@h:443", protocol=Protocol.VLESS,
                       fingerprint="mid", median_latency_ms=250.0),
        ]
        result = rank_by_latency(cfgs, top_n=2)
        assert result[0].link == "vless://fast@h:443"
        assert result[1].link == "vless://mid@h:443"

    def test_excludes_no_latency(self):
        cfgs = [
            ConfigItem(link="vless://no-latency@h:443", protocol=Protocol.VLESS,
                       fingerprint="nl"),  # No median_latency_ms
            ConfigItem(link="vless://has-latency@h:443", protocol=Protocol.VLESS,
                       fingerprint="hl", median_latency_ms=100.0),
        ]
        result = rank_by_latency(cfgs, top_n=10)
        assert len(result) == 1
        assert result[0].link == "vless://has-latency@h:443"

    def test_respects_top_n(self):
        cfgs = [ConfigItem(link=f"vless://c{i}@h:443", protocol=Protocol.VLESS,
                           fingerprint=f"f{i}", median_latency_ms=float(i))
                for i in range(10)]
        result = rank_by_latency(cfgs, top_n=3)
        assert len(result) == 3
        # Should be sorted: 0, 1, 2
        assert result[0].median_latency_ms == 0.0
        assert result[2].median_latency_ms == 2.0

    def test_empty_input(self):
        assert rank_by_latency([], top_n=100) == []


class TestComputeStatistics:
    def test_empty(self):
        stats = compute_statistics([])
        assert stats["count"] == 0
        assert stats["min"] is None
        assert stats["median"] is None

    def test_single_value(self):
        cfgs = [ConfigItem(link="x", protocol=Protocol.VLESS, fingerprint="f",
                           median_latency_ms=42.0)]
        stats = compute_statistics(cfgs)
        assert stats["count"] == 1
        assert stats["min"] == 42.0
        assert stats["median"] == 42.0
        assert stats["max"] == 42.0

    def test_multiple_values(self):
        cfgs = [
            ConfigItem(link="a", protocol=Protocol.VLESS, fingerprint="fa",
                       median_latency_ms=100.0),
            ConfigItem(link="b", protocol=Protocol.VLESS, fingerprint="fb",
                       median_latency_ms=200.0),
            ConfigItem(link="c", protocol=Protocol.VLESS, fingerprint="fc",
                       median_latency_ms=300.0),
        ]
        stats = compute_statistics(cfgs)
        assert stats["count"] == 3
        assert stats["min"] == 100.0
        assert stats["median"] == 200.0
        assert stats["max"] == 300.0

    def test_skips_none(self):
        cfgs = [
            ConfigItem(link="a", protocol=Protocol.VLESS, fingerprint="fa",
                       median_latency_ms=100.0),
            ConfigItem(link="b", protocol=Protocol.VLESS, fingerprint="fb"),  # No latency
        ]
        stats = compute_statistics(cfgs)
        assert stats["count"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
