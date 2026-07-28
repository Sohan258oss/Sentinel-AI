"""Tests for the Pattern 5 graph.

These assert the four branching behaviours the workbook requires are genuinely
present in the compiled graph and observable at runtime — not merely drawn in a
diagram.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.events import trace_bus
from app.graph.builder import SPECIALIST_NODES, build_graph, get_compiled_graph
from app.graph.nodes import route_after_reflection, route_specialists, severity_gate
from app.graph.state import IncidentState, merge_findings
from app.schemas.command import ActivationPlan, AgentDispatch, ReflectionVerdict
from app.schemas.common import GeoPoint, Location
from app.schemas.enums import AgentRole, HazardType, Severity, TraceEventType
from app.schemas.incident import ImpactEstimate, IncidentReport, SituationAssessment
from app.services.orchestrator import IncidentOrchestrator


def make_report(hazard: HazardType = HazardType.FLOOD) -> IncidentReport:
    return IncidentReport(
        incident_id="INC-TEST-001",
        description="Test incident for graph verification.",
        location=Location(
            name="Aluva",
            point=GeoPoint(latitude=10.1004, longitude=76.3570),
            district="Ernakulam",
            state="Kerala",
            population=310_000,
        ),
        declared_hazard=hazard,
        reported_casualties=5,
    )


class TestGraphStructure:
    def test_graph_compiles(self):
        assert get_compiled_graph() is not None

    def test_all_specialists_are_nodes(self):
        graph = build_graph().compile()
        nodes = set(graph.get_graph().nodes)
        for name in SPECIALIST_NODES:
            assert name in nodes, f"specialist {name} missing from graph"

    def test_reducer_merges_concurrent_writes(self):
        """The fan-in join depends on this; last-writer-wins would lose findings."""
        left = {"weather": "W", "medical": "M"}
        right = {"shelter": "S"}
        merged = merge_findings(left, right)
        assert merged == {"weather": "W", "medical": "M", "shelter": "S"}


class TestRouting:
    def test_conditional_fanout_returns_only_activated_specialists(self):
        state: IncidentState = {
            "activation_plan": ActivationPlan(
                incident_id="X",
                dispatches=[
                    AgentDispatch(agent=AgentRole.MEDICAL, reason="r", priority=1),
                    AgentDispatch(agent=AgentRole.WEATHER, reason="r", priority=2),
                ],
            )
        }  # type: ignore[typeddict-item]

        targets = route_specialists(state)
        assert set(targets) == {"medical", "weather"}
        assert "shelter" not in targets

    def test_fanout_returns_multiple_targets_for_parallelism(self):
        """Returning a list is what makes LangGraph run them in one superstep."""
        state: IncidentState = {
            "activation_plan": ActivationPlan(
                incident_id="X",
                dispatches=[
                    AgentDispatch(agent=role, reason="r", priority=1)
                    for role in (
                        AgentRole.WEATHER,
                        AgentRole.MEDICAL,
                        AgentRole.SHELTER,
                    )
                ],
            )
        }  # type: ignore[typeddict-item]
        targets = route_specialists(state)
        assert isinstance(targets, list)
        assert len(targets) == 3

    def test_empty_activation_falls_through_to_allocation(self):
        state: IncidentState = {
            "activation_plan": ActivationPlan(incident_id="X", dispatches=[])
        }  # type: ignore[typeddict-item]
        assert route_specialists(state) == ["allocation"]

    def test_reflection_cycle_returns_to_allocation_when_rejected(self):
        state: IncidentState = {
            "reflection": ReflectionVerdict(approved=False, overall_quality=0.3),
            "cycle": 1,
        }  # type: ignore[typeddict-item]
        assert route_after_reflection(state) == "allocation"

    def test_reflection_cycle_is_bounded(self):
        """Without this bound a critical reflection agent loops forever."""
        state: IncidentState = {
            "reflection": ReflectionVerdict(approved=False, overall_quality=0.3),
            "cycle": settings.max_reflection_cycles,
        }  # type: ignore[typeddict-item]
        assert route_after_reflection(state) == "communication"

    def test_approved_plan_proceeds_to_communication(self):
        state: IncidentState = {
            "reflection": ReflectionVerdict(approved=True, overall_quality=0.9),
            "cycle": 0,
        }  # type: ignore[typeddict-item]
        assert route_after_reflection(state) == "communication"

    def test_severity_gate_shortcircuits_trivial_incidents(self):
        trivial = SituationAssessment(
            hazard_type=HazardType.UNKNOWN,
            severity=Severity.INFORMATIONAL,
            confidence=0.5,
            headline="h",
            summary="s",
            impact=ImpactEstimate(population_at_risk=10),
        )
        assert severity_gate({"assessment": trivial}) == "communication"  # type: ignore[arg-type]

        serious = trivial.model_copy(update={"severity": Severity.SEVERE})
        assert severity_gate({"assessment": serious}) == "commander"  # type: ignore[arg-type]


@pytest.mark.asyncio
class TestEndToEnd:
    async def test_full_run_produces_operational_picture(self):
        orchestrator = IncidentOrchestrator()
        picture = await orchestrator.run_sync(make_report())

        assert picture.assessment is not None
        assert picture.activation_plan is not None
        assert picture.allocation_plan is not None
        assert picture.reflection is not None
        assert picture.communications is not None
        assert picture.consolidated_recommendations

    async def test_only_activated_specialists_produce_findings(self):
        """Proves the conditional branch actually gates execution."""
        orchestrator = IncidentOrchestrator()
        picture = await orchestrator.run_sync(make_report(HazardType.BUILDING_COLLAPSE))

        plan = picture.activation_plan
        assert plan is not None
        activated = {d.agent for d in plan.dispatches}

        # Building collapse doctrine does not warrant a weather specialist.
        assert AgentRole.WEATHER not in activated
        assert picture.weather is None
        # …but it certainly warrants medical.
        assert AgentRole.MEDICAL in activated
        assert picture.medical is not None

    async def test_trace_stream_covers_the_whole_lifecycle(self):
        orchestrator = IncidentOrchestrator()
        record = await orchestrator.submit(make_report())
        assert record.task is not None
        await record.task

        traces = trace_bus.history(record.run_id)
        event_types = {t.event_type for t in traces}

        assert TraceEventType.RUN_STARTED in event_types
        assert TraceEventType.ROUTING_DECISION in event_types
        assert TraceEventType.TOOL_CALL in event_types
        assert TraceEventType.CRITIQUE in event_types
        assert TraceEventType.RUN_COMPLETED in event_types

    async def test_run_is_resilient_to_a_hazard_with_no_imagery(self):
        orchestrator = IncidentOrchestrator()
        picture = await orchestrator.run_sync(make_report(HazardType.HEATWAVE))
        assert picture.assessment is not None
        assert not picture.errors
