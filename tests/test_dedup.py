"""Tests for deduplication layer -- Phase 4."""

from __future__ import annotations

from proxyaggregator.dedup.canonical import canonicalize, compute_content_hash
from proxyaggregator.dedup.deduplicator import Deduplicator
from proxyaggregator.dedup.endpoint import EndpointIdentity, endpoint_identity
from proxyaggregator.dedup.fuzzy import fuzzy_match
from proxyaggregator.dedup.models import DedupMatchType
from proxyaggregator.parsers.base import ParseResult

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _vless(
    host: str = "1.2.3.4",
    port: int = 443,
    user: str = "abc-def-123",
    password: str | None = None,
    sni: str | None = None,
    network: str | None = None,
    tls: str | None = None,
    path: str | None = None,
    host_header: str | None = None,
    fragment: str | None = None,
    service_name: str | None = None,
    flow: str | None = None,
    raw_uri: str | None = None,
) -> ParseResult:
    return ParseResult(
        protocol="vless",
        host=host,
        port=port,
        raw_uri=raw_uri or f"vless://{user}@{host}:{port}",
        user=user,
        password=password,
        sni=sni,
        network=network,
        tls=tls,
        path=path,
        host_header=host_header,
        fragment=fragment,
        service_name=service_name,
        flow=flow,
    )


def _vmess(
    host: str = "5.6.7.8",
    port: int = 8443,
    user: str = "vmess-uuid",
    sni: str | None = None,
    network: str | None = None,
    tls: str | None = None,
    path: str | None = None,
    fragment: str | None = None,
    raw_uri: str | None = None,
) -> ParseResult:
    return ParseResult(
        protocol="vmess",
        host=host,
        port=port,
        raw_uri=raw_uri or f"vmess://{user}@{host}:{port}",
        user=user,
        sni=sni,
        network=network,
        tls=tls,
        path=path,
        fragment=fragment,
    )


def _trojan(
    host: str = "9.10.11.12",
    port: int = 443,
    password: str = "trojan-pass",
    sni: str | None = None,
    raw_uri: str | None = None,
) -> ParseResult:
    return ParseResult(
        protocol="trojan",
        host=host,
        port=port,
        raw_uri=raw_uri or f"trojan://{password}@{host}:{port}",
        password=password,
        sni=sni,
    )


def _shadowsocks(
    host: str = "13.14.15.16",
    port: int = 8388,
    password: str = "ss-pass",
    method: str = "aes-256-gcm",
    raw_uri: str | None = None,
) -> ParseResult:
    return ParseResult(
        protocol="ss",
        host=host,
        port=port,
        raw_uri=raw_uri or f"ss://{host}:{port}",
        password=password,
        method=method,
    )


def _socks5(
    host: str = "17.18.19.20",
    port: int = 1080,
    user: str | None = None,
    password: str | None = None,
    raw_uri: str | None = None,
) -> ParseResult:
    return ParseResult(
        protocol="socks5",
        host=host,
        port=port,
        raw_uri=raw_uri or f"socks5://{host}:{port}",
        user=user,
        password=password,
    )


def _hysteria2(
    host: str = "21.22.23.24",
    port: int = 443,
    password: str = "hy2-pass",
    sni: str | None = None,
    obfs: str | None = None,
    obfs_password: str | None = None,
    raw_uri: str | None = None,
) -> ParseResult:
    return ParseResult(
        protocol="hysteria2",
        host=host,
        port=port,
        raw_uri=raw_uri or f"hysteria2://{host}:{port}",
        password=password,
        sni=sni,
        obfs=obfs,
        obfs_password=obfs_password,
    )


# ===========================================================================
# Content-hash based dedup tests
# ===========================================================================


class TestCanonicalization:
    """Tests for canonical representation."""

    def test_deterministic_output(self) -> None:
        a = _vless(sni="example.com", network="ws", tls="tls")
        b = _vless(sni="example.com", network="ws", tls="tls")
        assert canonicalize(a) == canonicalize(b)

    def test_field_ordering_does_not_matter(self) -> None:
        a = _vless(sni="s", network="n", tls="t")
        c = _vless(sni="s", tls="t", network="n")
        assert canonicalize(a) == canonicalize(c)

    def test_irrelevant_fields_excluded(self) -> None:
        a = _vless(raw_uri="vless://abc@1.2.3.4:443")
        b = _vless(raw_uri="vless://abc@1.2.3.4:443#different")
        assert canonicalize(a) == canonicalize(b)

    def test_host_lowercased(self) -> None:
        a = _vless(host="EXAMPLE.COM")
        b = _vless(host="example.com")
        assert canonicalize(a) == canonicalize(b)

    def test_meaningful_field_change_affects_hash(self) -> None:
        a = _vless(sni="a.com")
        b = _vless(sni="b.com")
        assert canonicalize(a) != canonicalize(b)

    def test_port_change_affects_hash(self) -> None:
        a = _vless(port=443)
        b = _vless(port=8443)
        assert canonicalize(a) != canonicalize(b)

    def test_protocol_change_affects_hash(self) -> None:
        a = _vless(host="x.com", port=443)
        b = _trojan(host="x.com", port=443)
        assert canonicalize(a) != canonicalize(b)

    def test_user_change_affects_hash(self) -> None:
        a = _vless(user="user1")
        b = _vless(user="user2")
        assert canonicalize(a) != canonicalize(b)

    def test_password_change_affects_hash(self) -> None:
        a = _trojan(password="pass1")
        b = _trojan(password="pass2")
        assert canonicalize(a) != canonicalize(b)

    def test_network_change_affects_hash(self) -> None:
        a = _vless(network="ws")
        b = _vless(network="grpc")
        assert canonicalize(a) != canonicalize(b)

    def test_tls_change_affects_hash(self) -> None:
        a = _vless(tls="tls")
        b = _vless(tls="reality")
        assert canonicalize(a) != canonicalize(b)

    def test_method_change_affects_hash(self) -> None:
        a = _shadowsocks(method="aes-256-gcm")
        b = _shadowsocks(method="chacha20-ietf-poly1305")
        assert canonicalize(a) != canonicalize(b)

    def test_fragment_excluded(self) -> None:
        a = _vless(fragment="name1")
        b = _vless(fragment="name2")
        assert canonicalize(a) == canonicalize(b)

    def test_sni_none_vs_empty(self) -> None:
        a = _vless(sni=None)
        b = _vless(sni="")
        assert canonicalize(a) == canonicalize(b)

    def test_path_none_vs_empty(self) -> None:
        a = _vless(path=None)
        b = _vless(path="")
        assert canonicalize(a) == canonicalize(b)

    def test_obfs_change_affects_hash(self) -> None:
        a = _hysteria2(obfs="salamander", obfs_password="obfs1")
        b = _hysteria2(obfs="salamander", obfs_password="obfs2")
        assert canonicalize(a) != canonicalize(b)


class TestComputeContentHash:
    """Tests for SHA-256 content hashing."""

    def test_deterministic(self) -> None:
        a = _vless()
        b = _vless()
        assert compute_content_hash(a) == compute_content_hash(b)

    def test_length_is_64(self) -> None:
        h = compute_content_hash(_vless())
        assert len(h) == 64

    def test_is_hex(self) -> None:
        h = compute_content_hash(_vless())
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_config_same_hash(self) -> None:
        a = _vless(sni="s.com", network="ws", tls="tls", path="/p")
        b = _vless(sni="s.com", network="ws", tls="tls", path="/p")
        assert compute_content_hash(a) == compute_content_hash(b)

    def test_different_config_different_hash(self) -> None:
        a = _vless(sni="a.com")
        b = _vless(sni="b.com")
        assert compute_content_hash(a) != compute_content_hash(b)

    def test_cross_protocol_different_hash(self) -> None:
        a = _vless(host="x.com", port=443)
        b = _trojan(host="x.com", port=443)
        assert compute_content_hash(a) != compute_content_hash(b)

    def test_same_endpoint_different_creds_different_hash(self) -> None:
        a = _vless(user="u1")
        b = _vless(user="u2")
        assert compute_content_hash(a) != compute_content_hash(b)

    def test_same_endpoint_different_method_different_hash(self) -> None:
        a = _shadowsocks(method="aes-128-gcm")
        b = _shadowsocks(method="aes-256-gcm")
        assert compute_content_hash(a) != compute_content_hash(b)


# ===========================================================================
# Endpoint-based dedup tests
# ===========================================================================


class TestEndpointIdentity:
    """Tests for endpoint identity extraction."""

    def test_basic_identity(self) -> None:
        ep = endpoint_identity(_vless())
        assert ep == EndpointIdentity(protocol="vless", host="1.2.3.4", port=443)

    def test_host_lowercased(self) -> None:
        ep = endpoint_identity(_vless(host="EXAMPLE.COM"))
        assert ep.host == "example.com"

    def test_same_endpoint_same_identity(self) -> None:
        a = _vless(user="u1", sni="s1")
        b = _vless(user="u2", sni="s2")
        assert endpoint_identity(a) == endpoint_identity(b)

    def test_different_port_different_identity(self) -> None:
        a = _vless(port=443)
        b = _vless(port=8443)
        assert endpoint_identity(a) != endpoint_identity(b)

    def test_different_host_different_identity(self) -> None:
        a = _vless(host="a.com")
        b = _vless(host="b.com")
        assert endpoint_identity(a) != endpoint_identity(b)

    def test_different_protocol_different_identity(self) -> None:
        a = _vless(host="x.com", port=443)
        b = _trojan(host="x.com", port=443)
        assert endpoint_identity(a) != endpoint_identity(b)

    def test_same_endpoint_different_credentials_distinct(self) -> None:
        """Endpoint identity does NOT merge different credentials."""
        a = _vless(user="u1")
        b = _vless(user="u2")
        ep_a = endpoint_identity(a)
        ep_b = endpoint_identity(b)
        assert ep_a == ep_b
        # But content hashes differ
        assert compute_content_hash(a) != compute_content_hash(b)

    def test_hashable(self) -> None:
        ep = endpoint_identity(_vless())
        s = {ep}
        assert ep in s


# ===========================================================================
# Fuzzy matching tests
# ===========================================================================


class TestFuzzyMatch:
    """Tests for fuzzy matching of near-duplicates."""

    def test_identical_configs_match(self) -> None:
        a = _vless(sni="s.com", network="ws")
        b = _vless(sni="s.com", network="ws")
        assert fuzzy_match(a, b) is True

    def test_different_fragment_still_matches(self) -> None:
        a = _vless(fragment="Node1")
        b = _vless(fragment="Node2")
        assert fuzzy_match(a, b) is True

    def test_different_host_header_still_matches(self) -> None:
        a = _vless(host_header="a.example.com")
        b = _vless(host_header="b.example.com")
        assert fuzzy_match(a, b) is True

    def test_different_raw_uri_still_matches(self) -> None:
        a = _vless(raw_uri="vless://u@1.2.3.4:443#X")
        b = _vless(raw_uri="vless://u@1.2.3.4:443#Y")
        assert fuzzy_match(a, b) is True

    def test_different_user_no_match(self) -> None:
        a = _vless(user="user1")
        b = _vless(user="user2")
        assert fuzzy_match(a, b) is False

    def test_different_password_no_match(self) -> None:
        a = _trojan(password="p1")
        b = _trojan(password="p2")
        assert fuzzy_match(a, b) is False

    def test_different_port_no_match(self) -> None:
        a = _vless(port=443)
        b = _vless(port=8443)
        assert fuzzy_match(a, b) is False

    def test_different_host_no_match(self) -> None:
        a = _vless(host="a.com")
        b = _vless(host="b.com")
        assert fuzzy_match(a, b) is False

    def test_different_protocol_no_match(self) -> None:
        a = _vless(host="x.com", port=443)
        b = _trojan(host="x.com", port=443)
        assert fuzzy_match(a, b) is False

    def test_different_network_no_match(self) -> None:
        a = _vless(network="ws", path="/p")
        b = _vless(network="grpc", path="/p")
        assert fuzzy_match(a, b) is False

    def test_different_tls_no_match(self) -> None:
        a = _vless(tls="tls", sni="s.com")
        b = _vless(tls="reality", sni="s.com")
        assert fuzzy_match(a, b) is False

    def test_different_method_no_match(self) -> None:
        a = _shadowsocks(method="aes-128-gcm")
        b = _shadowsocks(method="aes-256-gcm")
        assert fuzzy_match(a, b) is False

    def test_different_sni_no_match(self) -> None:
        a = _vless(sni="a.com")
        b = _vless(sni="b.com")
        assert fuzzy_match(a, b) is False

    def test_different_path_no_match(self) -> None:
        a = _vless(path="/a", network="ws")
        b = _vless(path="/b", network="ws")
        assert fuzzy_match(a, b) is False

    def test_different_service_name_no_match(self) -> None:
        a = _vless(service_name="svc1", network="grpc")
        b = _vless(service_name="svc2", network="grpc")
        assert fuzzy_match(a, b) is False

    def test_different_flow_no_match(self) -> None:
        a = _vless(flow="xtls-rprx-vision")
        b = _vless(flow="none")
        assert fuzzy_match(a, b) is False

    def test_different_obfs_no_match(self) -> None:
        a = _hysteria2(obfs="salamander", obfs_password="p1")
        b = _hysteria2(obfs="salamander", obfs_password="p2")
        assert fuzzy_match(a, b) is False

    def test_same_host_lowercase_matches(self) -> None:
        a = _vless(host="EXAMPLE.COM")
        b = _vless(host="example.com")
        assert fuzzy_match(a, b) is True


# ===========================================================================
# Ordering and determinism tests
# ===========================================================================


class TestDeduplicatorOrdering:
    """Tests for first-occurrence survivor policy and determinism."""

    def test_first_occurrence_survives(self) -> None:
        items = [_vless(), _vless(), _vless()]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        assert len(results) == 3
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.EXACT
        assert results[2].match_type == DedupMatchType.EXACT

    def test_deterministic_output(self) -> None:
        items = [_vless(), _vmess(), _trojan(), _vless()]
        dedup = Deduplicator()
        r1 = dedup.deduplicate(items)
        r2 = dedup.deduplicate(items)
        assert [r.match_type for r in r1] == [r.match_type for r in r2]

    def test_all_duplicates(self) -> None:
        items = [_vless(), _vless(), _vless()]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        assert results[0].match_type == DedupMatchType.NONE
        assert all(r.match_type == DedupMatchType.EXACT for r in results[1:])

    def test_no_duplicates(self) -> None:
        items = [
            _vless(user="u1", host="a.com"),
            _vless(user="u2", host="b.com"),
            _trojan(password="p1", host="c.com"),
        ]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        assert all(r.match_type == DedupMatchType.NONE for r in results)

    def test_mixed_exact_and_unique(self) -> None:
        items = [
            _vless(user="u1"),
            _vless(user="u1"),
            _vless(user="u2"),
            _vmess(user="m1"),
        ]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        types = [r.match_type for r in results]
        # Item 2 shares endpoint with items 0/1 (vless/1.2.3.4/443)
        assert types == [
            DedupMatchType.NONE,
            DedupMatchType.EXACT,
            DedupMatchType.ENDPOINT,
            DedupMatchType.NONE,
        ]


# ===========================================================================
# Deduplicator endpoint collision tests
# ===========================================================================


class TestDeduplicatorEndpoint:
    """Tests for endpoint-based dedup in the Deduplicator."""

    def test_same_endpoint_different_creds_endpoint_collision(self) -> None:
        items = [_vless(user="u1"), _vless(user="u2")]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.ENDPOINT

    def test_same_endpoint_different_method_endpoint_collision(self) -> None:
        items = [
            _shadowsocks(method="aes-128-gcm"),
            _shadowsocks(method="aes-256-gcm"),
        ]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.ENDPOINT

    def test_different_endpoint_no_collision(self) -> None:
        items = [_vless(host="a.com", port=443), _vless(host="b.com", port=443)]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        assert all(r.match_type == DedupMatchType.NONE for r in results)

    def test_identical_after_endpoint_collision_is_exact(self) -> None:
        """A, B(diff creds, same endpoint), C(identical to B) -> C is EXACT vs B."""
        items = [
            _vless(user="u1"),
            _vless(user="u2"),
            _vless(user="u2"),
        ]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.ENDPOINT
        assert results[2].match_type == DedupMatchType.EXACT
        assert results[2].match_index == 1

    def test_endpoint_collision_references_first_occurrence(self) -> None:
        """A, B(same endpoint), C(same endpoint) -> C references A (index 0)."""
        items = [
            _vless(user="u1"),
            _vless(user="u2"),
            _vless(user="u3"),
        ]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_index == 0
        assert results[2].match_index == 0


# ===========================================================================
# Deduplicator fuzzy tests
# ===========================================================================


class TestDeduplicatorFuzzy:
    """Tests for fuzzy matching in the Deduplicator."""

    def test_fuzzy_match_detected(self) -> None:
        items = [_vless(fragment="Node1"), _vless(fragment="Node2")]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.FUZZY

    def test_fuzzy_not_if_exact_also_found(self) -> None:
        items = [
            _vless(fragment="A"),
            _vless(fragment="A"),
            _vless(fragment="B"),
        ]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.EXACT
        assert results[2].match_type == DedupMatchType.FUZZY


# ===========================================================================
# Security tests
# ===========================================================================


class TestSecurity:
    """Security-focused tests."""

    def test_fingerprint_does_not_expose_password(self) -> None:
        config = _trojan(password="super-secret-password")
        h = compute_content_hash(config)
        assert "super-secret" not in h
        assert "secret" not in h

    def test_fingerprint_does_not_expose_user(self) -> None:
        config = _vless(user="my-secret-uuid")
        h = compute_content_hash(config)
        assert "my-secret-uuid" not in h

    def test_dedup_result_match_reason_no_secrets(self) -> None:
        items = [_vless(user="secret-user"), _vless(user="secret-user")]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        for r in results:
            if r.match_reason:
                assert "secret-user" not in r.match_reason


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_input(self) -> None:
        dedup = Deduplicator()
        results = dedup.deduplicate([])
        assert results == []

    def test_single_item(self) -> None:
        dedup = Deduplicator()
        results = dedup.deduplicate([_vless()])
        assert len(results) == 1
        assert results[0].match_type == DedupMatchType.NONE

    def test_fuzzy_with_unique_nodes(self) -> None:
        items = [
            _vless(fragment="N1"),
            _vless(fragment="N2"),
            _vless(fragment="N3"),
        ]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        assert results[0].match_type == DedupMatchType.NONE
        assert results[1].match_type == DedupMatchType.FUZZY
        assert results[2].match_type == DedupMatchType.FUZZY

    def test_mixed_fuzzy_and_exact_and_unique(self) -> None:
        items = [
            _vless(user="u1", fragment="A"),
            _vless(user="u1", fragment="A"),
            _vless(user="u1", fragment="B"),
            _vless(user="u2", host="other.com"),
        ]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        types = [r.match_type for r in results]
        assert types == [
            DedupMatchType.NONE,
            DedupMatchType.EXACT,
            DedupMatchType.FUZZY,
            DedupMatchType.NONE,
        ]

    def test_result_has_content_hash(self) -> None:
        items = [_vless(), _vless()]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        assert results[0].content_hash is not None
        assert results[1].content_hash is not None
        assert results[0].content_hash == results[1].content_hash

    def test_result_has_endpoint_identity(self) -> None:
        items = [_vless()]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        assert results[0].endpoint is not None
        assert results[0].endpoint.protocol == "vless"
        assert results[0].endpoint.host == "1.2.3.4"
        assert results[0].endpoint.port == 443

    def test_match_index_references_survivor(self) -> None:
        items = [_vless(), _vless(), _vless()]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        assert results[0].match_index is None
        assert results[1].match_index == 0
        assert results[2].match_index == 0

    def test_endpoint_match_index(self) -> None:
        items = [_vless(user="u1"), _vless(user="u2")]
        dedup = Deduplicator()
        results = dedup.deduplicate(items)
        assert results[0].match_index is None
        assert results[1].match_index == 0
