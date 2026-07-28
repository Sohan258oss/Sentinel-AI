"""The observability wire format.

Every node in the graph emits these. The frontend consumes them over SSE and
animates the command centre from them. Treating the trace as a first-class
schema — rather than log lines scraped later — is what makes the agent team
*visible* instead of a black box.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import Confidence, SentinelModel, utcnow
from app.schemas.enums import AgentRole, AgentStatus, TraceEventType


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class ToolInvocation(SentinelModel):
    """A single tool call, with enough detail to replay and audit it."""

    invocation_id: str = Field(default_factory=_new_id)
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_preview: str = Field(
        default="", description="Truncated result — full payloads stay out of the trace"
    )
    succeeded: bool = True
    used_fallback: bool = Field(
        default=False, description="True when live API was unavailable and seed data served"
    )
    latency_ms: int = 0
    error: str | None = None


class AgentTrace(SentinelModel):
    """One event on the operations feed."""

    event_id: str = Field(default_factory=_new_id)
    incident_id: str
    run_id: str
    sequence: int = 0
    timestamp: datetime = Field(default_factory=utcnow)

    event_type: TraceEventType
    agent: AgentRole
    status: AgentStatus = AgentStatus.RUNNING

    title: str = Field(description="Short label rendered on the timeline")
    detail: str = Field(default="", description="Reasoning text or result summary")

    tool_invocation: ToolInvocation | None = None
    confidence: Confidence | None = None
    latency_ms: int | None = None
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Structured extras for rich UI rendering"
    )

    def sse_event_name(self) -> str:
        return self.event_type.value


class RunMetrics(SentinelModel):
    """Aggregate telemetry for a completed graph run."""

    run_id: str
    incident_id: str
    started_at: datetime
    completed_at: datetime | None = None
    total_latency_ms: int = 0
    nodes_executed: int = 0
    tool_calls: int = 0
    fallbacks_used: int = 0
    retrieval_queries: int = 0
    reflection_cycles: int = 0
    llm_calls: int = 0
    errors: int = 0

    @property
    def degraded(self) -> bool:
        return self.fallbacks_used > 0 or self.errors > 0
