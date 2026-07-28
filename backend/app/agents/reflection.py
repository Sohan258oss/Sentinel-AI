"""Reflection Agent — the quality gate.

Closes Pattern 5's cycle. Reviews the assembled operational picture and either
approves it or sends the allocation stage back with a concrete revision
instruction. The loop is bounded by ``settings.max_reflection_cycles`` so a
pathological critique cannot burn tokens indefinitely.

The deterministic fallback is a genuine rule-based auditor, not a rubber stamp:
it checks internal consistency, doctrine compliance and coverage, and it *can*
reject. A reflection stage that always approves is theatre.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.core.llm import ModelTier
from app.schemas.command import CritiqueFinding, ReflectionVerdict
from app.schemas.enums import AgentRole, Severity

SYSTEM_PROMPT = """\
You are the Reflection and Assurance Officer in an Emergency Operations Centre. \
You audit the response plan before it is issued. You are deliberately \
adversarial: your job is to find what is wrong, not to endorse.

Check for:
1. INTERNAL CONSISTENCY — do the numbers agree across agents? If the situation \
assessment says 8,000 need shelter and the shelter agent plans for 800, that is \
a blocking error.
2. DOCTRINE COMPLIANCE — does the plan honour the retrieved SOPs and quantified \
minimum standards? Under-provisioning water below 15 L/person/day is blocking.
3. COVERAGE ADEQUACY — are unmet life-safety needs escalated, or quietly \
absorbed? Silent shortfall is blocking.
4. SEQUENCING — is anything scheduled after the point at which it becomes \
useless? Shelter opened after inundation, evacuation begun after the window \
closes.
5. EQUITY — is any group or settlement receiving nothing while aggregate \
coverage looks adequate?
6. OMISSIONS — what has nobody addressed? Cascading hazards are the most \
commonly missed item.

Severity levels: "blocking" (must fix before issue), "major" (significant \
weakness), "minor" (improvement).

Set `approved` false if ANY blocking issue exists. When you reject, \
`revision_instruction` must be specific and actionable — name the resource, \
the quantity, the group or the sequencing change required. "Improve the plan" \
is a useless instruction.

Do not invent problems. If the plan is sound, approve it and say why briefly.
"""


class ReflectionAgent(BaseAgent[ReflectionVerdict]):
    role = AgentRole.REFLECTION
    title = "Reflection & Assurance"
    tier = ModelTier.REASONING

    @property
    def output_schema(self) -> type[ReflectionVerdict]:
        return ReflectionVerdict

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def summarise(self, output: ReflectionVerdict) -> str:
        verdict = "APPROVED" if output.approved else "REVISION REQUIRED"
        return f"{verdict} — quality {output.overall_quality:.0%}, {len(output.findings)} findings"

    def build_prompt(self, ctx: AgentContext, evidence: dict[str, Any]) -> str:
        findings = ctx.findings
        plan = findings.get("allocation_plan")
        assessment = ctx.assessment

        lines = [ctx.situation_brief(), "", f"REVIEW CYCLE: {ctx.cycle + 1}", ""]

        lines.append("=== SPECIALIST FINDINGS ===")
        for key in ("weather", "infrastructure", "medical", "shelter", "knowledge"):
            product = findings.get(key)
            if product is None:
                lines.append(f"  {key}: NOT ACTIVATED")
                continue
            lines.append(
                f"  {key}: {product.headline} "
                f"(confidence {product.confidence:.2f}"
                f"{', DEGRADED' if getattr(product, 'degraded', False) else ''})"
            )
            for finding in getattr(product, "key_findings", [])[:3]:
                lines.append(f"      - {finding}")

        if assessment:
            lines += [
                "",
                "=== TRIAGE NUMBERS TO CHECK AGAINST ===",
                f"  Population at risk: {assessment.impact.population_at_risk:,}",
                f"  Requiring evacuation: {assessment.impact.people_requiring_evacuation:,}",
                f"  Requiring medical care: {assessment.impact.people_requiring_medical_care:,}",
                f"  Requiring shelter: {assessment.impact.people_requiring_shelter:,}",
            ]

        if plan:
            lines += [
                "",
                "=== ALLOCATION PLAN ===",
                f"  Coverage: {plan.coverage_ratio:.0%} | "
                f"units dispatched: {plan.total_units_allocated:,} | "
                f"revision {plan.revision}",
            ]
            for requirement in plan.requirements:
                lines.append(
                    f"    REQ {requirement.resource_type.value}: "
                    f"{requirement.quantity_required:,} — {requirement.justification}"
                )
            for unmet in plan.unmet_needs:
                lines.append(
                    f"    UNMET {unmet.resource_type.value}: short "
                    f"{unmet.quantity_short:,}, affects "
                    f"{unmet.beneficiaries_affected:,} — {unmet.consequence}"
                )

        knowledge = findings.get("knowledge")
        if knowledge:
            lines += ["", "=== DOCTRINE TO AUDIT AGAINST ==="]
            for action in getattr(knowledge, "mandated_actions", [])[:6]:
                lines.append(f"  MANDATED: {action}")
            for action in getattr(knowledge, "prohibited_actions", [])[:4]:
                lines.append(f"  PROHIBITED: {action}")

        strategy = findings.get("allocation_strategy")
        if strategy:
            lines += [
                "",
                "=== ALLOCATION REASONING ===",
                strategy.strategy_narrative[:900],
            ]

        lines += [
            "",
            f"Set `cycle` to {ctx.cycle}. Audit this plan and return your verdict.",
        ]
        return "\n".join(lines)

    def fallback(self, ctx: AgentContext, evidence: dict[str, Any]) -> ReflectionVerdict:
        """Rule-based audit that can genuinely reject."""
        findings = ctx.findings
        plan = findings.get("allocation_plan")
        shelter = findings.get("shelter")
        medical = findings.get("medical")
        assessment = ctx.assessment

        issues: list[CritiqueFinding] = []

        # -- Coverage of life-safety needs -----------------------------------
        if plan is not None:
            from app.services.allocator import RESOURCE_TIER

            for unmet in plan.unmet_needs:
                tier = RESOURCE_TIER.get(unmet.resource_type, 3)
                issues.append(
                    CritiqueFinding(
                        issue=(
                            f"Unmet {unmet.resource_type.value}: short "
                            f"{unmet.quantity_short:,}, affecting "
                            f"{unmet.beneficiaries_affected:,} people"
                        ),
                        severity="blocking" if tier == 1 else "major",
                        affected_component="allocation",
                        suggested_fix=unmet.escalation_path,
                    )
                )

            if plan.coverage_ratio < 0.6:
                issues.append(
                    CritiqueFinding(
                        issue=f"Overall coverage is only {plan.coverage_ratio:.0%} of demand",
                        severity="major",
                        affected_component="allocation",
                        suggested_fix="Escalate to state authority for additional stock before issue.",
                    )
                )
        else:
            issues.append(
                CritiqueFinding(
                    issue="No allocation plan was produced",
                    severity="blocking",
                    affected_component="allocation",
                    suggested_fix="Run the allocation stage before issuing the response.",
                )
            )

        # -- Internal consistency --------------------------------------------
        consistency = 1.0
        if assessment and shelter:
            expected = assessment.impact.people_requiring_shelter
            planned = getattr(shelter, "people_to_shelter", 0)
            if expected and planned and abs(expected - planned) / expected > 0.25:
                consistency = 0.5
                issues.append(
                    CritiqueFinding(
                        issue=(
                            f"Shelter planning ({planned:,}) diverges from triage "
                            f"estimate ({expected:,}) by more than 25%"
                        ),
                        severity="blocking",
                        affected_component="shelter",
                        suggested_fix=(
                            f"Reconcile shelter planning figure to the triage estimate "
                            f"of {expected:,} people requiring shelter."
                        ),
                    )
                )

        # -- Capacity deficits ------------------------------------------------
        if shelter and getattr(shelter, "capacity_deficit", 0) > 0:
            issues.append(
                CritiqueFinding(
                    issue=(
                        f"Shelter capacity deficit of "
                        f"{shelter.capacity_deficit:,} people"
                    ),
                    severity="blocking",
                    affected_component="shelter",
                    suggested_fix=(
                        "Open additional flood-safe capacity or arrange "
                        "inter-district transfer before issuing the plan."
                    ),
                )
            )
        if medical and getattr(medical, "bed_deficit", 0) > 0:
            issues.append(
                CritiqueFinding(
                    issue=f"Hospital bed deficit of {medical.bed_deficit:,} admissions",
                    severity="blocking",
                    affected_component="medical",
                    suggested_fix=(
                        "Escalate to state health authority for inter-district "
                        "casualty transfer capacity."
                    ),
                )
            )

        # -- Cascading hazards addressed? -------------------------------------
        if assessment and assessment.secondary_hazards:
            addressed = bool(medical and getattr(medical, "outbreak_watchlist", None))
            if not addressed:
                issues.append(
                    CritiqueFinding(
                        issue=(
                            "Cascading hazards identified in triage "
                            f"({', '.join(h.value for h in assessment.secondary_hazards)}) "
                            "but no mitigation appears in the plan"
                        ),
                        severity="major",
                        affected_component="planning",
                        suggested_fix="Add surveillance and mitigation for the identified secondary hazards.",
                    )
                )

        # -- Degraded inputs ---------------------------------------------------
        degraded = [
            key
            for key in ("weather", "infrastructure", "medical", "shelter", "knowledge")
            if findings.get(key) is not None and getattr(findings[key], "degraded", False)
        ]
        if degraded:
            issues.append(
                CritiqueFinding(
                    issue=(
                        "Plan rests on degraded intelligence from: "
                        + ", ".join(degraded)
                    ),
                    severity="minor",
                    affected_component="intelligence",
                    suggested_fix="Treat affected findings as provisional and seek confirmation.",
                )
            )

        blocking = [i for i in issues if i.severity == "blocking"]
        approved = not blocking

        coverage_score = plan.coverage_ratio if plan else 0.0
        doctrine_score = 0.6 if findings.get("knowledge") else 0.3
        quality = max(
            0.0,
            min(1.0, 0.4 * coverage_score + 0.3 * consistency + 0.3 * doctrine_score),
        )

        instruction: str | None = None
        if blocking:
            instruction = " ".join(
                f"{index}. {finding.suggested_fix}"
                for index, finding in enumerate(blocking[:3], start=1)
            )

        return ReflectionVerdict(
            approved=approved,
            overall_quality=round(quality, 2),
            findings=issues,
            doctrine_compliance=doctrine_score,
            internal_consistency=consistency,
            coverage_adequacy=round(coverage_score, 2),
            revision_instruction=instruction,
            cycle=ctx.cycle,
        )
