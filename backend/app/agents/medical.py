"""Medical Coordination Agent (SDG 3).

The decisive medical question in a mass-casualty event is not "how many are
hurt" but "can reachable capacity absorb them, and where does it break". This
agent computes the deficit explicitly, because a deficit is what triggers
escalation — and escalation delayed is the most expensive error in the response.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.schemas.common import Measure
from app.schemas.enums import AgentRole, HazardType, Urgency
from app.schemas.intelligence import HospitalStatus, MedicalIntel, Recommendation

SYSTEM_PROMPT = """\
You are the Medical Coordination Officer in an Emergency Operations Centre.

Rules:
- Casualty DISTRIBUTION is your primary product, not casualty counting. Left \
uncoordinated, most casualties self-present to the single nearest facility and \
overwhelm it while facilities twenty minutes further away sit idle.
- Route RED (immediate) casualties only to trauma-capable facilities with \
CONFIRMED available capacity. Never route to a facility already at capacity.
- Route GREEN (minor) casualties away from trauma centres entirely.
- Compute the bed deficit honestly: projected casualties needing admission \
minus reachable available capacity. If there is a deficit, say so loudly — it \
is the trigger for state-level escalation.
- Preserve reserve capacity. Never allocate the last ICU bed or ventilator in \
a district to one incident while the hazard is still escalating.
- A hospital inside the hazard zone is a liability as a referral destination. \
Flag flood-vulnerable or strained facilities explicitly.
- Assess post-event disease risk: after flooding expect leptospirosis, cholera, \
typhoid, hepatitis A and vector-borne illness.
- Triage counts must sum to approximately your casualty projection.
"""

#: Fraction of casualties by triage category, by hazard. Derived from published
#: mass-casualty event reviews; blunt, but transparent and defensible.
TRIAGE_PROFILE: dict[HazardType, tuple[float, float, float]] = {
    # (red, yellow, green)
    HazardType.EARTHQUAKE: (0.18, 0.32, 0.50),
    HazardType.BUILDING_COLLAPSE: (0.25, 0.35, 0.40),
    HazardType.FLOOD: (0.08, 0.22, 0.70),
    HazardType.URBAN_FLOOD: (0.06, 0.20, 0.74),
    HazardType.CYCLONE: (0.10, 0.28, 0.62),
    HazardType.WILDFIRE: (0.14, 0.30, 0.56),
    HazardType.STRUCTURAL_FIRE: (0.16, 0.30, 0.54),
    HazardType.INDUSTRIAL_CHEMICAL: (0.20, 0.35, 0.45),
    HazardType.LANDSLIDE: (0.22, 0.33, 0.45),
    HazardType.HEATWAVE: (0.05, 0.25, 0.70),
    HazardType.MASS_CASUALTY: (0.20, 0.35, 0.45),
}
DEFAULT_TRIAGE = (0.12, 0.28, 0.60)


class MedicalAgent(BaseAgent[MedicalIntel]):
    role = AgentRole.MEDICAL
    title = "Medical Coordination"

    @property
    def output_schema(self) -> type[MedicalIntel]:
        return MedicalIntel

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def gather(self, ctx: AgentContext) -> dict[str, Any]:
        hospitals = await self.call_tool(
            ctx,
            "find_hospital_capacity",
            latitude=ctx.latitude,
            longitude=ctx.longitude,
            radius_km=45.0,
            limit=8,
        )

        # Travel time to the nearest trauma centre bounds the whole casualty
        # evacuation plan, so compute it rather than assuming it.
        route: dict[str, Any] = {}
        trauma = [h for h in hospitals.get("hospitals", []) if h.get("trauma_capable")]
        if trauma:
            nearest = min(trauma, key=lambda h: h["distance_km"])
            route = await self.call_tool(
                ctx,
                "estimate_route",
                from_latitude=ctx.latitude,
                from_longitude=ctx.longitude,
                to_latitude=nearest["latitude"],
                to_longitude=nearest["longitude"],
                hazard_type=ctx.hazard_value,
            )
            route["facility"] = nearest["name"]

        return {"hospitals": hospitals, "route": route}

    def build_prompt(self, ctx: AgentContext, evidence: dict[str, Any]) -> str:
        hospitals = evidence.get("hospitals", {})
        route = evidence.get("route", {})

        lines = [
            ctx.situation_brief(),
            "",
            f"FOCUS QUESTION: {ctx.focus_question or 'Assess medical capacity against projected casualties.'}",
            "",
            "=== REACHABLE MEDICAL CAPACITY ===",
            f"Facilities in range: {hospitals.get('hospital_count', 0)}",
            f"Total available beds: {hospitals.get('total_available_beds', 0)}",
            f"Total ICU available: {hospitals.get('total_icu_available', 0)}",
            f"Ventilators available: {hospitals.get('total_ventilators', 0)}",
            f"Trauma-capable centres: {hospitals.get('trauma_centres', 0)}",
            f"Blood banks: {hospitals.get('blood_banks', 0)}",
        ]
        if hospitals.get("strained_facilities"):
            lines.append(
                "ALREADY STRAINED: " + ", ".join(hospitals["strained_facilities"])
            )

        lines.append("")
        for hospital in hospitals.get("hospitals", []):
            lines.append(
                f"  {hospital['name']} ({hospital['distance_km']} km) — "
                f"beds {hospital['available_beds']}/{hospital['total_beds']}, "
                f"ICU {hospital['icu_available']}, vent {hospital['ventilators_available']}, "
                f"trauma={hospital['trauma_capable']}, blood={hospital['blood_bank']}, "
                f"status={hospital['operational_status']}, "
                f"occupancy={hospital['occupancy_ratio']:.0%}"
            )

        if route:
            lines += [
                "",
                f"Nearest trauma centre: {route.get('facility')} — "
                f"{route.get('road_distance_km')} km, ETA {route.get('eta_minutes')} min "
                f"under {ctx.hazard_value} conditions.",
            ]

        lines += [
            "",
            "Produce the structured medical intelligence product. State the bed "
            "deficit explicitly and give concrete casualty-routing instructions.",
        ]
        return "\n".join(lines)

    def fallback(self, ctx: AgentContext, evidence: dict[str, Any]) -> MedicalIntel:
        hospitals_data = evidence.get("hospitals", {})
        route = evidence.get("route", {})
        rows = hospitals_data.get("hospitals", [])

        assessment = ctx.assessment
        hazard = assessment.hazard_type if assessment else HazardType.UNKNOWN
        projected = (
            assessment.impact.people_requiring_medical_care if assessment else 0
        )

        red_rate, yellow_rate, green_rate = TRIAGE_PROFILE.get(hazard, DEFAULT_TRIAGE)
        red = int(projected * red_rate)
        yellow = int(projected * yellow_rate)
        green = projected - red - yellow

        available_beds = int(hospitals_data.get("total_available_beds", 0))
        # Only RED and YELLOW require admission; GREEN are treated and released.
        requiring_admission = red + yellow
        deficit = max(0, requiring_admission - available_beds)

        eta = int(route.get("eta_minutes", 30) or 30)
        # Round trip plus 10 min handover; each ambulance carries one stretcher
        # case at a time. Target clearance of RED+YELLOW within 6 hours.
        round_trip_hours = max(0.25, (2 * eta + 10) / 60.0)
        ambulances = max(1, int((requiring_admission * round_trip_hours) / 6.0)) if requiring_admission else 0

        findings = [
            f"Projected {projected:,} casualties requiring care "
            f"(RED {red}, YELLOW {yellow}, GREEN {green})",
            f"{available_beds:,} beds available across "
            f"{hospitals_data.get('hospital_count', 0)} reachable facilities",
        ]
        if deficit:
            findings.append(
                f"BED DEFICIT: {deficit:,} admissions cannot be accommodated locally"
            )
        if hospitals_data.get("strained_facilities"):
            findings.append(
                "Facilities already strained: "
                + ", ".join(hospitals_data["strained_facilities"])
            )
        if route:
            findings.append(
                f"Nearest trauma centre {route.get('facility')} at "
                f"{route.get('eta_minutes')} min under current conditions"
            )

        recommendations: list[Recommendation] = []
        trauma_rows = [h for h in rows if h.get("trauma_capable") and h.get("available_beds", 0) > 0]
        if trauma_rows:
            top = sorted(trauma_rows, key=lambda h: -h["available_beds"])[:2]
            recommendations.append(
                Recommendation(
                    action=(
                        "Route RED casualties to "
                        + " and ".join(f"{h['name']} ({h['available_beds']} beds)" for h in top)
                    ),
                    rationale="Trauma-capable with confirmed available capacity.",
                    urgency=Urgency.IMMEDIATE,
                    owner="ambulance_control",
                )
            )
        non_trauma = [h for h in rows if not h.get("trauma_capable")]
        if non_trauma:
            recommendations.append(
                Recommendation(
                    action=(
                        "Divert GREEN (minor) casualties to "
                        + ", ".join(h["name"] for h in non_trauma[:2])
                    ),
                    rationale="Keeps trauma-centre capacity free for RED casualties.",
                    urgency=Urgency.URGENT,
                    owner="ambulance_control",
                )
            )
        if ambulances:
            recommendations.append(
                Recommendation(
                    action=f"Mobilise {ambulances} ambulances for casualty evacuation",
                    rationale=(
                        f"{requiring_admission} stretcher cases at a "
                        f"{round_trip_hours:.1f}h round trip, cleared within 6 hours."
                    ),
                    urgency=Urgency.IMMEDIATE,
                    owner="ems_control",
                )
            )
        if deficit:
            recommendations.append(
                Recommendation(
                    action=(
                        f"Escalate to state health authority for {deficit} "
                        "additional bed capacity or inter-district transfer"
                    ),
                    rationale="Local reachable capacity is insufficient for projected admissions.",
                    urgency=Urgency.IMMEDIATE,
                    owner="state_health_department",
                )
            )

        outbreak_risk = 0.0
        watchlist: list[str] = []
        if hazard in (HazardType.FLOOD, HazardType.URBAN_FLOOD, HazardType.TSUNAMI):
            outbreak_risk = 0.65
            watchlist = ["leptospirosis", "cholera", "typhoid", "hepatitis A", "dengue"]
            recommendations.append(
                Recommendation(
                    action="Initiate water-borne disease surveillance at all relief camps now",
                    rationale="Detection delay is the main determinant of outbreak size.",
                    urgency=Urgency.URGENT,
                    owner="district_health_officer",
                )
            )

        return MedicalIntel(
            headline=(
                f"{projected:,} casualties projected; {available_beds:,} beds reachable"
                + (f"; DEFICIT {deficit:,}" if deficit else "; capacity sufficient")
            )[:200],
            confidence=0.5,
            key_findings=findings,
            recommendations=recommendations,
            casualty_projection=projected,
            triage_categories={"red": red, "yellow": yellow, "green": green},
            hospitals=[HospitalStatus.model_validate(_hospital_row(h)) for h in rows],
            total_available_beds=available_beds,
            bed_deficit=deficit,
            ambulances_required=ambulances,
            priority_medicines=(
                ["ORS", "doxycycline", "antibiotics", "IV fluids", "water purification tablets"]
                if outbreak_risk
                else ["analgesics", "antibiotics", "IV fluids", "tetanus prophylaxis"]
            ),
            disease_outbreak_risk=outbreak_risk,
            outbreak_watchlist=watchlist,
            metrics=[
                Measure(label="Casualties projected", value=projected, unit="people"),
                Measure(label="Beds available", value=available_beds, unit="beds"),
                Measure(label="Bed deficit", value=deficit, unit="beds"),
                Measure(label="Ambulances required", value=ambulances, unit="vehicles"),
            ],
        )


def _hospital_row(row: dict[str, Any]) -> dict[str, Any]:
    """Adapt the tool's flat dict back into the HospitalStatus shape."""
    return {
        "facility_id": row["facility_id"],
        "name": row["name"],
        "point": {"latitude": row["latitude"], "longitude": row["longitude"]},
        "distance_km": row["distance_km"],
        "total_beds": row["total_beds"],
        "available_beds": row["available_beds"],
        "icu_available": row["icu_available"],
        "ventilators_available": row["ventilators_available"],
        "blood_bank": row["blood_bank"],
        "trauma_capable": row["trauma_capable"],
        "operational_status": row["operational_status"],
    }
