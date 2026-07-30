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


def assam_brahmaputra_flood() -> IncidentReport:
    return IncidentReport(
        incident_id=_incident_id("INC-FLD"),
        description=(
            "Brahmaputra river has breached the main embankment near Morigaon and "
            "Kaziranga fringe. Over 40 low-lying rural villages are submerged under "
            "rapidly rising waters. Multiple families are stranded on raised embankments "
            "and school rooftops. NDRF and SDRF motorboats dispatched for mass evacuation."
        ),
        location=Location(
            name="Morigaon",
            point=GeoPoint(latitude=26.2500, longitude=92.3380),
            district="Morigaon",
            state="Assam",
            population=950_000,
        ),
        source=ReportSource(
            channel="control_room",
            reporter_name="Assam State Disaster Management Authority (ASDMA)",
            verified=True,
            trust_weight=0.95,
        ),
        media_paths=_sample_image("flooded_areas"),
        reported_casualties=14,
        declared_hazard=HazardType.FLOOD,
    )


def uttarakhand_cloudburst() -> IncidentReport:
    return IncidentReport(
        incident_id=_incident_id("INC-LND"),
        description=(
            "High-intensity cloudburst over Chamoli district triggering severe "
            "flash floods and massive landslides across NH-58. Pilgrim transit "
            "corridor cut off at three places, mudslides blocking Alaknanda tributaries, "
            "and several mountain village structures damaged in upper reaches."
        ),
        location=Location(
            name="Chamoli",
            point=GeoPoint(latitude=30.4042, longitude=79.3280),
            district="Chamoli",
            state="Uttarakhand",
            population=380_000,
        ),
        source=ReportSource(
            channel="control_room",
            reporter_name="Uttarakhand State Emergency Operation Centre",
            verified=True,
            trust_weight=0.95,
        ),
        media_paths=_sample_image("blocked_road"),
        reported_casualties=22,
        declared_hazard=HazardType.LANDSLIDE,
    )


def odisha_super_cyclone() -> IncidentReport:
    return IncidentReport(
        incident_id=_incident_id("INC-CYC"),
        description=(
            "Very Severe Cyclonic Storm making landfall near Puri coast with "
            "sustained winds of 150 km/h and higher gusts. 3.5m storm surge has "
            "inundated coastal fishing hamlets in Puri and Jagatsinghpur. Power "
            "grid and telecom infrastructure severely damaged across coastal belt."
        ),
        location=Location(
            name="Puri",
            point=GeoPoint(latitude=19.8135, longitude=85.8312),
            district="Puri",
            state="Odisha",
            population=200_000,
        ),
        source=ReportSource(
            channel="control_room",
            reporter_name="Odisha State Disaster Management Authority (OSDMA)",
            verified=True,
            trust_weight=0.95,
        ),
        media_paths=_sample_image("flooded_areas"),
        reported_casualties=45,
        declared_hazard=HazardType.CYCLONE,
    )


def delhi_yamuna_flood() -> IncidentReport:
    return IncidentReport(
        incident_id=_incident_id("INC-UFLD"),
        description=(
            "Yamuna river water level crossed critical mark of 205.33m near Old "
            "Railway Bridge following heavy discharge from Hathnikund Barrage. Low-lying "
            "dense urban settlements at Yamuna Bazaar and Kashmiri Gate inundated. "
            "Water treatment plant operations impaired due to silt loading."
        ),
        location=Location(
            name="Delhi NCR",
            point=GeoPoint(latitude=28.6139, longitude=77.2090),
            district="Central Delhi",
            state="Delhi",
            population=11_000_000,
        ),
        source=ReportSource(
            channel="control_room",
            reporter_name="Delhi Disaster Management Authority (DDMA)",
            verified=True,
            trust_weight=0.9,
        ),
        media_paths=_sample_image("flooded_areas"),
        reported_casualties=5,
        declared_hazard=HazardType.URBAN_FLOOD,
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
            key="assam_brahmaputra_flood",
            title="Brahmaputra Flood — Morigaon, Assam",
            description=(
                "Embankment breach and massive rural riverine flooding across "
                "Assam floodplain villages."
            ),
            demonstrates=(
                "Eastern India riverine disaster triage, large-scale rural shelter "
                "allocation, and multi-agency NDRF/SDRF coordination."
            ),
            build=assam_brahmaputra_flood,
        ),
        Scenario(
            key="uttarakhand_cloudburst",
            title="Cloudburst & Landslide — Chamoli, Uttarakhand",
            description=(
                "Himalayan flash flood and landslide blocking major transit corridors "
                "and mountain settlements."
            ),
            demonstrates=(
                "High-altitude hazard routing, landslide imagery analysis, and "
                "emergency search-and-rescue resource dispatch."
            ),
            build=uttarakhand_cloudburst,
        ),
        Scenario(
            key="odisha_super_cyclone",
            title="Severe Cyclone — Puri, Odisha",
            description=(
                "Coastal landfall with storm surge, severe infrastructure destruction, "
                "and widespread power loss."
            ),
            demonstrates=(
                "Bay of Bengal cyclone response, strategic reserve release, and "
                "coastal evacuation logistics."
            ),
            build=odisha_super_cyclone,
        ),
        Scenario(
            key="delhi_yamuna_flood",
            title="Yamuna Urban Flood — Delhi NCR",
            description=(
                "High-density urban river flooding affecting key transit hubs "
                "and municipal water treatment facilities."
            ),
            demonstrates=(
                "Metropolitan urban flood triage, public utility protection, and "
                "mass urban population alert broadcasting."
            ),
            build=delhi_yamuna_flood,
        ),
        Scenario(
            key="urban_building_collapse",
            title="Building Collapse — Kochi, Kerala",
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
            title="Heat Advisory — Thrissur, Kerala",
            description="Low-severity heat advisory from an unverified citizen report.",
            demonstrates=(
                "The severity gate short-circuiting the command apparatus so a "
                "minor incident does not mobilise eleven agents."
            ),
            build=heatwave_advisory,
        ),
        Scenario(
            key="cyclone_landfall",
            title="Cyclone Landfall — Fort Kochi, Kerala",
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
