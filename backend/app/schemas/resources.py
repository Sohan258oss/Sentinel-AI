"""Resource coordination — the workbook's core problem, kept at the centre.

The allocation model is deliberately explicit: requirements and stock are
separate first-class objects, and an ``Allocation`` always names both the depot
it draws from and the requirement it satisfies. That traceability is what makes
the plan auditable by a human incident commander.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, computed_field

from app.schemas.common import Confidence, GeoPoint, SentinelModel, utcnow
from app.schemas.enums import AgentRole, OrganizationType, ResourceType, Urgency


class ResourceStock(SentinelModel):
    """What a depot physically holds right now."""

    resource_type: ResourceType
    quantity: int = Field(ge=0)
    unit: str = "units"
    reserved: int = Field(default=0, ge=0, description="Committed to other incidents")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def available(self) -> int:
        return max(0, self.quantity - self.reserved)


class Depot(SentinelModel):
    """A supply node — government warehouse, NGO store, hospital pharmacy."""

    depot_id: str
    name: str
    organization: str
    organization_type: OrganizationType
    point: GeoPoint
    stock: list[ResourceStock] = Field(default_factory=list)
    dispatch_delay_minutes: int = Field(
        default=30, ge=0, description="Time to mobilise before departure"
    )
    operational: bool = True

    def available_of(self, resource_type: ResourceType) -> int:
        return sum(s.available for s in self.stock if s.resource_type == resource_type)


class ResourceRequirement(SentinelModel):
    """Demand computed from the impact estimate and specialist findings."""

    resource_type: ResourceType
    quantity_required: int = Field(gt=0)
    urgency: Urgency = Urgency.URGENT
    justification: str = Field(
        description="Which finding produced this number — no unexplained demand"
    )
    beneficiaries: int = Field(default=0, ge=0)
    deadline_hours: float = Field(default=12.0, gt=0)
    requested_by: AgentRole = AgentRole.ALLOCATION


class Allocation(SentinelModel):
    """One dispatch instruction: this much, from here, to there, by then."""

    allocation_id: str
    resource_type: ResourceType
    quantity: int = Field(gt=0)
    from_depot_id: str
    from_depot_name: str
    to_location_name: str
    to_point: GeoPoint
    distance_km: float = Field(ge=0)
    eta_minutes: int = Field(ge=0)
    urgency: Urgency
    priority_score: float = Field(
        ge=0, description="Higher wins when supply is contested"
    )
    rationale: str = ""


class UnmetNeed(SentinelModel):
    """Honesty about shortfall. A plan that hides gaps is worse than useless."""

    resource_type: ResourceType
    quantity_short: int = Field(gt=0)
    beneficiaries_affected: int = 0
    escalation_path: str = Field(
        description="Who to ask next — neighbouring district, state, NDRF, centre"
    )
    consequence: str = ""


class AllocationPlan(SentinelModel):
    """Structured output of the Resource Allocation Agent."""

    plan_id: str
    generated_at: datetime = Field(default_factory=utcnow)
    requirements: list[ResourceRequirement] = Field(default_factory=list)
    allocations: list[Allocation] = Field(default_factory=list)
    unmet_needs: list[UnmetNeed] = Field(default_factory=list)
    strategy_narrative: str = Field(
        default="", description="LLM explanation of the prioritisation logic"
    )
    coverage_ratio: Confidence = Field(
        default=0.0, description="Fraction of demanded units actually allocated"
    )
    total_units_allocated: int = 0
    depots_engaged: list[str] = Field(default_factory=list)
    organizations_engaged: list[OrganizationType] = Field(default_factory=list)
    revision: int = Field(default=0, description="Incremented by the reflection cycle")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_fully_covered(self) -> bool:
        return not self.unmet_needs


class AllocationStrategy(SentinelModel):
    """The Allocation Agent's *reasoning* about a computed plan.

    Deliberately separate from :class:`AllocationPlan`. The plan's numbers come
    from the deterministic optimiser; this is the model's explanation and
    critique of them. Keeping them in different types makes it structurally
    impossible for a language model to quietly rewrite a quantity.
    """

    strategy_narrative: str = Field(
        description="Why this prioritisation, in the incident commander's terms"
    )
    prioritisation_rationale: list[str] = Field(
        default_factory=list, description="Ordered reasons for the sourcing choices"
    )
    risks: list[str] = Field(
        default_factory=list, description="What could cause this plan to fail"
    )
    escalation_advice: str = Field(
        default="", description="What to escalate, to whom, and how urgently"
    )
    equity_considerations: list[str] = Field(
        default_factory=list,
        description="Who is at risk of being under-served by this plan",
    )
    confidence: Confidence = 0.6


class VolunteerTask(SentinelModel):
    task_id: str
    title: str
    skill_required: str
    volunteers_needed: int = Field(gt=0)
    location_name: str
    point: GeoPoint
    urgency: Urgency = Urgency.URGENT
    briefing: str = ""
    safety_notes: list[str] = Field(default_factory=list)
