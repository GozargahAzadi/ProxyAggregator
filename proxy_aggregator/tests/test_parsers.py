"""Tests for parsers module — protocol detection, parsing, dedup keys."""
from __future__ import annotations

import base64
import json
import pytest

from proxy_aggregator.models import Protocol
from proxy_aggregator.parsers import (
    detect_protocol,
    is_dummy_config,
    try_base64_decode,
    extract_valid_lines,
    compute_fingerprint,
    parse_config,
)


# ── Protocol detection ───────────────────────────────────────────────────────

class TestDetectProtocol:
    def test_vless(self):
        assert detect_protocol("vless://uuid@host:443?encryption=none") == Protocol.VLESS

    def test_vmess(self):
        assert detect_protocol("vmess://base64payload") == Protocol.VMESS

    def test_trojan(self):
        assert detect_protocol("trojan://password@host:443") == Protocol.TROJAN

    def test_shadowsocks(self):
        assert detect_protocol("ss://method:pass@host:port") == Protocol.SHADOWSOCKS

    def test_hysteria2(self):
        assert detect_protocol("hysteria2://token@host:443") == Protocol.HYSTERIA2

    def test_socks(self):
        assert detect_protocol("socks://user:pass@host:1080") == Protocol.SOCKS

    def test_http_not_proxy(self):
        assert detect_protocol("https://example.com/config") == Protocol.UNKNOWN

    def test_empty(self):
        assert detect_protocol("") == Protocol.UNKNOWN

    def test_no_scheme(self):
        assert detect_protocol("just-a-hostname") == Protocol.UNKNOWN


# ── Dummy config detection ───────────────────────────────────────────────────

class TestIsDummyConfig:
    def test_real_config_not_dummy(self):
        assert not is_dummy_config("vless://abc123@1.2.3.4:443")

    def test_example_com_is_dummy(self):
        assert is_dummy_config("vless://user@example.com:443")

    def test_app_not_supported_is_dummy(self):
        assert is_dummy_config("vmess://xxx#App%20not%20supported")

    def test_too_short_is_dummy(self):
        assert is_dummy_config("vless://x")

    def test_replace_me_is_dummy(self):
        assert is_dummy_config("trojan://xxx#Replace Me")


# ── Base64 decoding ─────────────────────────────────────────────────────────

class TestTryBase64Decode:
    def test_plain_text_unchanged(self):
        text = "vless://abc@host:443"
        assert try_base64_decode(text) == text

    def test_base64_decoded(self):
        # Base64 of "vless://decoded@host:443"
        original = "vless://decoded@host:443"
        encoded = base64.b64encode(original.encode()).decode()
        assert try_base64_decode(encoded) == original

    def test_wrapped_base64(self):
        original = "vless://a@host:443\nvmess://b@host2:443"
        # Encode with newlines embedded
        wrapped = base64.b64encode(original.encode()).decode()
        wrapped = wrapped[:20] + "\n" + wrapped[20:]
        result = try_base64_decode(wrapped)
        assert result == original

    def test_invalid_base64_unchanged(self):
        assert try_base64_decode("!!!not-base64!!!") == "!!!not-base64!!!"


# ── Line extraction ──────────────────────────────────────────────────────────

class TestExtractValidLines:
    def test_skips_comments(self):
        # Use newline-separated lines without base64 wrapping
        text = "# This is a comment\n\nvless://abc@host:443"
        lines = extract_valid_lines(text)
        assert lines == ["vless://abc@host:443"]

    def test_skips_blank_lines(self):
        text = "\n\nvless://abc@host:443\n\n"
        lines = extract_valid_lines(text)
        assert lines == ["vless://abc@host:443"]

    def test_skips_http_urls(self):
        text = "https://example.com\nvless://abc@host:443"
        lines = extract_valid_lines(text)
        assert lines == ["vless://abc@host:443"]

    def test_basic_configs_preserved(self):
        text = "vless://a@h1:1\ntrojan://b@h2:2\n"
        lines = extract_valid_lines(text)
        assert len(lines) == 2
        assert "vless://a@h1:1" in lines
        assert "trojan://b@h2:2" in lines

    def test_base64_blob_decoded(self):
        # A base64 blob containing two proxy configs
        original = "vless://a@h1:443\ntrojan://b@h2:443"
        encoded = base64.b64encode(original.encode()).decode()
        lines = extract_valid_lines(encoded)
        assert len(lines) == 2


# ── Fingerprint ──────────────────────────────────────────────────────────────

class TestComputeFingerprint:
    def test_same_endpoint_same_fingerprint(self):
        links = [
            "vless://uuid@1.2.3.4:443?security=tls",
            "vless://uuid@1.2.3.4:443?security=none",
        ]
        fp1 = compute_fingerprint(links[0])
        fp2 = compute_fingerprint(links[1])
        # Same host/port → same fingerprint (CDN-aware dedup)
        assert fp1 == fp2

    def test_different_port_different_fingerprint(self):
        links = [
            "vless://uuid@1.2.3.4:443",
            "vless://uuid@1.2.3.4:8443",
        ]
        assert compute_fingerprint(links[0]) != compute_fingerprint(links[1])

    def test_deterministic(self):
        link = "vless://abc@host:443"
        assert compute_fingerprint(link) == compute_fingerprint(link)


# ── Full parse ───────────────────────────────────────────────────────────────

class TestParseConfig:
    def test_valid_vless(self):
        cfg = parse_config("vless://abc123@1.2.3.4:443")
        assert cfg is not None
        assert cfg.protocol == Protocol.VLESS
        assert cfg.fingerprint  # non-empty

    def test_invalid_returns_none(self):
        assert parse_config("not-a-url") is None

    def test_dummy_returns_none(self):
        assert parse_config("vless://user@example.com:443") is None

    def test_empty_returns_none(self):
        assert parse_config("") is None

    def test_vmess_with_remark(self):
        # VMess format: vmess://base64json where remark is in fragment
        payload = json.dumps({"ps": "My Server", "add": "1.2.3.4", "port": "443",
                              "id": "uuid", "aid": "0", "scy": "auto",
                              "net": "tcp", "type": "none", "host": "", "path": "",
                              "tls": "", "sni": "", "alpn": "", "fp": ""})
        b64 = base64.b64encode(payload.encode()).decode()
        link = f"vmess://{b64}#My%20Server"
        cfg = parse_config(link)
        assert cfg is not None
        assert cfg.remark == "My Server"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
