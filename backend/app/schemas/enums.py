"""Controlled vocabularies.

These enums are deliberately shared between the LLM structured-output schemas,
the REST API and the frontend. One vocabulary, no translation layers, no
stringly-typed drift between the model's answer and the operator's screen.
"""

from __future__ import annotations

from enum import Enum


class HazardType(str, Enum):
    FLOOD = "flood"
    URBAN_FLOOD = "urban_flood"
    CYCLONE = "cyclone"
    EARTHQUAKE = "earthquake"
    WILDFIRE = "wildfire"
    STRUCTURAL_FIRE = "structural_fire"
    LANDSLIDE = "landslide"
    HEATWAVE = "heatwave"
    BUILDING_COLLAPSE = "building_collapse"
    INDUSTRIAL_CHEMICAL = "industrial_chemical"
    EPIDEMIC = "epidemic"
    TSUNAMI = "tsunami"
    DROUGHT = "drought"
    MASS_CASUALTY = "mass_casualty"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    """INSARAG/NDMA-style escalation ladder."""

    INFORMATIONAL = "informational"
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"
    CATASTROPHIC = "catastrophic"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]

    @property
    def color(self) -> str:
        return _SEVERITY_COLOR[self]

    @classmethod
    def from_rank(cls, rank: int) -> "Severity":
        clamped = max(0, min(4, rank))
        return list(cls)[clamped]


_SEVERITY_RANK: dict[Severity, int] = {
    Severity.INFORMATIONAL: 0,
    Severity.MINOR: 1,
    Severity.MODERATE: 2,
    Severity.SEVERE: 3,
    Severity.CATASTROPHIC: 4,
}

_SEVERITY_COLOR: dict[Severity, str] = {
    Severity.INFORMATIONAL: "#38bdf8",
    Severity.MINOR: "#4ade80",
    Severity.MODERATE: "#facc15",
    Severity.SEVERE: "#fb923c",
    Severity.CATASTROPHIC: "#ef4444",
}


class IncidentPhase(str, Enum):
    """Disaster management lifecycle — the platform spans all four."""

    MITIGATION = "mitigation"
    PREPAREDNESS = "preparedness"
    RESPONSE = "response"
    RECOVERY = "recovery"


class IncidentStatus(str, Enum):
    RECEIVED = "received"
    ANALYZING = "analyzing"
    COORDINATING = "coordinating"
    ACTIVE = "active"
    STABILIZING = "stabilizing"
    RESOLVED = "resolved"
    FAILED = "failed"


class AgentRole(str, Enum):
    """Every node in the graph. The frontend renders this as the org chart."""

    INTAKE = "intake"
    SITUATION_ANALYSIS = "situation_analysis"
    COMMANDER = "commander"
    WEATHER = "weather"
    INFRASTRUCTURE = "infrastructure"
    MEDICAL = "medical"
    SHELTER = "shelter"
    KNOWLEDGE = "knowledge"
    LOGISTICS = "logistics"
    VOLUNTEER = "volunteer"
    ALLOCATION = "allocation"
    REFLECTION = "reflection"
    COMMUNICATION = "communication"


class AgentStatus(str, Enum):
    IDLE = "idle"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    FAILED = "failed"
    SKIPPED = "skipped"


class TraceEventType(str, Enum):
    """Wire protocol for the live operations feed."""

    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    RETRIEVAL = "retrieval"
    ROUTING_DECISION = "routing_decision"
    CRITIQUE = "critique"
    REVISION = "revision"
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    ERROR = "error"


class ResourceType(str, Enum):
    AMBULANCE = "ambulance"
    RESCUE_BOAT = "rescue_boat"
    FIRE_TENDER = "fire_tender"
    HELICOPTER = "helicopter"
    MEDICAL_TEAM = "medical_team"
    SEARCH_RESCUE_TEAM = "search_rescue_team"
    FOOD_PACKET = "food_packet"
    DRINKING_WATER = "drinking_water_litre"
    BLANKET = "blanket"
    TENT = "tent"
    MEDICINE_KIT = "medicine_kit"
    BLOOD_UNIT = "blood_unit"
    GENERATOR = "generator"
    WATER_PUMP = "water_pump"
    VOLUNTEER = "volunteer"


class Urgency(str, Enum):
    IMMEDIATE = "immediate"
    URGENT = "urgent"
    ROUTINE = "routine"


class OrganizationType(str, Enum):
    """SDG 17 — the platform is explicitly multi-stakeholder."""

    GOVERNMENT = "government"
    NDRF = "ndrf"
    MUNICIPAL = "municipal"
    HOSPITAL = "hospital"
    NGO = "ngo"
    POLICE = "police"
    FIRE_SERVICE = "fire_service"
    MILITARY = "military"
    VOLUNTEER_GROUP = "volunteer_group"
    PRIVATE_SECTOR = "private_sector"


class DamageClass(str, Enum):
    """Output vocabulary of the vision subsystem."""

    NO_DAMAGE = "no_damage"
    FLOODED_AREA = "flooded_area"
    FIRE = "fire"
    SMOKE = "smoke"
    COLLAPSED_BUILDING = "collapsed_building"
    DAMAGED_BUILDING = "damaged_building"
    BLOCKED_ROAD = "blocked_road"
    DAMAGED_BRIDGE = "damaged_bridge"
    STRANDED_PEOPLE = "stranded_people"
    VEHICLE_SUBMERGED = "vehicle_submerged"


class AudienceChannel(str, Enum):
    PUBLIC_ALERT = "public_alert"
    RESPONDER_BRIEF = "responder_brief"
    GOVERNMENT_SITREP = "government_sitrep"
    HOSPITAL_ADVISORY = "hospital_advisory"
    VOLUNTEER_TASKING = "volunteer_tasking"
