"""Situation Analysis Agent — the triage officer.

First agent to see an incident. Fuses the field report, live weather and
hydrology, and any attached imagery into a single structured assessment that
every downstream agent depends on. Its severity call determines how much of the
platform activates, so its fallback logic is written to be genuinely defensible
rather than a placeholder.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.core.llm import ModelTier
from app.schemas.enums import AgentRole, DamageClass, HazardType, Severity, TraceEventType
from app.schemas.incident import ImpactEstimate, SituationAssessment
from app.vision import analyze_images

SYSTEM_PROMPT = """\
You are the Situation Analysis Officer in an AI-operated Emergency Operations \
Centre. You perform initial triage on incoming incident reports.

Your assessment drives resource mobilisation for the entire response, so \
calibration matters more than confidence:

- OVERSTATING severity diverts scarce resources from other incidents.
- UNDERSTATING severity costs lives.

Rules:
- Ground every judgement in the EVIDENCE provided. Do not invent readings.
- Where evidence is thin, say so in `information_gaps` and lower your \
`confidence`. A low-confidence honest assessment is far more useful than a \
confident guess.
- Identify CASCADING hazards. Flood leads to epidemic and power failure; \
earthquake leads to fire; landslide can dam a river and cause a later surge. \
Planning only for the primary hazard is the most common strategic failure in \
disaster response.
- Population figures must be reasoned from the affected radius and the area \
population given, not asserted arbitrarily. Show that reasoning in `evidence`.
- Severity ladder: informational, minor, moderate, severe, catastrophic.

Return only the structured assessment.
"""

#: (evacuation multiplier, medical multiplier) applied to the severity-derived
#: base rates. Reflects how each hazard actually harms a population: floods
#: displace at scale with relatively low injury rates, while collapse and
#: chemical events injure a high proportion of a much smaller exposed group.
_HAZARD_IMPACT_PROFILE: dict[HazardType, tuple[float, float]] = {
    HazardType.FLOOD: (1.2, 0.5),
    HazardType.URBAN_FLOOD: (1.0, 0.4),
    HazardType.TSUNAMI: (1.4, 1.2),
    HazardType.CYCLONE: (1.3, 0.8),
    HazardType.EARTHQUAKE: (0.8, 3.0),
    HazardType.BUILDING_COLLAPSE: (0.2, 6.0),
    HazardType.LANDSLIDE: (0.6, 3.5),
    HazardType.WILDFIRE: (1.1, 1.2),
    HazardType.STRUCTURAL_FIRE: (0.3, 4.0),
    HazardType.INDUSTRIAL_CHEMICAL: (1.2, 3.0),
    HazardType.HEATWAVE: (0.05, 1.5),
    HazardType.EPIDEMIC: (0.05, 4.0),
    HazardType.DROUGHT: (0.1, 0.5),
    HazardType.MASS_CASUALTY: (0.2, 8.0),
    HazardType.UNKNOWN: (1.0, 1.0),
}

#: Hazards whose severity is legitimately driven by rainfall and river levels.
#: For anything else those signals are irrelevant — a rising river must not
#: escalate a heatwave, which is exactly the kind of cross-contamination a
#: naive "max of all signals" triage produces.
_HYDROLOGY_SENSITIVE: frozenset[HazardType] = frozenset(
    {
        HazardType.FLOOD,
        HazardType.URBAN_FLOOD,
        HazardType.LANDSLIDE,
        HazardType.CYCLONE,
        HazardType.TSUNAMI,
        HazardType.UNKNOWN,
    }
)

#: Upper bound on affected radius, in km. A structural collapse is a
#: street-scale event however severe it is; without this cap the population
#: model scales a single building failure to an entire district.
_HAZARD_MAX_RADIUS_KM: dict[HazardType, float] = {
    HazardType.BUILDING_COLLAPSE: 0.4,
    HazardType.STRUCTURAL_FIRE: 1.0,
    HazardType.MASS_CASUALTY: 1.0,
    HazardType.INDUSTRIAL_CHEMICAL: 3.0,
    HazardType.WILDFIRE: 10.0,
    HazardType.LANDSLIDE: 3.0,
}


class SituationAnalysisAgent(BaseAgent[SituationAssessment]):
    role = AgentRole.SITUATION_ANALYSIS
    title = "Situation Analysis"
    tier = ModelTier.REASONING

    @property
    def output_schema(self) -> type[SituationAssessment]:
        return SituationAssessment

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def gather(self, ctx: AgentContext) -> dict[str, Any]:
        evidence: dict[str, Any] = {}

        evidence["weather"] = await self.call_tool(
            ctx,
            "get_weather_conditions",
            latitude=ctx.latitude,
            longitude=ctx.longitude,
            place=ctx.report.location.name,
        )
        evidence["rivers"] = await self.call_tool(
            ctx,
            "get_river_levels",
            latitude=ctx.latitude,
            longitude=ctx.longitude,
            radius_km=70.0,
        )
        evidence["news"] = await self.call_tool(
            ctx,
            "search_news",
            query=f"{ctx.report.location.name} {ctx.hazard_value}",
            location=ctx.report.location.name,
            hours=24,
        )

        if ctx.report.media_paths:
            await self.emit(
                ctx,
                TraceEventType.REASONING,
                f"Analysing {len(ctx.report.media_paths)} incident image(s)",
                detail="Running fine-tuned CNN and vision-language model ensemble",
            )
            assessments = await analyze_images(ctx.report.media_paths)
            evidence["vision"] = [a.model_dump(mode="json") for a in assessments]
            evidence["_vision_objects"] = assessments

        return evidence

    def build_prompt(self, ctx: AgentContext, evidence: dict[str, Any]) -> str:
        weather = evidence.get("weather", {})
        rivers = evidence.get("rivers", {})
        news = evidence.get("news", {})
        vision = evidence.get("_vision_objects", [])

        sections = [ctx.situation_brief(), ""]

        if ctx.report.declared_hazard:
            sections.append(
                f"REPORTER-DECLARED HAZARD: {ctx.report.declared_hazard.value} "
                "(you may override this if the evidence contradicts it)"
            )
        if ctx.report.reported_casualties is not None:
            sections.append(f"REPORTED CASUALTIES: {ctx.report.reported_casualties}")
        sections.append(
            f"REPORT SOURCE: {ctx.report.source.channel} "
            f"(verified={ctx.report.source.verified}, "
            f"trust={ctx.report.source.trust_weight:.2f})"
        )

        sections += [
            "",
            "=== METEOROLOGY ===",
            f"Conditions: {weather.get('conditions', 'unknown')}",
            f"Rainfall last 24h: {weather.get('rainfall_mm_24h', 'unknown')} mm",
            f"Forecast next 24h: {weather.get('forecast_rainfall_mm_24h', 'unknown')} mm",
            f"Wind: {weather.get('wind_speed_kmh', 'unknown')} km/h",
            f"Deteriorating: {weather.get('escalating', 'unknown')}",
        ]

        sections += ["", "=== HYDROLOGY ==="]
        if rivers.get("gauge_count"):
            sections.append(
                f"Gauges in range: {rivers['gauge_count']} | "
                f"danger breached: {rivers.get('any_danger_breach')} | "
                f"warning breached: {rivers.get('any_warning_breach')} | "
                f"upstream dam spill: {rivers.get('dam_spill_active')}"
            )
            if rivers.get("min_hours_to_danger") is not None:
                sections.append(
                    f"LEAD TIME BEFORE DANGER LEVEL: "
                    f"{rivers['min_hours_to_danger']:.1f} hours"
                )
            for gauge in rivers.get("gauges", [])[:4]:
                sections.append(
                    f"  - {gauge['river']} @ {gauge['station']}: "
                    f"{gauge['current_level_m']}m (danger {gauge['danger_level_m']}m), "
                    f"{gauge['trend']} {gauge['rate_m_per_hr']:+.2f} m/hr"
                )
        else:
            sections.append("No river gauges within range.")

        sections += ["", "=== IMAGERY ANALYSIS ==="]
        if vision:
            for assessment in vision:
                sections.append(
                    f"  - {assessment.dominant_class.value} "
                    f"(models: {', '.join(assessment.models_used) or 'none'}, "
                    f"agreement {assessment.ensemble_agreement:.0%}): "
                    f"{assessment.description}"
                )
        else:
            sections.append("No imagery attached to this report.")

        sections += ["", "=== OPEN-SOURCE CORROBORATION ==="]
        if news.get("feed_available"):
            sections.append(f"{news.get('article_count', 0)} recent articles found.")
            for article in news.get("articles", [])[:4]:
                sections.append(f"  - {article.get('title')} ({article.get('source')})")
        else:
            sections.append(
                news.get("information_gap", "No open-source corroboration available.")
            )

        sections += [
            "",
            "Produce the structured situation assessment. Reason explicitly about "
            "population at risk from the affected radius and area population.",
        ]
        return "\n".join(sections)

    def fallback(self, ctx: AgentContext, evidence: dict[str, Any]) -> SituationAssessment:
        """Deterministic triage.

        Scores severity from independent physical signals and takes the maximum
        rather than an average — one severe indicator is enough to warrant a
        severe response, and averaging would let a calm signal mask a dangerous
        one.
        """
        weather = evidence.get("weather", {})
        rivers = evidence.get("rivers", {})
        vision_objects = evidence.get("_vision_objects", [])

        hazard = ctx.report.declared_hazard or HazardType.UNKNOWN
        signals: list[int] = []
        risks: list[str] = []
        evidence_notes: list[str] = []

        # -- Rainfall signal (IMD-style thresholds) --------------------------
        rainfall = float(weather.get("forecast_rainfall_mm_24h", 0) or 0)
        observed = float(weather.get("rainfall_mm_24h", 0) or 0)
        peak_rain = max(rainfall, observed)

        # Resolve the hazard BEFORE scoring, because which signals are even
        # relevant depends on what kind of event this is.
        for assessment in vision_objects:
            if hazard is not HazardType.UNKNOWN:
                break
            if assessment.dominant_class is DamageClass.FLOODED_AREA:
                hazard = HazardType.FLOOD
            elif assessment.dominant_class in (DamageClass.FIRE, DamageClass.SMOKE):
                hazard = HazardType.STRUCTURAL_FIRE
            elif assessment.dominant_class is DamageClass.COLLAPSED_BUILDING:
                hazard = HazardType.BUILDING_COLLAPSE
        if hazard is HazardType.UNKNOWN and (
            rivers.get("any_danger_breach") or rivers.get("any_warning_breach")
        ):
            hazard = HazardType.FLOOD

        hydrology_relevant = hazard in _HYDROLOGY_SENSITIVE

        # -- Rainfall signal (IMD-style thresholds) --------------------------
        if hydrology_relevant:
            if peak_rain > 204:
                signals.append(4)
                risks.append("Extremely heavy rainfall exceeding 204 mm/24h")
            elif peak_rain > 115:
                signals.append(3)
                risks.append("Very heavy rainfall 115-204 mm/24h")
            elif peak_rain > 64:
                signals.append(2)
            elif peak_rain > 15:
                signals.append(1)
            if peak_rain > 15:
                evidence_notes.append(f"Rainfall {peak_rain:.0f} mm/24h")

        # -- Hydrology signal ------------------------------------------------
        if hydrology_relevant:
            if rivers.get("any_danger_breach"):
                signals.append(4)
                risks.append("River gauge above danger level")
            elif rivers.get("any_warning_breach"):
                signals.append(3)
                risks.append("River gauge above warning level")

            lead_time = rivers.get("min_hours_to_danger")
            if lead_time is not None and lead_time < 12:
                # Graduated by how little time remains. A 3-hour window is a
                # different order of emergency from an 11-hour one, and
                # collapsing both to "catastrophic" makes the signal useless.
                if lead_time < 2:
                    signals.append(4)
                elif lead_time < 6:
                    signals.append(3)
                else:
                    signals.append(2)
                risks.append(
                    f"Danger level projected within {lead_time:.1f} hours — "
                    "evacuation window closing"
                )
            if rivers.get("dam_spill_active"):
                risks.append("Upstream reservoir spilling; downstream surge expected")
                evidence_notes.append("Upstream dam spill active")

        # -- Imagery signal --------------------------------------------------
        for assessment in vision_objects:
            signals.append(assessment.severity_signal.rank)
            evidence_notes.append(
                f"Imagery: {assessment.dominant_class.value} "
                f"({assessment.ensemble_agreement:.0%} model agreement)"
            )
            if assessment.dominant_class is DamageClass.FLOODED_AREA:
                hazard = HazardType.FLOOD if hazard is HazardType.UNKNOWN else hazard
            elif assessment.dominant_class in (DamageClass.FIRE, DamageClass.SMOKE):
                hazard = HazardType.STRUCTURAL_FIRE if hazard is HazardType.UNKNOWN else hazard
            elif assessment.dominant_class is DamageClass.COLLAPSED_BUILDING:
                hazard = HazardType.BUILDING_COLLAPSE if hazard is HazardType.UNKNOWN else hazard

        # -- Reported casualties --------------------------------------------
        casualties = ctx.report.reported_casualties or 0
        if casualties > 50:
            signals.append(4)
        elif casualties > 10:
            signals.append(3)
        elif casualties > 0:
            signals.append(2)
        if casualties:
            evidence_notes.append(f"{casualties} casualties reported from the field")

        severity = Severity.from_rank(max(signals) if signals else 1)

        # -- Impact estimation ----------------------------------------------
        radius_by_severity = {0: 1.0, 1: 2.0, 2: 4.0, 3: 8.0, 4: 15.0}
        radius = min(
            radius_by_severity[severity.rank],
            _HAZARD_MAX_RADIUS_KM.get(hazard, float("inf")),
        )
        area_population = ctx.report.location.population or 50_000

        # Fraction of the area population inside the affected radius, assuming
        # a nominal 25 km settlement radius. Crude but stated, not hidden.
        exposure = min(1.0, (radius**2) / (25.0**2))
        at_risk = ctx.report.people_affected_estimate or int(area_population * exposure)
        at_risk = max(at_risk, 100)

        evacuation_rate = {0: 0.0, 1: 0.02, 2: 0.08, 3: 0.25, 4: 0.45}[severity.rank]
        medical_rate = {0: 0.0, 1: 0.002, 2: 0.005, 3: 0.012, 4: 0.025}[severity.rank]

        # Hazards differ sharply in how they harm people. Flooding displaces
        # many and injures comparatively few; structural collapse does the
        # reverse. Applying one profile to both produces figures that a
        # domain expert immediately recognises as wrong.
        evacuation_factor, medical_factor = _HAZARD_IMPACT_PROFILE.get(hazard, (1.0, 1.0))
        evacuation_rate = min(0.95, evacuation_rate * evacuation_factor)
        medical_rate = min(0.5, medical_rate * medical_factor)

        secondary: list[HazardType] = []
        if hazard in (HazardType.FLOOD, HazardType.URBAN_FLOOD) and severity.rank >= 2:
            secondary = [HazardType.EPIDEMIC, HazardType.LANDSLIDE]
            risks.append("Water contamination and vector-borne disease risk post-flood")
        elif hazard is HazardType.EARTHQUAKE:
            secondary = [HazardType.STRUCTURAL_FIRE, HazardType.BUILDING_COLLAPSE]

        impact = ImpactEstimate(
            population_at_risk=at_risk,
            people_requiring_evacuation=int(at_risk * evacuation_rate),
            people_requiring_medical_care=max(casualties, int(at_risk * medical_rate)),
            people_requiring_shelter=int(at_risk * evacuation_rate * 0.85),
            affected_radius_km=radius,
            estimated_duration_hours=24.0 * (1 + severity.rank),
        )

        headline = (
            f"{hazard.value.replace('_', ' ').title()} — {severity.value} — "
            f"{ctx.report.location.name}"
        )

        return SituationAssessment(
            hazard_type=hazard,
            secondary_hazards=secondary,
            severity=severity,
            # Rule-based triage is legitimately less certain than reasoned
            # analysis; the confidence says so rather than overclaiming.
            confidence=0.55,
            headline=headline[:160],
            summary=(
                f"Deterministic triage of {hazard.value} at {ctx.report.location.label}. "
                f"Severity {severity.value} derived from "
                f"{len(signals)} independent physical indicators. "
                f"Approximately {at_risk:,} people estimated within the "
                f"{radius} km affected radius. "
                f"Computed by rule-based logic without model reasoning."
            ),
            impact=impact,
            immediate_risks=risks[:6],
            information_gaps=[
                "No model-based reasoning applied — assessment is rule-derived",
                "Ground-truth confirmation of affected extent not available",
                "Actual population distribution within radius unknown",
            ],
            evidence=evidence_notes[:8] or ["Field report only; no corroborating signals"],
        )
