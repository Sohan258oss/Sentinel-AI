"""Weather & Climate Intelligence Agent (SDG 13).

Answers the question that governs every other decision in a flood or cyclone:
*how much time is left*. Lead time before a danger threshold determines whether
the correct action is evacuation or shelter-in-place.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.schemas.common import Measure
from app.schemas.enums import AgentRole, Urgency
from app.schemas.intelligence import Recommendation, WeatherIntel

SYSTEM_PROMPT = """\
You are the Meteorology and Hydrology Officer in an Emergency Operations Centre.

Your single most important output is TIME: how long before conditions become \
untenable, and whether a safe operating window exists for outdoor rescue.

Rules:
- Use ONLY the readings supplied. Never invent a measurement.
- Indian rainfall classification: 64.5-115.5 mm/24h is heavy, 115.6-204.4 is \
very heavy, above 204.4 is extremely heavy. Apply these thresholds explicitly.
- Rate of rise matters more than absolute river level. A gauge 1.5 m below \
danger rising at 0.25 m/hr gives roughly six hours; the same level static gives \
days.
- Upstream dam spill means a downstream surge is already committed and cannot \
be cancelled. Treat it as a certainty, not a risk.
- If readings come from a modelled fallback rather than a live station, say so \
plainly in your findings and lower your confidence.
- `safe_operating_window_hours` is when outdoor rescue can proceed with \
acceptable responder risk. Set it to 0 if conditions are already unsafe.
"""


class WeatherAgent(BaseAgent[WeatherIntel]):
    role = AgentRole.WEATHER
    title = "Weather & Climate Intelligence"

    @property
    def output_schema(self) -> type[WeatherIntel]:
        return WeatherIntel

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def gather(self, ctx: AgentContext) -> dict[str, Any]:
        weather = await self.call_tool(
            ctx,
            "get_weather_conditions",
            latitude=ctx.latitude,
            longitude=ctx.longitude,
            place=ctx.report.location.name,
        )
        rivers = await self.call_tool(
            ctx,
            "get_river_levels",
            latitude=ctx.latitude,
            longitude=ctx.longitude,
            radius_km=80.0,
        )
        return {"weather": weather, "rivers": rivers}

    def build_prompt(self, ctx: AgentContext, evidence: dict[str, Any]) -> str:
        weather = evidence.get("weather", {})
        rivers = evidence.get("rivers", {})

        lines = [
            ctx.situation_brief(),
            "",
            f"FOCUS QUESTION: {ctx.focus_question or 'Assess meteorological and hydrological risk.'}",
            "",
            "=== OBSERVATIONS ===",
            f"Conditions: {weather.get('conditions')}",
            f"Rainfall 24h observed: {weather.get('rainfall_mm_24h')} mm",
            f"Rainfall 24h forecast: {weather.get('forecast_rainfall_mm_24h')} mm",
            f"Wind: {weather.get('wind_speed_kmh')} km/h",
            f"Humidity: {weather.get('humidity_pct')}%",
            f"Pressure: {weather.get('pressure_hpa')} hPa",
            f"Deteriorating: {weather.get('escalating')}",
            f"Data source: {'MODELLED FALLBACK' if weather.get('modelled_from') else 'live station'}",
            "",
            "=== RIVER GAUGES ===",
        ]

        for gauge in rivers.get("gauges", []):
            lines.append(
                f"  {gauge['river']} @ {gauge['station']} ({gauge['distance_km']} km): "
                f"{gauge['current_level_m']}m | warning {gauge['warning_level_m']}m | "
                f"danger {gauge['danger_level_m']}m | {gauge['trend']} "
                f"{gauge['rate_m_per_hr']:+.2f} m/hr | "
                f"hours to danger: {gauge['hours_to_danger']} | "
                f"dam {gauge['upstream_dam']} spilling: {gauge['dam_spill_active']}"
            )
        if not rivers.get("gauges"):
            lines.append("  (no gauges within range)")

        lines += [
            "",
            "Produce the structured weather intelligence product. State the "
            "operating window and the escalation timeline explicitly.",
        ]
        return "\n".join(lines)

    def fallback(self, ctx: AgentContext, evidence: dict[str, Any]) -> WeatherIntel:
        weather = evidence.get("weather", {})
        rivers = evidence.get("rivers", {})

        observed = float(weather.get("rainfall_mm_24h", 0) or 0)
        forecast = float(weather.get("forecast_rainfall_mm_24h", 0) or 0)
        wind = float(weather.get("wind_speed_kmh", 0) or 0)
        gauges = rivers.get("gauges", [])
        lead_time = rivers.get("min_hours_to_danger")

        worst = max(gauges, key=lambda g: g["current_level_m"] / max(g["danger_level_m"], 0.1), default=None) if gauges else None

        # Flood probability from level proximity and rate of rise.
        flood_probability = 0.0
        if worst:
            ratio = worst["current_level_m"] / max(worst["danger_level_m"], 0.1)
            flood_probability = min(1.0, max(0.0, (ratio - 0.6) / 0.4))
            if worst["dam_spill_active"]:
                flood_probability = min(1.0, flood_probability + 0.2)

        findings: list[str] = []
        if forecast > 204:
            findings.append(f"Extremely heavy rainfall forecast ({forecast:.0f} mm/24h)")
        elif forecast > 115:
            findings.append(f"Very heavy rainfall forecast ({forecast:.0f} mm/24h)")
        elif forecast > 64:
            findings.append(f"Heavy rainfall forecast ({forecast:.0f} mm/24h)")

        if rivers.get("dam_spill_active"):
            findings.append("Upstream reservoir spilling — downstream surge committed")
        if lead_time is not None:
            findings.append(f"Danger level projected in {lead_time:.1f} hours")
        if wind > 60:
            findings.append(f"Wind {wind:.0f} km/h exceeds safe boat-operation limits")

        # Safe operating window: the smaller of rainfall-driven and lead time.
        if wind > 60 or forecast > 204:
            window = 0.0
        elif lead_time is not None:
            window = max(0.0, lead_time - 1.0)  # one hour margin
        else:
            window = 12.0

        recommendations: list[Recommendation] = []
        if lead_time is not None and lead_time < 6:
            recommendations.append(
                Recommendation(
                    action=(
                        f"Begin evacuation of low-lying areas immediately — "
                        f"only {lead_time:.1f} hours before danger level"
                    ),
                    rationale="Evacuation cannot complete after inundation begins.",
                    urgency=Urgency.IMMEDIATE,
                    owner="district_administration",
                )
            )
        if rivers.get("dam_spill_active"):
            recommendations.append(
                Recommendation(
                    action="Confirm reservoir release schedule and publish downstream arrival times per gauge",
                    rationale="Unannounced release is a recurring cause of avoidable casualties.",
                    urgency=Urgency.IMMEDIATE,
                    owner="irrigation_department",
                )
            )
        if window <= 0:
            recommendations.append(
                Recommendation(
                    action="Suspend outdoor boat rescue operations until conditions improve",
                    rationale="Wind and rainfall exceed safe operating thresholds for crews.",
                    urgency=Urgency.IMMEDIATE,
                    owner="rescue_command",
                )
            )

        return WeatherIntel(
            headline=(
                f"{weather.get('conditions', 'Conditions unknown')}; "
                + (
                    f"{lead_time:.1f}h to danger level"
                    if lead_time is not None
                    else "no imminent gauge breach"
                )
            )[:200],
            confidence=0.5,
            key_findings=findings or ["No significant meteorological escalation detected"],
            recommendations=recommendations,
            current_conditions=str(weather.get("conditions", "unknown")),
            rainfall_mm_24h=observed,
            forecast_rainfall_mm_24h=forecast,
            wind_speed_kmh=wind,
            river_level_m=worst["current_level_m"] if worst else None,
            river_danger_level_m=worst["danger_level_m"] if worst else None,
            flood_probability=round(flood_probability, 2),
            escalation_expected=bool(weather.get("escalating")),
            forecast_narrative=(
                f"Rule-based forecast assessment. Observed {observed:.0f} mm/24h, "
                f"forecast {forecast:.0f} mm/24h, wind {wind:.0f} km/h. "
                + (
                    f"Nearest critical gauge {worst['river']} @ {worst['station']} at "
                    f"{worst['current_level_m']}m against danger {worst['danger_level_m']}m."
                    if worst
                    else "No river gauges in range."
                )
            ),
            safe_operating_window_hours=round(window, 1),
            metrics=[
                Measure(label="Rainfall (24h forecast)", value=forecast, unit="mm"),
                Measure(label="Wind speed", value=wind, unit="km/h"),
                Measure(
                    label="Flood probability",
                    value=round(flood_probability * 100, 1),
                    unit="%",
                ),
            ],
        )
