"""Weather and hydrology tools (SDG 13).

The offline fallback here is deliberately *derived* rather than invented. It
reads the seeded river-gauge network and back-solves plausible rainfall from
observed rates of rise and dam-spill status. That keeps the whole picture
internally consistent: the system never reports clear skies while simultaneously
showing a river climbing 0.2 m/hour. Inconsistent mock data is the fastest way
to destroy trust in a decision-support tool.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from app.core.config import settings
from app.core.exceptions import ToolExecutionError
from app.repositories.registry import river_gauges
from app.schemas.common import GeoPoint
from app.schemas.enums import AgentRole
from app.tools.base import SentinelTool, ToolResult

_OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
_OPENWEATHER_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"


def _deterministic_unit(*parts: Any) -> float:
    """Stable pseudo-random in [0, 1) — same inputs always give the same demo."""
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


class WeatherTool(SentinelTool):
    name: ClassVar[str] = "get_weather_conditions"
    description: ClassVar[str] = (
        "Current and 24-hour forecast weather for a coordinate: rainfall, wind, "
        "temperature, humidity and an assessment of whether conditions are "
        "deteriorating. Args: latitude (float), longitude (float), place (str)."
    )
    allowed_roles: ClassVar[tuple[AgentRole, ...]] = (
        AgentRole.WEATHER,
        AgentRole.SITUATION_ANALYSIS,
        AgentRole.COMMANDER,
    )

    def has_live_backend(self, **kwargs: Any) -> bool:
        return bool(settings.openweather_api_key) and not settings.offline_mode

    async def fetch_live(self, **kwargs: Any) -> ToolResult:
        latitude = float(kwargs["latitude"])
        longitude = float(kwargs["longitude"])
        params = {
            "lat": latitude,
            "lon": longitude,
            "appid": settings.openweather_api_key,
            "units": "metric",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            current = await client.get(_OPENWEATHER_URL, params=params)
            if current.status_code != 200:
                raise ToolExecutionError(self.name, f"HTTP {current.status_code}")
            now = current.json()

            forecast = await client.get(_OPENWEATHER_FORECAST_URL, params=params)
            slots = forecast.json().get("list", [])[:8] if forecast.status_code == 200 else []

        rain_now = float(now.get("rain", {}).get("1h", 0.0))
        forecast_rain = sum(float(s.get("rain", {}).get("3h", 0.0)) for s in slots)
        wind_kmh = float(now.get("wind", {}).get("speed", 0.0)) * 3.6

        return ToolResult(
            data={
                "conditions": now.get("weather", [{}])[0].get("description", "unknown"),
                "temperature_c": round(float(now.get("main", {}).get("temp", 0.0)), 1),
                "humidity_pct": now.get("main", {}).get("humidity", 0),
                "rainfall_mm_1h": round(rain_now, 1),
                "rainfall_mm_24h": round(rain_now * 6, 1),
                "forecast_rainfall_mm_24h": round(forecast_rain, 1),
                "wind_speed_kmh": round(wind_kmh, 1),
                "pressure_hpa": now.get("main", {}).get("pressure", 0),
                "escalating": forecast_rain > 60 or wind_kmh > 60,
                "observed_at": datetime.now(UTC).isoformat(),
            },
            source="openweathermap",
        )

    async def fetch_fallback(self, **kwargs: Any) -> ToolResult:
        latitude = float(kwargs["latitude"])
        longitude = float(kwargs["longitude"])
        place = kwargs.get("place", "unknown")
        origin = GeoPoint(latitude=latitude, longitude=longitude)

        nearby = river_gauges().near(origin, radius_km=80.0, limit=4)
        # Back-solve rainfall from catchment response. A river rising at
        # r m/hr in these basins corresponds to roughly 300-450 mm/24h of
        # upstream rainfall; we use a mid estimate and disclose it as modelled.
        max_rise = max((g.rate_of_change_m_per_hr for g in nearby), default=0.0)
        spill = any(g.dam_spill_active for g in nearby)

        jitter = _deterministic_unit(place, latitude, longitude, datetime.now(UTC).date())
        rainfall_24h = max(0.0, max_rise * 380.0 + jitter * 25.0)
        forecast_24h = rainfall_24h * (1.15 if max_rise > 0.1 else 0.6)
        wind_kmh = 18.0 + jitter * 30.0 + (15.0 if rainfall_24h > 120 else 0.0)

        if rainfall_24h > 200:
            conditions = "extremely heavy rainfall"
        elif rainfall_24h > 115:
            conditions = "very heavy rainfall"
        elif rainfall_24h > 64:
            conditions = "heavy rainfall"
        elif rainfall_24h > 15:
            conditions = "moderate rain"
        else:
            conditions = "light rain / overcast"

        return ToolResult(
            data={
                "conditions": conditions,
                "temperature_c": round(24.0 + jitter * 5.0, 1),
                "humidity_pct": int(78 + jitter * 18),
                "rainfall_mm_1h": round(rainfall_24h / 18.0, 1),
                "rainfall_mm_24h": round(rainfall_24h, 1),
                "forecast_rainfall_mm_24h": round(forecast_24h, 1),
                "wind_speed_kmh": round(wind_kmh, 1),
                "pressure_hpa": int(1004 - jitter * 8),
                "escalating": max_rise > 0.1 or spill,
                "upstream_dam_spill": spill,
                "modelled_from": [g.gauge_id for g in nearby],
                "observed_at": datetime.now(UTC).isoformat(),
            },
            source="hydrology-derived model (synthetic)",
        )


class RiverLevelTool(SentinelTool):
    name: ClassVar[str] = "get_river_levels"
    description: ClassVar[str] = (
        "River gauge readings near a coordinate: current level, warning and "
        "danger thresholds, rate of rise, upstream dam spill status, and hours "
        "of lead time before the danger mark is breached. "
        "Args: latitude (float), longitude (float), radius_km (float)."
    )
    allowed_roles: ClassVar[tuple[AgentRole, ...]] = (
        AgentRole.WEATHER,
        AgentRole.SITUATION_ANALYSIS,
        AgentRole.INFRASTRUCTURE,
    )

    def has_live_backend(self, **kwargs: Any) -> bool:
        # India-WRIS / CWC feeds require credentialed access; the seeded gauge
        # network stands in for them and is clearly labelled synthetic.
        return False

    async def fetch_live(self, **kwargs: Any) -> ToolResult:
        raise ToolExecutionError(self.name, "no live hydrology feed configured")

    async def fetch_fallback(self, **kwargs: Any) -> ToolResult:
        origin = GeoPoint(
            latitude=float(kwargs["latitude"]), longitude=float(kwargs["longitude"])
        )
        radius = float(kwargs.get("radius_km", 60.0))
        gauges = river_gauges().near(origin, radius_km=radius, limit=5)

        return ToolResult(
            data={
                "gauge_count": len(gauges),
                "any_danger_breach": any(g.breaches_danger for g in gauges),
                "any_warning_breach": any(g.breaches_warning for g in gauges),
                "dam_spill_active": any(g.dam_spill_active for g in gauges),
                "min_hours_to_danger": min(
                    (g.hours_to_danger for g in gauges if g.hours_to_danger is not None),
                    default=None,
                ),
                "gauges": [
                    {
                        "gauge_id": g.gauge_id,
                        "river": g.river,
                        "station": g.station,
                        "distance_km": g.distance_km,
                        "current_level_m": g.current_level_m,
                        "warning_level_m": g.warning_level_m,
                        "danger_level_m": g.danger_level_m,
                        "trend": g.trend,
                        "rate_m_per_hr": g.rate_of_change_m_per_hr,
                        "hours_to_danger": (
                            round(g.hours_to_danger, 1)
                            if g.hours_to_danger is not None
                            else None
                        ),
                        "breaches_warning": g.breaches_warning,
                        "breaches_danger": g.breaches_danger,
                        "upstream_dam": g.upstream_dam,
                        "dam_spill_active": g.dam_spill_active,
                    }
                    for g in gauges
                ],
            },
            source="seeded gauge network (synthetic)",
        )
