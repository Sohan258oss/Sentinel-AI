"""In-process trace bus.

Agents publish; the SSE endpoint subscribes. Two properties matter for a live
demo and neither is free:

1. **Replay** — an operator who opens the console mid-incident must still see
   everything that already happened, so every run keeps a bounded history that
   is replayed to late subscribers before they join the live feed.
2. **Backpressure isolation** — one stalled browser tab must never block the
   graph. Subscriber queues are bounded and drop-oldest; the agent side never
   awaits a slow consumer.

The interface is deliberately the shape of a message broker. Swapping this for
Redis pub/sub in a multi-worker deployment is a one-file change.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Final

from app.core.logging import get_logger
from app.schemas.trace import AgentTrace

logger = get_logger(__name__)

MAX_HISTORY: Final[int] = 500
SUBSCRIBER_QUEUE_SIZE: Final[int] = 256

#: Sentinel pushed onto subscriber queues to signal end-of-stream.
_CLOSED = object()


class TraceBus:
    """Fan-out event bus scoped by run id."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._history: dict[str, deque[AgentTrace]] = defaultdict(
            lambda: deque(maxlen=MAX_HISTORY)
        )
        self._sequence: dict[str, int] = defaultdict(int)
        self._closed_runs: set[str] = set()
        self._lock = asyncio.Lock()

    # -- Producer side -------------------------------------------------------

    async def publish(self, trace: AgentTrace) -> AgentTrace:
        """Record a trace and fan it out. Never blocks on slow consumers."""
        async with self._lock:
            self._sequence[trace.run_id] += 1
            trace.sequence = self._sequence[trace.run_id]
            self._history[trace.run_id].append(trace)
            targets = list(self._subscribers.get(trace.run_id, ()))

        for queue in targets:
            self._offer(queue, trace)
        return trace

    @staticmethod
    def _offer(queue: asyncio.Queue, item: object) -> None:
        """Drop-oldest enqueue. A lagging UI loses frames, not the run."""
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            with suppress(asyncio.QueueEmpty):
                queue.get_nowait()
            with suppress(asyncio.QueueFull):
                queue.put_nowait(item)

    async def close_run(self, run_id: str) -> None:
        """Signal completion so open SSE connections can terminate cleanly."""
        async with self._lock:
            self._closed_runs.add(run_id)
            targets = list(self._subscribers.get(run_id, ()))
        for queue in targets:
            self._offer(queue, _CLOSED)

    # -- Consumer side -------------------------------------------------------

    async def subscribe(
        self, run_id: str, *, replay: bool = True
    ) -> AsyncIterator[AgentTrace]:
        """Yield traces for a run: history first, then live events."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)

        async with self._lock:
            backlog = list(self._history[run_id]) if replay else []
            already_closed = run_id in self._closed_runs
            self._subscribers[run_id].add(queue)

        try:
            for trace in backlog:
                yield trace

            if already_closed:
                return

            while True:
                item = await queue.get()
                if item is _CLOSED:
                    return
                assert isinstance(item, AgentTrace)
                # Replayed events were already delivered above.
                if replay and backlog and item.sequence <= backlog[-1].sequence:
                    continue
                yield item
        finally:
            async with self._lock:
                self._subscribers[run_id].discard(queue)
                if not self._subscribers[run_id]:
                    self._subscribers.pop(run_id, None)

    # -- Introspection -------------------------------------------------------

    def history(self, run_id: str) -> list[AgentTrace]:
        return list(self._history.get(run_id, ()))

    def subscriber_count(self, run_id: str) -> int:
        return len(self._subscribers.get(run_id, ()))

    async def forget(self, run_id: str) -> None:
        """Release memory for a finished run."""
        async with self._lock:
            self._history.pop(run_id, None)
            self._sequence.pop(run_id, None)
            self._closed_runs.discard(run_id)


#: Process-wide bus. Injected rather than imported inside agents where possible.
trace_bus = TraceBus()
