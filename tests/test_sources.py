"""Tests for source collector architecture."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from proxyaggregator.models.source import SourceSchema
from proxyaggregator.sources.base import BaseSourceCollector
from proxyaggregator.sources.http import HttpSourceCollector
from proxyaggregator.sources.orchestrator import SourceOrchestrator
from proxyaggregator.sources.registry import CollectorRegistry, get_registry
from proxyaggregator.sources.result import SourceResult, SourceResultStatus

# --- SourceResult tests ---


class TestSourceResult:
    """Tests for SourceResult model."""

    def test_success_result(self):
        result = SourceResult(
            source_name="Test Source",
            source_type="http",
            source_url="https://example.com/proxies.txt",
            status=SourceResultStatus.SUCCESS,
            content="line1\nline2\nline3",
            status_code=200,
            fetched_at=datetime.now(tz=UTC),
            content_length=19,
        )
        assert result.status == SourceResultStatus.SUCCESS
        assert result.content == "line1\nline2\nline3"
        assert result.status_code == 200
        assert result.error is None

    def test_error_result(self):
        result = SourceResult(
            source_name="Failed Source",
            source_type="http",
            source_url="https://example.com/missing",
            status=SourceResultStatus.ERROR,
            content="",
            fetched_at=datetime.now(tz=UTC),
            error="HTTP 404: Not Found",
        )
        assert result.status == SourceResultStatus.ERROR
        assert result.error == "HTTP 404: Not Found"

    def test_timeout_result(self):
        result = SourceResult(
            source_name="Slow Source",
            source_type="http",
            source_url="https://slow.example.com/proxies",
            status=SourceResultStatus.TIMEOUT,
            content="",
            fetched_at=datetime.now(tz=UTC),
            error="Connection timed out",
        )
        assert result.status == SourceResultStatus.TIMEOUT

    def test_empty_content_result(self):
        result = SourceResult(
            source_name="Empty Source",
            source_type="http",
            source_url="https://example.com/empty",
            status=SourceResultStatus.SUCCESS,
            content="",
            status_code=200,
            fetched_at=datetime.now(tz=UTC),
            content_length=0,
        )
        assert result.content == ""
        assert result.content_length == 0

    def test_is_success_property(self):
        result = SourceResult(
            source_name="S",
            source_type="http",
            source_url="https://example.com",
            status=SourceResultStatus.SUCCESS,
            content="data",
            fetched_at=datetime.now(tz=UTC),
        )
        assert result.is_success is True

    def test_is_failure_property(self):
        result = SourceResult(
            source_name="S",
            source_type="http",
            source_url="https://example.com",
            status=SourceResultStatus.ERROR,
            content="",
            fetched_at=datetime.now(tz=UTC),
            error="fail",
        )
        assert result.is_success is False


# --- BaseSourceCollector tests ---


class TestBaseSourceCollector:
    """Tests for BaseSourceCollector contract."""

    def test_cannot_instantiate_base(self):
        with pytest.raises(TypeError):
            BaseSourceCollector()  # type: ignore[abstract]

    def test_subclass_must_implement_collect(self):
        class IncompleteCollector(BaseSourceCollector):
            pass

        with pytest.raises(TypeError):
            IncompleteCollector()  # type: ignore[abstract]

    def test_subclass_with_collect_works(self):
        class CompleteCollector(BaseSourceCollector):
            @property
            def supported_type(self) -> str:
                return "test"

            async def collect(self, source: SourceSchema) -> SourceResult:
                return SourceResult(
                    source_name=source.name,
                    source_type=source.source_type,
                    source_url=source.url,
                    status=SourceResultStatus.SUCCESS,
                    content="",
                    fetched_at=datetime.now(tz=UTC),
                )

        collector = CompleteCollector()
        assert collector.supported_type == "test"


# --- HttpSourceCollector tests ---


class TestHttpSourceCollector:
    """Tests for HttpSourceCollector with mocked HTTP responses."""

    def test_supported_type(self):
        collector = HttpSourceCollector()
        assert collector.supported_type == "http"

    @pytest.mark.asyncio
    async def test_collect_success(self):
        source = SourceSchema(
            name="GitHub Raw",
            source_type="http",
            url="https://raw.githubusercontent.com/user/proxies/main/proxies.txt",
        )

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "vless://user@host1:443\nvmess://user@host2:80"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        collector = HttpSourceCollector(timeout=10, max_response_bytes=10 * 1024 * 1024)

        with patch(
            "proxyaggregator.sources.http.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await collector.collect(source)

        assert result.status == SourceResultStatus.SUCCESS
        assert result.content == "vless://user@host1:443\nvmess://user@host2:80"
        assert result.status_code == 200
        assert result.source_name == "GitHub Raw"
        assert result.source_url == source.url
        assert result.error is None

    @pytest.mark.asyncio
    async def test_collect_http_error_status(self):
        source = SourceSchema(
            name="404 Source",
            source_type="http",
            url="https://example.com/missing",
        )

        mock_response = AsyncMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.raise_for_status = MagicMock(side_effect=Exception("404 Client Error"))

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        collector = HttpSourceCollector(timeout=10, max_response_bytes=10 * 1024 * 1024)

        with patch(
            "proxyaggregator.sources.http.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await collector.collect(source)

        assert result.status == SourceResultStatus.ERROR
        assert result.error is not None
        assert "404" in result.error

    @pytest.mark.asyncio
    async def test_collect_timeout(self):
        import httpx

        source = SourceSchema(
            name="Timeout Source",
            source_type="http",
            url="https://slow.example.com/proxies",
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Connect timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        collector = HttpSourceCollector(timeout=5, max_response_bytes=10 * 1024 * 1024)

        with patch(
            "proxyaggregator.sources.http.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await collector.collect(source)

        assert result.status == SourceResultStatus.TIMEOUT
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_collect_network_error(self):
        import httpx

        source = SourceSchema(
            name="Network Error Source",
            source_type="http",
            url="https://unreachable.example.com/proxies",
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        collector = HttpSourceCollector(timeout=10, max_response_bytes=10 * 1024 * 1024)

        with patch(
            "proxyaggregator.sources.http.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await collector.collect(source)

        assert result.status == SourceResultStatus.ERROR
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_collect_empty_response(self):
        source = SourceSchema(
            name="Empty Source",
            source_type="http",
            url="https://example.com/empty",
        )

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        collector = HttpSourceCollector(timeout=10, max_response_bytes=10 * 1024 * 1024)

        with patch(
            "proxyaggregator.sources.http.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await collector.collect(source)

        assert result.status == SourceResultStatus.SUCCESS
        assert result.content == ""
        assert result.content_length == 0

    @pytest.mark.asyncio
    async def test_collect_redirect_followed(self):
        source = SourceSchema(
            name="Redirect Source",
            source_type="http",
            url="https://example.com/redirect",
        )

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "final content"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        collector = HttpSourceCollector(timeout=10, max_response_bytes=10 * 1024 * 1024)

        with patch(
            "proxyaggregator.sources.http.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await collector.collect(source)

        assert result.status == SourceResultStatus.SUCCESS
        assert result.content == "final content"

    @pytest.mark.asyncio
    async def test_collect_truncates_large_response(self):
        source = SourceSchema(
            name="Large Source",
            source_type="http",
            url="https://example.com/huge",
        )

        large_content = "x" * 2000

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = large_content
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        collector = HttpSourceCollector(timeout=10, max_response_bytes=1000)

        with patch(
            "proxyaggregator.sources.http.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await collector.collect(source)

        assert result.status == SourceResultStatus.SUCCESS
        assert len(result.content) <= 1000


# --- CollectorRegistry tests ---


class TestCollectorRegistry:
    """Tests for collector registry."""

    def test_register_and_get(self):
        registry = CollectorRegistry()

        class DummyCollector(BaseSourceCollector):
            @property
            def supported_type(self) -> str:
                return "dummy"

            async def collect(self, source: SourceSchema) -> SourceResult:
                raise NotImplementedError

        collector = DummyCollector()
        registry.register(collector)

        assert registry.get("dummy") is collector

    def test_get_unknown_returns_none(self):
        registry = CollectorRegistry()
        assert registry.get("nonexistent") is None

    def test_register_overwrites(self):
        registry = CollectorRegistry()

        class CollectorA(BaseSourceCollector):
            @property
            def supported_type(self) -> str:
                return "x"

            async def collect(self, source: SourceSchema) -> SourceResult:
                raise NotImplementedError

        class CollectorB(BaseSourceCollector):
            @property
            def supported_type(self) -> str:
                return "x"

            async def collect(self, source: SourceSchema) -> SourceResult:
                raise NotImplementedError

        registry.register(CollectorA())
        registry.register(CollectorB())

        assert isinstance(registry.get("x"), CollectorB)

    def test_list_types(self):
        registry = CollectorRegistry()

        class C1(BaseSourceCollector):
            @property
            def supported_type(self) -> str:
                return "a"

            async def collect(self, source: SourceSchema) -> SourceResult:
                raise NotImplementedError

        class C2(BaseSourceCollector):
            @property
            def supported_type(self) -> str:
                return "b"

            async def collect(self, source: SourceSchema) -> SourceResult:
                raise NotImplementedError

        registry.register(C1())
        registry.register(C2())

        types = registry.supported_types
        assert set(types) == {"a", "b"}

    def test_default_registry_has_http(self):
        registry = get_registry()
        assert registry.get("http") is not None


# --- SourceOrchestrator tests ---


class TestSourceOrchestrator:
    """Tests for the source collection orchestrator."""

    def _make_source(self, name: str, url: str, source_type: str = "http") -> SourceSchema:
        return SourceSchema(name=name, source_type=source_type, url=url)

    def _make_result(
        self,
        name: str,
        url: str,
        content: str,
        status: SourceResultStatus = SourceResultStatus.SUCCESS,
    ) -> SourceResult:
        return SourceResult(
            source_name=name,
            source_type="http",
            source_url=url,
            status=status,
            content=content,
            fetched_at=datetime.now(tz=UTC),
            status_code=200 if status == SourceResultStatus.SUCCESS else None,
        )

    @pytest.mark.asyncio
    async def test_collect_single_source(self):
        source = self._make_source("Test", "https://example.com/proxies")
        expected = self._make_result("Test", "https://example.com/proxies", "data")

        class FakeCollector(BaseSourceCollector):
            @property
            def supported_type(self) -> str:
                return "http"

            async def collect(self, source: SourceSchema) -> SourceResult:
                return expected

        registry = CollectorRegistry()
        registry.register(FakeCollector())

        orchestrator = SourceOrchestrator(registry=registry)
        results = await orchestrator.collect_sources([source])

        assert len(results) == 1
        assert results[0].content == "data"

    @pytest.mark.asyncio
    async def test_collect_multiple_sources(self):
        sources = [
            self._make_source("S1", "https://a.com/proxies"),
            self._make_source("S2", "https://b.com/proxies"),
            self._make_source("S3", "https://c.com/proxies"),
        ]

        class FakeCollector(BaseSourceCollector):
            @property
            def supported_type(self) -> str:
                return "http"

            async def collect(self, source: SourceSchema) -> SourceResult:
                return SourceResult(
                    source_name=source.name,
                    source_type="http",
                    source_url=source.url,
                    status=SourceResultStatus.SUCCESS,
                    content=f"content-{source.name}",
                    fetched_at=datetime.now(tz=UTC),
                )

        registry = CollectorRegistry()
        registry.register(FakeCollector())

        orchestrator = SourceOrchestrator(registry=registry)
        results = await orchestrator.collect_sources(sources)

        assert len(results) == 3
        contents = {r.source_name: r.content for r in results}
        assert contents["S1"] == "content-S1"
        assert contents["S2"] == "content-S2"
        assert contents["S3"] == "content-S3"

    @pytest.mark.asyncio
    async def test_partial_failure_continues(self):
        sources = [
            self._make_source("OK1", "https://ok1.com/proxies"),
            self._make_source("FAIL", "https://fail.com/proxies"),
            self._make_source("OK2", "https://ok2.com/proxies"),
        ]

        call_count = 0

        class FakeCollector(BaseSourceCollector):
            @property
            def supported_type(self) -> str:
                return "http"

            async def collect(self, source: SourceSchema) -> SourceResult:
                nonlocal call_count
                call_count += 1
                if source.name == "FAIL":
                    return SourceResult(
                        source_name=source.name,
                        source_type="http",
                        source_url=source.url,
                        status=SourceResultStatus.ERROR,
                        content="",
                        fetched_at=datetime.now(tz=UTC),
                        error="fail",
                    )
                return SourceResult(
                    source_name=source.name,
                    source_type="http",
                    source_url=source.url,
                    status=SourceResultStatus.SUCCESS,
                    content=f"data-{source.name}",
                    fetched_at=datetime.now(tz=UTC),
                )

        registry = CollectorRegistry()
        registry.register(FakeCollector())

        orchestrator = SourceOrchestrator(registry=registry)
        results = await orchestrator.collect_sources(sources)

        assert len(results) == 3
        successes = [r for r in results if r.is_success]
        failures = [r for r in results if not r.is_success]
        assert len(successes) == 2
        assert len(failures) == 1
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_unsupported_source_type_fails(self):
        source = self._make_source("Unknown", "https://x.com/data", source_type="telegram")

        registry = CollectorRegistry()
        orchestrator = SourceOrchestrator(registry=registry)
        results = await orchestrator.collect_sources([source])

        assert len(results) == 1
        assert results[0].status == SourceResultStatus.ERROR
        assert "unsupported" in results[0].error.lower()

    @pytest.mark.asyncio
    async def test_empty_source_list(self):
        registry = CollectorRegistry()
        orchestrator = SourceOrchestrator(registry=registry)
        results = await orchestrator.collect_sources([])
        assert results == []

    @pytest.mark.asyncio
    async def test_results_preserve_order(self):
        sources = [self._make_source(f"S{i}", f"https://s{i}.com/proxies") for i in range(5)]

        class FakeCollector(BaseSourceCollector):
            @property
            def supported_type(self) -> str:
                return "http"

            async def collect(self, source: SourceSchema) -> SourceResult:
                return SourceResult(
                    source_name=source.name,
                    source_type="http",
                    source_url=source.url,
                    status=SourceResultStatus.SUCCESS,
                    content="ok",
                    fetched_at=datetime.now(tz=UTC),
                )

        registry = CollectorRegistry()
        registry.register(FakeCollector())

        orchestrator = SourceOrchestrator(registry=registry)
        results = await orchestrator.collect_sources(sources)

        for i, result in enumerate(results):
            assert result.source_name == f"S{i}"
