"""Government Knowledge Agent — the RAG specialist.

Retrieves official doctrine and SOPs from the verified corpus. This agent is
the platform's compliance anchor: the Reflection agent later scores the
allocation plan against what this agent retrieved, so doctrine is enforced
rather than merely displayed.

Uses **prompt chaining**: the single operational question is decomposed into
several targeted sub-queries, each retrieved separately and merged. On
multi-part questions this materially outperforms one broad similarity search.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.core.llm import ModelTier
from app.rag.retriever import RetrievalResult, get_retriever
from app.schemas.enums import AgentRole, HazardType, Severity, TraceEventType, Urgency
from app.schemas.intelligence import KnowledgeBrief, Recommendation

SYSTEM_PROMPT = """\
You are the Doctrine and Compliance Officer in an Emergency Operations Centre. \
You advise strictly from the RETRIEVED DOCTRINE supplied to you.

Absolute rules:
- Ground EVERY statement in the retrieved passages. If the doctrine does not \
address something, say so explicitly — do not fill the gap from general \
knowledge. An invented SOP is worse than no SOP, because it will be followed.
- `mandated_actions` are steps doctrine REQUIRES for this hazard and severity.
- `prohibited_actions` are things doctrine forbids. These are often the most \
valuable output, because they prevent well-intentioned errors.
- Quote specific quantified standards wherever doctrine gives them (litres per \
person, metres of space, ratios, thresholds). Numbers are actionable; \
paraphrase is not.
- Populate `citations` from the passages you actually used.
- If retrieval returned nothing, set confidence low and state that no doctrinal \
grounding was available.
"""


def build_subqueries(hazard: HazardType, severity: Severity) -> list[str]:
    """Decompose the operational question into targeted retrievals."""
    hazard_label = hazard.value.replace("_", " ")
    queries = [
        f"{hazard_label} standard operating procedure response",
        f"{hazard_label} evacuation and shelter requirements",
        "resource allocation priority order when demand exceeds supply",
        "relief camp minimum standards water sanitation space per person",
    ]
    if severity.rank >= Severity.SEVERE.rank:
        queries.append("mass casualty triage and hospital surge distribution")
        queries.append("escalation to state authority unmet needs")
    if hazard in (HazardType.FLOOD, HazardType.URBAN_FLOOD, HazardType.TSUNAMI):
        queries.append("post-flood disease surveillance and water contamination")
    return queries


class KnowledgeAgent(BaseAgent[KnowledgeBrief]):
    role = AgentRole.KNOWLEDGE
    title = "Doctrine & Compliance (RAG)"
    tier = ModelTier.FAST

    @property
    def output_schema(self) -> type[KnowledgeBrief]:
        return KnowledgeBrief

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def gather(self, ctx: AgentContext) -> dict[str, Any]:
        hazard = ctx.assessment.hazard_type if ctx.assessment else HazardType.UNKNOWN
        severity = ctx.assessment.severity if ctx.assessment else Severity.MODERATE

        queries = build_subqueries(hazard, severity)
        await self.emit(
            ctx,
            TraceEventType.RETRIEVAL,
            f"Decomposed into {len(queries)} doctrine queries",
            detail=" | ".join(queries),
            payload={"queries": queries},
        )

        retriever = get_retriever()
        result: RetrievalResult = retriever.multi_query(
            queries, top_k=3, hazard=hazard.value
        )

        await self.emit(
            ctx,
            TraceEventType.RETRIEVAL,
            f"Retrieved {len(result.chunks)} doctrine passages",
            detail="; ".join(
                f"{c.citation.source_id} §{c.citation.section} ({c.relevance:.2f})"
                for c in result.chunks[:6]
            )
            or "no passages above relevance threshold",
            confidence=(
                sum(c.relevance for c in result.chunks) / len(result.chunks)
                if result.chunks
                else 0.0
            ),
            payload={
                "citations": [
                    {
                        "source_id": c.citation.source_id,
                        "section": c.citation.section,
                        "title": c.citation.document_title,
                        "authority": c.citation.authority,
                        "relevance": round(c.relevance, 3),
                    }
                    for c in result.chunks
                ]
            },
        )
        return {"retrieval": result, "queries": queries}

    def build_prompt(self, ctx: AgentContext, evidence: dict[str, Any]) -> str:
        result: RetrievalResult | None = evidence.get("retrieval")
        context = result.as_context() if result else "NO DOCTRINE RETRIEVED."

        return "\n".join(
            [
                ctx.situation_brief(),
                "",
                f"FOCUS QUESTION: {ctx.focus_question or 'What does doctrine mandate for this incident?'}",
                "",
                "=== RETRIEVED DOCTRINE ===",
                context,
                "",
                "Produce the structured doctrine brief. Every mandated and "
                "prohibited action must trace to a retrieved passage above.",
            ]
        )

    def fallback(self, ctx: AgentContext, evidence: dict[str, Any]) -> KnowledgeBrief:
        """Extractive brief.

        With no model available we do not attempt to synthesise guidance. We
        surface the retrieved passages verbatim with their citations and let a
        human read them — the honest degradation for a compliance function.
        """
        result: RetrievalResult | None = evidence.get("retrieval")
        queries = evidence.get("queries", [])

        if result is None or result.is_empty:
            return KnowledgeBrief(
                headline="No doctrinal grounding available",
                confidence=0.1,
                key_findings=[
                    "Doctrine retrieval returned no passages above the relevance threshold.",
                    "Proceed on operational judgement; compliance cannot be verified.",
                ],
                query_used=" | ".join(queries),
                retrieved_chunks=0,
                degraded=True,
            )

        # Surface the retrieved section headings as the finding set — verbatim,
        # not synthesised.
        findings = [
            f"{c.citation.document_title} §{c.citation.section}: {c.citation.snippet[:180]}"
            for c in result.chunks[:6]
        ]

        return KnowledgeBrief(
            headline=(
                f"{len(result.chunks)} doctrine passages retrieved across "
                f"{len({c.citation.source_id for c in result.chunks})} documents"
            )[:200],
            confidence=0.45,
            key_findings=findings,
            applicable_sops=sorted(
                {
                    f"{c.citation.source_id} — {c.citation.document_title}"
                    for c in result.chunks
                }
            ),
            mandated_actions=[
                "See retrieved passages — not synthesised without model reasoning"
            ],
            citations=result.citations,
            query_used=" | ".join(queries),
            retrieved_chunks=len(result.chunks),
            recommendations=[
                Recommendation(
                    action="Review the retrieved doctrine passages directly before acting",
                    rationale=(
                        "No model was available to synthesise doctrine into "
                        "specific guidance; raw passages are provided instead."
                    ),
                    urgency=Urgency.ROUTINE,
                    owner="incident_commander",
                )
            ],
            degraded=True,
        )
