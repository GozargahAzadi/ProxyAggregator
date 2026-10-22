"""Tests for exporters — file format correctness."""
from __future__ import annotations

import base64
import json
import os
import tempfile
import pytest
from proxy_aggregator.models import ConfigItem, Protocol
from proxy_aggregator.exporters import (
    write_txt, write_base64_txt, write_json_index,
    write_health_json, write_state_json, write_top100,
)


class TestWriteTxt:
    def test_writes_lines(self):
        cfgs = [ConfigItem(link="vless://a@h1:443", protocol=Protocol.VLESS,
                           fingerprint="f1"),
                ConfigItem(link="trojan://b@h2:443", protocol=Protocol.TROJAN,
                           fingerprint="f2")]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "configs.txt")
            write_txt(path, cfgs)
            with open(path, encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            assert len(lines) == 2
            assert "vless://a@h1:443" in lines
            assert "trojan://b@h2:443" in lines

    def test_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "empty.txt")
            write_txt(path, [])
            with open(path, encoding="utf-8") as f:
                content = f.read()
            assert content == ""


class TestWriteBase64Txt:
    def test_encodes_content(self):
        cfgs = [ConfigItem(link="vless://a@h:443", protocol=Protocol.VLESS,
                           fingerprint="f")]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub.txt")
            write_base64_txt(path, cfgs)
            with open(path, encoding="ascii") as f:
                encoded = f.read().strip()
            decoded = base64.b64decode(encoded).decode("utf-8")
            assert "vless://a@h:443" in decoded
            assert "#profile-title" in decoded  # Hiddify header present

    def test_multiple_configs(self):
        cfgs = [
            ConfigItem(link="vless://a@h1:443", protocol=Protocol.VLESS,
                       fingerprint="f1"),
            ConfigItem(link="vless://b@h2:443", protocol=Protocol.VLESS,
                       fingerprint="f2"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub.txt")
            write_base64_txt(path, cfgs)
            with open(path, encoding="ascii") as f:
                encoded = f.read().strip()
            decoded = base64.b64decode(encoded).decode("utf-8")
            assert "vless://a@h1:443" in decoded
            assert "vless://b@h2:443" in decoded


class TestWriteJsonIndex:
    def test_creates_valid_json(self):
        cfgs = [ConfigItem(link="vless://a@h:443", protocol=Protocol.VLESS,
                           fingerprint="f")]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "index.json")
            write_json_index(path, {"sources_ok": 2},
                             {"all": cfgs, "verified": []},
                             {"vless": 1},
                             {"updated_at": "2026-01-01", "updated_at_unix": 0})
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            assert "categories" in data
            assert "protocols" in data
            assert data["protocols"]["vless"] == 1

    def test_empty_categories_not_included(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "index.json")
            write_json_index(path, {}, {}, {}, {"updated_at": "now"})
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # Empty categories should be omitted
            assert data.get("categories", {}) == {}


class TestWriteHealthJson:
    def test_writes_valid_json(self):
        data = {"run": {"total_configs": 100}, "cascade": {"layers": {}}}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "health.json")
            write_health_json(path, data)
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            assert loaded["run"]["total_configs"] == 100


class TestWriteStateJson:
    def test_writes_valid_json(self):
        data = {"last_run": "2026-01-01T00:00:00Z", "total_unique": 50}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "state.json")
            write_state_json(path, data)
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            assert loaded["total_unique"] == 50


class TestWriteTop100:
    def test_writes_lines(self):
        cfgs = [ConfigItem(link=f"vless://a{i}@h:443", protocol=Protocol.VLESS,
                           fingerprint=f"f{i}")
                for i in range(5)]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "top100.txt")
            write_top100(path, cfgs)
            with open(path, encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            assert len(lines) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
