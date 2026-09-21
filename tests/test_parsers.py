"""Tests for protocol parsers and URI normalization."""

from __future__ import annotations

import pytest

from proxyaggregator.parsers.base import BaseParser, ParseError, ParseResult
from proxyaggregator.parsers.detect import detect_protocol
from proxyaggregator.parsers.extract import extract_uris
from proxyaggregator.parsers.http_proxy import HttpProxyParser, HttpsProxyParser
from proxyaggregator.parsers.hysteria import Hysteria2Parser, HysteriaParser
from proxyaggregator.parsers.normalize import normalize_uri
from proxyaggregator.parsers.registry import ParserRegistry, get_registry
from proxyaggregator.parsers.shadowsocks import ShadowsocksParser
from proxyaggregator.parsers.socks import Socks4Parser, Socks5Parser
from proxyaggregator.parsers.trojan import TrojanParser
from proxyaggregator.parsers.vless import VlessParser
from proxyaggregator.parsers.vmess import VmessParser

# --- ParseResult tests ---


class TestParseResult:
    def test_valid_result(self):
        r = ParseResult(
            protocol="vless",
            host="example.com",
            port=443,
            raw_uri="vless://user@example.com:443",
            user="user",
        )
        assert r.protocol == "vless"
        assert r.host == "example.com"
        assert r.port == 443
        assert r.user == "user"
        assert r.password is None
        assert r.sni is None
        assert r.network is None
        assert r.tls is None

    def test_result_with_all_fields(self):
        r = ParseResult(
            protocol="vless",
            host="1.2.3.4",
            port=8443,
            raw_uri="vless://u@1.2.3.4:8443",
            user="u",
            password="pass",
            sni="sni.example.com",
            network="ws",
            tls="tls",
            path="/path",
            fragment="MyProxy",
        )
        assert r.password == "pass"
        assert r.sni == "sni.example.com"
        assert r.network == "ws"
        assert r.path == "/path"
        assert r.fragment == "MyProxy"


class TestParseError:
    def test_error_result(self):
        e = ParseError(protocol="vless", error="malformed URI", raw_uri="bad")
        assert e.protocol == "vless"
        assert e.error == "malformed URI"


# --- BaseParser tests ---


class TestBaseParser:
    def test_cannot_instantiate_base(self):
        with pytest.raises(TypeError):
            BaseParser()  # type: ignore[abstract]

    def test_subclass_must_implement(self):
        class Incomplete(BaseParser):
            pass

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]


# --- detect_protocol tests ---


class TestDetectProtocol:
    def test_vless(self):
        assert detect_protocol("vless://user@host:443") == "vless"

    def test_vmess(self):
        assert detect_protocol("vmess://base64data") == "vmess"

    def test_trojan(self):
        assert detect_protocol("trojan://pass@host:443") == "trojan"

    def test_shadowsocks(self):
        assert detect_protocol("ss://base64@host:443") == "ss"

    def test_hysteria(self):
        assert detect_protocol("hysteria://host:443?auth=abc") == "hysteria"

    def test_hysteria2(self):
        assert detect_protocol("hysteria2://pass@host:443") == "hysteria2"

    def test_socks4(self):
        assert detect_protocol("socks4://host:1080") == "socks4"

    def test_socks4a(self):
        assert detect_protocol("socks4a://host:1080") == "socks4a"

    def test_socks5(self):
        assert detect_protocol("socks5://user:pass@host:1080") == "socks5"

    def test_http_proxy(self):
        assert detect_protocol("http://proxy.example.com:8080") == "http"

    def test_https_proxy(self):
        assert detect_protocol("https://proxy.example.com:8443") == "https"

    def test_unknown_returns_none(self):
        assert detect_protocol("ftp://example.com/file") is None

    def test_empty_returns_none(self):
        assert detect_protocol("") is None

    def test_no_scheme_returns_none(self):
        assert detect_protocol("not-a-uri") is None


# --- ParserRegistry tests ---


class TestParserRegistry:
    def test_register_and_get(self):
        reg = ParserRegistry()

        class P(BaseParser):
            @property
            def supported_protocol(self) -> str:
                return "test"

            def parse(self, uri: str) -> ParseResult | ParseError:
                raise NotImplementedError

        reg.register(P())
        assert reg.get("test") is not None

    def test_get_unknown_returns_none(self):
        reg = ParserRegistry()
        assert reg.get("nonexistent") is None

    def test_default_registry_has_all(self):
        reg = get_registry()
        expected = [
            "vless", "vmess", "trojan", "ss",
            "hysteria", "hysteria2",
            "socks4", "socks4a", "socks5",
            "http", "https",
        ]
        for p in expected:
            assert reg.get(p) is not None, f"Missing parser for {p}"


# --- normalize_uri tests ---


class TestNormalizeUri:
    def test_lowercases_scheme(self):
        assert normalize_uri("VLESS://host:443").startswith("vless://")

    def test_strips_whitespace(self):
        assert normalize_uri("  vless://host:443  ") == "vless://host:443"

    def test_empty_returns_empty(self):
        assert normalize_uri("") == ""


# --- extract_uris tests ---


class TestExtractUris:
    def test_single_uri(self):
        result = extract_uris("vless://user@host:443")
        assert result == ["vless://user@host:443"]

    def test_multiple_lines(self):
        content = "vless://a@h1:443\nvless://b@h2:443"
        result = extract_uris(content)
        assert len(result) == 2

    def test_blank_lines_skipped(self):
        content = "vless://a@h:443\n\n\nvless://b@h:443"
        result = extract_uris(content)
        assert len(result) == 2

    def test_whitespace_trimmed(self):
        content = "  vless://a@h:443  \n  "
        result = extract_uris(content)
        assert result == ["vless://a@h:443"]

    def test_comments_skipped(self):
        content = "# this is a comment\nvless://a@h:443"
        result = extract_uris(content)
        assert len(result) == 1

    def test_empty_content(self):
        assert extract_uris("") == []

    def test_only_blanks_and_comments(self):
        content = "# comment\n\n  \n# another"
        assert extract_uris(content) == []


# --- VLESS parser tests ---


class TestVlessParser:
    def setup_method(self):
        self.parser = VlessParser()

    def test_supported_protocol(self):
        assert self.parser.supported_protocol == "vless"

    def test_basic_uri(self):
        r = self.parser.parse("vless://uuid@host.example.com:443")
        assert isinstance(r, ParseResult)
        assert r.protocol == "vless"
        assert r.host == "host.example.com"
        assert r.port == 443
        assert r.user == "uuid"

    def test_with_tls(self):
        uri = "vless://uuid@host:443?security=tls&sni=sni.example.com"
        r = self.parser.parse(uri)
        assert isinstance(r, ParseResult)
        assert r.tls == "tls"
        assert r.sni == "sni.example.com"

    def test_with_ws(self):
        uri = "vless://uuid@host:443?network=ws&path=%2Fws"
        r = self.parser.parse(uri)
        assert isinstance(r, ParseResult)
        assert r.network == "ws"
        assert r.path == "/ws"

    def test_with_grpc(self):
        uri = "vless://uuid@host:443?network=grpc&serviceName=grpc"
        r = self.parser.parse(uri)
        assert isinstance(r, ParseResult)
        assert r.network == "grpc"
        assert r.service_name == "grpc"

    def test_with_fragment(self):
        uri = "vless://uuid@host:443#MyConfig"
        r = self.parser.parse(uri)
        assert isinstance(r, ParseResult)
        assert r.fragment == "MyConfig"

    def test_with_flow(self):
        uri = "vless://uuid@host:443?flow=xtls-rprx-vision"
        r = self.parser.parse(uri)
        assert isinstance(r, ParseResult)
        assert r.flow == "xtls-rprx-vision"

    def test_malformed_no_host(self):
        r = self.parser.parse("vless://")
        assert isinstance(r, ParseError)

    def test_malformed_no_port(self):
        r = self.parser.parse("vless://uuid@host")
        assert isinstance(r, ParseError)

    def test_invalid_port(self):
        r = self.parser.parse("vless://uuid@host:99999")
        assert isinstance(r, ParseError)

    def test_empty_user(self):
        r = self.parser.parse("vless://@host:443")
        assert isinstance(r, ParseResult)
        assert r.user == ""

    def test_percent_encoded(self):
        uri = "vless://uuid@host:443?path=%2Fpath%20with%20spaces"
        r = self.parser.parse(uri)
        assert isinstance(r, ParseResult)
        assert r.path == "/path with spaces"

    def test_deterministic_output(self):
        uri = "vless://uuid@host:443?security=tls&sni=sni.example.com#Test"
        r1 = self.parser.parse(uri)
        r2 = self.parser.parse(uri)
        assert r1.model_dump() == r2.model_dump()


# --- VMess parser tests ---


class TestVmessParser:
    def setup_method(self):
        self.parser = VmessParser()

    def test_supported_protocol(self):
        assert self.parser.supported_protocol == "vmess"

    def test_valid_base64_json(self):
        import base64
        import json
        config = {
            "v": "2",
            "ps": "TestVMess",
            "add": "host.example.com",
            "port": "443",
            "id": "uuid-here",
            "aid": "0",
            "net": "tcp",
            "type": "none",
            "host": "",
            "path": "",
            "tls": "tls",
            "sni": "sni.example.com",
        }
        encoded = base64.b64encode(json.dumps(config).encode()).decode()
        uri = f"vmess://{encoded}"
        r = self.parser.parse(uri)
        assert isinstance(r, ParseResult)
        assert r.protocol == "vmess"
        assert r.host == "host.example.com"
        assert r.port == 443
        assert r.user == "uuid-here"
        assert r.network == "tcp"
        assert r.tls == "tls"
        assert r.sni == "sni.example.com"
        assert r.fragment == "TestVMess"

    def test_invalid_base64(self):
        r = self.parser.parse("vmess://not-valid-base64!!!")
        assert isinstance(r, ParseError)

    def test_invalid_json(self):
        import base64
        encoded = base64.b64encode(b"not json").decode()
        r = self.parser.parse(f"vmess://{encoded}")
        assert isinstance(r, ParseError)

    def test_missing_required_field(self):
        import base64
        import json
        config = {"v": "2", "ps": "Test", "add": "host.com"}
        encoded = base64.b64encode(json.dumps(config).encode()).decode()
        r = self.parser.parse(f"vmess://{encoded}")
        assert isinstance(r, ParseError)

    def test_invalid_port(self):
        import base64
        import json
        config = {
            "v": "2", "ps": "", "add": "host.com", "port": "99999",
            "id": "uuid", "aid": "0", "net": "tcp", "type": "none",
            "host": "", "path": "", "tls": "",
        }
        encoded = base64.b64encode(json.dumps(config).encode()).decode()
        r = self.parser.parse(f"vmess://{encoded}")
        assert isinstance(r, ParseError)

    def test_with_fragment(self):
        import base64
        import json
        config = {
            "v": "2", "ps": "MyNode", "add": "host.com", "port": "443",
            "id": "uuid", "aid": "0", "net": "ws", "type": "none",
            "host": "", "path": "/path", "tls": "tls", "sni": "sni.com",
        }
        encoded = base64.b64encode(json.dumps(config).encode()).decode()
        r = self.parser.parse(f"vmess://{encoded}#MyNode")
        assert isinstance(r, ParseResult)
        assert r.fragment == "MyNode"


# --- Trojan parser tests ---


class TestTrojanParser:
    def setup_method(self):
        self.parser = TrojanParser()

    def test_supported_protocol(self):
        assert self.parser.supported_protocol == "trojan"

    def test_basic_uri(self):
        r = self.parser.parse("trojan://password@host.example.com:443")
        assert isinstance(r, ParseResult)
        assert r.protocol == "trojan"
        assert r.host == "host.example.com"
        assert r.port == 443
        assert r.user == "password"

    def test_with_sni(self):
        uri = "trojan://pass@host:443?sni=sni.example.com"
        r = self.parser.parse(uri)
        assert isinstance(r, ParseResult)
        assert r.sni == "sni.example.com"

    def test_with_fragment(self):
        uri = "trojan://pass@host:443#MyTrojan"
        r = self.parser.parse(uri)
        assert isinstance(r, ParseResult)
        assert r.fragment == "MyTrojan"

    def test_malformed_no_host(self):
        r = self.parser.parse("trojan://")
        assert isinstance(r, ParseError)

    def test_invalid_port(self):
        r = self.parser.parse("trojan://pass@host:0")
        assert isinstance(r, ParseError)


# --- Shadowsocks parser tests ---


class TestShadowsocksParser:
    def setup_method(self):
        self.parser = ShadowsocksParser()

    def test_supported_protocol(self):
        assert self.parser.supported_protocol == "ss"

    def test_basic_sip002(self):
        import base64
        method_password = base64.b64encode(b"aes-256-gcm:password123").decode()
        uri = f"ss://{method_password}@host.example.com:8388"
        r = self.parser.parse(uri)
        assert isinstance(r, ParseResult)
        assert r.protocol == "ss"
        assert r.host == "host.example.com"
        assert r.port == 8388
        assert r.method == "aes-256-gcm"
        assert r.password == "password123"

    def test_with_fragment(self):
        import base64
        mp = base64.b64encode(b"chacha20-ietf-poly1305:pass").decode()
        uri = f"ss://{mp}@host:8388#MySS"
        r = self.parser.parse(uri)
        assert isinstance(r, ParseResult)
        assert r.fragment == "MySS"

    def test_invalid_base64(self):
        r = self.parser.parse("ss://not-valid!!!@host:8388")
        assert isinstance(r, ParseError)

    def test_missing_method(self):
        import base64
        mp = base64.b64encode(b":password").decode()
        r = self.parser.parse(f"ss://{mp}@host:8388")
        assert isinstance(r, ParseError)

    def test_invalid_port(self):
        import base64
        mp = base64.b64encode(b"aes-128-gcm:pass").decode()
        r = self.parser.parse(f"ss://{mp}@host:99999")
        assert isinstance(r, ParseError)


# --- Hysteria parser tests ---


class TestHysteriaParser:
    def setup_method(self):
        self.parser = HysteriaParser()

    def test_supported_protocol(self):
        assert self.parser.supported_protocol == "hysteria"

    def test_basic_uri(self):
        uri = "hysteria://host.example.com:443?auth=abc123"
        r = self.parser.parse(uri)
        assert isinstance(r, ParseResult)
        assert r.protocol == "hysteria"
        assert r.host == "host.example.com"
        assert r.port == 443

    def test_with_fragment(self):
        uri = "hysteria://host:443?auth=abc#MyHyp"
        r = self.parser.parse(uri)
        assert isinstance(r, ParseResult)
        assert r.fragment == "MyHyp"

    def test_malformed(self):
        r = self.parser.parse("hysteria://")
        assert isinstance(r, ParseError)

    def test_invalid_port(self):
        r = self.parser.parse("hysteria://host:0?auth=abc")
        assert isinstance(r, ParseError)


class TestHysteria2Parser:
    def setup_method(self):
        self.parser = Hysteria2Parser()

    def test_supported_protocol(self):
        assert self.parser.supported_protocol == "hysteria2"

    def test_basic_uri(self):
        uri = "hysteria2://password@host.example.com:443"
        r = self.parser.parse(uri)
        assert isinstance(r, ParseResult)
        assert r.protocol == "hysteria2"
        assert r.host == "host.example.com"
        assert r.port == 443
        assert r.user == "password"

    def test_with_sni(self):
        uri = "hysteria2://pass@host:443?sni=sni.example.com"
        r = self.parser.parse(uri)
        assert isinstance(r, ParseResult)
        assert r.sni == "sni.example.com"

    def test_malformed(self):
        r = self.parser.parse("hysteria2://")
        assert isinstance(r, ParseError)


# --- SOCKS parser tests ---


class TestSocks4Parser:
    def setup_method(self):
        self.parser = Socks4Parser()

    def test_supported_protocol(self):
        assert self.parser.supported_protocol == "socks4"

    def test_basic_uri(self):
        r = self.parser.parse("socks4://host.example.com:1080")
        assert isinstance(r, ParseResult)
        assert r.protocol == "socks4"
        assert r.host == "host.example.com"
        assert r.port == 1080

    def test_with_user(self):
        r = self.parser.parse("socks4://user@host:1080")
        assert isinstance(r, ParseResult)
        assert r.user == "user"

    def test_malformed(self):
        r = self.parser.parse("socks4://")
        assert isinstance(r, ParseError)


class TestSocks4aParser:
    def setup_method(self):
        self.parser = Socks4Parser()

    def test_socks4a_scheme(self):
        r = self.parser.parse("socks4a://host:1080")
        assert isinstance(r, ParseResult)
        assert r.protocol == "socks4"


class TestSocks5Parser:
    def setup_method(self):
        self.parser = Socks5Parser()

    def test_supported_protocol(self):
        assert self.parser.supported_protocol == "socks5"

    def test_basic_uri(self):
        r = self.parser.parse("socks5://host.example.com:1080")
        assert isinstance(r, ParseResult)
        assert r.protocol == "socks5"
        assert r.host == "host.example.com"
        assert r.port == 1080

    def test_with_credentials(self):
        r = self.parser.parse("socks5://user:pass@host:1080")
        assert isinstance(r, ParseResult)
        assert r.user == "user"
        assert r.password == "pass"

    def test_malformed(self):
        r = self.parser.parse("socks5://")
        assert isinstance(r, ParseError)


# --- HTTP/HTTPS proxy parser tests ---


class TestHttpProxyParser:
    def setup_method(self):
        self.parser = HttpProxyParser()

    def test_supported_protocol(self):
        assert self.parser.supported_protocol == "http"

    def test_basic_uri(self):
        r = self.parser.parse("http://proxy.example.com:8080")
        assert isinstance(r, ParseResult)
        assert r.protocol == "http"
        assert r.host == "proxy.example.com"
        assert r.port == 8080

    def test_with_credentials(self):
        r = self.parser.parse("http://user:pass@proxy:8080")
        assert isinstance(r, ParseResult)
        assert r.user == "user"
        assert r.password == "pass"

    def test_malformed(self):
        r = self.parser.parse("http://")
        assert isinstance(r, ParseError)


class TestHttpsProxyParser:
    def setup_method(self):
        self.parser = HttpsProxyParser()

    def test_supported_protocol(self):
        assert self.parser.supported_protocol == "https"

    def test_basic_uri(self):
        r = self.parser.parse("https://proxy.example.com:8443")
        assert isinstance(r, ParseResult)
        assert r.protocol == "https"
        assert r.host == "proxy.example.com"
        assert r.port == 8443

    def test_malformed(self):
        r = self.parser.parse("https://")
        assert isinstance(r, ParseError)


# --- Content extraction integration ---


class TestContentExtraction:
    def test_mixed_content(self):
        content = """# comment
vless://uuid@host1:443
trojan://pass@host2:443

# another comment
vmess://encoded
"""
        uris = extract_uris(content)
        assert len(uris) == 3

    def test_base64_encoded_content(self):
        import base64
        inner = "vless://uuid@host:443\ntrojan://pass@host:443"
        encoded = base64.b64encode(inner.encode()).decode()
        uris = extract_uris(encoded)
        assert len(uris) == 2
