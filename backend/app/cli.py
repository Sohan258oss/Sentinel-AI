"""Command-line runner.

    python -m app.cli scenarios
    python -m app.cli run kerala_flood
    python -m app.cli run kerala_flood --trace

Useful for demos without the frontend, and for verifying the whole pipeline
after a change.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.core.config import settings
from app.core.llm import get_llm_engine
from app.core.logging import configure_logging
from app.schemas.command import OperationalPicture
from app.services.orchestrator import get_orchestrator
from app.services.scenarios import get_scenario, list_scenarios

RULE = "=" * 78
THIN = "-" * 78


def _print_scenarios() -> None:
    print(f"\n{RULE}\nSENTINELAI DEMO SCENARIOS\n{RULE}")
    for scenario in list_scenarios():
        print(f"\n  {scenario['key']}")
        print(f"    {scenario['title']}")
        print(f"    {scenario['description']}")
        print(f"    Demonstrates: {scenario['demonstrates']}")
    print()


def _print_picture(picture: OperationalPicture) -> None:
    a = picture.assessment
    print(f"\n{RULE}")
    print(f"OPERATIONAL PICTURE — {picture.incident_id}")
    print(RULE)

    if a:
        print(f"\n  {a.headline}")
        print(f"  Hazard      : {a.hazard_type.value}")
        print(f"  Severity    : {a.severity.value.upper()} (confidence {a.confidence:.0%})")
        if a.secondary_hazards:
            print(f"  Cascading   : {', '.join(h.value for h in a.secondary_hazards)}")
        print(f"  At risk     : {a.impact.population_at_risk:,} people")
        print(f"  Evacuation  : {a.impact.people_requiring_evacuation:,}")
        print(f"  Medical     : {a.impact.people_requiring_medical_care:,}")
        print(f"  Shelter     : {a.impact.people_requiring_shelter:,}")
        print(f"\n  {a.summary}")
        if a.immediate_risks:
            print("\n  IMMEDIATE RISKS")
            for risk in a.immediate_risks:
                print(f"    - {risk}")

    plan = picture.activation_plan
    if plan:
        print(f"\n{THIN}\nCOMMANDER'S ACTIVATION DECISION\n{THIN}")
        print(f"  Intent: {plan.command_intent}")
        print("\n  ACTIVATED:")
        for dispatch in sorted(plan.dispatches, key=lambda d: d.priority):
            print(f"    [P{dispatch.priority}] {dispatch.agent.value}: {dispatch.reason}")
            if dispatch.focus_question:
                print(f"           -> {dispatch.focus_question}")
        if plan.declined:
            print("\n  DECLINED:")
            for dispatch in plan.declined:
                print(f"    {dispatch.agent.value}: {dispatch.reason}")
        if plan.escalate_to_state:
            print(f"\n  ESCALATION TO STATE: {plan.escalation_reason}")

    print(f"\n{THIN}\nSPECIALIST INTELLIGENCE\n{THIN}")
    for label, product in (
        ("WEATHER", picture.weather),
        ("INFRASTRUCTURE", picture.infrastructure),
        ("MEDICAL", picture.medical),
        ("SHELTER", picture.shelter),
        ("DOCTRINE (RAG)", picture.knowledge),
    ):
        if product is None:
            print(f"\n  {label}: not activated")
            continue
        flag = " [DEGRADED]" if getattr(product, "degraded", False) else ""
        print(f"\n  {label}{flag} (confidence {product.confidence:.0%})")
        print(f"    {product.headline}")
        for finding in product.key_findings[:4]:
            print(f"      - {finding}")
        if getattr(product, "citations", None):
            for citation in product.citations[:3]:
                print(
                    f"      [cite] {citation.source_id} §{citation.section} "
                    f"({citation.authority})"
                )

    allocation = picture.allocation_plan
    if allocation:
        print(f"\n{THIN}\nRESOURCE ALLOCATION\n{THIN}")
        print(
            f"  Coverage {allocation.coverage_ratio:.0%} | "
            f"{allocation.total_units_allocated:,} units | "
            f"{len(allocation.allocations)} dispatches | "
            f"revision {allocation.revision}"
        )
        print(
            f"  Partners: "
            f"{', '.join(o.value for o in allocation.organizations_engaged)}"
        )
        print("\n  DISPATCHES")
        for item in allocation.allocations[:12]:
            print(
                f"    {item.quantity:>7,} {item.resource_type.value:<22} "
                f"<- {item.from_depot_name[:34]:<34} "
                f"ETA {item.eta_minutes:>3} min"
            )
        if len(allocation.allocations) > 12:
            print(f"    … {len(allocation.allocations) - 12} more")

        if allocation.unmet_needs:
            print("\n  UNMET NEEDS")
            for unmet in allocation.unmet_needs:
                print(
                    f"    SHORT {unmet.quantity_short:>7,} "
                    f"{unmet.resource_type.value:<22} "
                    f"affects {unmet.beneficiaries_affected:,}"
                )
                print(f"      -> {unmet.escalation_path}")
        if allocation.strategy_narrative:
            print(f"\n  STRATEGY\n    {allocation.strategy_narrative}")

    reflection = picture.reflection
    if reflection:
        print(f"\n{THIN}\nREFLECTION & ASSURANCE\n{THIN}")
        print(
            f"  Verdict: {'APPROVED' if reflection.approved else 'REVISION REQUIRED'} "
            f"| quality {reflection.overall_quality:.0%} "
            f"| cycles run: {len(picture.reflection_history)}"
        )
        print(
            f"  consistency {reflection.internal_consistency:.0%} | "
            f"doctrine {reflection.doctrine_compliance:.0%} | "
            f"coverage {reflection.coverage_adequacy:.0%}"
        )
        for finding in reflection.findings[:6]:
            print(f"    [{finding.severity.upper()}] {finding.issue}")
            print(f"        fix: {finding.suggested_fix}")

    comms = picture.communications
    if comms:
        print(f"\n{THIN}\nCOMMUNICATIONS\n{THIN}")
        print(f"  Headline: {comms.public_alert_headline}")
        for artifact in comms.artifacts:
            print(f"\n  [{artifact.channel.value}] -> {artifact.audience}")
            print(f"    {artifact.body[:320]}")
        if comms.misinformation_guardrails:
            print("\n  MISINFORMATION GUARDRAILS")
            for guard in comms.misinformation_guardrails[:4]:
                print(f"    - {guard}")

    if picture.consolidated_recommendations:
        print(f"\n{THIN}\nCONSOLIDATED ACTION LIST\n{THIN}")
        for rec in picture.consolidated_recommendations[:10]:
            print(f"  [{rec.urgency.value.upper():<9}] {rec.action}")
            print(f"              owner: {rec.owner}")

    if picture.errors:
        print(f"\n  ERRORS: {picture.errors}")

    print(f"\n{RULE}")
    print(f"Completed in {picture.duration_seconds:.1f}s")
    print(RULE + "\n")


async def _run(scenario_key: str, show_trace: bool) -> int:
    scenario = get_scenario(scenario_key)
    report = scenario.create()
    orchestrator = get_orchestrator()

    engine = get_llm_engine()
    print(f"\n{RULE}")
    print(f"SENTINELAI — {scenario.title}")
    print(RULE)
    print(f"  Incident : {report.incident_id}")
    print(f"  Location : {report.location.label}")
    print(f"  Imagery  : {len(report.media_paths)} file(s)")
    print(f"  LLM      : {engine.descriptor}")
    if not engine.available:
        print("  MODE     : DETERMINISTIC (no model configured — rule-based agents)")
    print(RULE)

    record = await orchestrator.submit(report)

    if show_trace:
        print("\nLIVE AGENT TRACE")
        print(THIN)

        async def consume() -> None:
            async for trace in orchestrator.stream(record.run_id):
                marker = {
                    "node_started": ">>",
                    "node_completed": "OK",
                    "tool_call": "..",
                    "tool_result": "<-",
                    "retrieval": "RG",
                    "routing_decision": "->",
                    "critique": "!!",
                    "reasoning": "..",
                    "revision": "~~",
                    "error": "XX",
                    "run_started": "**",
                    "run_completed": "**",
                }.get(trace.event_type.value, "  ")
                print(f"  {marker} [{trace.agent.value:<18}] {trace.title[:90]}")

        consumer = asyncio.create_task(consume())
        assert record.task is not None
        await record.task
        await asyncio.sleep(0.2)
        consumer.cancel()
    else:
        assert record.task is not None
        await record.task

    if record.error:
        print(f"\nRUN FAILED: {record.error}\n")
        return 1

    assert record.picture is not None
    _print_picture(record.picture)

    metrics = record.metrics
    if metrics:
        print(
            f"  telemetry: {metrics.nodes_executed} nodes | "
            f"{metrics.tool_calls} tool calls | "
            f"{metrics.fallbacks_used} fallbacks | "
            f"{metrics.retrieval_queries} retrievals | "
            f"{metrics.reflection_cycles} critiques | "
            f"{metrics.errors} errors\n"
        )
    return 0


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="sentinelai", description="SentinelAI CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scenarios", help="list demo scenarios")

    run_parser = sub.add_parser("run", help="run a scenario end to end")
    run_parser.add_argument("scenario", help="scenario key")
    run_parser.add_argument("--trace", action="store_true", help="stream the live agent trace")

    args = parser.parse_args()

    if args.command == "scenarios":
        _print_scenarios()
        return 0

    return asyncio.run(_run(args.scenario, args.trace))


if __name__ == "__main__":
    sys.exit(main())
