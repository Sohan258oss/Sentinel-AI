"""Registry repositories — the platform's view of physical reality.

Every repository loads a seeded JSON registry once, validates it into domain
schemas, and exposes *geospatial* queries rather than raw rows. Agents ask
"what trauma-capable hospitals are within 25 km and still have ICU capacity?",
never "give me the hospital table".

Swapping the JSON backing store for PostGIS or a live government API means
reimplementing ``_load`` in one class. Nothing above this layer changes.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Any, Generic, TypeVar

from app.core.config import settings
from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger
from app.schemas.common import GeoPoint
from app.schemas.enums import OrganizationType, ResourceType
from app.schemas.intelligence import HospitalStatus, RiverGauge, ShelterSite
from app.schemas.resources import Depot, ResourceStock

logger = get_logger(__name__)

TRecord = TypeVar("TRecord")


def _read_seed(filename: str) -> dict[str, Any]:
    path = settings.seed_data_dir / filename
    if not path.exists():
        raise ConfigurationError(f"Missing seed registry: {path}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


class SeedRepository(ABC, Generic[TRecord]):
    """Base for JSON-backed registries."""

    filename: str
    collection_key: str

    def __init__(self) -> None:
        self._records: list[TRecord] | None = None
        self._meta: dict[str, Any] = {}

    @abstractmethod
    def _parse(self, raw: dict[str, Any]) -> TRecord:
        """Convert one raw JSON record into a validated domain object."""

    def _load(self) -> list[TRecord]:
        if self._records is not None:
            return self._records

        payload = _read_seed(self.filename)
        self._meta = payload.get("_meta", {})
        rows = payload.get(self.collection_key, [])

        parsed: list[TRecord] = []
        for row in rows:
            try:
                parsed.append(self._parse(row))
            except Exception as exc:  # noqa: BLE001 - one bad row must not kill startup
                logger.error(
                    "registry.row_invalid",
                    registry=self.filename,
                    row_id=row.get("facility_id") or row.get("shelter_id") or row.get("depot_id"),
                    error=str(exc)[:200],
                )

        self._records = parsed
        logger.info(
            "registry.loaded",
            registry=self.filename,
            records=len(parsed),
            synthetic=self._meta.get("synthetic", False),
        )
        return parsed

    @property
    def meta(self) -> dict[str, Any]:
        """Provenance metadata — surfaced in the UI as a SIMULATED DATA badge."""
        self._load()
        return self._meta

    def all(self) -> list[TRecord]:
        return list(self._load())

    def __len__(self) -> int:
        return len(self._load())


def _point(row: dict[str, Any]) -> GeoPoint:
    return GeoPoint(latitude=row["latitude"], longitude=row["longitude"])


class HospitalRepository(SeedRepository[HospitalStatus]):
    filename = "hospitals.json"
    collection_key = "hospitals"

    def _parse(self, raw: dict[str, Any]) -> HospitalStatus:
        return HospitalStatus(
            facility_id=raw["facility_id"],
            name=raw["name"],
            point=_point(raw),
            total_beds=raw.get("total_beds", 0),
            available_beds=raw.get("available_beds", 0),
            icu_available=raw.get("icu_available", 0),
            ventilators_available=raw.get("ventilators_available", 0),
            blood_bank=raw.get("blood_bank", False),
            trauma_capable=raw.get("trauma_capable", False),
            operational_status=raw.get("operational_status", "operational"),
        )

    def near(
        self,
        origin: GeoPoint,
        *,
        radius_km: float = 50.0,
        limit: int = 8,
        trauma_only: bool = False,
        require_beds: bool = False,
    ) -> list[HospitalStatus]:
        """Reachable hospitals, nearest first, with distance stamped on each."""
        results: list[HospitalStatus] = []
        for hospital in self._load():
            if trauma_only and not hospital.trauma_capable:
                continue
            if require_beds and hospital.available_beds <= 0:
                continue
            distance = origin.distance_km(hospital.point)
            if distance > radius_km:
                continue
            enriched = hospital.model_copy(update={"distance_km": round(distance, 2)})
            results.append(enriched)

        results.sort(key=lambda h: h.distance_km)
        return results[:limit]


class ShelterRepository(SeedRepository[ShelterSite]):
    filename = "shelters.json"
    collection_key = "shelters"

    def _parse(self, raw: dict[str, Any]) -> ShelterSite:
        return ShelterSite(
            shelter_id=raw["shelter_id"],
            name=raw["name"],
            point=_point(raw),
            capacity=raw.get("capacity", 0),
            current_occupancy=raw.get("current_occupancy", 0),
            has_medical_post=raw.get("has_medical_post", False),
            has_power_backup=raw.get("has_power_backup", False),
            accessible=raw.get("accessible", True),
            flood_safe=raw.get("flood_safe", True),
        )

    def near(
        self,
        origin: GeoPoint,
        *,
        radius_km: float = 40.0,
        limit: int = 10,
        flood_safe_only: bool = False,
        accessible_only: bool = False,
    ) -> list[ShelterSite]:
        results: list[ShelterSite] = []
        for shelter in self._load():
            if flood_safe_only and not shelter.flood_safe:
                continue
            if accessible_only and not shelter.accessible:
                continue
            distance = origin.distance_km(shelter.point)
            if distance > radius_km:
                continue
            results.append(shelter.model_copy(update={"distance_km": round(distance, 2)}))

        # Nearest first, but a shelter with no spare capacity is useless — push
        # those to the back rather than dropping them (the commander still
        # wants to see that they are full).
        results.sort(key=lambda s: (s.spare_capacity == 0, s.distance_km))
        return results[:limit]


class DepotRepository(SeedRepository[Depot]):
    filename = "depots.json"
    collection_key = "depots"

    def _parse(self, raw: dict[str, Any]) -> Depot:
        return Depot(
            depot_id=raw["depot_id"],
            name=raw["name"],
            organization=raw["organization"],
            organization_type=OrganizationType(raw["organization_type"]),
            point=_point(raw),
            dispatch_delay_minutes=raw.get("dispatch_delay_minutes", 30),
            operational=raw.get("operational", True),
            stock=[
                ResourceStock(
                    resource_type=ResourceType(s["resource_type"]),
                    quantity=s.get("quantity", 0),
                    reserved=s.get("reserved", 0),
                    unit=s.get("unit", "units"),
                )
                for s in raw.get("stock", [])
            ],
        )

    def near(
        self,
        origin: GeoPoint,
        *,
        radius_km: float = 120.0,
        resource_type: ResourceType | None = None,
        operational_only: bool = True,
    ) -> list[Depot]:
        """Supply nodes in range, nearest first, optionally filtered by stock."""
        results: list[Depot] = []
        for depot in self._load():
            if operational_only and not depot.operational:
                continue
            if resource_type is not None and depot.available_of(resource_type) <= 0:
                continue
            if origin.distance_km(depot.point) > radius_km:
                continue
            results.append(depot)

        results.sort(key=lambda d: origin.distance_km(d.point))
        return results

    def total_available(self, resource_type: ResourceType) -> int:
        return sum(d.available_of(resource_type) for d in self._load() if d.operational)

    def organizations(self) -> list[OrganizationType]:
        return sorted({d.organization_type for d in self._load()}, key=lambda o: o.value)


class RiverGaugeRepository(SeedRepository[RiverGauge]):
    filename = "river_gauges.json"
    collection_key = "gauges"

    def _parse(self, raw: dict[str, Any]) -> RiverGauge:
        return RiverGauge(
            gauge_id=raw["gauge_id"],
            river=raw["river"],
            station=raw["station"],
            point=_point(raw),
            current_level_m=raw["current_level_m"],
            warning_level_m=raw["warning_level_m"],
            danger_level_m=raw["danger_level_m"],
            highest_recorded_m=raw.get("highest_recorded_m"),
            trend=raw.get("trend", "steady"),
            rate_of_change_m_per_hr=raw.get("rate_of_change_m_per_hr", 0.0),
            upstream_dam=raw.get("upstream_dam"),
            dam_spill_active=raw.get("dam_spill_active", False),
        )

    def near(
        self, origin: GeoPoint, *, radius_km: float = 60.0, limit: int = 5
    ) -> list[RiverGauge]:
        results: list[RiverGauge] = []
        for gauge in self._load():
            distance = origin.distance_km(gauge.point)
            if distance > radius_km:
                continue
            results.append(gauge.model_copy(update={"distance_km": round(distance, 2)}))

        # Most dangerous first — a breached gauge 40 km away matters more than a
        # calm one next door.
        results.sort(key=lambda g: (-int(g.breaches_danger), -int(g.breaches_warning), g.distance_km))
        return results[:limit]


@lru_cache
def hospitals() -> HospitalRepository:
    return HospitalRepository()


@lru_cache
def shelters() -> ShelterRepository:
    return ShelterRepository()


@lru_cache
def depots() -> DepotRepository:
    return DepotRepository()


@lru_cache
def river_gauges() -> RiverGaugeRepository:
    return RiverGaugeRepository()


def registry_provenance() -> dict[str, Any]:
    """Aggregate provenance for the UI's data-integrity badge."""
    return {
        "hospitals": hospitals().meta,
        "shelters": shelters().meta,
        "depots": depots().meta,
        "river_gauges": river_gauges().meta,
    }
