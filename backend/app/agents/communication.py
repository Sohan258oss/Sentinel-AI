"""Communication Agent — audience-differentiated messaging.

The same situation requires materially different messages for the public, for
responders, for government, for hospitals and for volunteers. This agent
produces all of them from one operational picture, and pre-empts the rumour
categories that predictably emerge during disasters.

The volunteer-safety boundary is treated as mandatory content, not decoration:
untrained volunteers attempting water rescue is a recurring source of
preventable responder deaths.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.core.llm import ModelTier
from app.schemas.command import CommunicationArtifact, CommunicationPackage
from app.schemas.enums import AgentRole, AudienceChannel, HazardType, Severity

SYSTEM_PROMPT = """\
You are the Emergency Risk Communication Officer.

Every public warning you write must contain all five elements. Messages \
missing any of them measurably reduce protective action:
1. HAZARD — what is happening, specifically
2. LOCATION — precisely who is affected, by named area
3. TIMING — when impact is expected and how long there is to act
4. ACTION — exactly what to do, as an imperative
5. SOURCE — which authority issued this

Rules:
- Never write "take necessary precautions". That is not a warning; it hands the \
decision back to people who lack the information to make it.
- State uncertainty explicitly. Populations tolerate acknowledged uncertainty; \
they do not forgive discovered concealment.
- NEVER issue an all-clear. That requires verification you do not have.
- Tailor each artifact genuinely to its audience:
  * public_alert — short, imperative, plain language, actionable now
  * responder_brief — tactical detail, responder hazards, command structure
  * government_sitrep — assessment, resource status, unmet needs, decisions required
  * hospital_advisory — expected casualty volume and category, timing, routing
  * volunteer_tasking — specific tasks, required skills, and an EXPLICIT list of \
what volunteers must NOT attempt
- `misinformation_guardrails` must pre-empt the rumours this specific hazard \
predictably generates. Lead with the verified fact; do not repeat the false \
claim prominently.
- Do not invent statistics. Use only figures from the operational picture.
"""

#: Rumour categories that predictably emerge, by hazard.
RUMOUR_PATTERNS: dict[HazardType, list[str]] = {
    HazardType.FLOOD: [
        "Dam-failure rumours triggering mass panic movement — state the verified reservoir status and release schedule.",
        "Inflated casualty figures — publish only confirmed counts and name the authoritative channel.",
        "False all-clear messages causing premature return into the flood zone.",
        "Claims that piped water is safe when it is not, or unsafe when it is — state the verified test status.",
    ],
    HazardType.EARTHQUAKE: [
        "Aftershock prediction rumours — no one can predict aftershock timing; say so plainly.",
        "False reports of specific buildings being safe to re-enter before engineering assessment.",
        "Inflated casualty figures circulating ahead of confirmed counts.",
    ],
    HazardType.CYCLONE: [
        "'The storm has passed' messages during eye passage — warn explicitly that the eyewall returns.",
        "Fuel and supply shortage rumours driving hoarding.",
    ],
    HazardType.EPIDEMIC: [
        "Unverified cure and prevention claims.",
        "Rumours that reporting symptoms leads to forced removal, which suppresses case reporting.",
    ],
}

DEFAULT_RUMOURS = [
    "Casualty figures diverging from confirmed counts — publish only verified numbers.",
    "Fabricated official instructions, including false evacuation or all-clear orders.",
    "Supply shortage claims driving hoarding of fuel, water and medicine.",
]


class CommunicationAgent(BaseAgent[CommunicationPackage]):
    role = AgentRole.COMMUNICATION
    title = "Risk Communication"
    tier = ModelTier.FAST

    @property
    def output_schema(self) -> type[CommunicationPackage]:
        return CommunicationPackage

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def summarise(self, output: CommunicationPackage) -> str:
        return (
            output.public_alert_headline
            or f"{len(output.artifacts)} communication artifacts prepared"
        )

    def build_prompt(self, ctx: AgentContext, evidence: dict[str, Any]) -> str:
        findings = ctx.findings
        plan = findings.get("allocation_plan")
        weather = findings.get("weather")
        shelter = findings.get("shelter")
        medical = findings.get("medical")

        lines = [ctx.situation_brief(), "", "=== OPERATIONAL PICTURE FOR MESSAGING ==="]

        if weather:
            lines.append(f"  Weather: {weather.headline}")
            if getattr(weather, "safe_operating_window_hours", None) is not None:
                lines.append(
                    f"    Safe operating window: {weather.safe_operating_window_hours} hours"
                )
        if shelter:
            lines.append(f"  Shelter: {shelter.headline}")
            for route in getattr(shelter, "evacuation_routes", [])[:4]:
                lines.append(f"    Destination: {route}")
        if medical:
            lines.append(f"  Medical: {medical.headline}")
            lines.append(f"    Triage split: {getattr(medical, 'triage_categories', {})}")
        if plan:
            lines.append(
                f"  Resources: {plan.total_units_allocated:,} units dispatched, "
                f"{plan.coverage_ratio:.0%} coverage"
            )
            if plan.unmet_needs:
                lines.append(
                    "    UNMET: "
                    + "; ".join(
                        f"{u.resource_type.value} short {u.quantity_short:,}"
                        for u in plan.unmet_needs[:4]
                    )
                )

        lines += [
            "",
            "Produce the communication package. Write one artifact for each of: "
            "public_alert, responder_brief, government_sitrep, hospital_advisory, "
            "volunteer_tasking.",
        ]
        return "\n".join(lines)

    def fallback(
        self, ctx: AgentContext, evidence: dict[str, Any]
    ) -> CommunicationPackage:
        assessment = ctx.assessment
        findings = ctx.findings
        plan = findings.get("allocation_plan")
        shelter = findings.get("shelter")
        medical = findings.get("medical")
        weather = findings.get("weather")

        hazard = assessment.hazard_type if assessment else HazardType.UNKNOWN
        severity = assessment.severity if assessment else Severity.MODERATE
        place = ctx.report.location.label
        hazard_label = hazard.value.replace("_", " ")

        timing = "Impact is occurring now."
        if weather is not None:
            window = getattr(weather, "safe_operating_window_hours", None)
            if window is not None and window > 0:
                timing = f"Conditions are expected to remain workable for approximately {window:.0f} hours."
            elif window == 0:
                timing = "Conditions are already unsafe for outdoor movement."

        destinations = ""
        if shelter is not None and getattr(shelter, "evacuation_routes", None):
            destinations = " Proceed to: " + "; ".join(shelter.evacuation_routes[:3]) + "."

        headline = f"{severity.value.upper()} {hazard_label} — {place}"

        public_body = (
            f"HAZARD: A {hazard_label} affecting {place}. "
            f"WHO IS AFFECTED: Residents within approximately "
            f"{assessment.impact.affected_radius_km if assessment else 5} km of "
            f"{ctx.report.location.name}. "
            f"TIMING: {timing} "
            f"ACTION: Move to higher ground or a designated relief camp now."
            f"{destinations} Do not attempt to cross moving water — 30 cm is enough "
            f"to sweep a vehicle. Do not wait for a further message before moving. "
            f"SOURCE: District Emergency Operations Centre. "
            f"This assessment was generated by automated analysis and has not yet "
            f"been confirmed by a human duty officer."
        )

        artifacts = [
            CommunicationArtifact(
                channel=AudienceChannel.PUBLIC_ALERT,
                audience="Residents of the affected area",
                subject=headline,
                body=public_body,
                call_to_action=[
                    "Move to a designated relief camp or higher ground now",
                    "Do not cross moving water on foot or by vehicle",
                    "Take essential medication and identity documents",
                    "Assist elderly and disabled neighbours to evacuate",
                ],
            ),
            CommunicationArtifact(
                channel=AudienceChannel.RESPONDER_BRIEF,
                audience="Field response teams",
                subject=f"Tactical brief — {hazard_label} — {place}",
                body=(
                    f"Situation: {assessment.summary if assessment else 'Assessment pending.'} "
                    f"Responder hazards: electrical isolation must be CONFIRMED with the "
                    f"distribution utility before entering inundated areas; submerged roads "
                    f"are structurally suspect due to scour; do not enter moving water of "
                    f"unknown depth. "
                    + (
                        f"Operating window: {weather.safe_operating_window_hours} hours. "
                        if weather is not None
                        and getattr(weather, "safe_operating_window_hours", None) is not None
                        else ""
                    )
                    + f"Boat operations require two crew plus one trained swimmer. "
                    f"Report to the district EOC on the established net."
                ),
                call_to_action=[
                    "Confirm electrical isolation before entry",
                    "Verify boat crew composition before launch",
                    "Report route status changes to the EOC immediately",
                ],
            ),
            CommunicationArtifact(
                channel=AudienceChannel.GOVERNMENT_SITREP,
                audience="District and state administration",
                subject=f"SITREP — {ctx.incident_id} — {place}",
                body=(
                    f"Hazard: {hazard_label}. Severity: {severity.value}. "
                    f"Population at risk: "
                    f"{assessment.impact.population_at_risk:,} " if assessment else ""
                )
                + (
                    f"Resource coverage: {plan.coverage_ratio:.0%} with "
                    f"{plan.total_units_allocated:,} units dispatched across "
                    f"{len(plan.organizations_engaged)} partner organisations. "
                    if plan
                    else "Resource plan pending. "
                )
                + (
                    "UNMET NEEDS REQUIRING ESCALATION: "
                    + "; ".join(
                        f"{u.resource_type.value} short {u.quantity_short:,} "
                        f"({u.escalation_path})"
                        for u in plan.unmet_needs[:5]
                    )
                    if plan and plan.unmet_needs
                    else "All requirements currently covered."
                ),
                call_to_action=(
                    [
                        f"Approve escalation for {u.resource_type.value}"
                        for u in (plan.unmet_needs[:3] if plan else [])
                    ]
                    or ["Note the situation report"]
                ),
            ),
            CommunicationArtifact(
                channel=AudienceChannel.HOSPITAL_ADVISORY,
                audience="Receiving hospitals and health facilities",
                subject=f"Casualty advisory — {place}",
                body=(
                    (
                        f"Expect approximately {medical.casualty_projection:,} casualties. "
                        f"Triage split: {medical.triage_categories}. "
                        + (
                            f"Projected bed deficit across reachable facilities: "
                            f"{medical.bed_deficit:,} admissions. "
                            if getattr(medical, "bed_deficit", 0)
                            else ""
                        )
                        + "RED casualties are being routed to trauma-capable facilities "
                        "with confirmed capacity; GREEN casualties are being diverted to "
                        "primary care to preserve trauma capacity. "
                        "Alert blood banks now — O-negative is the binding constraint "
                        "before cross-matching."
                    )
                    if medical is not None
                    else "Medical assessment pending. Prepare for casualty reception."
                ),
                call_to_action=[
                    "Confirm current available bed and ICU count to the EOC",
                    "Activate mass casualty protocol",
                    "Alert blood bank",
                ],
            ),
            CommunicationArtifact(
                channel=AudienceChannel.VOLUNTEER_TASKING,
                audience="Registered volunteers",
                subject=f"Volunteer tasking — {place}",
                body=(
                    "Tasks required: relief camp registration and management, "
                    "supply distribution, kitchen support, assisting elderly and "
                    "disabled evacuees at camps, and communication runner duties. "
                    "SAFETY BOUNDARY — YOU MUST NOT: attempt water rescue, enter "
                    "flooded buildings, handle downed electrical lines, operate "
                    "boats without certification, or enter any structure placarded "
                    "unsafe. Untrained volunteers attempting water rescue is a "
                    "recurring cause of preventable deaths. Report to the camp "
                    "coordinator and sign in before beginning any task."
                ),
                call_to_action=[
                    "Report to your assigned relief camp coordinator",
                    "Sign in before starting any task",
                    "Do not attempt water rescue under any circumstances",
                ],
            ),
        ]

        return CommunicationPackage(
            artifacts=artifacts,
            public_alert_headline=headline,
            misinformation_guardrails=RUMOUR_PATTERNS.get(hazard, DEFAULT_RUMOURS),
        )
