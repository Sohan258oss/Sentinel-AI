"""Supply-depot and routing tools (SDG 9, SDG 17).

``estimate_route`` is intentionally a *model* rather than a map API call. During
a disaster the road network is exactly what has changed, so a routing service
trained on normal conditions is confidently wrong. We instead derive travel time
from distance, a terrain factor and an explicit hazard-degradation multiplier,
and we disclose the assumption. An honest estimate with stated assumptions beats
a precise-looking number that ignores the flood.
"""

from __future__ import annotations

from typing import Any, ClassVar

from app.core.exceptions import ToolExecutionError
from app.repositories.registry import depots
from app.schemas.common import GeoPoint
from app.schemas.enums import AgentRole, HazardType, ResourceType
from app.tools.base import SentinelTool, ToolResult

#: How much slower ground movement becomes under each hazard, empirically
#: informed by post-event reviews of Indian flood and cyclone responses.
HAZARD_SPEED_PENALTY: dict[HazardType, float] = {
    HazardType.FLOOD: 2.4,
    HazardType.URBAN_FLOOD: 2.6,
    HazardType.CYCLONE: 2.2,
    HazardType.LANDSLIDE: 3.0,
    HazardType.EARTHQUAKE: 2.8,
    HazardType.BUILDING_COLLAPSE: 1.6,
    HazardType.WILDFIRE: 1.9,
    HazardType.STRUCTURAL_FIRE: 1.3,
    HazardType.INDUSTRIAL_CHEMICAL: 1.7,
    HazardType.HEATWAVE: 1.1,
    HazardType.EPIDEMIC: 1.1,
    HazardType.TSUNAMI: 2.7,
    HazardType.DROUGHT: 1.0,
    HazardType.MASS_CASUALTY: 1.4,
    HazardType.UNKNOWN: 1.5,
}

BASE_ROAD_SPEED_KMH = 42.0


class DepotStockTool(SentinelTool):
    name: ClassVar[str] = "find_supply_depots"
    description: ClassVar[str] = (
        "Relief supply depots near a coordinate across all partner organisations "
        "(government, NDRF, municipal, NGO, hospital, volunteer), with available "
        "stock per resource type and mobilisation delay. Args: latitude (float), "
        "longitude (float), radius_km (float), resource_type (str, optional)."
    )
    allowed_roles: ClassVar[tuple[AgentRole, ...]] = (
        AgentRole.ALLOCATION,
        AgentRole.LOGISTICS,
        AgentRole.COMMANDER,
    )

    async def fetch_live(self, **kwargs: Any) -> ToolResult:
        raise ToolExecutionError(self.name, "no live inventory integration configured")

    async def fetch_fallback(self, **kwargs: Any) -> ToolResult:
        origin = GeoPoint(
            latitude=float(kwargs["latitude"]), longitude=float(kwargs["longitude"])
        )
        radius = float(kwargs.get("radius_km", 120.0))

        resource_filter: ResourceType | None = None
        raw_type = kwargs.get("resource_type")
        if raw_type:
            try:
                resource_filter = ResourceType(raw_type)
            except ValueError:
                resource_filter = None

        found = depots().near(origin, radius_km=radius, resource_type=resource_filter)

        totals: dict[str, int] = {}
        for depot in found:
            for stock in depot.stock:
                key = stock.resource_type.value
                totals[key] = totals.get(key, 0) + stock.available

        return ToolResult(
            data={
                "depot_count": len(found),
                "organizations": sorted({d.organization_type.value for d in found}),
                "aggregate_available": totals,
                "depots": [
                    {
                        "depot_id": d.depot_id,
                        "name": d.name,
                        "organization": d.organization,
                        "organization_type": d.organization_type.value,
                        "distance_km": round(origin.distance_km(d.point), 2),
                        "latitude": d.point.latitude,
                        "longitude": d.point.longitude,
                        "dispatch_delay_minutes": d.dispatch_delay_minutes,
                        "stock": {
                            s.resource_type.value: s.available for s in d.stock
                        },
                    }
                    for d in found
                ],
            },
            source="seeded depot registry (synthetic)",
        )


class RouteEstimateTool(SentinelTool):
    name: ClassVar[str] = "estimate_route"
    description: ClassVar[str] = (
        "Estimated ground travel time between two coordinates under current "
        "hazard conditions, accounting for road degradation. Returns distance, "
        "ETA in minutes and the degradation assumption used. Args: from_latitude, "
        "from_longitude, to_latitude, to_longitude (floats), hazard_type (str)."
    )
    allowed_roles: ClassVar[tuple[AgentRole, ...]] = (
        AgentRole.ALLOCATION,
        AgentRole.LOGISTICS,
        AgentRole.MEDICAL,
        AgentRole.INFRASTRUCTURE,
    )

    async def fetch_live(self, **kwargs: Any) -> ToolResult:
        raise ToolExecutionError(self.name, "live traffic routing not configured")

    async def fetch_fallback(self, **kwargs: Any) -> ToolResult:
        start = GeoPoint(
            latitude=float(kwargs["from_latitude"]),
            longitude=float(kwargs["from_longitude"]),
        )
        end = GeoPoint(
            latitude=float(kwargs["to_latitude"]),
            longitude=float(kwargs["to_longitude"]),
        )

        try:
            hazard = HazardType(kwargs.get("hazard_type", "unknown"))
        except ValueError:
            hazard = HazardType.UNKNOWN

        straight_line = start.distance_km(end)
        # Road distance exceeds great-circle distance; 1.35 is a standard
        # detour factor for Indian district road networks.
        road_km = straight_line * 1.35
        penalty = HAZARD_SPEED_PENALTY.get(hazard, 1.5)
        effective_speed = BASE_ROAD_SPEED_KMH / penalty
        eta_minutes = (road_km / effective_speed) * 60.0 if effective_speed else 0.0

        return ToolResult(
            data={
                "straight_line_km": round(straight_line, 2),
                "road_distance_km": round(road_km, 2),
                "eta_minutes": int(round(eta_minutes)),
                "effective_speed_kmh": round(effective_speed, 1),
                "hazard_degradation_factor": penalty,
                "assumption": (
                    f"Ground movement modelled at {effective_speed:.0f} km/h "
                    f"({penalty}x slower than baseline) due to {hazard.value}. "
                    "Not a live traffic reading."
                ),
            },
            source="hazard-adjusted routing model",
        )
