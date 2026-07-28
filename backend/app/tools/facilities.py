"""Hospital and shelter tools (SDG 3, SDG 11).

These query the registry repositories rather than an external API, so there is
no "live" variant to fail — but they still go through :class:`SentinelTool` so
that timing, tracing and the fallback disclosure contract stay uniform across
every tool the agents can call.
"""

from __future__ import annotations

from typing import Any, ClassVar

from app.core.exceptions import ToolExecutionError
from app.repositories.registry import hospitals, shelters
from app.schemas.common import GeoPoint
from app.schemas.enums import AgentRole
from app.tools.base import SentinelTool, ToolResult


class HospitalCapacityTool(SentinelTool):
    name: ClassVar[str] = "find_hospital_capacity"
    description: ClassVar[str] = (
        "Hospitals near a coordinate with live bed, ICU, ventilator and blood-bank "
        "capacity, distance, and operational status. Use to decide casualty "
        "routing. Args: latitude (float), longitude (float), radius_km (float), "
        "trauma_only (bool), require_beds (bool)."
    )
    allowed_roles: ClassVar[tuple[AgentRole, ...]] = (
        AgentRole.MEDICAL,
        AgentRole.SITUATION_ANALYSIS,
        AgentRole.ALLOCATION,
    )

    async def fetch_live(self, **kwargs: Any) -> ToolResult:
        raise ToolExecutionError(self.name, "no live HMIS integration configured")

    async def fetch_fallback(self, **kwargs: Any) -> ToolResult:
        origin = GeoPoint(
            latitude=float(kwargs["latitude"]), longitude=float(kwargs["longitude"])
        )
        found = hospitals().near(
            origin,
            radius_km=float(kwargs.get("radius_km", 40.0)),
            limit=int(kwargs.get("limit", 8)),
            trauma_only=bool(kwargs.get("trauma_only", False)),
            require_beds=bool(kwargs.get("require_beds", False)),
        )

        return ToolResult(
            data={
                "hospital_count": len(found),
                "total_available_beds": sum(h.available_beds for h in found),
                "total_icu_available": sum(h.icu_available for h in found),
                "total_ventilators": sum(h.ventilators_available for h in found),
                "trauma_centres": sum(1 for h in found if h.trauma_capable),
                "blood_banks": sum(1 for h in found if h.blood_bank),
                "strained_facilities": [
                    h.name for h in found if h.operational_status != "operational"
                ],
                "hospitals": [
                    {
                        "facility_id": h.facility_id,
                        "name": h.name,
                        "distance_km": h.distance_km,
                        "latitude": h.point.latitude,
                        "longitude": h.point.longitude,
                        "total_beds": h.total_beds,
                        "available_beds": h.available_beds,
                        "icu_available": h.icu_available,
                        "ventilators_available": h.ventilators_available,
                        "blood_bank": h.blood_bank,
                        "trauma_capable": h.trauma_capable,
                        "operational_status": h.operational_status,
                        "occupancy_ratio": round(h.occupancy_ratio, 2),
                    }
                    for h in found
                ],
            },
            source="seeded hospital registry (synthetic)",
        )


class ShelterAvailabilityTool(SentinelTool):
    name: ClassVar[str] = "find_shelter_capacity"
    description: ClassVar[str] = (
        "Relief camps and shelters near a coordinate with capacity, current "
        "occupancy, spare capacity, medical post, power backup, accessibility "
        "and whether the site is itself flood-safe. Args: latitude (float), "
        "longitude (float), radius_km (float), flood_safe_only (bool)."
    )
    allowed_roles: ClassVar[tuple[AgentRole, ...]] = (
        AgentRole.SHELTER,
        AgentRole.SITUATION_ANALYSIS,
        AgentRole.ALLOCATION,
    )

    async def fetch_live(self, **kwargs: Any) -> ToolResult:
        raise ToolExecutionError(self.name, "no live camp-management integration")

    async def fetch_fallback(self, **kwargs: Any) -> ToolResult:
        origin = GeoPoint(
            latitude=float(kwargs["latitude"]), longitude=float(kwargs["longitude"])
        )
        found = shelters().near(
            origin,
            radius_km=float(kwargs.get("radius_km", 35.0)),
            limit=int(kwargs.get("limit", 10)),
            flood_safe_only=bool(kwargs.get("flood_safe_only", False)),
            accessible_only=bool(kwargs.get("accessible_only", False)),
        )

        # A shelter that is itself in the flood plain is a liability, not an
        # asset. Surfacing this separately is what turns a directory lookup
        # into an actual planning input.
        at_risk = [s for s in found if not s.flood_safe]
        unreachable = [s for s in found if not s.accessible]

        return ToolResult(
            data={
                "shelter_count": len(found),
                "total_capacity": sum(s.capacity for s in found),
                "total_spare_capacity": sum(s.spare_capacity for s in found),
                "safe_spare_capacity": sum(
                    s.spare_capacity for s in found if s.flood_safe and s.accessible
                ),
                "shelters_with_medical_post": sum(1 for s in found if s.has_medical_post),
                "shelters_at_flood_risk": [s.name for s in at_risk],
                "shelters_currently_unreachable": [s.name for s in unreachable],
                "shelters": [
                    {
                        "shelter_id": s.shelter_id,
                        "name": s.name,
                        "distance_km": s.distance_km,
                        "latitude": s.point.latitude,
                        "longitude": s.point.longitude,
                        "capacity": s.capacity,
                        "current_occupancy": s.current_occupancy,
                        "spare_capacity": s.spare_capacity,
                        "has_medical_post": s.has_medical_post,
                        "has_power_backup": s.has_power_backup,
                        "accessible": s.accessible,
                        "flood_safe": s.flood_safe,
                    }
                    for s in found
                ],
            },
            source="seeded shelter registry (synthetic)",
        )
