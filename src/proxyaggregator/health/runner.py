"""Concurrent, multi-IP proxy health check runner.

The runner fans out to every candidate IP for a single proxy endpoint, uses
the first successful IP, and bounds all work with hard timeouts. Only IPs
produced by Phase 5 resolution (or direct literal IPs) are ever dialed, and
every dial is validated against the target policy first.
"""

from __future__ import annotations

import asyncio
import ipaddress
from dataclasses import dataclass
from typing import TYPE_CHECKING

from proxyaggregator.geoip.resolver import resolve_host
from proxyaggregator.health import errors
from proxyaggregator.health.checks import (
    DEFAULT_TIMEOUT,
    CheckError,
    check_tcp,
    close_quietly,
    upgrade_tls,
)
from proxyaggregator.health.models import (
    CheckStage,
    HealthCheckResult,
    HealthStatus,
)
from proxyaggregator.health.policy import TargetPolicy
from proxyaggregator.health.protocols import (
    check_http_connect,
    check_socks4,
    check_socks5,
)

if TYPE_CHECKING:
    from proxyaggregator.config.settings import Settings
    from proxyaggregator.geoip.enrich import EnrichmentResult
    from proxyaggregator.health.protocols import ProtocolCheckOutcome
    from proxyaggregator.parsers.base import ParseResult

# Protocol handshakes that complete a real on-wire exchange.
_PROTOCOL_CHECKERS = {
    "http": check_http_connect,
    "https": check_http_connect,
    "socks5": check_socks5,
    "socks4": check_socks4,
    "socks4a": check_socks4,
}

# Protocols whose transport is described by a TLS stage.
_TLS_TRANSPORT_PROTOCOLS = ("https", "trojan", "vless", "vmess")

# Statuses at which the multi-IP fan-out stops probing further addresses.
_EARLY_STOP_STATUSES = (HealthStatus.OK, HealthStatus.UNSUPPORTED)

# Aggregation priority: lower number = better result.
_STATUS_PRIORITY = {
    HealthStatus.OK: 0,
    HealthStatus.UNSUPPORTED: 1,
    HealthStatus.PROTOCOL_FAILURE: 2,
    HealthStatus.TLS_FAILURE: 3,
    HealthStatus.TIMEOUT: 4,
    HealthStatus.UNREACHABLE: 5,
    HealthStatus.DNS_FAILURE: 6,
    HealthStatus.DECLINED: 7,
    HealthStatus.SKIPPED: 8,
}


def _tc_priority(status: HealthStatus) -> int:
    return _STATUS_PRIORITY[status]


def protocol_uses_tls(parsed: ParseResult) -> bool:
    """Return True when this endpoint's transport wraps in TLS."""
    if parsed.protocol in ("https", "trojan"):
        return True
    if parsed.protocol not in _TLS_TRANSPORT_PROTOCOLS:
        return False
    # vless / vmess: security controls the TLS layer.
    return parsed.tls not in (None, "", "none")


def _host_is_literal_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class HealthEntry:
    """One proxy endpoint ready to be checked."""

    parsed: ParseResult
    enrichment: EnrichmentResult | None = None
    proxy_config_id: int | None = None


@dataclass
class _Attempt:
    """Per-IP check outcome used while aggregating a single endpoint."""

    ip: str
    status: HealthStatus
    connect_ms: float | None = None
    tls_ms: float | None = None
    proxy_ms: float | None = None
    tls_used: bool = False
    protocol_checked: bool = False
    tls_verified: bool = False
    error: str | None = None
    stage: CheckStage = CheckStage.TCP


def _status_from_error(code: str) -> HealthStatus:
    if code == errors.CONNECTION_TIMEOUT:
        return HealthStatus.TIMEOUT
    if code.startswith("tls."):
        return HealthStatus.TLS_FAILURE
    if code.startswith(("socks.", "http.", "protocol.")):
        return HealthStatus.PROTOCOL_FAILURE
    if code == errors.DNS_FAILURE:
        return HealthStatus.DNS_FAILURE
    return HealthStatus.UNREACHABLE


def _combine_latency(attempt: _Attempt) -> float | None:
    """Total latency for a completed attempt (connect + tls + protocol)."""
    parts = [p for p in (attempt.connect_ms, attempt.tls_ms, attempt.proxy_ms) if p is not None]
    if not parts:
        return None
    return round(sum(parts), 3)


class HealthRunner:
    """Run bounded, concurrent health checks over proxy endpoints."""

    def __init__(
        self,
        *,
        policy: TargetPolicy | None = None,
        timeout: float | None = None,
        concurrency: int | None = None,
        max_ips_per_host: int | None = None,
        verify_tls: bool = False,
        connect_target: tuple[str, int] | None = None,
    ) -> None:
        self.policy = policy or TargetPolicy()
        self.timeout = DEFAULT_TIMEOUT if timeout is None else timeout
        self.concurrency = 50 if concurrency is None else concurrency
        self.max_ips_per_host = 8 if max_ips_per_host is None else max_ips_per_host
        self.verify_tls = verify_tls
        self.connect_target = connect_target

    # ------------------------------------------------------------------ API

    async def check(self, entry: HealthEntry) -> HealthCheckResult:
        """Run a single bounded health check for one proxy endpoint."""
        candidates, raw_count = self._candidate_ips(entry)
        attempts = await self._probe_all(entry, candidates)
        best = _select_best(attempts)
        return self._build_result(entry, candidates, raw_count, attempts, best)

    async def check_all(self, entries: list[HealthEntry]) -> list[HealthCheckResult]:
        """Check many endpoints with a bounded worker pool."""
        semaphore = asyncio.Semaphore(self.concurrency)

        async def _worker(entry: HealthEntry) -> HealthCheckResult:
            async with semaphore:
                return await self.check(entry)

        return await asyncio.gather(*(_worker(entry) for entry in entries))

    # ------------------------------------------------------------ internals

    def _candidate_ips(self, entry: HealthEntry) -> tuple[list[str], int]:
        """Produce the policy-filtered, capped list of IPs to try.

        Returns ``(allowed, raw_count)`` where ``raw_count`` is the number of
        addresses found before policy filtering, so callers can distinguish
        DNS failure from policy declination.
        """
        parsed = entry.parsed
        if entry.enrichment is not None and entry.enrichment.all_resolved_ips:
            raw = list(entry.enrichment.all_resolved_ips)
        elif _host_is_literal_ip(parsed.host):
            raw = [str(ipaddress.ip_address(parsed.host))]
        else:
            resolved = resolve_host(parsed.host)
            if not resolved.resolved or not resolved.addresses:
                return [], 0
            raw = list(resolved.addresses)

        allowed, _rejected = self.policy.split_allowed(raw)
        return allowed[: self.max_ips_per_host], len(raw)

    async def _probe_all(self, entry: HealthEntry, ips: list[str]) -> list[_Attempt]:
        """Probe every candidate IP, stopping early on the first OK/UNSUPPORTED."""
        if not ips:
            return []

        async def _guard(ip: str) -> _Attempt:
            try:
                return await asyncio.wait_for(self._probe_ip(entry, ip), timeout=self.timeout)
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                return _Attempt(
                    ip=ip,
                    status=HealthStatus.TIMEOUT,
                    error=errors.CONNECTION_TIMEOUT,
                )
            except CheckError as exc:
                return _Attempt(
                    ip=ip,
                    status=_status_from_error(exc.code),
                    error=exc.code,
                )
            except Exception:
                return _Attempt(
                    ip=ip,
                    status=HealthStatus.UNREACHABLE,
                    error=errors.CONNECTION_ERROR,
                )

        tasks = [asyncio.create_task(_guard(ip)) for ip in ips]
        pending = set(tasks)
        finished: list[_Attempt] = []
        try:
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    finished.append(task.result())
                if pending and _select_best(finished).status in _EARLY_STOP_STATUSES:
                    break
        finally:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        return finished

    async def _probe_ip(self, entry: HealthEntry, ip: str) -> _Attempt:
        """Run TCP -> TLS -> protocol checks against a single candidate IP."""
        parsed = entry.parsed
        connect_ms: float | None = None
        tls_ms: float | None = None
        proxy_ms: float | None = None
        tls_used = False
        tls_verified = False
        stage = CheckStage.TCP

        writer = None
        try:
            reader, writer, connect_ms = await check_tcp(ip, parsed.port, timeout=self.timeout)

            if protocol_uses_tls(parsed):
                tls_used = True
                reader, writer, tls_ms, tls_verified = await upgrade_tls(
                    reader,
                    writer,
                    server_hostname=self._sni(parsed),
                    verify_cert=self.verify_tls,
                    timeout=self.timeout,
                )
                stage = CheckStage.TLS

            checker = _PROTOCOL_CHECKERS.get(parsed.protocol)
            if checker is None:
                # Transport is healthy but we have no true protocol client.
                return _Attempt(
                    ip=ip,
                    status=HealthStatus.UNSUPPORTED,
                    connect_ms=connect_ms,
                    tls_ms=tls_ms,
                    tls_used=tls_used,
                    tls_verified=tls_verified,
                    stage=stage,
                )

            target_host, target_port = self._connect_target(parsed)
            user, password = self._credentials(parsed)
            outcome: ProtocolCheckOutcome = await checker(
                reader,
                writer,
                target_host=target_host,
                target_port=target_port,
                user=user,
                password=password,
                timeout=self.timeout,
            )
            proxy_ms = outcome.proxy_ms
            stage = CheckStage.PROTOCOL

            if outcome.ok:
                return _Attempt(
                    ip=ip,
                    status=HealthStatus.OK,
                    connect_ms=connect_ms,
                    tls_ms=tls_ms,
                    proxy_ms=proxy_ms,
                    tls_used=tls_used,
                    protocol_checked=True,
                    tls_verified=tls_verified,
                    stage=stage,
                )
            return _Attempt(
                ip=ip,
                status=HealthStatus.PROTOCOL_FAILURE,
                connect_ms=connect_ms,
                tls_ms=tls_ms,
                proxy_ms=proxy_ms,
                tls_used=tls_used,
                protocol_checked=True,
                tls_verified=tls_verified,
                error=outcome.error,
                stage=stage,
            )
        finally:
            await close_quietly(writer)

    def _sni(self, parsed: ParseResult) -> str | None:
        if parsed.sni:
            return parsed.sni
        if not _host_is_literal_ip(parsed.host):
            return parsed.host
        return None

    def _connect_target(self, parsed: ParseResult) -> tuple[str, int]:
        if self.connect_target is not None:
            return self.connect_target
        # Ask the proxy to tunnel back to its own advertised endpoint. This
        # verifies the full protocol handshake without any external service.
        return parsed.host, parsed.port

    @staticmethod
    def _credentials(parsed: ParseResult) -> tuple[str | None, str | None]:
        return parsed.user, parsed.password

    def _build_result(
        self,
        entry: HealthEntry,
        candidates: list[str],
        raw_count: int,
        attempts: list[_Attempt],
        best: _Attempt,
    ) -> HealthCheckResult:
        parsed = entry.parsed
        if best.ip == "":
            if raw_count and not candidates:
                status, error = HealthStatus.DECLINED, errors.POLICY_DECLINED
            else:
                status, error = HealthStatus.DNS_FAILURE, errors.DNS_FAILURE
            return HealthCheckResult(
                proxy_config_id=entry.proxy_config_id,
                protocol=parsed.protocol,
                host=parsed.host,
                port=parsed.port,
                status=status,
                attempted_ips=list(candidates),
                error=error,
            )

        return HealthCheckResult(
            proxy_config_id=entry.proxy_config_id,
            protocol=parsed.protocol,
            host=parsed.host,
            port=parsed.port,
            status=best.status,
            checked_ip=best.ip,
            attempted_ips=list(candidates),
            stage=best.stage,
            connect_ms=best.connect_ms,
            tls_ms=best.tls_ms,
            proxy_ms=best.proxy_ms,
            latency_ms=_combine_latency(best),
            tls_used=best.tls_used,
            protocol_checked=best.protocol_checked,
            tls_verified=best.tls_verified,
            error=best.error,
        )


def _select_best(attempts: list[_Attempt]) -> _Attempt:
    """Pick the best result across all candidate-IP attempts."""
    if not attempts:
        return _Attempt(ip="", status=HealthStatus.DNS_FAILURE)
    return min(attempts, key=lambda a: _tc_priority(a.status))


def build_health_runner(settings: Settings) -> HealthRunner:
    """Construct a HealthRunner from application settings.

    Every retained health setting maps directly onto the runner: per-proxy
    timeout, worker concurrency, per-host IP cap, and TLS verification mode.
    ``connect_target`` is intentionally left ``None`` so the default remains
    the self-tunnel (the proxy is asked to tunnel back to its own advertised
    endpoint); there is deliberately no external health target configured.
    """
    return HealthRunner(
        timeout=settings.health_check_timeout,
        concurrency=settings.health_check_concurrency,
        max_ips_per_host=settings.health_check_max_ips_per_host,
        verify_tls=settings.health_check_verify_tls,
    )
