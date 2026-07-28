"""Vision subsystem interfaces.

Three independent detectors sit behind one interface:

* :class:`DamageClassifier` — a fine-tuned CNN. Fast, cheap, offline, and the
  component that makes the "we trained a model" claim real.
* ``ObjectDetector`` — a localising detector (YOLO), optional at runtime.
* ``VLMAnalyst`` — a vision-language model. Slower and networked, but capable of
  describing novel scenes the CNN was never trained on.

Keeping them behind one protocol means the ensemble can run whichever subset is
actually available and honestly report how much they agreed. A single-model
vision pipeline has no way to express uncertainty; three do.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.enums import DamageClass, Severity
from app.schemas.intelligence import DamageDetection

#: How strongly each damage class implies overall incident severity. Used to
#: turn a visual finding into an operational signal.
#: A single image is evidence of local conditions, not a district-wide verdict.
#: These deliberately top out at SEVERE: no photograph on its own justifies a
#: CATASTROPHIC declaration, which mobilises state-level resources. Escalation
#: to catastrophic requires corroborating signals (casualty counts, hydrology,
#: multiple reports), which the triage agent combines separately.
DAMAGE_SEVERITY: dict[DamageClass, Severity] = {
    DamageClass.NO_DAMAGE: Severity.INFORMATIONAL,
    DamageClass.SMOKE: Severity.MODERATE,
    DamageClass.BLOCKED_ROAD: Severity.MODERATE,
    DamageClass.DAMAGED_BUILDING: Severity.MODERATE,
    DamageClass.VEHICLE_SUBMERGED: Severity.MODERATE,
    DamageClass.DAMAGED_BRIDGE: Severity.SEVERE,
    DamageClass.FLOODED_AREA: Severity.SEVERE,
    DamageClass.FIRE: Severity.SEVERE,
    DamageClass.COLLAPSED_BUILDING: Severity.SEVERE,
    DamageClass.STRANDED_PEOPLE: Severity.SEVERE,
}


class VisionDetector(ABC):
    """Common contract for every vision component."""

    name: str

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether this detector can actually run right now."""

    @abstractmethod
    async def analyze(self, image_path: Path) -> list[DamageDetection]:
        """Return detections for one image. Must not raise."""

    def describe(self) -> str:
        return f"{self.name} ({'available' if self.available else 'unavailable'})"
