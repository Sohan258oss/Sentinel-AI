"""Tests for domain invariants, triage calibration and retrieval.

The triage tests exist because the severity call drives every downstream
decision, and because the two bugs it has already had — a rising river
escalating a heatwave, and a single building collapse scaled to a whole
district — were both invisible until the numbers were read by eye.
"""

from __future__ import annotations

import pytest

from app.agents.base import AgentContext
from app.agents.situation import SituationAnalysisAgent
from app.rag.chunking import chunk_document, parse_document
from app.rag.retriever import get_retriever
from app.repositories.registry import depots, hospitals, river_gauges, shelters
from app.schemas.common import GeoPoint, Location
from app.schemas.enums import HazardType, ResourceType, Severity
from app.schemas.incident import ImpactEstimate, IncidentReport
from app.core.config import settings

ALUVA = GeoPoint(latitude=10.1004, longitude=76.3570)


class TestSchemaInvariants:
    def test_sub_populations_cannot_exceed_population_at_risk(self):
        """LLMs produce internally inconsistent numbers; the schema clamps them."""
        impact = ImpactEstimate(
            population_at_risk=1000,
            people_requiring_evacuation=5000,
            people_requiring_medical_care=9999,
            people_requiring_shelter=2000,
        )
        assert impact.people_requiring_evacuation == 1000
        assert impact.people_requiring_medical_care == 1000
        assert impact.people_requiring_shelter == 1000

    def test_severity_ordering(self):
        assert Severity.CATASTROPHIC.rank > Severity.SEVERE.rank
        assert Severity.INFORMATIONAL.rank < Severity.MINOR.rank
        assert Severity.from_rank(4) is Severity.CATASTROPHIC
        assert Severity.from_rank(99) is Severity.CATASTROPHIC  # clamped

    def test_geopoint_distance_is_sane(self):
        kochi = GeoPoint(latitude=9.9312, longitude=76.2673)
        distance = ALUVA.distance_km(kochi)
        # Aluva to Kochi is roughly 19 km.
        assert 15 < distance < 25


class TestRegistries:
    def test_all_registries_load(self):
        assert len(hospitals()) > 0
        assert len(shelters()) > 0
        assert len(depots()) > 0
        assert len(river_gauges()) > 0

    def test_registries_are_labelled_synthetic(self):
        """Provenance must be explicit — the UI shows a SIMULATED DATA badge."""
        for repository in (hospitals(), shelters(), depots(), river_gauges()):
            assert repository.meta.get("synthetic") is True

    def test_nearest_first_ordering(self):
        found = hospitals().near(ALUVA, radius_km=50)
        distances = [h.distance_km for h in found]
        assert distances == sorted(distances)

    def test_radius_filter_excludes_distant_facilities(self):
        near = hospitals().near(ALUVA, radius_km=5)
        assert all(h.distance_km <= 5 for h in near)

    def test_trauma_filter(self):
        trauma = hospitals().near(ALUVA, radius_km=60, trauma_only=True)
        assert all(h.trauma_capable for h in trauma)

    def test_gauge_lead_time_calculation(self):
        for gauge in river_gauges().all():
            hours = gauge.hours_to_danger
            if gauge.breaches_danger:
                assert hours == 0.0
            elif gauge.rate_of_change_m_per_hr <= 0:
                assert hours is None
            else:
                assert hours is not None and hours > 0

    def test_depot_available_accounts_for_reservations(self):
        for depot in depots().all():
            for stock in depot.stock:
                assert stock.available == max(0, stock.quantity - stock.reserved)


class TestTriageCalibration:
    """Regression tests for the two severity bugs found during integration."""

    @staticmethod
    def _context(hazard: HazardType, population: int = 310_000) -> AgentContext:
        return AgentContext(
            report=IncidentReport(
                incident_id="INC-CAL",
                description="calibration probe",
                location=Location(
                    name="Test Town",
                    point=ALUVA,
                    district="Ernakulam",
                    state="Kerala",
                    population=population,
                ),
                declared_hazard=hazard,
            ),
            run_id="test",
        )

    def test_rising_river_does_not_escalate_a_heatwave(self):
        """Hydrology signals must be gated to water-related hazards."""
        agent = SituationAnalysisAgent()
        evidence = {
            "weather": {"rainfall_mm_24h": 120, "forecast_rainfall_mm_24h": 150},
            "rivers": {
                "any_danger_breach": True,
                "any_warning_breach": True,
                "min_hours_to_danger": 1.0,
                "dam_spill_active": True,
                "gauges": [],
            },
        }
        assessment = agent.fallback(self._context(HazardType.HEATWAVE), evidence)
        assert assessment.severity.rank <= Severity.MINOR.rank, (
            "a rising river escalated a heatwave — hydrology gating regressed"
        )

    def test_same_evidence_does_escalate_a_flood(self):
        agent = SituationAnalysisAgent()
        evidence = {
            "weather": {"rainfall_mm_24h": 120, "forecast_rainfall_mm_24h": 150},
            "rivers": {
                "any_danger_breach": True,
                "any_warning_breach": True,
                "min_hours_to_danger": 1.0,
                "dam_spill_active": True,
                "gauges": [],
            },
        }
        assessment = agent.fallback(self._context(HazardType.FLOOD), evidence)
        assert assessment.severity.rank >= Severity.SEVERE.rank

    def test_building_collapse_stays_street_scale(self):
        """A single structural collapse must not scale to a whole district."""
        agent = SituationAnalysisAgent()
        assessment = agent.fallback(
            self._context(HazardType.BUILDING_COLLAPSE), {"weather": {}, "rivers": {}}
        )
        assert assessment.impact.affected_radius_km <= 1.0
        assert assessment.impact.population_at_risk < 5_000, (
            "collapse radius model regressed — a single building scaled district-wide"
        )

    def test_flood_displaces_more_than_it_injures(self):
        agent = SituationAnalysisAgent()
        assessment = agent.fallback(
            self._context(HazardType.FLOOD),
            {
                "weather": {"forecast_rainfall_mm_24h": 130},
                "rivers": {"any_warning_breach": True, "gauges": []},
            },
        )
        impact = assessment.impact
        assert impact.people_requiring_evacuation > impact.people_requiring_medical_care

    def test_flood_identifies_cascading_epidemic_risk(self):
        agent = SituationAnalysisAgent()
        assessment = agent.fallback(
            self._context(HazardType.FLOOD),
            {
                "weather": {"forecast_rainfall_mm_24h": 130},
                "rivers": {"any_danger_breach": True, "gauges": []},
            },
        )
        assert HazardType.EPIDEMIC in assessment.secondary_hazards


class TestRAG:
    def test_frontmatter_and_chunking(self):
        path = next(settings.knowledge_base_dir.glob("*.md"))
        document = parse_document(path)
        assert document.frontmatter.get("title")
        assert document.document_id

        chunks = chunk_document(document)
        assert chunks
        for chunk in chunks:
            assert chunk.section, "chunk lost its section heading — citations degrade"
            assert chunk.document_id == document.document_id

    @pytest.mark.parametrize(
        "query",
        [
            "how much drinking water per person per day",
            "casualty distribution across hospitals",
            "resource allocation priority order",
            "flood evacuation sequencing",
        ],
    )
    def test_core_doctrine_is_retrievable(self, query: str):
        result = get_retriever().retrieve(query, top_k=3)
        if result.degraded:
            pytest.skip("vector store unavailable in this environment")
        assert not result.is_empty, f"no doctrine retrieved for: {query}"
        assert result.chunks[0].relevance > 0.3

    def test_citations_are_attributable(self):
        result = get_retriever().retrieve("relief camp minimum standards", top_k=3)
        if result.degraded or result.is_empty:
            pytest.skip("vector store unavailable in this environment")
        for citation in result.citations:
            assert citation.source_id
            assert citation.document_title
            assert citation.snippet


class TestTools:
    @pytest.mark.asyncio
    async def test_fallbacks_are_self_consistent(self):
        """Weather and hydrology must not contradict each other.

        The offline weather model derives rainfall from gauge dynamics precisely
        so the picture cannot show clear skies beside a climbing river.
        """
        from app.tools import load_tools, registry

        load_tools()
        weather, _ = await registry.get("get_weather_conditions").invoke(
            latitude=ALUVA.latitude, longitude=ALUVA.longitude, place="Aluva"
        )
        rivers, _ = await registry.get("get_river_levels").invoke(
            latitude=ALUVA.latitude, longitude=ALUVA.longitude
        )

        if rivers.data.get("any_warning_breach"):
            assert weather.data["rainfall_mm_24h"] > 15, (
                "rivers are rising but the weather model reports negligible rain"
            )

    @pytest.mark.asyncio
    async def test_news_tool_generates_no_synthetic_articles(self):
        """Fabricating headlines about real places would be disinformation."""
        from app.tools import load_tools, registry

        load_tools()
        result, _ = await registry.get("search_news").invoke(query="Aluva flood")
        assert result.data["article_count"] == 0
        assert result.data["feed_available"] is False
        assert "information_gap" in result.data

    @pytest.mark.asyncio
    async def test_route_estimate_degrades_speed_under_hazard(self):
        from app.tools import load_tools, registry

        load_tools()
        tool = registry.get("estimate_route")
        clear, _ = await tool.invoke(
            from_latitude=10.15, from_longitude=76.39,
            to_latitude=10.10, to_longitude=76.35, hazard_type="drought",
        )
        flooded, _ = await tool.invoke(
            from_latitude=10.15, from_longitude=76.39,
            to_latitude=10.10, to_longitude=76.35, hazard_type="flood",
        )
        assert flooded.data["eta_minutes"] > clear.data["eta_minutes"]
        assert flooded.data["assumption"]


class TestVision:
    def test_damage_severity_never_reaches_catastrophic(self):
        """No single photograph should trigger a state-level mobilisation."""
        from app.vision.base import DAMAGE_SEVERITY

        for damage_class, severity in DAMAGE_SEVERITY.items():
            assert severity.rank <= Severity.SEVERE.rank, (
                f"{damage_class} maps to {severity} — imagery alone cannot "
                "justify a catastrophic declaration"
            )
