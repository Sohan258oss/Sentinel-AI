"""Agent memory.

Two distinct kinds, because they answer different questions:

* **Episodic** — what happened during *this* incident. Lets a later node see
  what an earlier one concluded without threading every field through the graph
  state, and gives the Reflection agent the run's own history to critique.
* **Semantic** — durable lessons across incidents. After each run the platform
  distils what was learned ("Paravur camp flooded at 4.5 m at Aluva gauge; do
  not designate it below that level") and retrieves it for future incidents in
  the same area or hazard class.

Semantic memory is what makes the platform improve with use rather than
restarting from zero every time — the difference between a tool and a system
that accumulates institutional knowledge.

Storage is a JSON-backed store with an in-memory index. The interface is
deliberately narrow so it can move to Postgres or a vector DB without touching
callers.
"""

from __future__ import annotations

import json
import threading
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import Field

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.common import GeoPoint, SentinelModel, utcnow
from app.schemas.enums import AgentRole, HazardType, Severity

logger = get_logger(__name__)


class EpisodicEntry(SentinelModel):
    """One thing an agent concluded during a run."""

    incident_id: str
    run_id: str
    agent: AgentRole
    summary: str
    detail: str = ""
    confidence: float = 0.5
    created_at: datetime = Field(default_factory=utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)


class SemanticLesson(SentinelModel):
    """A durable, reusable lesson learned from a past incident."""

    lesson_id: str
    hazard_type: HazardType
    region: str
    point: GeoPoint | None = None
    severity_seen: Severity = Severity.MODERATE
    lesson: str = Field(description="The transferable insight, stated as guidance")
    evidence: str = Field(default="", description="What in the incident produced it")
    source_incident_id: str = ""
    times_reinforced: int = 1
    created_at: datetime = Field(default_factory=utcnow)

    def matches(
        self, *, hazard: HazardType, point: GeoPoint | None, radius_km: float
    ) -> bool:
        if self.hazard_type != hazard:
            return False
        if self.point is None or point is None:
            return True  # region-agnostic lesson
        return self.point.distance_km(point) <= radius_km


class MemoryStore:
    """Combined episodic + semantic memory with JSON persistence."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (settings.seed_data_dir.parent / "memory.json")
        self._episodic: dict[str, list[EpisodicEntry]] = defaultdict(list)
        self._semantic: dict[str, SemanticLesson] = {}
        self._lock = threading.Lock()
        self._loaded = False

    # -- Persistence ---------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._loaded = True
            if not self._path.exists():
                return
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
                for row in payload.get("semantic", []):
                    lesson = SemanticLesson.model_validate(row)
                    self._semantic[lesson.lesson_id] = lesson
                logger.info("memory.loaded", lessons=len(self._semantic))
            except Exception as exc:  # noqa: BLE001 - memory loss must not be fatal
                logger.error("memory.load_failed", error=str(exc)[:200])

    def _persist(self) -> None:
        """Only semantic memory persists; episodic memory is per-run."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "semantic": [
                    lesson.model_dump(mode="json") for lesson in self._semantic.values()
                ],
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.error("memory.persist_failed", error=str(exc)[:200])

    # -- Episodic ------------------------------------------------------------

    def remember(self, entry: EpisodicEntry) -> None:
        self._episodic[entry.incident_id].append(entry)

    def recall_episode(
        self, incident_id: str, *, agent: AgentRole | None = None
    ) -> list[EpisodicEntry]:
        entries = self._episodic.get(incident_id, [])
        if agent is not None:
            return [e for e in entries if e.agent == agent]
        return list(entries)

    def episode_digest(self, incident_id: str, *, limit: int = 12) -> str:
        """Compact prose summary of the run so far, for prompt injection."""
        entries = self.recall_episode(incident_id)[-limit:]
        if not entries:
            return "(no prior agent findings in this incident)"
        return "\n".join(
            f"- [{e.agent.value}] {e.summary} (confidence {e.confidence:.2f})"
            for e in entries
        )

    def forget_episode(self, incident_id: str) -> None:
        self._episodic.pop(incident_id, None)

    # -- Semantic ------------------------------------------------------------

    def learn(self, lesson: SemanticLesson) -> SemanticLesson:
        """Store a lesson, reinforcing an existing one if it duplicates."""
        self._ensure_loaded()

        for existing in self._semantic.values():
            if (
                existing.hazard_type == lesson.hazard_type
                and existing.region.lower() == lesson.region.lower()
                and _similar(existing.lesson, lesson.lesson)
            ):
                existing.times_reinforced += 1
                self._persist()
                logger.info(
                    "memory.lesson_reinforced",
                    lesson_id=existing.lesson_id,
                    count=existing.times_reinforced,
                )
                return existing

        self._semantic[lesson.lesson_id] = lesson
        self._persist()
        logger.info("memory.lesson_learned", lesson_id=lesson.lesson_id, hazard=lesson.hazard_type.value)
        return lesson

    def recall_lessons(
        self,
        *,
        hazard: HazardType,
        point: GeoPoint | None = None,
        radius_km: float = 60.0,
        limit: int = 5,
    ) -> list[SemanticLesson]:
        """Lessons applicable to an incident, most reinforced first."""
        self._ensure_loaded()
        matches = [
            lesson
            for lesson in self._semantic.values()
            if lesson.matches(hazard=hazard, point=point, radius_km=radius_km)
        ]
        matches.sort(key=lambda l: (l.times_reinforced, l.created_at), reverse=True)
        return matches[:limit]

    def lessons_digest(
        self, *, hazard: HazardType, point: GeoPoint | None = None, limit: int = 5
    ) -> str:
        lessons = self.recall_lessons(hazard=hazard, point=point, limit=limit)
        if not lessons:
            return "(no prior lessons recorded for this hazard and area)"
        return "\n".join(
            f"- {l.lesson} [from {l.source_incident_id or 'prior incident'}, "
            f"reinforced {l.times_reinforced}x]"
            for l in lessons
        )

    def all_lessons(self) -> list[SemanticLesson]:
        self._ensure_loaded()
        return sorted(
            self._semantic.values(), key=lambda l: l.times_reinforced, reverse=True
        )

    def prune(self, *, older_than_days: int = 365) -> int:
        """Drop stale, never-reinforced lessons."""
        self._ensure_loaded()
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        stale = [
            lid
            for lid, lesson in self._semantic.items()
            if lesson.created_at < cutoff and lesson.times_reinforced <= 1
        ]
        for lid in stale:
            del self._semantic[lid]
        if stale:
            self._persist()
        return len(stale)


def _similar(left: str, right: str, threshold: float = 0.7) -> bool:
    """Cheap token-overlap similarity — enough to catch restatements."""
    left_tokens = set(left.lower().split())
    right_tokens = set(right.lower().split())
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
    return overlap >= threshold


_store: MemoryStore | None = None


def get_memory() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store
