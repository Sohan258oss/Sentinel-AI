"""Infrastructure Agent (SDG 9).

The most valuable infrastructure product for a commander is not a list of what
is broken — it is the list of corridors that still work, and how long they will
last. A settlement with no viable corridor is *isolated*, which changes its
resource requirement entirely: it needs air or water delivery and
self-sufficiency stock, not a truck convoy.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.schemas.common import Measure
from app.schemas.enums import AgentRole, DamageClass, HazardType, Urgency
from app.schemas.intelligence import (
    InfrastructureIntel,
    Recommendation,
    VisionAssessment,
)
from app.vision import analyze_images

SYSTEM_PROMPT = """\
You are the Critical Infrastructure Officer in an Emergency Operations Centre.

Lifeline priority order, because each depends on those above it:
1. Access routes  2. Water supply  3. Power  4. Telecommunications  5. Sanitation

Rules:
- Your primary deliverable is `access_corridors`: routes INTO the affected area \
that remain viable, and how long they will last. Identifying what is broken \
without identifying what still works gives the commander nothing to act on.
- Treat any road that has been submerged as suspect. Scour erodes support \
beneath an intact-looking surface.
- The most common bridge failure mode is the approach embankment, not the span. \
Debris accumulation at piers converts a bridge into a dam and is an urgent \
finding.
- Assume load restrictions for relief convoys. A heavy vehicle collapsing a \
marginal bridge severs the route for everyone.
- Rescue teams must not enter inundated areas before electrical isolation is \
CONFIRMED with the distribution utility.
- Imagery findings are indicative, never conclusive. Automated damage \
classification must not be the sole basis for declaring anything safe. If the \
vision models disagreed, say so.
"""


class InfrastructureAgent(BaseAgent[InfrastructureIntel]):
    role = AgentRole.INFRASTRUCTURE
    title = "Infrastructure Assessment"

    @property
    def output_schema(self) -> type[InfrastructureIntel]:
        return InfrastructureIntel

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def gather(self, ctx: AgentContext) -> dict[str, Any]:
        evidence: dict[str, Any] = {}

        evidence["rivers"] = await self.call_tool(
            ctx,
            "get_river_levels",
            latitude=ctx.latitude,
            longitude=ctx.longitude,
            radius_km=60.0,
        )
        evidence["depots"] = await self.call_tool(
            ctx,
            "find_supply_depots",
            latitude=ctx.latitude,
            longitude=ctx.longitude,
            radius_km=120.0,
        )

        # Corridor viability from the nearest depots — these are the routes
        # relief will actually travel.
        corridors: list[dict[str, Any]] = []
        for depot in evidence["depots"].get("depots", [])[:4]:
            route = await self.call_tool(
                ctx,
                "estimate_route",
                from_latitude=depot["latitude"],
                from_longitude=depot["longitude"],
                to_latitude=ctx.latitude,
                to_longitude=ctx.longitude,
                hazard_type=ctx.hazard_value,
            )
            corridors.append({**route, "from": depot["name"], "organization": depot["organization"]})
        evidence["corridors"] = corridors

        if ctx.report.media_paths:
            assessments = await analyze_images(ctx.report.media_paths)
            evidence["_vision"] = assessments
            evidence["vision"] = [a.model_dump(mode="json") for a in assessments]

        return evidence

    def build_prompt(self, ctx: AgentContext, evidence: dict[str, Any]) -> str:
        rivers = evidence.get("rivers", {})
        corridors = evidence.get("corridors", [])
        vision: list[VisionAssessment] = evidence.get("_vision", [])

        lines = [
            ctx.situation_brief(),
            "",
            f"FOCUS QUESTION: {ctx.focus_question or 'Assess infrastructure damage and access viability.'}",
            "",
            "=== HYDROLOGICAL LOAD ON STRUCTURES ===",
            f"Danger breach: {rivers.get('any_danger_breach')} | "
            f"warning breach: {rivers.get('any_warning_breach')} | "
            f"dam spill: {rivers.get('dam_spill_active')}",
            "",
            "=== SUPPLY CORRIDORS (depot -> incident) ===",
        ]
        for corridor in corridors:
            lines.append(
                f"  {corridor.get('from')} ({corridor.get('organization')}): "
                f"{corridor.get('road_distance_km')} km, "
                f"ETA {corridor.get('eta_minutes')} min at "
                f"{corridor.get('effective_speed_kmh')} km/h "
                f"({corridor.get('hazard_degradation_factor')}x degradation)"
            )
        if not corridors:
            lines.append("  (no corridor data)")

        lines += ["", "=== IMAGERY ASSESSMENT ==="]
        if vision:
            for assessment in vision:
                lines.append(
                    f"  {assessment.image_path.split('/')[-1]}: "
                    f"{assessment.dominant_class.value} "
                    f"(models {', '.join(assessment.models_used)}, "
                    f"agreement {assessment.ensemble_agreement:.0%}) — "
                    f"{assessment.description}"
                )
        else:
            lines.append("  No imagery attached.")

        lines += [
            "",
            "Produce the structured infrastructure intelligence product. Name the "
            "viable access corridors explicitly.",
        ]
        return "\n".join(lines)

    def fallback(
        self, ctx: AgentContext, evidence: dict[str, Any]
    ) -> InfrastructureIntel:
        rivers = evidence.get("rivers", {})
        corridors = evidence.get("corridors", [])
        vision: list[VisionAssessment] = evidence.get("_vision", [])

        hazard = ctx.assessment.hazard_type if ctx.assessment else HazardType.UNKNOWN
        flooding = hazard in (
            HazardType.FLOOD,
            HazardType.URBAN_FLOOD,
            HazardType.TSUNAMI,
        )

        # Structural risk from hydrology and imagery, combined.
        risk = 0.0
        if rivers.get("any_danger_breach"):
            risk += 0.45
        elif rivers.get("any_warning_breach"):
            risk += 0.25
        if rivers.get("dam_spill_active"):
            risk += 0.15

        blocked_roads: list[str] = []
        bridges: list[str] = []
        findings: list[str] = []

        for assessment in vision:
            if assessment.dominant_class in (
                DamageClass.COLLAPSED_BUILDING,
                DamageClass.DAMAGED_BUILDING,
            ):
                risk += 0.25
            if assessment.dominant_class is DamageClass.BLOCKED_ROAD:
                blocked_roads.append(
                    f"Route obstruction identified in {assessment.image_path.split('/')[-1]}"
                )
                risk += 0.15
            if assessment.dominant_class is DamageClass.DAMAGED_BRIDGE:
                bridges.append("Bridge damage identified in imagery")
                risk += 0.2
            if assessment.ensemble_agreement and assessment.ensemble_agreement < 0.5:
                findings.append(
                    f"Vision models DISAGREED on {assessment.image_path.split('/')[-1]} "
                    f"({assessment.ensemble_agreement:.0%} agreement) — human verification required"
                )

        risk = min(1.0, risk)

        # Corridors ranked by ETA; the slowest are the first to be severed.
        viable = sorted(corridors, key=lambda c: c.get("eta_minutes", 9999))
        access_corridors = [
            f"{c.get('from')} -> incident: {c.get('road_distance_km')} km, "
            f"ETA {c.get('eta_minutes')} min"
            for c in viable[:4]
        ]

        if flooding:
            findings.append(
                "All submerged road segments must be treated as structurally suspect "
                "(scour risk) until inspected"
            )
            bridges.append("Inspect bridge approach embankments and clear pier debris")

        if rivers.get("any_danger_breach"):
            findings.append("River above danger level — lateral load on bridge piers elevated")
        if corridors:
            slowest = max(corridors, key=lambda c: c.get("eta_minutes", 0))
            findings.append(
                f"Longest supply corridor is {slowest.get('from')} at "
                f"{slowest.get('eta_minutes')} min — first to be severed if conditions worsen"
            )

        recommendations = [
            Recommendation(
                action="Confirm electrical isolation with the distribution utility before any rescue team enters inundated areas",
                rationale="Downed conductors energise standing water well beyond visible contact.",
                urgency=Urgency.IMMEDIATE,
                owner="power_utility",
            )
        ]
        if viable:
            recommendations.append(
                Recommendation(
                    action=f"Designate {viable[0].get('from')} corridor as the primary relief route",
                    rationale=f"Shortest viable ETA at {viable[0].get('eta_minutes')} minutes.",
                    urgency=Urgency.URGENT,
                    owner="logistics_cell",
                )
            )
        if flooding:
            recommendations.append(
                Recommendation(
                    action="Impose load restrictions on all bridges on relief routes pending inspection",
                    rationale="A heavy vehicle collapsing a marginal bridge severs the route for everyone.",
                    urgency=Urgency.URGENT,
                    owner="public_works_department",
                )
            )

        return InfrastructureIntel(
            headline=(
                f"Structural risk {risk:.0%}; {len(viable)} supply corridors assessed"
            )[:200],
            confidence=0.5,
            key_findings=findings or ["No significant infrastructure damage indicators"],
            recommendations=recommendations,
            roads_blocked=blocked_roads,
            bridges_at_risk=bridges,
            power_outage_areas=(
                [f"Precautionary isolation advised for inundated sectors of {ctx.report.location.name}"]
                if flooding
                else []
            ),
            water_supply_status="at risk of contamination" if flooding else "unknown",
            telecom_status="unknown",
            access_corridors=access_corridors,
            structural_risk_score=round(risk, 2),
            vision_assessments=vision,
            metrics=[
                Measure(label="Structural risk", value=round(risk * 100, 1), unit="%"),
                Measure(label="Viable corridors", value=len(viable), unit="routes"),
            ],
        )
