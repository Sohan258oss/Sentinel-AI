"""Incident orchestration.

Owns the lifecycle of a graph run: start it, track it, stream its traces, and
assemble the final :class:`OperationalPicture`. The API layer talks only to
this service, never to LangGraph directly, so the transport and the reasoning
engine stay independently replaceable.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.core.events import trace_bus
from app.core.exceptions import IncidentNotFoundError
from app.core.logging import get_logger, run_context
from app.core.resilience import Stopwatch
from app.graph.builder import get_compiled_graph
from app.graph.state import initial_state
from app.schemas.command import OperationalPicture
from app.schemas.enums import IncidentStatus
from app.schemas.incident import IncidentReport, IncidentSummary
from app.schemas.intelligence import Recommendation
from app.schemas.trace import AgentTrace, RunMetrics

logger = get_logger(__name__)


@dataclass
class RunRecord:
    """Everything known about one incident run."""

    run_id: str
    incident_id: str
    report: IncidentReport
    started_at: datetime
    task: asyncio.Task | None = None
    picture: OperationalPicture | None = None
    metrics: RunMetrics | None = None
    error: str | None = None
    status: IncidentStatus = IncidentStatus.RECEIVED

    @property
    def is_running(self) -> bool:
        return self.task is not None and not self.task.done()


class IncidentOrchestrator:
    """Runs incidents through the graph and keeps their results addressable."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._by_incident: dict[str, str] = {}
        self._lock = asyncio.Lock()

    # -- Submission ----------------------------------------------------------

    async def submit(self, report: IncidentReport) -> RunRecord:
        """Start a run in the background and return immediately.

        Returning before completion is what lets the UI subscribe to the trace
        stream and watch the agent team work, rather than staring at a spinner
        until a monolithic response arrives.
        """
        run_id = uuid.uuid4().hex[:12]
        record = RunRecord(
            run_id=run_id,
            incident_id=report.incident_id,
            report=report,
            started_at=datetime.now(UTC),
        )

        async with self._lock:
            self._runs[run_id] = record
            self._by_incident[report.incident_id] = run_id

        record.task = asyncio.create_task(self._execute(record))
        logger.info("orchestrator.submitted", incident_id=report.incident_id, run_id=run_id)
        return record

    async def run_sync(self, report: IncidentReport) -> OperationalPicture:
        """Run to completion and return the picture. Used by CLI and tests."""
        record = await self.submit(report)
        assert record.task is not None
        await record.task
        if record.error:
            raise RuntimeError(record.error)
        assert record.picture is not None
        return record.picture

    # -- Execution -----------------------------------------------------------

    async def _execute(self, record: RunRecord) -> None:
        watch = Stopwatch()
        metrics = RunMetrics(
            run_id=record.run_id,
            incident_id=record.incident_id,
            started_at=record.started_at,
        )

        with run_context(incident_id=record.incident_id, run_id=record.run_id):
            try:
                graph = get_compiled_graph()
                config = {
                    "configurable": {"thread_id": f"{record.incident_id}:{record.run_id}"},
                    "recursion_limit": 50,
                }

                final_state = await graph.ainvoke(
                    initial_state(record.report, record.run_id), config=config
                )

                record.picture = self._assemble(record, final_state)
                record.status = record.picture.status
                logger.info(
                    "orchestrator.completed",
                    incident_id=record.incident_id,
                    duration_ms=watch.elapsed_ms,
                    severity=record.picture.severity.value,
                )
            except Exception as exc:  # noqa: BLE001 - boundary of the whole run
                record.error = str(exc)
                record.status = IncidentStatus.FAILED
                metrics.errors += 1
                logger.error(
                    "orchestrator.failed",
                    incident_id=record.incident_id,
                    error=str(exc)[:500],
                    exc_info=True,
                )
            finally:
                history = trace_bus.history(record.run_id)
                metrics.completed_at = datetime.now(UTC)
                metrics.total_latency_ms = watch.elapsed_ms
                metrics.nodes_executed = sum(
                    1 for t in history if t.event_type.value == "node_completed"
                )
                metrics.tool_calls = sum(
                    1 for t in history if t.event_type.value == "tool_call"
                )
                metrics.fallbacks_used = sum(
                    1
                    for t in history
                    if t.tool_invocation is not None and t.tool_invocation.used_fallback
                )
                metrics.retrieval_queries = sum(
                    1 for t in history if t.event_type.value == "retrieval"
                )
                metrics.reflection_cycles = sum(
                    1 for t in history if t.event_type.value == "critique"
                )
                metrics.errors += sum(
                    1 for t in history if t.event_type.value == "error"
                )
                record.metrics = metrics

                await trace_bus.close_run(record.run_id)

    def _assemble(self, record: RunRecord, state: dict[str, Any]) -> OperationalPicture:
        findings = state.get("findings", {}) or {}

        picture = OperationalPicture(
            incident_id=record.incident_id,
            status=state.get("status", IncidentStatus.RESOLVED),
            created_at=record.started_at,
            completed_at=datetime.now(UTC),
            report=record.report,
            assessment=state.get("assessment"),
            activation_plan=state.get("activation_plan"),
            weather=findings.get("weather"),
            infrastructure=findings.get("infrastructure"),
            medical=findings.get("medical"),
            shelter=findings.get("shelter"),
            knowledge=findings.get("knowledge"),
            allocation_plan=state.get("allocation_plan"),
            reflection=state.get("reflection"),
            reflection_history=state.get("reflection_history", []),
            communications=state.get("communications"),
            errors=state.get("errors", []),
        )

        # Consolidate every specialist's recommendations, most urgent first, so
        # the commander gets one action list rather than five.
        consolidated: list[Recommendation] = []
        for key in ("weather", "infrastructure", "medical", "shelter", "knowledge"):
            product = findings.get(key)
            if product is not None:
                consolidated.extend(getattr(product, "recommendations", []))

        urgency_rank = {"immediate": 0, "urgent": 1, "routine": 2}
        consolidated.sort(key=lambda r: urgency_rank.get(r.urgency.value, 3))
        picture.consolidated_recommendations = consolidated

        return picture

    # -- Retrieval -----------------------------------------------------------

    def get_run(self, run_id: str) -> RunRecord:
        if run_id not in self._runs:
            raise IncidentNotFoundError(run_id)
        return self._runs[run_id]

    def get_by_incident(self, incident_id: str) -> RunRecord:
        run_id = self._by_incident.get(incident_id)
        if run_id is None:
            raise IncidentNotFoundError(incident_id)
        return self._runs[run_id]

    def list_runs(self) -> list[IncidentSummary]:
        summaries: list[IncidentSummary] = []
        for record in sorted(
            self._runs.values(), key=lambda r: r.started_at, reverse=True
        ):
            picture = record.picture
            assessment = picture.assessment if picture else None
            summaries.append(
                IncidentSummary(
                    incident_id=record.incident_id,
                    headline=(
                        assessment.headline
                        if assessment
                        else record.report.description[:120]
                    ),
                    hazard_type=(
                        assessment.hazard_type
                        if assessment
                        else (record.report.declared_hazard or _unknown_hazard())
                    ),
                    severity=(
                        assessment.severity if assessment else _informational()
                    ),
                    status=record.status,
                    location=record.report.location,
                    reported_at=record.report.reported_at,
                    updated_at=(
                        picture.completed_at or record.started_at
                        if picture
                        else record.started_at
                    ),
                    population_at_risk=(
                        assessment.impact.population_at_risk if assessment else 0
                    ),
                    agents_engaged=(
                        len(picture.activation_plan.dispatches)
                        if picture and picture.activation_plan
                        else 0
                    ),
                )
            )
        return summaries

    async def stream(self, run_id: str) -> AsyncIterator[AgentTrace]:
        """Live trace feed for a run, with replay of anything already emitted."""
        self.get_run(run_id)  # raises if unknown
        async for trace in trace_bus.subscribe(run_id, replay=True):
            yield trace

    def history(self, run_id: str) -> list[AgentTrace]:
        return trace_bus.history(run_id)


def _unknown_hazard():
    from app.schemas.enums import HazardType

    return HazardType.UNKNOWN


def _informational():
    from app.schemas.enums import Severity

    return Severity.INFORMATIONAL


_orchestrator: IncidentOrchestrator | None = None


def get_orchestrator() -> IncidentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = IncidentOrchestrator()
    return _orchestrator
