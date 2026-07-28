"""Primitives shared across every other schema module."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]

EARTH_RADIUS_KM = 6371.0088


class SentinelModel(BaseModel):
    """Base for every schema: strict, immutable-ish, JSON-friendly."""

    model_config = ConfigDict(
        extra="ignore",
        use_enum_values=False,
        validate_assignment=True,
        populate_by_name=True,
        ser_json_timedelta="float",
    )


def utcnow() -> datetime:
    return datetime.now(UTC)


class GeoPoint(SentinelModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    def distance_km(self, other: "GeoPoint") -> float:
        """Great-circle distance. Used by every routing and allocation path."""
        lat1, lon1, lat2, lon2 = map(
            math.radians,
            (self.latitude, self.longitude, other.latitude, other.longitude),
        )
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"{self.latitude:.4f},{self.longitude:.4f}"


class Location(SentinelModel):
    """A place, as an operator would name it — plus machine coordinates."""

    name: str = Field(description="Human-readable place name, e.g. 'Kochi, Kerala'")
    point: GeoPoint
    district: str | None = None
    state: str | None = None
    country: str = "India"
    population: int | None = Field(
        default=None, ge=0, description="Best-known population of the named area"
    )

    @property
    def label(self) -> str:
        parts = [p for p in (self.name, self.district, self.state) if p]
        # De-duplicate when name already contains the district/state.
        seen: list[str] = []
        for part in parts:
            if part not in seen:
                seen.append(part)
        return ", ".join(seen)


class Citation(SentinelModel):
    """Provenance for a retrieved claim. Non-negotiable in emergency doctrine."""

    source_id: str
    document_title: str
    section: str | None = None
    page: int | None = None
    snippet: str = Field(description="Verbatim supporting text from the source")
    relevance: Confidence = 0.5
    authority: str | None = Field(
        default=None, description="Issuing body, e.g. 'NDMA' or 'WHO'"
    )


class Measure(SentinelModel):
    """A named quantity with units — avoids unit-less numbers in LLM output."""

    label: str
    value: float
    unit: str
    trend: str | None = Field(default=None, description="rising | falling | steady")


class TimeWindow(SentinelModel):
    starts_at: datetime
    ends_at: datetime

    @property
    def duration_hours(self) -> float:
        return (self.ends_at - self.starts_at).total_seconds() / 3600.0
