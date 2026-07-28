"""LangGraph assembly — Pattern 5: Hybrid Branching.

All four branching behaviours in one graph:

  ① CONDITIONAL ROUTING   commander -> a per-incident subset of specialists
  ② PARALLEL FAN-OUT      that subset executes in a single superstep
  ③ REDUCER FAN-IN        concurrent writes merge via ``merge_findings``
  ④ BOUNDED CYCLE         reflection -> allocation, capped by configuration

A severity gate short-circuits trivial incidents past the command apparatus
entirely, which is a fifth conditional edge and the reason the graph is
*hybrid* rather than merely parallel.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.core.logging import get_logger
from app.graph.nodes import (
    allocation_node,
    commander_node,
    communication_node,
    finalize_node,
    intake_node,
    make_specialist_node,
    reflection_node,
    route_after_reflection,
    route_specialists,
    severity_gate,
    situation_node,
)
from app.graph.state import IncidentState
from app.schemas.command import DISPATCHABLE_AGENTS

logger = get_logger(__name__)

#: Node names for the dispatchable specialists, matching ``AgentRole`` values
#: so the Commander's output maps directly onto graph nodes with no lookup.
SPECIALIST_NODES: list[str] = [role.value for role in DISPATCHABLE_AGENTS]


def build_graph() -> StateGraph:
    """Construct the incident response graph."""
    builder: StateGraph = StateGraph(IncidentState)

    # -- Nodes ---------------------------------------------------------------
    builder.add_node("intake", intake_node)
    builder.add_node("situation_analysis", situation_node)
    builder.add_node("commander", commander_node)

    for role in DISPATCHABLE_AGENTS:
        builder.add_node(role.value, make_specialist_node(role))

    builder.add_node("allocation", allocation_node)
    builder.add_node("reflection", reflection_node)
    builder.add_node("communication", communication_node)
    builder.add_node("finalize", finalize_node)

    # -- Sequential spine ----------------------------------------------------
    builder.add_edge(START, "intake")
    builder.add_edge("intake", "situation_analysis")

    # Severity gate: trivial incidents bypass the command apparatus.
    builder.add_conditional_edges(
        "situation_analysis",
        severity_gate,
        ["commander", "communication"],
    )

    # ① + ② Conditional routing into a parallel superstep.
    builder.add_conditional_edges(
        "commander",
        route_specialists,
        [*SPECIALIST_NODES, "allocation"],
    )

    # ③ Fan-in. Every specialist converges on allocation; LangGraph waits only
    # for the ones that actually ran in this superstep.
    for node_name in SPECIALIST_NODES:
        builder.add_edge(node_name, "allocation")

    builder.add_edge("allocation", "reflection")

    # ④ Bounded reflection cycle.
    builder.add_conditional_edges(
        "reflection",
        route_after_reflection,
        ["allocation", "communication"],
    )

    builder.add_edge("communication", "finalize")
    builder.add_edge("finalize", END)

    return builder


@lru_cache
def get_compiled_graph() -> Any:
    """Compile once and reuse.

    An in-memory checkpointer gives per-incident thread isolation and time-travel
    inspection during a run. Swapping in a Postgres or Redis saver is a one-line
    change and is what a multi-worker deployment would use.
    """
    graph = build_graph().compile(checkpointer=InMemorySaver())
    logger.info(
        "graph.compiled",
        specialists=SPECIALIST_NODES,
        nodes=len(SPECIALIST_NODES) + 7,
    )
    return graph


def render_mermaid() -> str:
    """Mermaid source for the architecture diagram in the docs and UI."""
    specialists = "\n".join(
        f"    COMMANDER -->|conditional| {name.upper()}[{name.replace('_', ' ').title()}]"
        for name in SPECIALIST_NODES
    )
    joins = "\n".join(f"    {name.upper()} --> ALLOCATION" for name in SPECIALIST_NODES)
    return f"""flowchart TD
    START([Incident Report]) --> INTAKE[Intake]
    INTAKE --> SITUATION[Situation Analysis<br/>vision + triage]
    SITUATION -->|severity gate| COMMANDER[Commander<br/>routing decision]
    SITUATION -.->|informational only| COMMS
{specialists}
{joins}
    ALLOCATION[Resource Allocation<br/>optimiser + narration] --> REFLECTION[Reflection<br/>quality gate]
    REFLECTION -->|revision required| ALLOCATION
    REFLECTION -->|approved| COMMS[Communication]
    COMMS --> FINALIZE[Finalize<br/>learn lessons]
    FINALIZE --> DONE([Operational Picture])
"""
