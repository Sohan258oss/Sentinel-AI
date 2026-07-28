"""Command-level schemas: routing plans, critique verdicts, and the final picture."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import Confidence, SentinelModel, utcnow
from app.schemas.enums import (
    AgentRole,
    AudienceChannel,
    IncidentStatus,
    Severity,
)
from app.schemas.incident import IncidentReport, SituationAssessment
from app.schemas.intelligence import (
    InfrastructureIntel,
    KnowledgeBrief,
    MedicalIntel,
    Recommendation,
    ShelterIntel,
    WeatherIntel,
)
from app.schemas.resources import AllocationPlan, VolunteerTask

#: Specialists the Commander is allowed to activate. Kept separate from
#: AgentRole so control-plane nodes (intake, reflection…) can never be routed to.
DISPATCHABLE_AGENTS: tuple[AgentRole, ...] = (
    AgentRole.WEATHER,
    AgentRole.INFRASTRUCTURE,
    AgentRole.MEDICAL,
    AgentRole.SHELTER,
    AgentRole.KNOWLEDGE,
)


class AgentDispatch(SentinelModel):
    """One line of the Commander's tasking order."""

    agent: AgentRole
    reason: str = Field(description="Why this specialist is warranted for THIS incident")
    priority: int = Field(default=2, ge=1, le=3, description="1 = highest")
    focus_question: str = Field(
        default="",
        description="The specific question this agent must answer",
    )


class ActivationPlan(SentinelModel):
    """Structured output of the Commander Agent — Pattern 5's routing decision.

    This object *is* the conditional branch: the graph reads ``dispatches`` and
    fans out to exactly those nodes, in parallel, for this incident only.
    """

    incident_id: str
    dispatches: list[AgentDispatch] = Field(default_factory=list)
    declined: list[AgentDispatch] = Field(
        default_factory=list,
        description="Agents explicitly NOT activated, with reasoning — shown in the UI",
    )
    command_intent: str = Field(
        default="",
        description="Commander's intent statement, in the military-doctrine sense",
    )
    escalate_to_state: bool = False
    escalation_reason: str | None = None

    @property
    def active_agents(self) -> list[AgentRole]:
        ordered = sorted(self.dispatches, key=lambda d: d.priority)
        return [d.agent for d in ordered]


class CritiqueFinding(SentinelModel):
    issue: str
    severity: str = Field(description="blocking | major | minor")
    affected_component: str
    suggested_fix: str


class ReflectionVerdict(SentinelModel):
    """Structured output of the Reflection Agent — the quality gate."""

    approved: bool
    overall_quality: Confidence
    findings: list[CritiqueFinding] = Field(default_factory=list)
    doctrine_compliance: Confidence = Field(
        default=0.5, description="Does the plan honour the retrieved SOPs?"
    )
    internal_consistency: Confidence = 0.5
    coverage_adequacy: Confidence = 0.5
    revision_instruction: str | None = Field(
        default=None, description="Concrete guidance fed back into allocation"
    )
    cycle: int = 0

    @property
    def has_blocking_issues(self) -> bool:
        return any(f.severity == "blocking" for f in self.findings)


class CommunicationArtifact(SentinelModel):
    """One audience-tailored message."""

    channel: AudienceChannel
    audience: str
    subject: str
    body: str
    language: str = "en"
    call_to_action: list[str] = Field(default_factory=list)


class CommunicationPackage(SentinelModel):
    """Structured output of the Communication Agent."""

    artifacts: list[CommunicationArtifact] = Field(default_factory=list)
    public_alert_headline: str = ""
    misinformation_guardrails: list[str] = Field(
        default_factory=list,
        description="Claims to pre-emptively debunk — a real disaster failure mode",
    )


class OperationalPicture(SentinelModel):
    """The single object the frontend renders. Everything the run produced."""

    incident_id: str
    status: IncidentStatus
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None

    report: IncidentReport
    assessment: SituationAssessment | None = None
    activation_plan: ActivationPlan | None = None

    weather: WeatherIntel | None = None
    infrastructure: InfrastructureIntel | None = None
    medical: MedicalIntel | None = None
    shelter: ShelterIntel | None = None
    knowledge: KnowledgeBrief | None = None

    allocation_plan: AllocationPlan | None = None
    volunteer_tasks: list[VolunteerTask] = Field(default_factory=list)
    reflection: ReflectionVerdict | None = None
    reflection_history: list[ReflectionVerdict] = Field(default_factory=list)
    communications: CommunicationPackage | None = None

    consolidated_recommendations: list[Recommendation] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def severity(self) -> Severity:
        return self.assessment.severity if self.assessment else Severity.INFORMATIONAL

    @property
    def duration_seconds(self) -> float | None:
        if not self.completed_at:
            return None
        return (self.completed_at - self.created_at).total_seconds()
