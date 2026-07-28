"""Resource requirement derivation and constrained allocation.

This module is deliberately **deterministic**. Language models are excellent at
explaining a plan and poor at arithmetic over a dozen interacting constraints,
so the split is:

    optimiser  -> computes WHAT and HOW MUCH and FROM WHERE   (this module)
    LLM        -> explains WHY, and stress-tests the reasoning (allocation agent)

Every number a commander sees therefore traces to an auditable calculation with
a stated standard behind it, not to a model's impression of a plausible figure.

Two properties are enforced that naive allocators miss:

* **Strategic reserve.** A fixed fraction of district stock is withheld for the
  next incident. Emptying the nearest depot for the current event is how a
  district ends up with nothing when the second landslide happens at 03:00.
* **Honest shortfall.** Requirements that cannot be met become ``UnmetNeed``
  records with an escalation path, never silently dropped. A plan that hides
  its gaps delays escalation, which is the most expensive error in disaster
  logistics.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.logging import get_logger
from app.repositories.registry import depots as depot_repository
from app.schemas.common import GeoPoint
from app.schemas.enums import (
    AgentRole,
    HazardType,
    OrganizationType,
    ResourceType,
    Severity,
    Urgency,
)
from app.schemas.incident import SituationAssessment
from app.schemas.intelligence import MedicalIntel, ShelterIntel
from app.schemas.resources import (
    Allocation,
    AllocationPlan,
    Depot,
    ResourceRequirement,
    UnmetNeed,
)

logger = get_logger(__name__)

# -- Humanitarian planning standards ----------------------------------------
# Each constant is a published minimum standard, not a guess. They are named so
# the justification strings can cite them.

WATER_LITRES_PER_PERSON_DAY = 15
FOOD_PACKETS_PER_PERSON_DAY = 3
BLANKETS_PER_PERSON = 1
PERSONS_PER_TENT = 5
PERSONS_PER_MEDICINE_KIT = 50
PERSONS_PER_VOLUNTEER = 40
CASUALTIES_PER_MEDICAL_TEAM = 100
EVACUEES_PER_BOAT_TRIP = 8
BOAT_TRIPS_PER_HOUR = 2
TRAPPED_PER_SEARCH_TEAM = 25

#: Fraction of district stock withheld for subsequent incidents.
STRATEGIC_RESERVE_FRACTION = 0.15

#: No single depot may be drawn below this fraction of its stock for one
#: requirement, so one incident cannot strip a depot bare.
MAX_DEPOT_DRAWDOWN = 0.80

#: Priority tier per resource, from allocation doctrine:
#: 1 = life safety, 2 = incident stabilisation, 3 = sustainment.
RESOURCE_TIER: dict[ResourceType, int] = {
    ResourceType.RESCUE_BOAT: 1,
    ResourceType.SEARCH_RESCUE_TEAM: 1,
    ResourceType.AMBULANCE: 1,
    ResourceType.MEDICAL_TEAM: 1,
    ResourceType.HELICOPTER: 1,
    ResourceType.BLOOD_UNIT: 1,
    ResourceType.FIRE_TENDER: 1,
    ResourceType.DRINKING_WATER: 1,
    ResourceType.MEDICINE_KIT: 2,
    ResourceType.WATER_PUMP: 2,
    ResourceType.GENERATOR: 2,
    ResourceType.FOOD_PACKET: 2,
    ResourceType.TENT: 3,
    ResourceType.BLANKET: 3,
    ResourceType.VOLUNTEER: 3,
}

URGENCY_WEIGHT: dict[Urgency, float] = {
    Urgency.IMMEDIATE: 3.0,
    Urgency.URGENT: 2.0,
    Urgency.ROUTINE: 1.0,
}


@dataclass
class AllocationInputs:
    """Everything the optimiser needs, gathered from specialist findings."""

    assessment: SituationAssessment
    destination: GeoPoint
    destination_name: str
    medical: MedicalIntel | None = None
    shelter: ShelterIntel | None = None


# ---------------------------------------------------------------------------
# Requirement derivation
# ---------------------------------------------------------------------------


def derive_requirements(inputs: AllocationInputs) -> list[ResourceRequirement]:
    """Compute demand from the operational picture using published standards."""
    assessment = inputs.assessment
    impact = assessment.impact
    hazard = assessment.hazard_type
    requirements: list[ResourceRequirement] = []

    sheltered = (
        inputs.shelter.people_to_shelter
        if inputs.shelter and inputs.shelter.people_to_shelter
        else impact.people_requiring_shelter
    )
    evacuating = impact.people_requiring_evacuation
    at_risk = impact.population_at_risk
    duration_days = max(1.0, impact.estimated_duration_hours / 24.0)

    def add(
        resource: ResourceType,
        quantity: int,
        justification: str,
        *,
        urgency: Urgency,
        beneficiaries: int,
        deadline_hours: float,
    ) -> None:
        if quantity > 0:
            requirements.append(
                ResourceRequirement(
                    resource_type=resource,
                    quantity_required=int(quantity),
                    urgency=urgency,
                    justification=justification,
                    beneficiaries=int(beneficiaries),
                    deadline_hours=deadline_hours,
                    requested_by=AgentRole.ALLOCATION,
                )
            )

    # -- Life safety ---------------------------------------------------------

    if evacuating and hazard in (
        HazardType.FLOOD,
        HazardType.URBAN_FLOOD,
        HazardType.TSUNAMI,
        HazardType.CYCLONE,
    ):
        # Boats needed to clear the evacuation load within 6 hours.
        boats = -(-evacuating // (EVACUEES_PER_BOAT_TRIP * BOAT_TRIPS_PER_HOUR * 6))
        add(
            ResourceType.RESCUE_BOAT,
            boats,
            f"{evacuating:,} people require water evacuation; "
            f"{EVACUEES_PER_BOAT_TRIP} per trip at {BOAT_TRIPS_PER_HOUR} trips/hour "
            f"clears the load in 6 hours",
            urgency=Urgency.IMMEDIATE,
            beneficiaries=evacuating,
            deadline_hours=6.0,
        )

    if hazard in (HazardType.EARTHQUAKE, HazardType.BUILDING_COLLAPSE, HazardType.LANDSLIDE):
        trapped = max(1, int(impact.people_requiring_medical_care * 0.3))
        add(
            ResourceType.SEARCH_RESCUE_TEAM,
            -(-trapped // TRAPPED_PER_SEARCH_TEAM),
            f"Estimated {trapped:,} potentially trapped casualties at "
            f"{TRAPPED_PER_SEARCH_TEAM} per specialist team; survival rates fall "
            f"sharply after 24 hours",
            urgency=Urgency.IMMEDIATE,
            beneficiaries=trapped,
            deadline_hours=24.0,
        )

    if inputs.medical:
        add(
            ResourceType.AMBULANCE,
            inputs.medical.ambulances_required,
            f"Computed from {inputs.medical.casualty_projection:,} projected "
            f"casualties and round-trip time to receiving facilities",
            urgency=Urgency.IMMEDIATE,
            beneficiaries=inputs.medical.casualty_projection,
            deadline_hours=6.0,
        )
        casualties = inputs.medical.casualty_projection
        add(
            ResourceType.MEDICAL_TEAM,
            -(-casualties // CASUALTIES_PER_MEDICAL_TEAM) if casualties else 0,
            f"{casualties:,} projected casualties at "
            f"{CASUALTIES_PER_MEDICAL_TEAM} per medical team",
            urgency=Urgency.IMMEDIATE,
            beneficiaries=casualties,
            deadline_hours=8.0,
        )
        red = inputs.medical.triage_categories.get("red", 0)
        add(
            ResourceType.BLOOD_UNIT,
            red * 2,
            f"{red:,} RED-category casualties at 2 units each; O-negative is the "
            f"binding constraint before cross-matching",
            urgency=Urgency.IMMEDIATE,
            beneficiaries=red,
            deadline_hours=6.0,
        )

    # Water is life safety, not sustainment — dehydration kills within days.
    if sheltered:
        add(
            ResourceType.DRINKING_WATER,
            int(sheltered * WATER_LITRES_PER_PERSON_DAY * duration_days),
            f"{sheltered:,} people sheltered x {WATER_LITRES_PER_PERSON_DAY} L/person/day "
            f"(humanitarian minimum standard) x {duration_days:.1f} days",
            urgency=Urgency.IMMEDIATE,
            beneficiaries=sheltered,
            deadline_hours=12.0,
        )

    # -- Stabilisation -------------------------------------------------------

    if sheltered:
        add(
            ResourceType.FOOD_PACKET,
            int(sheltered * FOOD_PACKETS_PER_PERSON_DAY * duration_days),
            f"{sheltered:,} people x {FOOD_PACKETS_PER_PERSON_DAY} meals/day x "
            f"{duration_days:.1f} days",
            urgency=Urgency.URGENT,
            beneficiaries=sheltered,
            deadline_hours=24.0,
        )
        add(
            ResourceType.MEDICINE_KIT,
            -(-sheltered // PERSONS_PER_MEDICINE_KIT),
            f"One kit per {PERSONS_PER_MEDICINE_KIT} sheltered persons for "
            f"primary care and chronic-condition continuity",
            urgency=Urgency.URGENT,
            beneficiaries=sheltered,
            deadline_hours=24.0,
        )
        add(
            ResourceType.VOLUNTEER,
            -(-sheltered // PERSONS_PER_VOLUNTEER),
            f"Camp operations at one volunteer per {PERSONS_PER_VOLUNTEER} residents",
            urgency=Urgency.URGENT,
            beneficiaries=sheltered,
            deadline_hours=24.0,
        )

    if hazard in (HazardType.FLOOD, HazardType.URBAN_FLOOD):
        add(
            ResourceType.WATER_PUMP,
            max(2, at_risk // 5000),
            "Dewatering of inundated areas to restore access and reduce "
            "standing-water disease risk",
            urgency=Urgency.URGENT,
            beneficiaries=at_risk,
            deadline_hours=36.0,
        )

    if inputs.shelter:
        no_power = sum(
            1 for site in inputs.shelter.shelters if not site.has_power_backup
        )
        add(
            ResourceType.GENERATOR,
            no_power,
            f"{no_power} reachable shelters lack power backup; lighting and "
            f"medical refrigeration depend on it",
            urgency=Urgency.URGENT,
            beneficiaries=sheltered,
            deadline_hours=24.0,
        )

    # -- Sustainment ---------------------------------------------------------

    if sheltered:
        add(
            ResourceType.BLANKET,
            int(sheltered * BLANKETS_PER_PERSON),
            f"{sheltered:,} sheltered persons x {BLANKETS_PER_PERSON} blanket each",
            urgency=Urgency.ROUTINE,
            beneficiaries=sheltered,
            deadline_hours=48.0,
        )
        deficit = inputs.shelter.capacity_deficit if inputs.shelter else 0
        if deficit > 0:
            add(
                ResourceType.TENT,
                -(-deficit // PERSONS_PER_TENT),
                f"Shelter capacity deficit of {deficit:,} people at "
                f"{PERSONS_PER_TENT} persons per tent",
                urgency=Urgency.URGENT,
                beneficiaries=deficit,
                deadline_hours=24.0,
            )

    logger.info(
        "allocator.requirements_derived",
        count=len(requirements),
        hazard=hazard.value,
        sheltered=sheltered,
    )
    return requirements


# ---------------------------------------------------------------------------
# Constrained allocation
# ---------------------------------------------------------------------------


def _priority_score(requirement: ResourceRequirement) -> float:
    """Higher wins when supply is contested.

    Combines doctrine tier, urgency, reach (beneficiaries) and time pressure.
    Tier dominates by design: no quantity of tier-3 need outranks an unmet
    tier-1 need.
    """
    tier = RESOURCE_TIER.get(requirement.resource_type, 3)
    tier_weight = {1: 1000.0, 2: 100.0, 3: 10.0}[tier]
    urgency = URGENCY_WEIGHT[requirement.urgency]
    # Log-ish scaling so a huge beneficiary count cannot swamp tier ordering.
    reach = min(10.0, (requirement.beneficiaries or 1) ** 0.25)
    time_pressure = 24.0 / max(1.0, requirement.deadline_hours)
    return tier_weight * urgency + reach * 5.0 + time_pressure * 3.0


def _effective_eta_minutes(depot: Depot, destination: GeoPoint, hazard: HazardType) -> int:
    """Mobilisation delay plus hazard-degraded travel time.

    A depot 40 km away that mobilises in 15 minutes beats one 20 km away that
    takes 90 minutes. Distance alone is the wrong sort key.
    """
    from app.tools.logistics import BASE_ROAD_SPEED_KMH, HAZARD_SPEED_PENALTY

    straight = depot.point.distance_km(destination)
    road_km = straight * 1.35
    penalty = HAZARD_SPEED_PENALTY.get(hazard, 1.5)
    speed = BASE_ROAD_SPEED_KMH / penalty
    travel = (road_km / speed) * 60.0 if speed else 0.0
    return int(round(depot.dispatch_delay_minutes + travel))


ESCALATION_PATH: dict[int, str] = {
    1: "Immediate escalation to State Disaster Management Authority and NDRF for air/inter-district lift",
    2: "Escalation to State Disaster Management Authority for inter-district transfer",
    3: "Request via district administration to neighbouring districts and NGO partners",
}

CONSEQUENCE: dict[ResourceType, str] = {
    ResourceType.RESCUE_BOAT: "Evacuation cannot complete before inundation; people remain in the flood zone",
    ResourceType.AMBULANCE: "Casualty evacuation delayed; preventable deaths among RED-category casualties",
    ResourceType.DRINKING_WATER: "Camps fall below the 15 L/person/day survival standard",
    ResourceType.MEDICAL_TEAM: "Casualties exceed clinical capacity at receiving facilities",
    ResourceType.BLOOD_UNIT: "Transfusion capacity exhausted for trauma casualties",
    ResourceType.SEARCH_RESCUE_TEAM: "Trapped casualties not reached within the 24-hour survival window",
    ResourceType.FOOD_PACKET: "Sheltered population goes unfed",
    ResourceType.TENT: "Displaced people remain without covered space",
    ResourceType.WATER_PUMP: "Standing water persists, prolonging access loss and disease risk",
    ResourceType.GENERATOR: "Shelters without lighting or medical refrigeration after dark",
}


def allocate(
    requirements: list[ResourceRequirement],
    inputs: AllocationInputs,
    *,
    reserve_fraction: float = STRATEGIC_RESERVE_FRACTION,
    revision: int = 0,
) -> AllocationPlan:
    """Assign depot stock to requirements under priority and reserve constraints."""
    hazard = inputs.assessment.hazard_type
    destination = inputs.destination

    available_depots = depot_repository().near(destination, radius_km=200.0)
    # Working ledger of what each depot can still give, after reserve.
    ledger: dict[tuple[str, ResourceType], int] = {}
    for depot in available_depots:
        for stock in depot.stock:
            spare = int(stock.available * (1.0 - reserve_fraction))
            if spare > 0:
                ledger[(depot.depot_id, stock.resource_type)] = spare

    depot_by_id = {d.depot_id: d for d in available_depots}
    eta_cache = {
        d.depot_id: _effective_eta_minutes(d, destination, hazard) for d in available_depots
    }

    ordered = sorted(requirements, key=_priority_score, reverse=True)

    allocations: list[Allocation] = []
    unmet: list[UnmetNeed] = []
    total_allocated = 0
    total_required = sum(r.quantity_required for r in requirements)

    for requirement in ordered:
        outstanding = requirement.quantity_required

        # Nearest-by-ETA depots that hold this resource.
        candidates = sorted(
            (
                depot_id
                for (depot_id, resource), spare in ledger.items()
                if resource == requirement.resource_type and spare > 0
            ),
            key=lambda depot_id: eta_cache.get(depot_id, 9999),
        )

        for depot_id in candidates:
            if outstanding <= 0:
                break

            depot = depot_by_id[depot_id]
            key = (depot_id, requirement.resource_type)
            spare = ledger.get(key, 0)
            if spare <= 0:
                continue

            # Never strip one depot for a single requirement.
            original = depot.available_of(requirement.resource_type)
            cap = max(1, int(original * MAX_DEPOT_DRAWDOWN))
            draw = min(outstanding, spare, cap)
            if draw <= 0:
                continue

            ledger[key] = spare - draw
            outstanding -= draw
            total_allocated += draw

            allocations.append(
                Allocation(
                    allocation_id=f"ALC-{uuid.uuid4().hex[:8].upper()}",
                    resource_type=requirement.resource_type,
                    quantity=draw,
                    from_depot_id=depot.depot_id,
                    from_depot_name=depot.name,
                    to_location_name=inputs.destination_name,
                    to_point=destination,
                    distance_km=round(depot.point.distance_km(destination), 2),
                    eta_minutes=eta_cache.get(depot_id, 0),
                    urgency=requirement.urgency,
                    priority_score=round(_priority_score(requirement), 2),
                    rationale=(
                        f"{draw:,} of {requirement.quantity_required:,} "
                        f"{requirement.resource_type.value} from {depot.organization} "
                        f"({eta_cache.get(depot_id, 0)} min ETA including "
                        f"{depot.dispatch_delay_minutes} min mobilisation)."
                    ),
                )
            )

        if outstanding > 0:
            tier = RESOURCE_TIER.get(requirement.resource_type, 3)
            unmet.append(
                UnmetNeed(
                    resource_type=requirement.resource_type,
                    quantity_short=outstanding,
                    beneficiaries_affected=requirement.beneficiaries,
                    escalation_path=ESCALATION_PATH[tier],
                    consequence=CONSEQUENCE.get(
                        requirement.resource_type,
                        "Requirement unmet; operational impact requires assessment",
                    ),
                )
            )

    engaged_depot_ids = {a.from_depot_id for a in allocations}
    organizations = sorted(
        {
            depot_by_id[depot_id].organization_type
            for depot_id in engaged_depot_ids
            if depot_id in depot_by_id
        },
        key=lambda o: o.value,
    )

    plan = AllocationPlan(
        plan_id=f"PLAN-{uuid.uuid4().hex[:8].upper()}",
        requirements=requirements,
        allocations=allocations,
        unmet_needs=unmet,
        coverage_ratio=(
            round(total_allocated / total_required, 3) if total_required else 1.0
        ),
        total_units_allocated=total_allocated,
        depots_engaged=sorted(
            depot_by_id[d].name for d in engaged_depot_ids if d in depot_by_id
        ),
        organizations_engaged=organizations,
        revision=revision,
    )

    logger.info(
        "allocator.plan_built",
        allocations=len(allocations),
        unmet=len(unmet),
        coverage=plan.coverage_ratio,
        organizations=len(organizations),
    )
    return plan


def build_plan(inputs: AllocationInputs, *, revision: int = 0) -> AllocationPlan:
    """Convenience: derive requirements then allocate against them."""
    requirements = derive_requirements(inputs)
    return allocate(requirements, inputs, revision=revision)


def severity_reserve_fraction(severity: Severity) -> float:
    """Catastrophic events justify committing the reserve; minor ones do not."""
    return {
        Severity.INFORMATIONAL: 0.30,
        Severity.MINOR: 0.25,
        Severity.MODERATE: 0.20,
        Severity.SEVERE: 0.15,
        Severity.CATASTROPHIC: 0.05,
    }[severity]


__all__ = [
    "AllocationInputs",
    "allocate",
    "build_plan",
    "derive_requirements",
    "severity_reserve_fraction",
]
