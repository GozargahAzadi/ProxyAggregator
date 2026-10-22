"""Tests for data models."""
from __future__ import annotations

import pytest
from proxy_aggregator.models import ConfigItem, Protocol, SourceResult, RunSummary


class TestConfigItem:
    def test_frozen(self):
        cfg = ConfigItem(link="vless://a@h:443", protocol=Protocol.VLESS,
                         fingerprint="abc")
        with pytest.raises(AttributeError):
            cfg.link = "new"

    def test_can_modify_via_object_setattr(self):
        cfg = ConfigItem(link="x", protocol=Protocol.VLESS, fingerprint="f")
        object.__setattr__(cfg, "verified_rounds", 3)
        object.__setattr__(cfg, "total_rounds", 3)
        object.__setattr__(cfg, "median_latency_ms", 50.0)
        assert cfg.verified_rounds == 3
        assert cfg.is_verified
        assert cfg.is_fast

    def test_equality_by_fingerprint(self):
        cfg1 = ConfigItem(link="vless://a@h:443", protocol=Protocol.VLESS,
                          fingerprint="same-fp")
        cfg2 = ConfigItem(link="vless://different-link", protocol=Protocol.VLESS,
                          fingerprint="same-fp")
        assert cfg1 == cfg2

    def test_ordering(self):
        cfg1 = ConfigItem(link="a", protocol=Protocol.VLESS, fingerprint="b")
        cfg2 = ConfigItem(link="b", protocol=Protocol.VLESS, fingerprint="a")
        assert cfg1 < cfg2 or cfg1 > cfg2  # just check it doesn't crash

    def test_is_verified_false_by_default(self):
        cfg = ConfigItem(link="x", protocol=Protocol.VLESS, fingerprint="f")
        assert not cfg.is_verified

    def test_is_verified_true_when_all_rounds_pass(self):
        cfg = ConfigItem(link="x", protocol=Protocol.VLESS, fingerprint="f",
                         verified_rounds=3, total_rounds=3)
        assert cfg.is_verified

    def test_is_verified_false_when_partial(self):
        cfg = ConfigItem(link="x", protocol=Protocol.VLESS, fingerprint="f",
                         verified_rounds=2, total_rounds=3)
        assert not cfg.is_verified

    def test_is_fast_requires_verified(self):
        cfg = ConfigItem(link="x", protocol=Protocol.VLESS, fingerprint="f",
                         median_latency_ms=50.0)
        assert not cfg.is_fast  # not verified

    def test_is_fast_when_verified_and_low_latency(self):
        cfg = ConfigItem(link="x", protocol=Protocol.VLESS, fingerprint="f",
                         verified_rounds=3, total_rounds=3, median_latency_ms=50.0)
        assert cfg.is_fast

    def test_category_tags(self):
        cfg = ConfigItem(link="x", protocol=Protocol.VLESS, fingerprint="f")
        assert cfg.category_tags == ["all"]

    def test_category_tags_with_verification(self):
        cfg = ConfigItem(link="x", protocol=Protocol.VLESS, fingerprint="f",
                         verified_rounds=3, total_rounds=3, median_latency_ms=50.0,
                         secure=True)
        tags = cfg.category_tags
        assert "all" in tags
        assert "verified" in tags
        assert "fast" in tags
        assert "secure" in tags


class TestSourceResult:
    def test_defaults(self):
        sr = SourceResult(url="https://example.com", status="ok")
        assert sr.status == "ok"
        assert sr.config_count == 0
        assert sr.error is None

    def test_failure(self):
        sr = SourceResult(url="https://example.com", status="fail",
                          error="network timeout")
        assert sr.status == "fail"


class TestRunSummary:
    def test_to_dict(self):
        s = RunSummary(total_configs=100, unique_configs=80)
        d = s.to_dict()
        assert d["total_configs"] == 100
        assert d["unique_configs"] == 80

    def test_default_values(self):
        s = RunSummary()
        assert s.elapsed_sec == 0.0
        assert s.sources == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
