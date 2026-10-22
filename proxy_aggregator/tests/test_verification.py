"""Tests for verification module — mock-based, no live network needed."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from proxy_aggregator.models import ConfigItem, Protocol
from proxy_aggregator.verification import verify_config_direct, run_verification_round


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
        result = verify_config_direct(cfg)
        assert not result["success"]
        assert "tcp-fail" in result["error"]

    @patch("proxy_aggregator.verification.socket.socket")
    def test_invalid_host(self, mock_socket_cls):
        """Test when host is missing."""
        cfg = ConfigItem(link="vless://:443", protocol=Protocol.VLESS,
                         fingerprint="bad-fp")
        result = verify_config_direct(cfg)
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
        result = verify_config_direct(cfg)
        assert not result["success"]
        assert "tls" in result["error"] or "handshake" in result["error"]


class TestRunVerificationRound:
    def test_empty_list(self):
        result = run_verification_round([])
        assert result["stats"]["total"] == 0
        assert result["stats"]["ok"] == 0

    @patch("proxy_aggregator.verification.verify_config_direct")
    def test_all_pass(self, mock_verify):
        mock_verify.return_value = {"success": True, "latency_ms": 100.0,
                                     "error": "", "status_code": 204}
        cfgs = [ConfigItem(link=f"vless://a{i}@h:443", protocol=Protocol.VLESS,
                           fingerprint=f"fp{i}")
                for i in range(3)]
        result = run_verification_round(cfgs, round_num=1)
        assert result["stats"]["ok"] == 3
        assert result["stats"]["failed"] == 0

    @patch("proxy_aggregator.verification.verify_config_direct")
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
