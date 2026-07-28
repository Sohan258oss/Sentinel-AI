"""LLM access layer.

Every model call in the platform goes through ``LLMEngine``. Agents never
import a vendor SDK, never build a client, and never see a provider name. That
buys three things:

* **Swappability** — Gemini today, Claude or a local model tomorrow, one file.
* **Honesty** — when no model is reachable the engine raises
  :class:`LLMUnavailableError` instead of inventing an answer, and agents fall
  back to deterministic domain logic that is clearly marked ``degraded``.
* **Instrumentation** — call counts, latency and failures are captured in one
  place rather than sprinkled across twelve agents.
"""

from __future__ import annotations

import base64
import mimetypes
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.config import LLMProvider, settings
from app.core.exceptions import (
    ConfigurationError,
    LLMUnavailableError,
    StructuredOutputError,
)
from app.core.logging import get_logger
from app.core.resilience import CircuitBreaker, Stopwatch, with_retries

logger = get_logger(__name__)

TSchema = TypeVar("TSchema", bound=BaseModel)


class ModelTier(str):
    """Which class of model a call needs.

    Separating these lets us route cheap extraction to a fast model and genuine
    planning to a stronger one — a real cost lever at scale, and a one-line
    change per call site.
    """

    FAST = "fast"
    REASONING = "reasoning"


@dataclass
class LLMStats:
    calls: int = 0
    failures: int = 0
    total_latency_ms: int = 0
    by_agent: dict[str, int] = field(default_factory=dict)

    def record(self, agent: str, latency_ms: int, ok: bool) -> None:
        self.calls += 1
        self.total_latency_ms += latency_ms
        self.by_agent[agent] = self.by_agent.get(agent, 0) + 1
        if not ok:
            self.failures += 1


llm_stats = LLMStats()


class LLMEngine(ABC):
    """The only model interface the rest of the codebase knows about."""

    @property
    @abstractmethod
    def available(self) -> bool:
        """True when a real model can be reached."""

    @property
    @abstractmethod
    def descriptor(self) -> str:
        """Human-readable provider/model label for traces and the UI."""

    @abstractmethod
    async def structured(
        self,
        schema: type[TSchema],
        *,
        system: str,
        user: str,
        images: list[str | Path] | None = None,
        tier: str = ModelTier.FAST,
        agent: str = "unknown",
    ) -> TSchema:
        """Return a validated instance of ``schema``, or raise."""

    @abstractmethod
    async def text(
        self,
        *,
        system: str,
        user: str,
        images: list[str | Path] | None = None,
        tier: str = ModelTier.FAST,
        agent: str = "unknown",
    ) -> str:
        """Return free-form text."""


class UnavailableEngine(LLMEngine):
    """Used in offline mode or when no API key is configured.

    Deliberately raises rather than fabricating. Offline SentinelAI is a
    deterministic expert system, not a model pretending to be one.
    """

    def __init__(self, reason: str) -> None:
        self._reason = reason

    @property
    def available(self) -> bool:
        return False

    @property
    def descriptor(self) -> str:
        return f"unavailable ({self._reason})"

    async def structured(self, schema: type[TSchema], **kwargs: Any) -> TSchema:
        raise LLMUnavailableError(self._reason)

    async def text(self, **kwargs: Any) -> str:
        raise LLMUnavailableError(self._reason)


class LangChainEngine(LLMEngine):
    """Concrete engine backed by LangChain chat models."""

    def __init__(self, provider: LLMProvider, fast_model: str, reasoning_model: str) -> None:
        self._provider = provider
        self._model_names = {
            ModelTier.FAST: fast_model,
            ModelTier.REASONING: reasoning_model,
        }
        self._clients: dict[str, Any] = {}
        self._breaker = CircuitBreaker(name=f"llm:{provider.value}", failure_threshold=4)

    @property
    def available(self) -> bool:
        return not self._breaker.is_open

    @property
    def descriptor(self) -> str:
        return f"{self._provider.value}:{self._model_names[ModelTier.FAST]}"

    # -- Client construction -------------------------------------------------

    def _client(self, tier: str) -> Any:
        if tier in self._clients:
            return self._clients[tier]

        model_name = self._model_names.get(tier, self._model_names[ModelTier.FAST])
        client = self._build_client(model_name)
        self._clients[tier] = client
        return client

    def _build_client(self, model_name: str) -> Any:
        common = {
            "temperature": settings.llm_temperature,
            "max_retries": 0,  # retries are owned by our resilience layer
            "timeout": settings.llm_timeout_seconds,
        }

        if self._provider is LLMProvider.GEMINI:
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=settings.google_api_key,
                **common,
            )

        if self._provider is LLMProvider.ANTHROPIC:
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=model_name,
                api_key=settings.anthropic_api_key,
                max_tokens=4096,
                **common,
            )

        if self._provider is LLMProvider.OPENAI:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=model_name, api_key=settings.openai_api_key, **common
            )

        raise ConfigurationError(f"Unsupported LLM provider: {self._provider}")

    # -- Message assembly ----------------------------------------------------

    @staticmethod
    def _encode_image(path: str | Path) -> dict[str, Any]:
        file_path = Path(path)
        if not file_path.exists():
            raise StructuredOutputError(f"Image not found: {file_path}")
        mime = mimetypes.guess_type(file_path.name)[0] or "image/jpeg"
        payload = base64.b64encode(file_path.read_bytes()).decode()
        return {"type": "image_url", "image_url": f"data:{mime};base64,{payload}"}

    def _messages(
        self, system: str, user: str, images: list[str | Path] | None
    ) -> list[Any]:
        from langchain_core.messages import HumanMessage, SystemMessage

        if not images:
            return [SystemMessage(content=system), HumanMessage(content=user)]

        content: list[dict[str, Any]] = [{"type": "text", "text": user}]
        content.extend(self._encode_image(image) for image in images)
        return [SystemMessage(content=system), HumanMessage(content=content)]

    # -- Public API ----------------------------------------------------------

    async def structured(
        self,
        schema: type[TSchema],
        *,
        system: str,
        user: str,
        images: list[str | Path] | None = None,
        tier: str = ModelTier.FAST,
        agent: str = "unknown",
    ) -> TSchema:
        if self._breaker.is_open:
            raise LLMUnavailableError(f"{self.descriptor} circuit open")

        client = self._client(tier).with_structured_output(schema)
        messages = self._messages(system, user, images)
        watch = Stopwatch()

        async def call() -> TSchema:
            result = await client.ainvoke(messages)
            if isinstance(result, schema):
                return result
            if isinstance(result, dict):
                return schema.model_validate(result)
            raise StructuredOutputError(
                f"{agent}: expected {schema.__name__}, got {type(result).__name__}"
            )

        try:
            value = await with_retries(
                call,
                attempts=settings.llm_max_retries,
                timeout=settings.llm_timeout_seconds,
                label=f"llm.structured:{agent}",
            )
        except Exception as exc:  # noqa: BLE001 - vendor boundary
            self._breaker.record_failure()
            llm_stats.record(agent, watch.elapsed_ms, ok=False)
            raise LLMUnavailableError(
                f"{self.descriptor} failed for {agent}: {exc}"
            ) from exc

        self._breaker.record_success()
        llm_stats.record(agent, watch.elapsed_ms, ok=True)
        logger.debug(
            "llm.structured.ok",
            agent=agent,
            schema=schema.__name__,
            latency_ms=watch.elapsed_ms,
        )
        return value

    async def text(
        self,
        *,
        system: str,
        user: str,
        images: list[str | Path] | None = None,
        tier: str = ModelTier.FAST,
        agent: str = "unknown",
    ) -> str:
        if self._breaker.is_open:
            raise LLMUnavailableError(f"{self.descriptor} circuit open")

        client = self._client(tier)
        messages = self._messages(system, user, images)
        watch = Stopwatch()

        async def call() -> str:
            response = await client.ainvoke(messages)
            content = getattr(response, "content", response)
            if isinstance(content, list):  # multimodal responses come back chunked
                return "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            return str(content)

        try:
            value = await with_retries(
                call,
                attempts=settings.llm_max_retries,
                timeout=settings.llm_timeout_seconds,
                label=f"llm.text:{agent}",
            )
        except Exception as exc:  # noqa: BLE001 - vendor boundary
            self._breaker.record_failure()
            llm_stats.record(agent, watch.elapsed_ms, ok=False)
            raise LLMUnavailableError(
                f"{self.descriptor} failed for {agent}: {exc}"
            ) from exc

        self._breaker.record_success()
        llm_stats.record(agent, watch.elapsed_ms, ok=True)
        return value


@lru_cache
def get_llm_engine() -> LLMEngine:
    """Process-wide engine, chosen once from configuration."""
    if settings.offline_mode:
        logger.warning("llm.offline_mode", detail="deterministic fallbacks only")
        return UnavailableEngine("offline mode enabled")

    if settings.llm_provider is LLMProvider.MOCK:
        return UnavailableEngine("mock provider selected")

    if not settings.active_api_key:
        logger.warning(
            "llm.no_api_key",
            provider=settings.llm_provider.value,
            detail="running on deterministic fallbacks",
        )
        return UnavailableEngine(f"no API key for {settings.llm_provider.value}")

    try:
        engine = LangChainEngine(
            provider=settings.llm_provider,
            fast_model=settings.llm_model,
            reasoning_model=settings.llm_reasoning_model,
        )
        logger.info("llm.ready", provider=engine.descriptor)
        return engine
    except Exception as exc:  # noqa: BLE001 - startup must not crash the service
        logger.error("llm.init_failed", error=str(exc))
        return UnavailableEngine(f"initialisation failed: {exc}")
