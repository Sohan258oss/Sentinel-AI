"""Commander Agent — the orchestrator.

Produces the :class:`ActivationPlan`, which the graph reads to decide which
specialist nodes execute. This agent's output *is* Pattern 5's conditional
branch — not a description of one.

Two design points worth stating:

* **Declining an agent is recorded, not silent.** The plan carries a
  ``declined`` list with reasons. An operator seeing "Shelter Agent not
  activated — no displacement expected at this severity" can challenge the
  decision. Silent non-activation is indistinguishable from a bug.
* **The fallback is a real doctrine-derived routing table**, so the platform
  still triages sensibly with no model available.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.core.llm import ModelTier
from app.memory.store import get_memory
from app.schemas.command import ActivationPlan, AgentDispatch
from app.schemas.enums import AgentRole, HazardType, Severity

SYSTEM_PROMPT = """\
You are the Incident Commander of an AI-operated Emergency Operations Centre. \
You do not perform analysis yourself. You decide WHICH specialist officers to \
activate for this specific incident, and you state your command intent.

Available specialists:
- weather: meteorology, hydrology, flood forecasting, safe operating windows.
- infrastructure: roads, bridges, power, water, telecom, structural damage, \
access corridors.
- medical: casualty projection, hospital capacity, casualty distribution, \
ambulances, disease risk.
- shelter: evacuation destinations, camp capacity, vulnerable groups.
- knowledge: retrieval of official doctrine and standard operating procedures \
from the verified document corpus.

Rules:
- Activate a specialist ONLY when this incident genuinely requires their \
analysis. Activating everyone for a minor incident wastes response capacity \
and buries the signal for the operator.
- ALWAYS activate `knowledge` for incidents of moderate severity or above — \
doctrine compliance is not optional in emergency response.
- For every specialist you do NOT activate, record it in `declined` with a \
reason. Your decisions must be auditable.
- Give each activated specialist a sharp `focus_question` — the single most \
decision-relevant thing they must determine. Vague tasking produces vague \
intelligence.
- Set priority 1 for life-safety-critical specialists, 3 for supporting ones.
- `command_intent` must state the objective, not the activity: what the end \
state should look like, in two or three sentences.
- Set `escalate_to_state` true when district-level resources are plainly \
insufficient.
"""

#: Doctrine-derived routing used when no model is available. Maps hazard to the
#: specialists that hazard's response demands.
HAZARD_ROUTING: dict[HazardType, tuple[AgentRole, ...]] = {
    HazardType.FLOOD: (
        AgentRole.WEATHER,
        AgentRole.SHELTER,
        AgentRole.INFRASTRUCTURE,
        AgentRole.MEDICAL,
    ),
    HazardType.URBAN_FLOOD: (
        AgentRole.WEATHER,
        AgentRole.INFRASTRUCTURE,
        AgentRole.SHELTER,
    ),
    HazardType.CYCLONE: (
        AgentRole.WEATHER,
        AgentRole.SHELTER,
        AgentRole.INFRASTRUCTURE,
        AgentRole.MEDICAL,
    ),
    HazardType.EARTHQUAKE: (
        AgentRole.MEDICAL,
        AgentRole.INFRASTRUCTURE,
        AgentRole.SHELTER,
    ),
    HazardType.BUILDING_COLLAPSE: (AgentRole.MEDICAL, AgentRole.INFRASTRUCTURE),
    HazardType.WILDFIRE: (AgentRole.WEATHER, AgentRole.SHELTER, AgentRole.MEDICAL),
    HazardType.STRUCTURAL_FIRE: (AgentRole.MEDICAL, AgentRole.INFRASTRUCTURE),
    HazardType.LANDSLIDE: (
        AgentRole.WEATHER,
        AgentRole.INFRASTRUCTURE,
        AgentRole.MEDICAL,
    ),
    HazardType.HEATWAVE: (AgentRole.WEATHER, AgentRole.MEDICAL),
    HazardType.EPIDEMIC: (AgentRole.MEDICAL, AgentRole.SHELTER),
    HazardType.INDUSTRIAL_CHEMICAL: (
        AgentRole.MEDICAL,
        AgentRole.WEATHER,
        AgentRole.SHELTER,
    ),
    HazardType.TSUNAMI: (AgentRole.WEATHER, AgentRole.SHELTER, AgentRole.MEDICAL),
    HazardType.MASS_CASUALTY: (AgentRole.MEDICAL,),
    HazardType.DROUGHT: (AgentRole.WEATHER,),
    HazardType.UNKNOWN: (AgentRole.WEATHER, AgentRole.INFRASTRUCTURE, AgentRole.MEDICAL),
}

FOCUS_QUESTIONS: dict[AgentRole, str] = {
    AgentRole.WEATHER: "How much time remains before conditions worsen, and is there a safe operating window for outdoor rescue?",
    AgentRole.INFRASTRUCTURE: "Which access corridors into the affected area remain viable, and for how long?",
    AgentRole.MEDICAL: "Can reachable hospital capacity absorb the projected casualty load, and where is the deficit?",
    AgentRole.SHELTER: "Is there enough safe, reachable shelter capacity for the displaced population?",
    AgentRole.KNOWLEDGE: "What do official SOPs mandate and prohibit for this hazard at this severity?",
}


class CommanderAgent(BaseAgent[ActivationPlan]):
    role = AgentRole.COMMANDER
    title = "Incident Commander"
    tier = ModelTier.REASONING

    @property
    def output_schema(self) -> type[ActivationPlan]:
        return ActivationPlan

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def gather(self, ctx: AgentContext) -> dict[str, Any]:
        """Recall institutional memory from comparable past incidents."""
        memory = get_memory()
        hazard = (
            ctx.assessment.hazard_type if ctx.assessment else HazardType.UNKNOWN
        )
        lessons = memory.lessons_digest(
            hazard=hazard, point=ctx.report.location.point
        )
        return {"lessons": lessons}

    def build_prompt(self, ctx: AgentContext, evidence: dict[str, Any]) -> str:
        return "\n".join(
            [
                ctx.situation_brief(),
                "",
                "=== INSTITUTIONAL MEMORY (lessons from prior incidents) ===",
                evidence.get("lessons", "(none)"),
                "",
                f"Incident id for the plan: {ctx.incident_id}",
                "",
                "Decide which specialists to activate, task each with a sharp "
                "focus question, record those you decline and why, and state "
                "your command intent.",
            ]
        )

    def summarise(self, output: ActivationPlan) -> str:
        agents = ", ".join(a.value for a in output.active_agents) or "none"
        return f"Activated {len(output.dispatches)} specialists: {agents}"

    def fallback(self, ctx: AgentContext, evidence: dict[str, Any]) -> ActivationPlan:
        severity = ctx.assessment.severity if ctx.assessment else Severity.MODERATE
        hazard = ctx.assessment.hazard_type if ctx.assessment else HazardType.UNKNOWN

        selected = list(HAZARD_ROUTING.get(hazard, HAZARD_ROUTING[HazardType.UNKNOWN]))

        # Doctrine: retrieval is mandatory at moderate severity and above.
        if severity.rank >= Severity.MODERATE.rank:
            selected.append(AgentRole.KNOWLEDGE)

        # Minor incidents do not warrant the full team.
        if severity.rank <= Severity.MINOR.rank:
            selected = selected[:2]

        dispatches = [
            AgentDispatch(
                agent=role,
                reason=(
                    f"Standard activation for {hazard.value} at "
                    f"{severity.value} severity (doctrine-derived routing table)."
                ),
                priority=1 if role in (AgentRole.MEDICAL, AgentRole.SHELTER) else 2,
                focus_question=FOCUS_QUESTIONS.get(role, ""),
            )
            for role in dict.fromkeys(selected)  # de-duplicate, preserve order
        ]

        activated = {d.agent for d in dispatches}
        declined = [
            AgentDispatch(
                agent=role,
                reason=(
                    f"Not indicated for {hazard.value} at {severity.value} severity "
                    "by the doctrine routing table."
                ),
                priority=3,
            )
            for role in (
                AgentRole.WEATHER,
                AgentRole.INFRASTRUCTURE,
                AgentRole.MEDICAL,
                AgentRole.SHELTER,
                AgentRole.KNOWLEDGE,
            )
            if role not in activated
        ]

        return ActivationPlan(
            incident_id=ctx.incident_id,
            dispatches=dispatches,
            declined=declined,
            command_intent=(
                f"Stabilise the {hazard.value} incident at "
                f"{ctx.report.location.label}. Priority is life safety: complete "
                f"evacuation of at-risk population and ensure casualty capacity "
                f"is not exceeded. Routing determined by doctrine table without "
                f"model reasoning."
            ),
            escalate_to_state=severity.rank >= Severity.SEVERE.rank,
            escalation_reason=(
                "Severity at or above 'severe' exceeds typical district-level "
                "response capacity."
                if severity.rank >= Severity.SEVERE.rank
                else None
            ),
        )
