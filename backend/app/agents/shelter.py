"""Shelter & Evacuation Agent (SDG 11).

Applies quantified humanitarian minimum standards rather than counting heads
against nominal capacity. A camp holding its "capacity" at 2 m² per person with
one toilet per 80 people is not sheltering people; it is incubating an outbreak.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.schemas.common import Measure
from app.schemas.enums import AgentRole, Urgency
from app.schemas.intelligence import Recommendation, ShelterIntel, ShelterSite

SYSTEM_PROMPT = """\
You are the Shelter and Evacuation Officer in an Emergency Operations Centre.

Apply these humanitarian minimum standards as hard planning figures:
- 15 litres of drinking water per person per day (7.5 L is the absolute \
48-hour survival floor).
- 3.5 m² of covered living space per person.
- 1 toilet per 20 people, sex-segregated.
- 1 water point per 250 people.

Rules:
- A shelter inside the hazard zone is a liability, not an asset. Flag any \
designated site that is NOT flood-safe or NOT currently accessible, and \
exclude it from usable capacity.
- Usable capacity is lower than stated capacity. Discount space used by \
kitchens, stores and medical posts.
- If safe reachable capacity is less than the displaced population, that is a \
CAPACITY DEFICIT. State it explicitly and escalate — do not silently absorb it \
through overcrowding.
- Always address vulnerable groups specifically: unaccompanied minors, elderly, \
persons with disability, pregnant and lactating women, and people with chronic \
conditions such as dialysis or insulin dependence. Most post-event mortality \
comes from failing these groups, not from the hazard itself.
- Evacuation routes must not pass through the hazard zone.
"""


class ShelterAgent(BaseAgent[ShelterIntel]):
    role = AgentRole.SHELTER
    title = "Shelter & Evacuation"

    @property
    def output_schema(self) -> type[ShelterIntel]:
        return ShelterIntel

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def gather(self, ctx: AgentContext) -> dict[str, Any]:
        shelters = await self.call_tool(
            ctx,
            "find_shelter_capacity",
            latitude=ctx.latitude,
            longitude=ctx.longitude,
            radius_km=40.0,
            limit=12,
        )
        return {"shelters": shelters}

    def build_prompt(self, ctx: AgentContext, evidence: dict[str, Any]) -> str:
        shelters = evidence.get("shelters", {})
        needing = (
            ctx.assessment.impact.people_requiring_shelter if ctx.assessment else 0
        )

        lines = [
            ctx.situation_brief(),
            "",
            f"FOCUS QUESTION: {ctx.focus_question or 'Assess shelter capacity against displacement.'}",
            "",
            f"PEOPLE REQUIRING SHELTER: {needing:,}",
            "",
            "=== SHELTER NETWORK ===",
            f"Sites in range: {shelters.get('shelter_count', 0)}",
            f"Total spare capacity: {shelters.get('total_spare_capacity', 0):,}",
            f"SAFE and REACHABLE spare capacity: {shelters.get('safe_spare_capacity', 0):,}",
            f"Sites with medical posts: {shelters.get('shelters_with_medical_post', 0)}",
        ]
        if shelters.get("shelters_at_flood_risk"):
            lines.append(
                "AT FLOOD RISK (exclude from usable capacity): "
                + ", ".join(shelters["shelters_at_flood_risk"])
            )
        if shelters.get("shelters_currently_unreachable"):
            lines.append(
                "CURRENTLY UNREACHABLE: "
                + ", ".join(shelters["shelters_currently_unreachable"])
            )

        lines.append("")
        for site in shelters.get("shelters", []):
            lines.append(
                f"  {site['name']} ({site['distance_km']} km) — "
                f"spare {site['spare_capacity']}/{site['capacity']}, "
                f"medical={site['has_medical_post']}, power={site['has_power_backup']}, "
                f"accessible={site['accessible']}, flood_safe={site['flood_safe']}"
            )

        lines += [
            "",
            "Produce the structured shelter intelligence product. Compute the "
            "capacity deficit against SAFE reachable capacity only.",
        ]
        return "\n".join(lines)

    def fallback(self, ctx: AgentContext, evidence: dict[str, Any]) -> ShelterIntel:
        data = evidence.get("shelters", {})
        rows = data.get("shelters", [])

        needing = ctx.assessment.impact.people_requiring_shelter if ctx.assessment else 0
        safe_capacity = int(data.get("safe_spare_capacity", 0))
        deficit = max(0, needing - safe_capacity)

        unusable = list(data.get("shelters_at_flood_risk", [])) + list(
            data.get("shelters_currently_unreachable", [])
        )

        findings = [
            f"{needing:,} people require shelter",
            f"{safe_capacity:,} safe and reachable spaces available across "
            f"{data.get('shelter_count', 0)} sites",
        ]
        if unusable:
            findings.append(
                f"{len(set(unusable))} designated sites unusable (flood-exposed or unreachable): "
                + ", ".join(sorted(set(unusable))[:4])
            )
        if deficit:
            findings.append(f"CAPACITY DEFICIT: {deficit:,} people without safe shelter space")

        # Water requirement at the humanitarian minimum standard.
        water_litres_per_day = needing * 15

        recommendations: list[Recommendation] = []
        usable = [
            s for s in rows if s.get("flood_safe") and s.get("accessible") and s.get("spare_capacity", 0) > 0
        ]
        if usable:
            top = sorted(usable, key=lambda s: (-s["spare_capacity"], s["distance_km"]))[:3]
            recommendations.append(
                Recommendation(
                    action=(
                        "Direct evacuees to "
                        + ", ".join(f"{s['name']} ({s['spare_capacity']} spaces)" for s in top)
                    ),
                    rationale="Flood-safe, currently accessible, with the largest spare capacity.",
                    urgency=Urgency.IMMEDIATE,
                    owner="district_administration",
                )
            )
        if data.get("shelters_at_flood_risk"):
            recommendations.append(
                Recommendation(
                    action=(
                        "Reclassify and evacuate flood-exposed camps: "
                        + ", ".join(data["shelters_at_flood_risk"][:3])
                    ),
                    rationale="A designated shelter inside the inundation zone endangers its occupants.",
                    urgency=Urgency.IMMEDIATE,
                    owner="district_administration",
                )
            )
        if deficit:
            recommendations.append(
                Recommendation(
                    action=(
                        f"Open additional shelter capacity for {deficit:,} people or "
                        "arrange inter-district transfer"
                    ),
                    rationale=(
                        "Overcrowding below 3.5 m² per person converts a shelter into "
                        "a disease vector."
                    ),
                    urgency=Urgency.IMMEDIATE,
                    owner="state_disaster_authority",
                )
            )
        recommendations.append(
            Recommendation(
                action=f"Provision {water_litres_per_day:,} litres of drinking water per day",
                rationale="Humanitarian minimum standard of 15 litres per person per day.",
                urgency=Urgency.URGENT,
                owner="water_authority",
            )
        )

        return ShelterIntel(
            headline=(
                f"{needing:,} need shelter; {safe_capacity:,} safe spaces available"
                + (f"; DEFICIT {deficit:,}" if deficit else "; capacity sufficient")
            )[:200],
            confidence=0.5,
            key_findings=findings,
            recommendations=recommendations,
            people_to_shelter=needing,
            shelters=[ShelterSite.model_validate(_shelter_row(s)) for s in rows],
            total_spare_capacity=int(data.get("total_spare_capacity", 0)),
            capacity_deficit=deficit,
            evacuation_routes=[
                f"To {s['name']} ({s['distance_km']} km)" for s in usable[:4]
            ],
            vulnerable_groups=[
                "Unaccompanied minors — register and assign protection officer",
                "Elderly and persons with disability — accessible sanitation, ground floor",
                "Pregnant and lactating women — privacy and proximity to medical post",
                "Chronic conditions (dialysis, insulin, TB, HIV) — treatment continuity",
            ],
            metrics=[
                Measure(label="People requiring shelter", value=needing, unit="people"),
                Measure(label="Safe spare capacity", value=safe_capacity, unit="spaces"),
                Measure(label="Capacity deficit", value=deficit, unit="spaces"),
                Measure(
                    label="Daily water requirement",
                    value=water_litres_per_day,
                    unit="litres/day",
                ),
            ],
        )


def _shelter_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "shelter_id": row["shelter_id"],
        "name": row["name"],
        "point": {"latitude": row["latitude"], "longitude": row["longitude"]},
        "distance_km": row["distance_km"],
        "capacity": row["capacity"],
        "current_occupancy": row["current_occupancy"],
        "has_medical_post": row["has_medical_post"],
        "has_power_backup": row["has_power_backup"],
        "accessible": row["accessible"],
        "flood_safe": row["flood_safe"],
    }
