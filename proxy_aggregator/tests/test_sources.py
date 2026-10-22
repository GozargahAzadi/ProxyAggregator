"""Tests for sources module — mocking urllib to avoid live network."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from proxy_aggregator.sources import fetch_source, classify_source


class TestFetchSource:
    @patch("proxy_aggregator.sources.urllib.request.urlopen")
    def test_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"vless://test@host:443\n"
        mock_urlopen.return_value.__enter__ = lambda s: mock_resp
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        text, code, err = fetch_source("https://example.com/configs")
        assert code == 200
        assert err == ""
        assert "vless://test@host:443" in text

    @patch("proxy_aggregator.sources.urllib.request.urlopen")
    def test_404_dead(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError("https://example.com", 404,
                                              "Not Found", None, None)
        text, code, err = fetch_source("https://example.com/missing")
        assert code == 404
        assert err == "dead"

    @patch("proxy_aggregator.sources.urllib.request.urlopen")
    def test_timeout(self, mock_urlopen):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("timed out")
        text, code, err = fetch_source("https://example.com/slow")
        assert code is None
        assert err == "timeout"

    @patch("proxy_aggregator.sources.urllib.request.urlopen")
    def test_truncated(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"x" * 11_000_000  # > MAX_RESPONSE_SIZE
        mock_urlopen.return_value.__enter__ = lambda s: mock_resp
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        text, code, err = fetch_source("https://example.com/huge")
        assert len(text) <= 10_000_000
        assert err == "truncated"


class TestClassifySource:
    def test_dead_source(self):
        result = classify_source("https://example.com", "", 404, "dead")
        assert result.status == "fail"
        assert "4xx" in result.error

    def test_network_error(self):
        result = classify_source("https://example.com", "", None, "timeout")
        assert result.status == "fail"
        assert result.error == "timeout"

    def test_empty_content(self):
        result = classify_source("https://example.com", "   \n  ", 200, "")
        assert result.status == "empty"

    def test_valid_source(self):
        result = classify_source("https://example.com", "vless://test@host:443\n",
                                 200, "")
        assert result.status == "ok"
        assert result.config_count == 0  # filled later by parser


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
