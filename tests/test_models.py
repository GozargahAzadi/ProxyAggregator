"""Tests for Pydantic domain models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from proxyaggregator.models.health_check import HealthCheckSchema
from proxyaggregator.models.proxy_config import ProxyConfigSchema
from proxyaggregator.models.source import SourceSchema


class TestProxyConfigSchema:
    """Tests for ProxyConfig Pydantic schema."""

    def test_valid_proxy_config(self):
        config = ProxyConfigSchema(
            protocol="vless",
            host="example.com",
            port=443,
            raw_uri="vless://user@example.com:443?security=tls",
            content_hash="a" * 64,
        )
        assert config.protocol == "vless"
        assert config.host == "example.com"
        assert config.port == 443
        assert config.is_alive is False
        assert config.latency_ms is None
        assert config.country_code is None
        assert config.city is None
        assert config.latitude is None
        assert config.longitude is None

    def test_proxy_config_defaults(self):
        config = ProxyConfigSchema(
            protocol="vmess",
            host="1.2.3.4",
            port=8080,
            raw_uri="vmess://encoded-data",
            content_hash="b" * 64,
        )
        assert config.is_alive is False
        assert config.latency_ms is None
        assert config.country_code is None
        assert config.city is None
        assert config.latitude is None
        assert config.longitude is None

    def test_proxy_config_with_geo(self):
        config = ProxyConfigSchema(
            protocol="trojan",
            host="server.com",
            port=443,
            raw_uri="trojan://pass@server.com:443",
            content_hash="c" * 64,
            country_code="US",
            city="New York",
            latitude=40.7128,
            longitude=-74.0060,
        )
        assert config.country_code == "US"
        assert config.city == "New York"
        assert config.latitude == 40.7128
        assert config.longitude == -74.0060

    def test_proxy_config_invalid_port_low(self):
        with pytest.raises(ValidationError):
            ProxyConfigSchema(
                protocol="vless",
                host="example.com",
                port=0,
                raw_uri="vless://user@example.com:0",
                content_hash="d" * 64,
            )

    def test_proxy_config_invalid_port_high(self):
        with pytest.raises(ValidationError):
            ProxyConfigSchema(
                protocol="vless",
                host="example.com",
                port=99999,
                raw_uri="vless://user@example.com:99999",
                content_hash="e" * 64,
            )

    def test_proxy_config_empty_protocol_rejected(self):
        with pytest.raises(ValidationError):
            ProxyConfigSchema(
                protocol="",
                host="example.com",
                port=443,
                raw_uri="vless://user@example.com:443",
                content_hash="f" * 64,
            )

    def test_proxy_config_empty_host_rejected(self):
        with pytest.raises(ValidationError):
            ProxyConfigSchema(
                protocol="vless",
                host="",
                port=443,
                raw_uri="vless://user@:443",
                content_hash="a" * 63 + "b",
            )

    def test_proxy_config_invalid_content_hash_length(self):
        with pytest.raises(ValidationError):
            ProxyConfigSchema(
                protocol="vless",
                host="example.com",
                port=443,
                raw_uri="vless://user@example.com:443",
                content_hash="tooshort",
            )

    def test_proxy_config_country_code_length(self):
        with pytest.raises(ValidationError):
            ProxyConfigSchema(
                protocol="vless",
                host="example.com",
                port=443,
                raw_uri="vless://user@example.com:443",
                content_hash="a" * 64,
                country_code="USA",
            )

    def test_proxy_config_optional_fields_none(self):
        config = ProxyConfigSchema(
            protocol="hysteria2",
            host="hy2.example.com",
            port=8443,
            raw_uri="hysteria2://pass@hy2.example.com:8443",
            content_hash="a" * 64,
        )
        assert config.is_alive is False
        assert config.country_code is None
        assert config.city is None


class TestSourceSchema:
    """Tests for Source Pydantic schema."""

    def test_valid_source(self):
        source = SourceSchema(
            name="Telegram Channel",
            source_type="telegram",
            url="https://t.me/proxies",
        )
        assert source.name == "Telegram Channel"
        assert source.source_type == "telegram"
        assert source.config_count == 0
        assert source.last_fetched_at is None

    def test_source_with_fetched_at(self):
        now = datetime.now(tz=UTC)
        source = SourceSchema(
            name="GitHub Repo",
            source_type="github",
            url="https://github.com/user/proxies",
            last_fetched_at=now,
            config_count=42,
        )
        assert source.last_fetched_at == now
        assert source.config_count == 42

    def test_source_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            SourceSchema(
                name="",
                source_type="telegram",
                url="https://t.me/proxies",
            )

    def test_source_empty_url_rejected(self):
        with pytest.raises(ValidationError):
            SourceSchema(
                name="Bad Source",
                source_type="telegram",
                url="",
            )

    def test_source_empty_source_type_rejected(self):
        with pytest.raises(ValidationError):
            SourceSchema(
                name="Bad Source",
                source_type="",
                url="https://t.me/proxies",
            )


class TestHealthCheckSchema:
    """Tests for HealthCheck Pydantic schema."""

    def test_valid_health_check(self):
        check = HealthCheckSchema(
            proxy_config_id=1,
            is_alive=True,
            latency_ms=123.45,
        )
        assert check.proxy_config_id == 1
        assert check.is_alive is True
        assert check.latency_ms == 123.45
        assert check.error_message is None

    def test_health_check_failed(self):
        check = HealthCheckSchema(
            proxy_config_id=2,
            is_alive=False,
            error_message="Connection refused",
        )
        assert check.is_alive is False
        assert check.latency_ms is None
        assert check.error_message == "Connection refused"

    def test_health_check_invalid_config_id(self):
        with pytest.raises(ValidationError):
            HealthCheckSchema(
                proxy_config_id=0,
                is_alive=True,
                latency_ms=50.0,
            )

    def test_health_check_negative_latency(self):
        with pytest.raises(ValidationError):
            HealthCheckSchema(
                proxy_config_id=1,
                is_alive=True,
                latency_ms=-1.0,
            )
