"""Resilience primitives.

A disaster platform that falls over when a third-party weather API rate-limits
is an ironic failure. Every outbound dependency is wrapped in these.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class CircuitBreaker:
    """Stop hammering a dependency that is clearly down.

    After ``failure_threshold`` consecutive failures the circuit opens and calls
    short-circuit to the fallback for ``reset_after_seconds``, then a single
    trial call is allowed through to test recovery.
    """

    name: str
    failure_threshold: int = 3
    reset_after_seconds: float = 60.0

    _failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.reset_after_seconds:
            # Half-open: allow one trial call through.
            self._opened_at = None
            self._failures = self.failure_threshold - 1
            logger.info("circuit.half_open", circuit=self.name)
            return False
        return True

    def record_success(self) -> None:
        if self._failures or self._opened_at:
            logger.info("circuit.closed", circuit=self.name)
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold and self._opened_at is None:
            self._opened_at = time.monotonic()
            logger.warning(
                "circuit.opened", circuit=self.name, failures=self._failures
            )


async def with_retries(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    timeout: float | None = None,
    label: str = "operation",
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Exponential backoff with jitter and a per-attempt timeout."""
    last_error: BaseException | None = None

    for attempt in range(1, attempts + 1):
        try:
            if timeout is not None:
                return await asyncio.wait_for(operation(), timeout=timeout)
            return await operation()
        except asyncio.CancelledError:
            raise
        except retry_on as exc:
            last_error = exc
            if attempt == attempts:
                break
            # Deterministic jitter keeps tests reproducible while still
            # de-synchronising concurrent agents hitting the same API.
            jitter = (hash((label, attempt)) % 100) / 1000.0
            delay = min(max_delay, base_delay * (2 ** (attempt - 1))) + jitter
            logger.warning(
                "retry.scheduled",
                label=label,
                attempt=attempt,
                of=attempts,
                delay_s=round(delay, 2),
                error=str(exc)[:200],
            )
            await asyncio.sleep(delay)

    assert last_error is not None
    logger.error("retry.exhausted", label=label, attempts=attempts, error=str(last_error)[:300])
    raise last_error


async def with_fallback(
    primary: Callable[[], Awaitable[T]],
    fallback: Callable[[], Awaitable[T]],
    *,
    label: str = "operation",
    breaker: CircuitBreaker | None = None,
    attempts: int = 2,
    timeout: float | None = 15.0,
) -> tuple[T, bool]:
    """Run ``primary``; on failure run ``fallback``.

    Returns ``(value, used_fallback)`` so callers can honestly mark degraded
    output rather than silently presenting seed data as live intelligence.
    """
    if breaker is not None and breaker.is_open:
        logger.info("fallback.circuit_open", label=label)
        return await fallback(), True

    try:
        value = await with_retries(
            primary, attempts=attempts, timeout=timeout, label=label
        )
    except Exception as exc:  # noqa: BLE001 - deliberate boundary
        if breaker is not None:
            breaker.record_failure()
        logger.warning("fallback.engaged", label=label, error=str(exc)[:200])
        return await fallback(), True

    if breaker is not None:
        breaker.record_success()
    return value, False


class Stopwatch:
    """Millisecond timing for trace events."""

    def __init__(self) -> None:
        self._start = time.perf_counter()

    @property
    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)

    def __enter__(self) -> "Stopwatch":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc: Any) -> None:
        return None
