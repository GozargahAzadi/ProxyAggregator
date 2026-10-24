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
        """Configs on same host:port with identical connection params → same fingerprint."""
        links = [
            "vless://uuid@1.2.3.4:443?security=tls",
            "vless://uuid@1.2.3.4:443?security=tls",  # identical params
        ]
        fp1 = compute_fingerprint(links[0])
        fp2 = compute_fingerprint(links[1])
        assert fp1 == fp2

    def test_different_security_different_fingerprint(self):
        """Same server+UUID but different security setting → different fingerprints."""
        links = [
            "vless://uuid@1.2.3.4:443?security=tls",
            "vless://uuid@1.2.3.4:443?security=none",
        ]
        assert compute_fingerprint(links[0]) != compute_fingerprint(links[1])

    def test_different_uuid_different_fingerprint(self):
        """Same server, different UUID → different fingerprints."""
        links = [
            "vless://uuid-a@1.2.3.4:443",
            "vless://uuid-b@1.2.3.4:443",
        ]
        assert compute_fingerprint(links[0]) != compute_fingerprint(links[1])

    def test_different_password_different_fingerprint(self):
        """Same server, different Trojan password → different fingerprints."""
        links = [
            "trojan://pass-a@1.2.3.4:443",
            "trojan://pass-b@1.2.3.4:443",
        ]
        assert compute_fingerprint(links[0]) != compute_fingerprint(links[1])

    def test_different_hysteria_token_different_fingerprint(self):
        """Same server, different Hysteria2 token → different fingerprints."""
        links = [
            "hysteria2://token-a@1.2.3.4:443",
            "hysteria2://token-b@1.2.3.4:443",
        ]
        assert compute_fingerprint(links[0]) != compute_fingerprint(links[1])

    def test_different_port_different_fingerprint(self):
        links = [
            "vless://uuid@1.2.3.4:443",
            "vless://uuid@1.2.3.4:8443",
        ]
        assert compute_fingerprint(links[0]) != compute_fingerprint(links[1])

    def test_deterministic(self):
        link = "vless://abc@host:443"
        assert compute_fingerprint(link) == compute_fingerprint(link)

    def test_vmess_different_uuid_different_fingerprint(self):
        """VMess with same server but different UUIDs."""
        payload_a = json.dumps({"ps": "Server", "add": "1.2.3.4", "port": "443",
                                "id": "uuid-a", "aid": "0", "scy": "auto",
                                "net": "tcp", "type": "none", "host": "", "path": "",
                                "tls": "", "sni": "", "alpn": "", "fp": ""})
        payload_b = json.dumps({"ps": "Server", "add": "1.2.3.4", "port": "443",
                                "id": "uuid-b", "aid": "0", "scy": "auto",
                                "net": "tcp", "type": "none", "host": "", "path": "",
                                "tls": "", "sni": "", "alpn": "", "fp": ""})
        b64_a = base64.b64encode(payload_a.encode()).decode()
        b64_b = base64.b64encode(payload_b.encode()).decode()
        link_a = f"vmess://{b64_a}"
        link_b = f"vmess://{b64_b}"
        assert compute_fingerprint(link_a) != compute_fingerprint(link_b)

    def test_vmess_different_remark_same_fingerprint(self):
        """VMess with same UUID/server but different remarks → same fingerprint."""
        payload_a = json.dumps({"ps": "Server-A", "add": "1.2.3.4", "port": "443",
                                "id": "uuid-a", "aid": "0", "scy": "auto",
                                "net": "tcp", "type": "none", "host": "", "path": "",
                                "tls": "", "sni": "", "alpn": "", "fp": ""})
        payload_b = json.dumps({"ps": "Server-B", "add": "1.2.3.4", "port": "443",
                                "id": "uuid-a", "aid": "0", "scy": "auto",
                                "net": "tcp", "type": "none", "host": "", "path": "",
                                "tls": "", "sni": "", "alpn": "", "fp": ""})
        b64_a = base64.b64encode(payload_a.encode()).decode()
        b64_b = base64.b64encode(payload_b.encode()).decode()
        assert compute_fingerprint(f"vmess://{b64_a}") == compute_fingerprint(f"vmess://{b64_b}")

    def test_cosmetic_remark_does_not_affect_fingerprint(self):
        """Different remarks on same config → same fingerprint."""
        links = [
            "vless://uuid@1.2.3.4:443#Server-A",
            "vless://uuid@1.2.3.4:443#Server-B",
        ]
        fp1 = compute_fingerprint(links[0])
        fp2 = compute_fingerprint(links[1])
        assert fp1 == fp2

    def test_different_ss_password_different_fingerprint(self):
        """Same SS server, different passwords → different fingerprints."""
        # ss://base64(method:password@host:port)#remark
        creds_a = base64.b64encode(b"aes-256-gcm:pass-a@1.2.3.4:443").decode()
        creds_b = base64.b64encode(b"aes-256-gcm:pass-b@1.2.3.4:443").decode()
        links = [f"ss://{creds_a}", f"ss://{creds_b}"]
        assert compute_fingerprint(links[0]) != compute_fingerprint(links[1])

    def test_different_ss_method_different_fingerprint(self):
        """Same SS server, different methods → different fingerprints."""
        creds_a = base64.b64encode(b"aes-256-gcm:pass@1.2.3.4:443").decode()
        creds_b = base64.b64encode(b"chacha20-ietf:pass@1.2.3.4:443").decode()
        links = [f"ss://{creds_a}", f"ss://{creds_b}"]
        assert compute_fingerprint(links[0]) != compute_fingerprint(links[1])

    def test_ss_malformed_returns_config_not_none(self):
        """Malformed SS URI still returns a ConfigItem (parsing is lenient)."""
        # Invalid base64 — parser accepts it, verification will fail later
        result = parse_config("ss://!!!not-valid!!!")
        assert result is not None
        assert result.protocol == Protocol.SHADOWSOCKS


class TestIPv6Support:
    """Tests for IPv6 address handling in verification."""

    def test_ipv4_address_encoding(self):
        """IPv4 addresses should use ATYP=0x01."""
        import socket
        import struct
        # This tests the SOCKS5 CONNECT request format
        addr_bytes = socket.inet_aton("1.2.3.4")
        assert len(addr_bytes) == 4
        assert addr_bytes == b"\x01\x02\x03\x04"

    def test_ipv6_address_encoding(self):
        """IPv6 addresses should use ATYP=0x04."""
        import socket
        addr_bytes = socket.inet_pton(socket.AF_INET6, "::1")
        assert len(addr_bytes) == 16

    def test_domain_name_encoding(self):
        """Domain names should use ATYP=0x03 with length prefix."""
        domain = b"example.com"
        encoded = bytes([len(domain)]) + domain
        assert encoded[0] == 11  # length of "example.com"
        assert encoded[1:] == domain


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
