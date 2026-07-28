"""Incident intake and the triage assessment produced from it."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from app.schemas.common import Citation, Confidence, Location, SentinelModel, utcnow
from app.schemas.enums import (
    HazardType,
    IncidentPhase,
    IncidentStatus,
    Severity,
)


class ReportSource(SentinelModel):
    """Where an incident report came from — drives trust weighting."""

    channel: str = Field(
        description="citizen_app | control_room | sensor | social_media | field_responder"
    )
    reporter_name: str | None = None
    reporter_contact: str | None = None
    verified: bool = False
    trust_weight: Confidence = Field(
        default=0.5,
        description="How much the triage agent should lean on this report",
    )


class IncidentReport(SentinelModel):
    """The raw input to the whole system."""

    incident_id: str
    description: str = Field(
        min_length=3, description="Free-text account of what is happening"
    )
    location: Location
    reported_at: datetime = Field(default_factory=utcnow)
    source: ReportSource = Field(default_factory=lambda: ReportSource(channel="control_room"))
    media_paths: list[str] = Field(
        default_factory=list, description="Local paths to attached imagery"
    )
    reported_casualties: int | None = Field(default=None, ge=0)
    people_affected_estimate: int | None = Field(default=None, ge=0)
    phase: IncidentPhase = IncidentPhase.RESPONSE
    declared_hazard: HazardType | None = Field(
        default=None,
        description="Hazard as declared by the reporter; the agent may override it",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImpactEstimate(SentinelModel):
    """Quantified consequence — feeds the allocation optimiser directly."""

    population_at_risk: int = Field(ge=0)
    people_requiring_evacuation: int = Field(default=0, ge=0)
    people_requiring_medical_care: int = Field(default=0, ge=0)
    people_requiring_shelter: int = Field(default=0, ge=0)
    affected_radius_km: float = Field(default=2.0, gt=0, le=500)
    critical_infrastructure_at_risk: list[str] = Field(default_factory=list)
    estimated_duration_hours: float = Field(default=24.0, gt=0)

    @model_validator(mode="after")
    def _sub_populations_are_bounded(self) -> "ImpactEstimate":
        """A sub-population cannot exceed the population at risk.

        LLMs produce internally inconsistent numbers often enough that this
        needs to be a hard invariant rather than a hopeful prompt instruction.
        """
        ceiling = self.population_at_risk
        for field in (
            "people_requiring_evacuation",
            "people_requiring_medical_care",
            "people_requiring_shelter",
        ):
            if getattr(self, field) > ceiling:
                object.__setattr__(self, field, ceiling)
        return self


class SituationAssessment(SentinelModel):
    """Structured output of the Situation Analysis Agent — the triage verdict."""

    hazard_type: HazardType
    secondary_hazards: list[HazardType] = Field(
        default_factory=list,
        description="Cascading risks, e.g. flood -> epidemic",
    )
    severity: Severity
    confidence: Confidence
    headline: str = Field(
        max_length=160, description="One-line situation summary for the ops board"
    )
    summary: str = Field(description="3-5 sentence analytical assessment")
    impact: ImpactEstimate
    immediate_risks: list[str] = Field(
        default_factory=list, description="What gets worse in the next 6 hours"
    )
    information_gaps: list[str] = Field(
        default_factory=list,
        description="What the analyst does NOT know — drives further tasking",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Observations that justify the severity call",
    )
    citations: list[Citation] = Field(default_factory=list)

    @property
    def is_major(self) -> bool:
        return self.severity.rank >= Severity.SEVERE.rank


class IncidentSummary(SentinelModel):
    """Compact projection used by list views and the map layer."""

    incident_id: str
    headline: str
    hazard_type: HazardType
    severity: Severity
    status: IncidentStatus
    location: Location
    reported_at: datetime
    updated_at: datetime
    population_at_risk: int = 0
    agents_engaged: int = 0
