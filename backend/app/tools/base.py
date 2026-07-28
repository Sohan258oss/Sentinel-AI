"""Tool abstraction.

Three rules hold for every tool in the platform:

1. **A tool never raises at the agent boundary.** It returns a
   :class:`ToolResult` that is either live or fallback. An agent asking for
   hospital capacity during an earthquake must not crash because an API is down.
2. **Fallback is always disclosed.** ``used_fallback`` propagates into the trace
   and ultimately into the UI, so an operator can see which parts of the
   picture are live and which are simulated. Silent degradation would be a
   safety failure in a real deployment.
3. **Tools are capability-scoped.** Agents receive only the tools their role
   justifies, which keeps prompts small and makes the trace legible.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

from app.core.logging import get_logger
from app.core.resilience import CircuitBreaker, Stopwatch, with_fallback
from app.schemas.enums import AgentRole
from app.schemas.trace import ToolInvocation

logger = get_logger(__name__)


@dataclass
class ToolResult:
    """Uniform envelope returned by every tool."""

    data: dict[str, Any]
    source: str = "seed"
    used_fallback: bool = False
    latency_ms: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def preview(self, limit: int = 280) -> str:
        text = ", ".join(f"{k}={v}" for k, v in self.data.items())
        return text[:limit] + ("…" if len(text) > limit else "")


class SentinelTool(ABC):
    """Base class for all tools.

    Subclasses implement :meth:`fetch_live` (may raise) and :meth:`fetch_fallback`
    (must not raise). The base class owns retries, timeouts, circuit breaking,
    timing and trace-record construction so no subclass reimplements them.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    #: Which agents are permitted to call this tool.
    allowed_roles: ClassVar[tuple[AgentRole, ...]] = ()

    def __init__(self) -> None:
        self._breaker = CircuitBreaker(name=f"tool:{self.name}")

    # -- Subclass contract ---------------------------------------------------

    @abstractmethod
    async def fetch_live(self, **kwargs: Any) -> ToolResult:
        """Query the real external source. May raise."""

    @abstractmethod
    async def fetch_fallback(self, **kwargs: Any) -> ToolResult:
        """Deterministic offline answer. Must never raise."""

    def has_live_backend(self, **kwargs: Any) -> bool:
        """Whether a live call is even possible (e.g. an API key exists)."""
        return False

    # -- Public entry point --------------------------------------------------

    async def run(self, **kwargs: Any) -> ToolResult:
        watch = Stopwatch()

        if not self.has_live_backend(**kwargs):
            result = await self._safe_fallback(**kwargs)
            result.used_fallback = True
            result.latency_ms = watch.elapsed_ms
            return result

        async def primary() -> ToolResult:
            return await self.fetch_live(**kwargs)

        async def secondary() -> ToolResult:
            return await self._safe_fallback(**kwargs)

        result, used_fallback = await with_fallback(
            primary,
            secondary,
            label=f"tool:{self.name}",
            breaker=self._breaker,
            attempts=2,
            timeout=12.0,
        )
        result.used_fallback = result.used_fallback or used_fallback
        result.latency_ms = watch.elapsed_ms
        return result

    async def _safe_fallback(self, **kwargs: Any) -> ToolResult:
        try:
            return await self.fetch_fallback(**kwargs)
        except Exception as exc:  # noqa: BLE001 - last line of defence
            logger.error("tool.fallback_failed", tool=self.name, error=str(exc)[:300])
            return ToolResult(
                data={},
                source="none",
                used_fallback=True,
                error=f"{self.name} unavailable: {exc}",
            )

    async def invoke(self, **kwargs: Any) -> tuple[ToolResult, ToolInvocation]:
        """Run the tool and produce a trace record alongside the result."""
        result = await self.run(**kwargs)
        record = ToolInvocation(
            tool_name=self.name,
            arguments={k: _summarise(v) for k, v in kwargs.items()},
            result_preview=result.preview(),
            succeeded=result.ok,
            used_fallback=result.used_fallback,
            latency_ms=result.latency_ms,
            error=result.error,
        )
        logger.debug(
            "tool.invoked",
            tool=self.name,
            fallback=result.used_fallback,
            latency_ms=result.latency_ms,
            ok=result.ok,
        )
        return result, record


def _summarise(value: Any) -> Any:
    """Keep trace arguments small and JSON-safe."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (list, tuple)) and len(value) > 5:
        return f"[{len(value)} items]"
    if isinstance(value, str) and len(value) > 200:
        return value[:200] + "…"
    return value


@dataclass
class ToolRegistry:
    """Capability-scoped tool catalogue."""

    _tools: dict[str, SentinelTool] = field(default_factory=dict)

    def register(self, tool: SentinelTool) -> SentinelTool:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool name: {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> SentinelTool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    def for_role(self, role: AgentRole) -> list[SentinelTool]:
        return [t for t in self._tools.values() if role in t.allowed_roles]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def describe_for_role(self, role: AgentRole) -> str:
        """Prompt-ready tool manifest for a given agent."""
        tools = self.for_role(role)
        if not tools:
            return "(no tools available)"
        return "\n".join(f"- {t.name}: {t.description}" for t in tools)

    def as_langchain_tools(self, role: AgentRole) -> list[Any]:
        """Adapter for LangChain-native agents (ReAct / tool-calling loops)."""
        from langchain_core.tools import StructuredTool

        adapted: list[Any] = []
        for tool in self.for_role(role):
            adapted.append(
                StructuredTool.from_function(
                    coroutine=_bind(tool),
                    name=tool.name,
                    description=tool.description,
                )
            )
        return adapted


def _bind(tool: SentinelTool) -> Callable[..., Awaitable[dict[str, Any]]]:
    async def _call(**kwargs: Any) -> dict[str, Any]:
        result = await tool.run(**kwargs)
        return {"data": result.data, "used_fallback": result.used_fallback}

    return _call


#: Process-wide registry, populated by ``app.tools.load_tools()``.
registry = ToolRegistry()
