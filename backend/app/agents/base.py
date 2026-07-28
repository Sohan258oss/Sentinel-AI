"""Agent foundation.

Every agent in SentinelAI is a template-method implementation of one lifecycle::

    emit(started)
      -> gather()              # deterministic tool calls, always run
      -> reason()              # LLM structured output over the gathered evidence
           on failure -> fallback()   # deterministic domain logic
      -> remember()            # write to episodic memory
    emit(completed)

Why this shape:

* **Tools run before the model, not through it.** Letting an LLM decide whether
  to check hospital capacity means it sometimes doesn't. Evidence gathering is
  deterministic; judgement is the model's job. This also makes runs
  reproducible and dramatically cheaper.
* **Every agent has a real fallback.** Not a stub — actual domain logic that
  computes the same output type from the same evidence. With no API key the
  platform degrades into a deterministic expert system rather than failing.
  ``degraded=True`` propagates so the UI never passes rule-based output off as
  model reasoning.
* **Tracing is in the base class.** An agent author cannot forget to emit, so
  the live operations feed is complete by construction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from app.core.events import trace_bus
from app.core.exceptions import LLMUnavailableError
from app.core.llm import LLMEngine, ModelTier, get_llm_engine
from app.core.logging import get_logger
from app.core.resilience import Stopwatch
from app.memory.store import EpisodicEntry, MemoryStore, get_memory
from app.schemas.command import ActivationPlan
from app.schemas.common import SentinelModel
from app.schemas.enums import AgentRole, AgentStatus, TraceEventType
from app.schemas.incident import IncidentReport, SituationAssessment
from app.schemas.trace import AgentTrace
from app.tools import load_tools, registry

logger = get_logger(__name__)

TOutput = TypeVar("TOutput", bound=SentinelModel)


@dataclass
class AgentContext:
    """Everything an agent needs to do its job.

    Passed by the graph rather than assembled by the agent, so agents stay
    independently testable — construct a context, call run, assert on output.
    """

    report: IncidentReport
    run_id: str
    assessment: SituationAssessment | None = None
    activation_plan: ActivationPlan | None = None
    focus_question: str = ""
    revision_instruction: str | None = None
    cycle: int = 0
    #: Cross-agent findings available at fan-in (allocation, reflection, comms).
    findings: dict[str, Any] = field(default_factory=dict)

    @property
    def incident_id(self) -> str:
        return self.report.incident_id

    @property
    def latitude(self) -> float:
        return self.report.location.point.latitude

    @property
    def longitude(self) -> float:
        return self.report.location.point.longitude

    @property
    def hazard_value(self) -> str:
        if self.assessment:
            return self.assessment.hazard_type.value
        if self.report.declared_hazard:
            return self.report.declared_hazard.value
        return "unknown"

    def situation_brief(self) -> str:
        """Shared situational context injected into every specialist prompt."""
        lines = [
            f"INCIDENT: {self.incident_id}",
            f"LOCATION: {self.report.location.label} "
            f"({self.latitude:.4f}, {self.longitude:.4f})",
            f"REPORTED: {self.report.reported_at.isoformat()}",
            f"FIELD REPORT: {self.report.description}",
        ]
        if self.report.location.population:
            lines.append(f"AREA POPULATION: {self.report.location.population:,}")

        if self.assessment:
            a = self.assessment
            lines += [
                "",
                f"TRIAGE: {a.hazard_type.value} / severity {a.severity.value} "
                f"(confidence {a.confidence:.2f})",
                f"ASSESSMENT: {a.summary}",
                f"POPULATION AT RISK: {a.impact.population_at_risk:,}",
                f"NEEDING EVACUATION: {a.impact.people_requiring_evacuation:,}",
                f"NEEDING MEDICAL CARE: {a.impact.people_requiring_medical_care:,}",
                f"NEEDING SHELTER: {a.impact.people_requiring_shelter:,}",
                f"AFFECTED RADIUS: {a.impact.affected_radius_km} km",
            ]
            if a.immediate_risks:
                lines.append("IMMEDIATE RISKS: " + "; ".join(a.immediate_risks[:4]))
            if a.secondary_hazards:
                lines.append(
                    "CASCADING HAZARDS: "
                    + ", ".join(h.value for h in a.secondary_hazards)
                )
        return "\n".join(lines)


class BaseAgent(ABC, Generic[TOutput]):
    """Template-method base for every agent."""

    role: AgentRole
    #: Short label shown on the ops board.
    title: str = ""
    #: Which model class this agent's judgement warrants.
    tier: str = ModelTier.FAST

    def __init__(
        self,
        engine: LLMEngine | None = None,
        memory: MemoryStore | None = None,
    ) -> None:
        self.engine = engine or get_llm_engine()
        self.memory = memory or get_memory()
        load_tools()

    # -- Subclass contract ---------------------------------------------------

    @property
    @abstractmethod
    def output_schema(self) -> type[TOutput]:
        """The structured type this agent must produce."""

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Role definition, standards and constraints for this agent."""

    async def gather(self, ctx: AgentContext) -> dict[str, Any]:
        """Deterministically collect evidence via tools. Override as needed."""
        return {}

    @abstractmethod
    def build_prompt(self, ctx: AgentContext, evidence: dict[str, Any]) -> str:
        """Compose the user message from context and gathered evidence."""

    @abstractmethod
    def fallback(self, ctx: AgentContext, evidence: dict[str, Any]) -> TOutput:
        """Deterministic domain logic used when no model is available."""

    def images_for(self, ctx: AgentContext) -> list[str] | None:
        """Override to send incident imagery to a multimodal model."""
        return None

    def summarise(self, output: TOutput) -> str:
        """One-line summary written into episodic memory and the trace."""
        for attribute in ("headline", "command_intent", "public_alert_headline"):
            value = getattr(output, attribute, None)
            if value:
                return str(value)
        return f"{self.role.value} completed"

    # -- Tracing helpers -----------------------------------------------------

    async def emit(
        self,
        ctx: AgentContext,
        event_type: TraceEventType,
        title: str,
        *,
        detail: str = "",
        status: AgentStatus = AgentStatus.RUNNING,
        confidence: float | None = None,
        latency_ms: int | None = None,
        payload: dict[str, Any] | None = None,
        tool_invocation: Any = None,
    ) -> None:
        await trace_bus.publish(
            AgentTrace(
                incident_id=ctx.incident_id,
                run_id=ctx.run_id,
                event_type=event_type,
                agent=self.role,
                status=status,
                title=title,
                detail=detail,
                confidence=confidence,
                latency_ms=latency_ms,
                payload=payload or {},
                tool_invocation=tool_invocation,
            )
        )

    async def call_tool(
        self, ctx: AgentContext, tool_name: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Invoke a tool with full trace emission. Returns its data payload."""
        tool = registry.get(tool_name)
        await self.emit(
            ctx,
            TraceEventType.TOOL_CALL,
            f"Calling {tool_name}",
            detail=tool.description[:160],
            payload={"tool": tool_name},
        )

        result, record = await tool.invoke(**kwargs)

        await self.emit(
            ctx,
            TraceEventType.TOOL_RESULT,
            f"{tool_name} returned",
            detail=result.preview(),
            latency_ms=result.latency_ms,
            tool_invocation=record,
            payload={
                "tool": tool_name,
                "used_fallback": result.used_fallback,
                "source": result.source,
            },
        )
        return result.data

    # -- Lifecycle -----------------------------------------------------------

    async def run(self, ctx: AgentContext) -> TOutput:
        watch = Stopwatch()
        await self.emit(
            ctx,
            TraceEventType.NODE_STARTED,
            self.title or self.role.value.replace("_", " ").title(),
            detail=ctx.focus_question or "Standing up specialist analysis",
            status=AgentStatus.RUNNING,
        )

        try:
            evidence = await self.gather(ctx)
        except Exception as exc:  # noqa: BLE001 - evidence gathering is best-effort
            logger.error("agent.gather_failed", agent=self.role.value, error=str(exc)[:300])
            await self.emit(
                ctx,
                TraceEventType.ERROR,
                "Evidence gathering degraded",
                detail=str(exc)[:300],
                status=AgentStatus.DEGRADED,
            )
            evidence = {}

        output, degraded, reason = await self._reason(ctx, evidence)

        if hasattr(output, "degraded") and degraded:
            try:
                output.degraded = True  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 - schema may not allow assignment
                pass

        summary = self.summarise(output)
        self.memory.remember(
            EpisodicEntry(
                incident_id=ctx.incident_id,
                run_id=ctx.run_id,
                agent=self.role,
                summary=summary,
                detail=reason or "",
                confidence=float(getattr(output, "confidence", 0.5) or 0.5),
            )
        )

        await self.emit(
            ctx,
            TraceEventType.NODE_COMPLETED,
            summary,
            detail=reason or "",
            status=AgentStatus.DEGRADED if degraded else AgentStatus.COMPLETED,
            confidence=float(getattr(output, "confidence", 0.5) or 0.5),
            latency_ms=watch.elapsed_ms,
            payload={"degraded": degraded},
        )
        return output

    async def _reason(
        self, ctx: AgentContext, evidence: dict[str, Any]
    ) -> tuple[TOutput, bool, str]:
        """LLM path with deterministic fallback. Returns (output, degraded, note)."""
        if not self.engine.available:
            output = self.fallback(ctx, evidence)
            await self.emit(
                ctx,
                TraceEventType.REASONING,
                "Deterministic analysis (no model available)",
                detail=(
                    "Rule-based domain logic applied. Output is computed from "
                    "tool evidence, not model reasoning."
                ),
                status=AgentStatus.DEGRADED,
            )
            return output, True, "deterministic fallback: no LLM configured"

        prompt = self.build_prompt(ctx, evidence)
        try:
            output = await self.engine.structured(
                self.output_schema,
                system=self.system_prompt,
                user=prompt,
                images=self.images_for(ctx),
                tier=self.tier,
                agent=self.role.value,
            )
            await self.emit(
                ctx,
                TraceEventType.REASONING,
                "Analysis complete",
                detail=self.summarise(output),
                confidence=float(getattr(output, "confidence", 0.5) or 0.5),
            )
            return output, False, ""
        except LLMUnavailableError as exc:
            logger.warning("agent.llm_unavailable", agent=self.role.value, error=str(exc)[:200])
            output = self.fallback(ctx, evidence)
            await self.emit(
                ctx,
                TraceEventType.REASONING,
                "Model unavailable — deterministic analysis applied",
                detail=str(exc)[:240],
                status=AgentStatus.DEGRADED,
            )
            return output, True, f"deterministic fallback: {exc}"
        except Exception as exc:  # noqa: BLE001 - never let one agent kill the run
            logger.error("agent.reason_failed", agent=self.role.value, error=str(exc)[:300])
            output = self.fallback(ctx, evidence)
            await self.emit(
                ctx,
                TraceEventType.ERROR,
                "Analysis failed — deterministic analysis applied",
                detail=str(exc)[:240],
                status=AgentStatus.DEGRADED,
            )
            return output, True, f"error fallback: {exc}"
