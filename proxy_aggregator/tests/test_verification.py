"""Tests for verification module — mock-based, no live network needed."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from proxy_aggregator.models import ConfigItem, Protocol
from proxy_aggregator.verification import verify_config, run_verification_round


class TestVerifyConfigDirect:
    def _make_cfg(self, scheme="vless", host="127.0.0.1", port=443):
        return ConfigItem(
            link=f"{scheme}://test@{host}:{port}",
            protocol=getattr(Protocol, scheme.upper()),
            fingerprint="test-fp",
        )

    @patch("proxy_aggregator.verification.socket.socket")
    def test_tcp_connect_failure(self, mock_socket_cls):
        """Test when TCP connection fails."""
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = ConnectionRefusedError("refused")
        mock_socket_cls.return_value = mock_sock

        cfg = self._make_cfg(host="10.255.255.1", port=12345)
        result = verify_config(cfg)
        assert not result["success"]
        assert "tcp-fail" in result["error"]

    @patch("proxy_aggregator.verification.socket.socket")
    def test_invalid_host(self, mock_socket_cls):
        """Test when host is missing."""
        cfg = ConfigItem(link="vless://:443", protocol=Protocol.VLESS,
                         fingerprint="bad-fp")
        result = verify_config(cfg)
        assert not result["success"]
        assert result["error"] == "invalid host/port"

    @patch("proxy_aggregator.verification.socket.socket")
    @patch("proxy_aggregator.verification.ssl.create_default_context")
    def test_tls_handshake_failure(self, mock_ssl_ctx, mock_socket_cls):
        """Test when TLS handshake fails."""
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock

        mock_ctx = MagicMock()
        mock_tls_sock = MagicMock()
        mock_tls_sock.do_handshake.side_effect = Exception("handshake failed")
        mock_ctx.wrap_socket.return_value = mock_tls_sock
        mock_ssl_ctx.return_value = mock_ctx

        cfg = self._make_cfg(host="127.0.0.1", port=443)
        result = verify_config(cfg)
        assert not result["success"]
        assert "tls" in result["error"] or "handshake" in result["error"]


class TestRunVerificationRound:
    def test_empty_list(self):
        result = run_verification_round([])
        assert result["stats"]["total"] == 0
        assert result["stats"]["ok"] == 0

    @patch("proxy_aggregator.verification.verify_config")
    def test_all_pass(self, mock_verify):
        mock_verify.return_value = {"success": True, "latency_ms": 100.0,
                                     "error": "", "status_code": 204}
        cfgs = [ConfigItem(link=f"vless://a{i}@h:443", protocol=Protocol.VLESS,
                           fingerprint=f"fp{i}")
                for i in range(3)]
        result = run_verification_round(cfgs, round_num=1)
        assert result["stats"]["ok"] == 3
        assert result["stats"]["failed"] == 0

    @patch("proxy_aggregator.verification.verify_config")
    def test_some_fail(self, mock_verify):
        mock_verify.side_effect = [
            {"success": True, "latency_ms": 50.0, "error": "", "status_code": 204},
            {"success": False, "latency_ms": None, "error": "timeout", "status_code": None},
            {"success": True, "latency_ms": 75.0, "error": "", "status_code": 204},
        ]
        cfgs = [ConfigItem(link=f"vless://a{i}@h:443", protocol=Protocol.VLESS,
                           fingerprint=f"fp{i}")
                for i in range(3)]
        result = run_verification_round(cfgs, round_num=1)
        assert result["stats"]["ok"] == 2
        assert result["stats"]["failed"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestVLESSRealityConfig:
    """Regression tests for VLESS Reality config generation."""

    def test_vless_reality_config_generated(self):
        """VLESS with security=reality should generate a valid Xray config."""
        from proxy_aggregator.verification import _build_xray_config
        link = ("vless://testuuid@1.2.3.4:443"
                "?security=reality&pbk=pubkey&sid=sid&sni=sni.example.com")
        cfg = _build_xray_config(link, Protocol.VLESS, 10000)
        assert cfg is not None
        ob = cfg["outbounds"][0]
        assert ob["protocol"] == "vless"
        assert ob["streamSettings"]["security"] == "reality"
        assert ob["streamSettings"]["realitySettings"]["serverName"] == "sni.example.com"
        assert ob["streamSettings"]["realitySettings"]["publicKey"] == "pubkey"
        assert ob["streamSettings"]["realitySettings"]["shortId"] == "sid"

    def test_vless_reality_missing_sid_uses_empty(self):
        """VLESS with reality but no sid param should not crash."""
        from proxy_aggregator.verification import _build_xray_config
        link = "vless://testuuid@1.2.3.4:443?security=reality&pbk=pubkey&sni=sni.com"
        cfg = _build_xray_config(link, Protocol.VLESS, 10000)
        assert cfg is not None
        assert cfg["outbounds"][0]["streamSettings"]["realitySettings"]["shortId"] == ""


class TestHttpThroughSocks5:
    """Unit tests for _http_through_socks5 using mocked sockets."""

    @patch("proxy_aggregator.verification.socket.socket")
    def test_ipv4_connect_success(self, mock_socket_cls):
        """IPv4 target should encode with ATYP=0x01 and big-endian port."""
        from proxy_aggregator.verification import _http_through_socks5

        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock

        # Simulate: handshake ok, connect ok, then HTTP response
        mock_sock.recv.side_effect = [
            b"\x05\x00",  # handshake ok
            b"\x05\x00\x00\x01\xac\x1f\x0a\x27\x13\x88",  # connect ok for 172.31.10.39:5000
            b"HTTP/1.1 200 OK\r\n\r\n",  # HTTP response
        ]

        result = _http_through_socks5("127.0.0.1", 1080, "172.31.10.39", 5000, "/test", 5000, 5000, 10.0)
        assert result["success"] is True
        assert result["status_code"] == 200

        # Verify CONNECT request encoding
        calls = mock_sock.sendall.call_args_list
        connect_req = calls[1][0][0]
        assert connect_req[0] == 0x05 and connect_req[1] == 0x01 and connect_req[2] == 0x00 and connect_req[3] == 0x01
        assert connect_req[-2:] == b"\x13\x88"  # big-endian 5000

    @patch("proxy_aggregator.verification.socket.socket")
    def test_domain_name_connect(self, mock_socket_cls):
        """Domain name target should encode with ATYP=0x03 and length prefix."""
        from proxy_aggregator.verification import _http_through_socks5

        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.recv.side_effect = [
            b"\x05\x00",
            b"\x05\x00\x00\x03\x0bexample.com\x13\x88",
            b"HTTP/1.1 204 No Content\r\n\r\n",
        ]

        result = _http_through_socks5("127.0.0.1", 1080, "example.com", 5000, "/", 5000, 5000, 10.0)
        assert result["success"] is True

        calls = mock_sock.sendall.call_args_list
        connect_req = calls[1][0][0]
        assert connect_req[3] == 0x03  # ATYP domain
        assert connect_req[4] == 11  # length of "example.com"

    @patch("proxy_aggregator.verification.socket.socket")
    def test_socks5_rejection(self, mock_socket_cls):
        """SOCKS5 connection rejected → failure result."""
        from proxy_aggregator.verification import _http_through_socks5

        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.recv.side_effect = [b"\x05\x00", b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00"]

        result = _http_through_socks5("127.0.0.1", 1080, "1.2.3.4", 443, "/", 5000, 5000, 10.0)
        assert result["success"] is False
        assert "socks-connect-reject" in result["error"]

    def test_invalid_port_rejected(self):
        """Port outside 1-65535 should return failure immediately."""
        from proxy_aggregator.verification import _http_through_socks5
        result = _http_through_socks5("127.0.0.1", 1080, "1.2.3.4", 0, "/", 5000, 5000, 10.0)
        assert result["success"] is False
        assert result["error"] == "invalid-port"

        result2 = _http_through_socks5("127.0.0.1", 1080, "1.2.3.4", 70000, "/", 5000, 5000, 10.0)
        assert result2["success"] is False
        assert result2["error"] == "invalid-port"

    @patch("proxy_aggregator.verification.socket.socket")
    def test_http_failure_after_tunnel(self, mock_socket_cls):
        """Successful tunnel but HTTP returns 404 → failure result."""
        from proxy_aggregator.verification import _http_through_socks5

        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.recv.side_effect = [
            b"\x05\x00",
            b"\x05\x00\x00\x01\xac\x1f\x0a\x27\x13\x88",
            b"HTTP/1.1 404 Not Found\r\n\r\n",
        ]

        result = _http_through_socks5("127.0.0.1", 1080, "172.31.10.39", 5000, "/missing", 5000, 5000, 10.0)
        assert result["success"] is False
        assert result["status_code"] == 404

    @patch("proxy_aggregator.verification.socket.socket")
    def test_handshake_failure(self, mock_socket_cls):
        """Server responds with bad handshake → failure."""
        from proxy_aggregator.verification import _http_through_socks5

        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.recv.return_value = b"\x05\xFF"

        result = _http_through_socks5("127.0.0.1", 1080, "1.2.3.4", 443, "/", 5000, 5000, 10.0)
        assert result["success"] is False
        assert "socks-handshake-fail" in result["error"]


class TestHysteria2Verification:
    """Tests for Hysteria2 verification handling."""

    def test_hysteria2_returns_unsupported(self):
        """Hysteria2 should return unsupported result without spawning Xray."""
        from proxy_aggregator.verification import _verify_via_xray
        from proxy_aggregator.models import ConfigItem, Protocol

        cfg = ConfigItem(link="hysteria2://token@1.2.3.4:443", protocol=Protocol.HYSTERIA2, fingerprint="test")
        with patch("proxy_aggregator.verification._has_xray", return_value=True):
            result = _verify_via_xray(cfg)
        assert result is not None
        assert result["success"] is False
        assert result["error"] == "hysteria2-unsupported"
        assert result["method"] == "xray"
        assert result["structural_only"] is False
