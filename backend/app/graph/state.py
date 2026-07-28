"""Graph state and reducers.

The reducer on ``findings`` is what makes Pattern 5's parallel fan-in work.
Five specialist nodes execute in the same superstep and each returns a
``findings`` dict; LangGraph merges their concurrent writes through
:func:`merge_findings` rather than letting the last writer win.

Without a reducer here, running specialists in parallel silently discards all
but one of their outputs — a failure that looks like "the agent didn't run"
and is genuinely hard to diagnose.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from app.schemas.command import (
    ActivationPlan,
    CommunicationPackage,
    ReflectionVerdict,
)
from app.schemas.enums import IncidentStatus
from app.schemas.incident import IncidentReport, SituationAssessment
from app.schemas.resources import AllocationPlan, AllocationStrategy


def merge_findings(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Merge concurrent specialist writes into one findings map."""
    merged = dict(left or {})
    merged.update(right or {})
    return merged


def keep_last(left: Any, right: Any) -> Any:
    """Last write wins, ignoring ``None`` so a skipped node cannot erase state."""
    return right if right is not None else left


class IncidentState(TypedDict, total=False):
    """The complete state threaded through the graph."""

    # -- Identity ------------------------------------------------------------
    incident_id: str
    run_id: str
    report: IncidentReport
    status: IncidentStatus

    # -- Sequential stages ---------------------------------------------------
    assessment: SituationAssessment | None
    activation_plan: ActivationPlan | None

    # -- Parallel specialist outputs (merged by reducer) ---------------------
    findings: Annotated[dict[str, Any], merge_findings]

    # -- Allocation and assurance -------------------------------------------
    allocation_plan: AllocationPlan | None
    allocation_strategy: AllocationStrategy | None
    reflection: ReflectionVerdict | None
    reflection_history: Annotated[list[ReflectionVerdict], operator.add]
    cycle: int

    # -- Output --------------------------------------------------------------
    communications: CommunicationPackage | None
    errors: Annotated[list[str], operator.add]


def initial_state(report: IncidentReport, run_id: str) -> IncidentState:
    return IncidentState(
        incident_id=report.incident_id,
        run_id=run_id,
        report=report,
        status=IncidentStatus.RECEIVED,
        assessment=None,
        activation_plan=None,
        findings={},
        allocation_plan=None,
        allocation_strategy=None,
        reflection=None,
        reflection_history=[],
        cycle=0,
        communications=None,
        errors=[],
    )
