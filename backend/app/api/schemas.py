"""API request/response contracts.

Kept separate from the domain schemas so the public HTTP surface can evolve
without forcing a change to the agents' internal types, and vice versa.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import SentinelModel
from app.schemas.enums import HazardType


class IncidentSubmission(SentinelModel):
    """Operator-facing incident report payload."""

    description: str = Field(min_length=3, max_length=4000)
    location_name: str = Field(min_length=1, max_length=200)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    district: str | None = None
    state: str | None = None
    population: int | None = Field(default=None, ge=0)
    declared_hazard: HazardType | None = None
    reported_casualties: int | None = Field(default=None, ge=0)
    people_affected_estimate: int | None = Field(default=None, ge=0)
    channel: str = "control_room"
    reporter_name: str | None = None
    verified: bool = False
    media_paths: list[str] = Field(default_factory=list)


class RunAccepted(SentinelModel):
    """Returned immediately on submission so the client can start streaming."""

    run_id: str
    incident_id: str
    stream_url: str
    status_url: str


class SubsystemStatus(SentinelModel):
    name: str
    available: bool
    detail: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SystemStatus(SentinelModel):
    """Honest capability report — drives the UI's degradation banners."""

    app: str
    version: str
    environment: str
    llm: SubsystemStatus
    vision: SubsystemStatus
    retrieval: SubsystemStatus
    registries: SubsystemStatus
    deterministic_mode: bool = Field(
        description="True when no model is reachable and agents run rule-based logic"
    )
    data_provenance: dict[str, Any] = Field(default_factory=dict)
    mapbox_token: str | None = None
