"""Specialist agent findings.

Every specialist returns a schema that shares the ``IntelligenceProduct`` base:
a headline, a confidence, explicit recommendations, and citations. Uniformity
here is what lets the Commander and the Reflection agent reason over findings
generically instead of special-casing twelve shapes.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import (
    Citation,
    Confidence,
    GeoPoint,
    Measure,
    SentinelModel,
)
from app.schemas.enums import AgentRole, DamageClass, Severity, Urgency


class Recommendation(SentinelModel):
    """An actionable instruction. Agents propose; the Commander disposes."""

    action: str = Field(description="Imperative, specific, executable by a human team")
    rationale: str
    urgency: Urgency = Urgency.URGENT
    owner: str = Field(
        default="incident_commander",
        description="Which organisation or role should execute this",
    )
    depends_on: list[str] = Field(default_factory=list)


class IntelligenceProduct(SentinelModel):
    """Common contract for every specialist agent's output."""

    agent: AgentRole
    headline: str = Field(max_length=200)
    confidence: Confidence = 0.6
    key_findings: list[str] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    metrics: list[Measure] = Field(default_factory=list)
    degraded: bool = Field(
        default=False,
        description="True when the agent ran on fallback data rather than live feeds",
    )


class RiverGauge(SentinelModel):
    """A hydrological observation point — the earliest hard signal of flooding."""

    gauge_id: str
    river: str
    station: str
    point: GeoPoint
    distance_km: float = 0.0
    current_level_m: float
    warning_level_m: float
    danger_level_m: float
    highest_recorded_m: float | None = None
    trend: str = "steady"
    rate_of_change_m_per_hr: float = 0.0
    upstream_dam: str | None = None
    dam_spill_active: bool = False

    @property
    def breaches_warning(self) -> bool:
        return self.current_level_m >= self.warning_level_m

    @property
    def breaches_danger(self) -> bool:
        return self.current_level_m >= self.danger_level_m

    @property
    def hours_to_danger(self) -> float | None:
        """Lead time before the danger mark, at the current rate of rise.

        This is the single most decision-relevant number in a flood: it tells
        the commander how long there is to evacuate.
        """
        if self.breaches_danger:
            return 0.0
        if self.rate_of_change_m_per_hr <= 0:
            return None
        return (self.danger_level_m - self.current_level_m) / self.rate_of_change_m_per_hr


class WeatherIntel(IntelligenceProduct):
    agent: AgentRole = AgentRole.WEATHER
    current_conditions: str = ""
    rainfall_mm_24h: float = 0.0
    forecast_rainfall_mm_24h: float = 0.0
    wind_speed_kmh: float = 0.0
    river_level_m: float | None = None
    river_danger_level_m: float | None = None
    flood_probability: Confidence = 0.0
    escalation_expected: bool = False
    forecast_narrative: str = ""
    safe_operating_window_hours: float | None = Field(
        default=None,
        description="How long conditions permit outdoor rescue operations",
    )


class DamageDetection(SentinelModel):
    """One finding from the vision subsystem."""

    damage_class: DamageClass
    confidence: Confidence
    detector: str = Field(description="cnn | yolo | vlm | ensemble")
    bounding_box: list[float] | None = Field(
        default=None, description="[x1, y1, x2, y2] in normalised image coordinates"
    )
    note: str | None = None


class VisionAssessment(SentinelModel):
    """Aggregate verdict across all imagery attached to an incident."""

    image_path: str
    detections: list[DamageDetection] = Field(default_factory=list)
    dominant_class: DamageClass = DamageClass.NO_DAMAGE
    severity_signal: Severity = Severity.MINOR
    description: str = ""
    models_used: list[str] = Field(default_factory=list)
    ensemble_agreement: Confidence = Field(
        default=0.0,
        description="How strongly the CNN, detector and VLM concur",
    )


class InfrastructureIntel(IntelligenceProduct):
    agent: AgentRole = AgentRole.INFRASTRUCTURE
    roads_blocked: list[str] = Field(default_factory=list)
    bridges_at_risk: list[str] = Field(default_factory=list)
    power_outage_areas: list[str] = Field(default_factory=list)
    water_supply_status: str = "unknown"
    telecom_status: str = "unknown"
    access_corridors: list[str] = Field(
        default_factory=list, description="Routes still viable for relief convoys"
    )
    vision_assessments: list[VisionAssessment] = Field(default_factory=list)
    structural_risk_score: Confidence = 0.0


class HospitalStatus(SentinelModel):
    facility_id: str
    name: str
    point: GeoPoint
    distance_km: float = 0.0
    total_beds: int = 0
    available_beds: int = 0
    icu_available: int = 0
    ventilators_available: int = 0
    blood_bank: bool = False
    trauma_capable: bool = False
    operational_status: str = "operational"

    @property
    def occupancy_ratio(self) -> float:
        if self.total_beds <= 0:
            return 1.0
        return 1.0 - (self.available_beds / self.total_beds)


class MedicalIntel(IntelligenceProduct):
    agent: AgentRole = AgentRole.MEDICAL
    casualty_projection: int = 0
    triage_categories: dict[str, int] = Field(
        default_factory=dict, description="red/yellow/green counts"
    )
    hospitals: list[HospitalStatus] = Field(default_factory=list)
    total_available_beds: int = 0
    bed_deficit: int = Field(
        default=0, description="Projected casualties minus reachable capacity"
    )
    ambulances_required: int = 0
    priority_medicines: list[str] = Field(default_factory=list)
    disease_outbreak_risk: Confidence = 0.0
    outbreak_watchlist: list[str] = Field(default_factory=list)


class ShelterSite(SentinelModel):
    shelter_id: str
    name: str
    point: GeoPoint
    distance_km: float = 0.0
    capacity: int = 0
    current_occupancy: int = 0
    has_medical_post: bool = False
    has_power_backup: bool = False
    accessible: bool = True
    flood_safe: bool = True

    @property
    def spare_capacity(self) -> int:
        return max(0, self.capacity - self.current_occupancy)


class ShelterIntel(IntelligenceProduct):
    agent: AgentRole = AgentRole.SHELTER
    people_to_shelter: int = 0
    shelters: list[ShelterSite] = Field(default_factory=list)
    total_spare_capacity: int = 0
    capacity_deficit: int = 0
    evacuation_routes: list[str] = Field(default_factory=list)
    vulnerable_groups: list[str] = Field(
        default_factory=list,
        description="Elderly, disabled, pregnant, children — SDG 11 equity lens",
    )


class KnowledgeBrief(IntelligenceProduct):
    """RAG output: doctrine and SOPs retrieved from verified documents."""

    agent: AgentRole = AgentRole.KNOWLEDGE
    query_used: str = ""
    applicable_sops: list[str] = Field(default_factory=list)
    mandated_actions: list[str] = Field(
        default_factory=list, description="Steps doctrine REQUIRES for this hazard"
    )
    prohibited_actions: list[str] = Field(default_factory=list)
    coordination_contacts: list[str] = Field(default_factory=list)
    retrieved_chunks: int = 0
