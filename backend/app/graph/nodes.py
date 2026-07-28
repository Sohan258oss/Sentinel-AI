"""Graph nodes.

Each node is a thin adapter: build an :class:`AgentContext` from graph state,
run the agent, return a state delta. Domain logic lives in agents; orchestration
concerns live here. That separation is what lets an agent be unit-tested without
constructing a graph.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.agents import AgentContext, get_agent
from app.core.config import settings
from app.core.events import trace_bus
from app.core.logging import get_logger
from app.graph.state import IncidentState
from app.memory.store import SemanticLesson, get_memory
from app.schemas.command import DISPATCHABLE_AGENTS
from app.schemas.enums import (
    AgentRole,
    AgentStatus,
    IncidentStatus,
    Severity,
    TraceEventType,
)
from app.schemas.trace import AgentTrace
from app.services.allocator import (
    AllocationInputs,
    allocate,
    derive_requirements,
    severity_reserve_fraction,
)

logger = get_logger(__name__)

#: Maps a dispatchable role to the state key its finding is stored under.
FINDING_KEY: dict[AgentRole, str] = {
    AgentRole.WEATHER: "weather",
    AgentRole.INFRASTRUCTURE: "infrastructure",
    AgentRole.MEDICAL: "medical",
    AgentRole.SHELTER: "shelter",
    AgentRole.KNOWLEDGE: "knowledge",
}


def _context(state: IncidentState, **overrides: Any) -> AgentContext:
    """Build an agent context from graph state.

    Overrides are merged rather than passed through as extra kwargs, so a caller
    may override any defaulted field (``cycle``, ``findings``, …) without
    colliding with the value derived from state.
    """
    fields: dict[str, Any] = {
        "report": state["report"],
        "run_id": state["run_id"],
        "assessment": state.get("assessment"),
        "activation_plan": state.get("activation_plan"),
        "findings": state.get("findings", {}),
        "cycle": state.get("cycle", 0),
    }
    fields.update(overrides)
    return AgentContext(**fields)


async def _emit(
    state: IncidentState,
    agent: AgentRole,
    event_type: TraceEventType,
    title: str,
    *,
    detail: str = "",
    status: AgentStatus = AgentStatus.RUNNING,
    payload: dict[str, Any] | None = None,
) -> None:
    await trace_bus.publish(
        AgentTrace(
            incident_id=state["incident_id"],
            run_id=state["run_id"],
            event_type=event_type,
            agent=agent,
            status=status,
            title=title,
            detail=detail,
            payload=payload or {},
        )
    )


# ---------------------------------------------------------------------------
# Sequential stages
# ---------------------------------------------------------------------------


async def intake_node(state: IncidentState) -> dict[str, Any]:
    """Normalise the incoming report and open the run."""
    report = state["report"]

    await _emit(
        state,
        AgentRole.INTAKE,
        TraceEventType.RUN_STARTED,
        f"Incident {report.incident_id} received",
        detail=(
            f"{report.description[:200]} — {report.location.label} "
            f"via {report.source.channel}"
        ),
        payload={
            "incident_id": report.incident_id,
            "location": report.location.model_dump(mode="json"),
            "media_count": len(report.media_paths),
            "channel": report.source.channel,
        },
    )
    await _emit(
        state,
        AgentRole.INTAKE,
        TraceEventType.NODE_COMPLETED,
        "Intake complete",
        detail=f"{len(report.media_paths)} image(s) attached",
        status=AgentStatus.COMPLETED,
    )
    return {"status": IncidentStatus.ANALYZING}


async def situation_node(state: IncidentState) -> dict[str, Any]:
    agent = get_agent(AgentRole.SITUATION_ANALYSIS)
    assessment = await agent.run(_context(state))
    return {"assessment": assessment, "status": IncidentStatus.COORDINATING}


async def commander_node(state: IncidentState) -> dict[str, Any]:
    agent = get_agent(AgentRole.COMMANDER)
    plan = await agent.run(_context(state))

    # Guard: the model may name a non-dispatchable role. Silently routing to a
    # non-existent node would fail the whole graph, so filter and disclose.
    valid = [d for d in plan.dispatches if d.agent in DISPATCHABLE_AGENTS]
    dropped = [d.agent.value for d in plan.dispatches if d.agent not in DISPATCHABLE_AGENTS]
    if dropped:
        logger.warning("commander.invalid_dispatch_filtered", dropped=dropped)
        plan.dispatches = valid

    await _emit(
        state,
        AgentRole.COMMANDER,
        TraceEventType.ROUTING_DECISION,
        f"Dispatching {len(plan.dispatches)} specialists",
        detail=plan.command_intent[:400],
        payload={
            "activated": [d.agent.value for d in plan.dispatches],
            "declined": [
                {"agent": d.agent.value, "reason": d.reason} for d in plan.declined
            ],
            "escalate_to_state": plan.escalate_to_state,
            "dispatches": [
                {
                    "agent": d.agent.value,
                    "priority": d.priority,
                    "reason": d.reason,
                    "focus_question": d.focus_question,
                }
                for d in plan.dispatches
            ],
        },
    )
    return {"activation_plan": plan, "status": IncidentStatus.ACTIVE}


# ---------------------------------------------------------------------------
# Parallel specialists
# ---------------------------------------------------------------------------


def make_specialist_node(role: AgentRole):
    """Build a node function for a dispatchable specialist."""

    async def node(state: IncidentState) -> dict[str, Any]:
        agent = get_agent(role)
        plan = state.get("activation_plan")

        focus = ""
        if plan is not None:
            for dispatch in plan.dispatches:
                if dispatch.agent == role:
                    focus = dispatch.focus_question
                    break

        product = await agent.run(_context(state, focus_question=focus))
        return {"findings": {FINDING_KEY[role]: product}}

    node.__name__ = f"{role.value}_node"
    return node


# ---------------------------------------------------------------------------
# Allocation, assurance, output
# ---------------------------------------------------------------------------


async def allocation_node(state: IncidentState) -> dict[str, Any]:
    """Deterministic optimisation, then LLM narration of the result."""
    assessment = state.get("assessment")
    report = state["report"]
    findings = state.get("findings", {})
    cycle = state.get("cycle", 0)
    reflection = state.get("reflection")

    if assessment is None:
        return {"errors": ["Allocation skipped: no situation assessment available"]}

    inputs = AllocationInputs(
        assessment=assessment,
        destination=report.location.point,
        destination_name=report.location.label,
        medical=findings.get("medical"),
        shelter=findings.get("shelter"),
    )

    requirements = derive_requirements(inputs)
    plan = allocate(
        requirements,
        inputs,
        reserve_fraction=severity_reserve_fraction(assessment.severity),
        revision=cycle,
    )

    await _emit(
        state,
        AgentRole.ALLOCATION,
        TraceEventType.REASONING if cycle == 0 else TraceEventType.REVISION,
        (
            f"Computed allocation plan (revision {cycle})"
            if cycle
            else "Computed allocation plan"
        ),
        detail=(
            f"{plan.total_units_allocated:,} units across "
            f"{len(plan.allocations)} dispatches from "
            f"{len(plan.depots_engaged)} depots; coverage "
            f"{plan.coverage_ratio:.0%}; {len(plan.unmet_needs)} unmet needs"
        ),
        payload={
            "coverage_ratio": plan.coverage_ratio,
            "unmet_count": len(plan.unmet_needs),
            "organizations": [o.value for o in plan.organizations_engaged],
            "revision": cycle,
        },
    )

    # The agent explains the computed plan; it never alters the numbers.
    agent = get_agent(AgentRole.ALLOCATION)
    context = _context(
        state,
        revision_instruction=(
            reflection.revision_instruction if reflection and cycle else None
        ),
    )
    context.findings = {**findings, "allocation_plan": plan}
    strategy = await agent.run(context)

    plan.strategy_narrative = strategy.strategy_narrative

    return {
        "allocation_plan": plan,
        "allocation_strategy": strategy,
        "findings": {"allocation_plan": plan, "allocation_strategy": strategy},
    }


async def reflection_node(state: IncidentState) -> dict[str, Any]:
    agent = get_agent(AgentRole.REFLECTION)
    cycle = state.get("cycle", 0)

    context = _context(state, cycle=cycle)
    context.findings = {
        **state.get("findings", {}),
        "allocation_plan": state.get("allocation_plan"),
        "allocation_strategy": state.get("allocation_strategy"),
    }

    verdict = await agent.run(context)
    verdict.cycle = cycle

    await _emit(
        state,
        AgentRole.REFLECTION,
        TraceEventType.CRITIQUE,
        "APPROVED" if verdict.approved else "REVISION REQUIRED",
        detail=(
            verdict.revision_instruction
            or f"Quality {verdict.overall_quality:.0%}; no blocking issues found"
        ),
        status=AgentStatus.COMPLETED,
        payload={
            "approved": verdict.approved,
            "quality": verdict.overall_quality,
            "cycle": cycle,
            "findings": [
                {
                    "issue": f.issue,
                    "severity": f.severity,
                    "component": f.affected_component,
                    "fix": f.suggested_fix,
                }
                for f in verdict.findings
            ],
        },
    )

    return {
        "reflection": verdict,
        "reflection_history": [verdict],
        "cycle": cycle + 1,
    }


async def communication_node(state: IncidentState) -> dict[str, Any]:
    agent = get_agent(AgentRole.COMMUNICATION)

    context = _context(state)
    context.findings = {
        **state.get("findings", {}),
        "allocation_plan": state.get("allocation_plan"),
    }

    package = await agent.run(context)
    return {"communications": package, "status": IncidentStatus.STABILIZING}


async def finalize_node(state: IncidentState) -> dict[str, Any]:
    """Distil durable lessons, then close the run.

    This is what makes the platform improve with use: each incident deposits
    reusable knowledge that future runs of the Commander retrieve.
    """
    assessment = state.get("assessment")
    report = state["report"]
    findings = state.get("findings", {})
    plan = state.get("allocation_plan")
    memory = get_memory()

    lessons: list[str] = []

    if assessment is not None:
        shelter = findings.get("shelter")
        if shelter is not None and getattr(shelter, "capacity_deficit", 0) > 0:
            lessons.append(
                f"{report.location.name}: shelter capacity was short by "
                f"{shelter.capacity_deficit:,} during a {assessment.severity.value} "
                f"{assessment.hazard_type.value}. Pre-position additional capacity."
            )
            unusable = [s.name for s in getattr(shelter, "shelters", []) if not s.flood_safe]
            if unusable:
                lessons.append(
                    f"{report.location.name}: these designated shelters are "
                    f"flood-exposed and should be reclassified: "
                    f"{', '.join(unusable[:3])}."
                )

        medical = findings.get("medical")
        if medical is not None and getattr(medical, "bed_deficit", 0) > 0:
            lessons.append(
                f"{report.location.name}: reachable hospital capacity fell short by "
                f"{medical.bed_deficit:,} beds during a "
                f"{assessment.hazard_type.value}. Pre-arrange inter-district transfer."
            )

        if plan is not None:
            for unmet in plan.unmet_needs[:3]:
                lessons.append(
                    f"{report.location.name}: {unmet.resource_type.value} was short "
                    f"{unmet.quantity_short:,} for a {assessment.severity.value} "
                    f"{assessment.hazard_type.value}. Increase pre-positioned stock."
                )

        for text in lessons:
            memory.learn(
                SemanticLesson(
                    lesson_id=f"LSN-{uuid.uuid4().hex[:8].upper()}",
                    hazard_type=assessment.hazard_type,
                    region=report.location.name,
                    point=report.location.point,
                    severity_seen=assessment.severity,
                    lesson=text,
                    evidence=assessment.headline,
                    source_incident_id=report.incident_id,
                )
            )

    if lessons:
        await _emit(
            state,
            AgentRole.REFLECTION,
            TraceEventType.REASONING,
            f"Recorded {len(lessons)} institutional lessons",
            detail=" | ".join(lessons[:3]),
            status=AgentStatus.COMPLETED,
            payload={"lessons": lessons},
        )

    await _emit(
        state,
        AgentRole.COMMANDER,
        TraceEventType.RUN_COMPLETED,
        "Operational picture complete",
        detail=(
            f"Severity {assessment.severity.value if assessment else 'unknown'}; "
            f"{len(findings)} intelligence products; "
            f"{state.get('cycle', 0)} reflection cycle(s)"
        ),
        status=AgentStatus.COMPLETED,
        payload={
            "reflection_cycles": state.get("cycle", 0),
            "lessons_learned": len(lessons),
        },
    )

    return {"status": IncidentStatus.RESOLVED}


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------


def route_specialists(state: IncidentState) -> list[str]:
    """Conditional fan-out — Pattern 5's branch point.

    Returns a LIST of node names, which LangGraph executes as one parallel
    superstep. Exactly which specialists appear is decided per-incident by the
    Commander.
    """
    plan = state.get("activation_plan")
    if plan is None or not plan.dispatches:
        # Nothing to consult — go straight to allocation rather than stalling.
        return ["allocation"]

    targets = [
        d.agent.value
        for d in sorted(plan.dispatches, key=lambda x: x.priority)
        if d.agent in DISPATCHABLE_AGENTS
    ]
    return targets or ["allocation"]


def route_after_reflection(state: IncidentState) -> str:
    """Cycle back for revision, or proceed — bounded by configuration."""
    verdict = state.get("reflection")
    cycle = state.get("cycle", 0)

    if verdict is None:
        return "communication"

    if verdict.approved:
        return "communication"

    if cycle >= settings.max_reflection_cycles:
        logger.info(
            "graph.reflection_budget_exhausted",
            cycle=cycle,
            max_cycles=settings.max_reflection_cycles,
        )
        return "communication"

    return "allocation"


def severity_gate(state: IncidentState) -> str:
    """Trivial incidents skip the full command apparatus.

    Standing up eleven agents for a fallen tree branch is exactly the kind of
    indiscriminate behaviour that makes an operator stop trusting the system.
    """
    assessment = state.get("assessment")
    if assessment is None:
        return "commander"
    if assessment.severity.rank <= Severity.INFORMATIONAL.rank:
        return "communication"
    return "commander"
