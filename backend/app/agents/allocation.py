"""Resource Allocation Agent — the workbook's core problem.

Division of labour is strict and deliberate:

* The **optimiser** (``app.services.allocator``) decides what, how much, from
  which depot, by when. Deterministic, auditable, reproducible.
* This **agent** explains the plan, stress-tests it, and flags equity gaps and
  failure modes. It never touches a quantity.

Letting a language model do constrained multi-depot arithmetic would be the
single most fragile choice available; letting it explain that arithmetic to a
human commander is exactly what it is good at.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.core.llm import ModelTier
from app.schemas.enums import AgentRole
from app.schemas.resources import AllocationPlan, AllocationStrategy

SYSTEM_PROMPT = """\
You are the Resource Allocation Officer in an Emergency Operations Centre. \
A constrained optimiser has already produced a dispatch plan. Your job is to \
explain it, challenge it, and expose what it cannot see.

You must NOT restate or alter any quantity, depot or ETA. Those are computed \
and authoritative.

Apply this doctrine when judging the plan:
- Priority order is life safety, then incident stabilisation, then property. \
No quantity of lower-tier need outranks an unmet higher-tier need.
- A strategic reserve is withheld deliberately. Do not characterise withheld \
stock as a shortfall.
- UNMET NEEDS are the most important part of the plan. State plainly what \
cannot be covered, who is affected, and exactly who must be asked next.
- Consider access decay: a requirement in an area about to become unreachable \
must be served before an equal one that will stay reachable.
- Consider EQUITY explicitly. Aggregate coverage can look adequate while a \
cut-off settlement or a vulnerable group receives nothing. Name who is at risk \
of being under-served.
- Identify what would make this plan fail: route severance, depot \
unavailability, demand growth, or a concurrent second incident.

Be concise and operational. A commander reads this under time pressure.
"""


class AllocationAgent(BaseAgent[AllocationStrategy]):
    role = AgentRole.ALLOCATION
    title = "Resource Allocation"
    tier = ModelTier.REASONING

    @property
    def output_schema(self) -> type[AllocationStrategy]:
        return AllocationStrategy

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def summarise(self, output: AllocationStrategy) -> str:
        return output.strategy_narrative[:180] if output.strategy_narrative else "Allocation strategy prepared"

    def build_prompt(self, ctx: AgentContext, evidence: dict[str, Any]) -> str:
        plan: AllocationPlan | None = ctx.findings.get("allocation_plan")
        if plan is None:
            return ctx.situation_brief() + "\n\nNo allocation plan was computed."

        lines = [
            ctx.situation_brief(),
            "",
            "=== COMPUTED ALLOCATION PLAN (authoritative — do not alter) ===",
            f"Plan {plan.plan_id} | revision {plan.revision}",
            f"Coverage: {plan.coverage_ratio:.0%} of demanded units allocated",
            f"Total units dispatched: {plan.total_units_allocated:,}",
            f"Depots engaged: {len(plan.depots_engaged)} "
            f"({', '.join(plan.depots_engaged[:5])})",
            f"Partner organisations: "
            f"{', '.join(o.value for o in plan.organizations_engaged)}",
            "",
            "--- REQUIREMENTS ---",
        ]
        for requirement in plan.requirements:
            lines.append(
                f"  {requirement.resource_type.value}: "
                f"{requirement.quantity_required:,} ({requirement.urgency.value}, "
                f"deadline {requirement.deadline_hours:.0f}h, "
                f"serves {requirement.beneficiaries:,}) — {requirement.justification}"
            )

        lines += ["", "--- DISPATCHES ---"]
        for allocation in plan.allocations[:20]:
            lines.append(
                f"  {allocation.quantity:,} {allocation.resource_type.value} "
                f"from {allocation.from_depot_name} "
                f"({allocation.distance_km} km, ETA {allocation.eta_minutes} min, "
                f"{allocation.urgency.value})"
            )
        if len(plan.allocations) > 20:
            lines.append(f"  … and {len(plan.allocations) - 20} further dispatches")

        lines += ["", "--- UNMET NEEDS ---"]
        if plan.unmet_needs:
            for unmet in plan.unmet_needs:
                lines.append(
                    f"  SHORT {unmet.quantity_short:,} {unmet.resource_type.value} "
                    f"affecting {unmet.beneficiaries_affected:,} people. "
                    f"Consequence: {unmet.consequence} "
                    f"Escalation: {unmet.escalation_path}"
                )
        else:
            lines.append("  All requirements covered from available stock.")

        if ctx.revision_instruction:
            lines += [
                "",
                "=== REVISION INSTRUCTION FROM REFLECTION REVIEW ===",
                ctx.revision_instruction,
                "Address this specifically in your narrative.",
            ]

        # Supporting intelligence, so the agent can spot equity gaps the
        # optimiser is structurally blind to.
        shelter = ctx.findings.get("shelter")
        medical = ctx.findings.get("medical")
        infrastructure = ctx.findings.get("infrastructure")
        knowledge = ctx.findings.get("knowledge")

        lines += ["", "=== SUPPORTING INTELLIGENCE ==="]
        if medical:
            lines.append(f"  Medical: {medical.headline}")
            if medical.bed_deficit:
                lines.append(f"    BED DEFICIT: {medical.bed_deficit:,}")
        if shelter:
            lines.append(f"  Shelter: {shelter.headline}")
            if shelter.vulnerable_groups:
                lines.append(
                    "    Vulnerable groups: " + "; ".join(shelter.vulnerable_groups[:3])
                )
        if infrastructure:
            lines.append(f"  Infrastructure: {infrastructure.headline}")
            if infrastructure.access_corridors:
                lines.append(
                    "    Corridors: " + "; ".join(infrastructure.access_corridors[:3])
                )
        if knowledge and knowledge.mandated_actions:
            lines.append(
                "  Doctrine mandates: " + "; ".join(knowledge.mandated_actions[:4])
            )

        lines += [
            "",
            "Explain and challenge this plan. Do not restate quantities.",
        ]
        return "\n".join(lines)

    def fallback(self, ctx: AgentContext, evidence: dict[str, Any]) -> AllocationStrategy:
        plan: AllocationPlan | None = ctx.findings.get("allocation_plan")
        if plan is None:
            return AllocationStrategy(
                strategy_narrative="No allocation plan was available to explain.",
                confidence=0.1,
            )

        rationale = [
            "Requirements ranked by doctrine tier (life safety, then stabilisation, "
            "then sustainment), then urgency, reach and deadline.",
            "Each requirement sourced from the depot with the lowest effective ETA, "
            "counting mobilisation delay as well as hazard-degraded travel time.",
            f"A strategic reserve was withheld at each depot, and no single depot "
            f"was drawn below {100 - int(80)}% of stock for one requirement, to "
            f"preserve capacity for subsequent incidents.",
        ]

        risks = []
        if plan.unmet_needs:
            risks.append(
                f"{len(plan.unmet_needs)} requirement(s) unmet — escalation is "
                "required and is the binding constraint on this response."
            )
        if plan.allocations:
            slowest = max(plan.allocations, key=lambda a: a.eta_minutes)
            risks.append(
                f"Longest dispatch is {slowest.eta_minutes} min from "
                f"{slowest.from_depot_name}; route severance would strand it."
            )
        risks.append(
            "ETAs assume modelled hazard-degraded road speeds, not live traffic; "
            "actual times may be worse."
        )

        equity: list[str] = []
        shelter = ctx.findings.get("shelter")
        if shelter and getattr(shelter, "capacity_deficit", 0):
            equity.append(
                f"{shelter.capacity_deficit:,} people have no safe shelter space "
                "allocated; they are the group most at risk of being under-served."
            )
        if shelter and getattr(shelter, "vulnerable_groups", None):
            equity.append(
                "Vulnerable groups (unaccompanied minors, elderly, persons with "
                "disability, chronic-condition patients) require dedicated provision "
                "not visible in aggregate coverage."
            )

        escalation = ""
        if plan.unmet_needs:
            escalation = "; ".join(
                f"{u.resource_type.value} short {u.quantity_short:,} — {u.escalation_path}"
                for u in plan.unmet_needs[:4]
            )

        return AllocationStrategy(
            strategy_narrative=(
                f"Deterministic allocation covering {plan.coverage_ratio:.0%} of "
                f"demanded units across {len(plan.depots_engaged)} depots and "
                f"{len(plan.organizations_engaged)} partner organisations. "
                f"{plan.total_units_allocated:,} units dispatched. "
                + (
                    f"{len(plan.unmet_needs)} requirement(s) could not be met and "
                    "require escalation."
                    if plan.unmet_needs
                    else "All requirements covered from available stock."
                )
                + " Computed by rule-based optimisation without model reasoning."
            ),
            prioritisation_rationale=rationale,
            risks=risks,
            escalation_advice=escalation,
            equity_considerations=equity,
            confidence=0.5,
        )
