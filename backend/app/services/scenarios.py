"""Demo scenarios.

Scripted incidents that exercise different paths through the graph. These are
not fixtures with canned outputs — they are genuine inputs that run the full
agent team, so a demo shows the real system reasoning rather than a replay.

Each scenario is chosen to make a *different* architectural property visible:

* ``kerala_flood`` — the flagship. Severe, multi-agent, imagery-driven,
  produces a shelter deficit that forces a reflection cycle.
* ``urban_building_collapse`` — different hazard routing entirely; the
  Commander declines weather and shelter, proving routing is per-incident.
* ``heatwave_advisory`` — low severity; demonstrates the severity gate
  short-circuiting the command apparatus.
* ``cyclone_landfall`` — catastrophic; drives the strategic reserve down and
  produces unmet needs and state escalation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.schemas.common import GeoPoint, Location
from app.schemas.enums import HazardType
from app.schemas.incident import IncidentReport, ReportSource


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    description: str
    demonstrates: str
    build: object  # callable returning IncidentReport

    def create(self) -> IncidentReport:
        return self.build()  # type: ignore[operator]


def _sample_image(class_name: str) -> list[str]:
    """Pick a real image from the training corpus for the vision pipeline.

    Using genuine disaster imagery means the CNN and VLM actually run during a
    demo instead of being asserted to exist.
    """
    folder = settings.knowledge_base_dir.parent / "ml" / "datasets" / "aider" / class_name
    if not folder.exists():
        return []
    images = sorted(folder.glob("*.jpg"))
    if not images:
        return []
    # Deterministic pick so demos are reproducible.
    return [str(images[len(images) // 3])]


def _incident_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


def kerala_flood() -> IncidentReport:
    return IncidentReport(
        incident_id=_incident_id("INC-FLD"),
        description=(
            "Periyar river has breached its bank near Aluva town. Water has entered "
            "residential colonies in the low-lying areas around the market and the "
            "bus stand. Ground floors are submerged to roughly chest height in "
            "several streets. Idukki reservoir began controlled spill six hours ago "
            "and levels are still climbing. Multiple families are reported stranded "
            "on rooftops. Road access from the north is under water."
        ),
        location=Location(
            name="Aluva",
            point=GeoPoint(latitude=10.1004, longitude=76.3570),
            district="Ernakulam",
            state="Kerala",
            population=310_000,
        ),
        source=ReportSource(
            channel="control_room",
            reporter_name="Ernakulam District Control Room",
            verified=True,
            trust_weight=0.9,
        ),
        media_paths=_sample_image("flooded_areas"),
        reported_casualties=12,
        declared_hazard=HazardType.FLOOD,
    )


def urban_building_collapse() -> IncidentReport:
    return IncidentReport(
        incident_id=_incident_id("INC-COL"),
        description=(
            "A four-storey residential building has partially collapsed in a dense "
            "neighbourhood of Kochi following structural failure during renovation "
            "work. The rear section has come down completely. Neighbours report "
            "approximately fifteen to twenty residents were inside at the time. "
            "Dust and debris are blocking the access lane, and adjacent structures "
            "appear to be leaning."
        ),
        location=Location(
            name="Kochi",
            point=GeoPoint(latitude=9.9312, longitude=76.2673),
            district="Ernakulam",
            state="Kerala",
            population=680_000,
        ),
        source=ReportSource(
            channel="field_responder",
            reporter_name="Fire and Rescue Station Officer",
            verified=True,
            trust_weight=0.95,
        ),
        media_paths=_sample_image("collapsed_building"),
        reported_casualties=18,
        declared_hazard=HazardType.BUILDING_COLLAPSE,
    )


def heatwave_advisory() -> IncidentReport:
    return IncidentReport(
        incident_id=_incident_id("INC-HEA"),
        description=(
            "Ambient temperature has been above 38 degrees for three consecutive "
            "days in Thrissur with high humidity. A few outdoor workers have "
            "reported dizziness at a construction site. No hospitalisations so far. "
            "Requesting advisory guidance."
        ),
        location=Location(
            name="Thrissur",
            point=GeoPoint(latitude=10.5276, longitude=76.2144),
            district="Thrissur",
            state="Kerala",
            population=315_000,
        ),
        source=ReportSource(
            channel="citizen_app",
            verified=False,
            trust_weight=0.4,
        ),
        declared_hazard=HazardType.HEATWAVE,
    )


def cyclone_landfall() -> IncidentReport:
    return IncidentReport(
        incident_id=_incident_id("INC-CYC"),
        description=(
            "Severe cyclonic storm is making landfall along the Ernakulam coast. "
            "Sustained winds are estimated at 130 km/h with gusts higher. Storm "
            "surge has inundated the coastal strip at Fort Kochi and Vypin island. "
            "Power distribution has failed across the coastal belt and telecom is "
            "intermittent. Multiple structures have lost roofing. Fishing "
            "communities on Vypin are cut off as the connecting road is submerged."
        ),
        location=Location(
            name="Fort Kochi",
            point=GeoPoint(latitude=9.9658, longitude=76.2422),
            district="Ernakulam",
            state="Kerala",
            population=240_000,
        ),
        source=ReportSource(
            channel="control_room",
            reporter_name="State Emergency Operations Centre",
            verified=True,
            trust_weight=0.95,
        ),
        media_paths=_sample_image("flooded_areas"),
        reported_casualties=34,
        declared_hazard=HazardType.CYCLONE,
    )


SCENARIOS: dict[str, Scenario] = {
    scenario.key: scenario
    for scenario in [
        Scenario(
            key="kerala_flood",
            title="Periyar River Flood — Aluva, Kerala",
            description=(
                "Severe riverine flooding with upstream dam spill, stranded "
                "residents and imagery from the incident site."
            ),
            demonstrates=(
                "Full multi-agent activation, vision ensemble, RAG doctrine "
                "grounding, and a reflection cycle triggered by a shelter deficit."
            ),
            build=kerala_flood,
        ),
        Scenario(
            key="urban_building_collapse",
            title="Building Collapse — Kochi",
            description=(
                "Structural collapse with trapped occupants in a dense urban area."
            ),
            demonstrates=(
                "Hazard-specific routing: the Commander activates medical and "
                "infrastructure but declines weather, proving routing is decided "
                "per-incident rather than fixed."
            ),
            build=urban_building_collapse,
        ),
        Scenario(
            key="heatwave_advisory",
            title="Heat Advisory — Thrissur",
            description="Low-severity heat advisory from an unverified citizen report.",
            demonstrates=(
                "The severity gate short-circuiting the command apparatus so a "
                "minor incident does not mobilise eleven agents."
            ),
            build=heatwave_advisory,
        ),
        Scenario(
            key="cyclone_landfall",
            title="Cyclone Landfall — Fort Kochi",
            description=(
                "Catastrophic cyclone with storm surge, isolated island "
                "communities and infrastructure failure."
            ),
            demonstrates=(
                "Strategic reserve release at catastrophic severity, unmet-need "
                "escalation to state level, and multi-organisation sourcing."
            ),
            build=cyclone_landfall,
        ),
    ]
}


def get_scenario(key: str) -> Scenario:
    if key not in SCENARIOS:
        raise KeyError(f"Unknown scenario '{key}'. Available: {sorted(SCENARIOS)}")
    return SCENARIOS[key]


def list_scenarios() -> list[dict[str, str]]:
    return [
        {
            "key": s.key,
            "title": s.title,
            "description": s.description,
            "demonstrates": s.demonstrates,
        }
        for s in SCENARIOS.values()
    ]
