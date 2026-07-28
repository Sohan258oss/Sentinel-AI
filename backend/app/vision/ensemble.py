"""Multi-model vision ensemble.

Fuses the fine-tuned CNN, the optional object detector and the VLM into one
assessment, and — the part that actually matters operationally — reports how
much they *agreed*.

Agreement is the honest uncertainty signal. When the CNN says "flooded area"
at 0.94 and the VLM independently describes submerged vehicles, a commander can
act on that. When the CNN says "flood" and the VLM says "no disaster visible",
the correct output is not a confident average — it is a flag that the image
needs human review. A single-model pipeline cannot express that distinction,
which is the whole reason for running three.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.enums import DamageClass, Severity
from app.schemas.intelligence import DamageDetection, VisionAssessment
from app.vision.base import DAMAGE_SEVERITY, VisionDetector
from app.vision.classifier import DamageClassifier
from app.vision.vlm import VLMAnalyst

logger = get_logger(__name__)

#: Relative trust per detector. The CNN is trained specifically for this task
#: and is weighted accordingly; the VLM generalises better but is less
#: calibrated on this narrow label set.
DETECTOR_WEIGHT: dict[str, float] = {
    "cnn": 1.0,
    "yolo": 0.85,
    "vlm": 0.9,
}

#: Below this fused score a class is not reported at all.
REPORTING_FLOOR = 0.18


class VisionEnsemble:
    """Runs every available detector and reconciles their output."""

    def __init__(self, detectors: list[VisionDetector] | None = None) -> None:
        self._detectors: list[VisionDetector] = detectors or [
            DamageClassifier(),
            VLMAnalyst(),
        ]

    @property
    def available_detectors(self) -> list[str]:
        return [d.name for d in self._detectors if d.available]

    def status(self) -> dict[str, bool]:
        return {d.name: d.available for d in self._detectors}

    async def analyze(self, image_path: str | Path) -> VisionAssessment:
        path = Path(image_path)

        if not path.exists():
            logger.error("vision.image_missing", path=str(path))
            return VisionAssessment(
                image_path=str(path),
                description="Image file could not be read.",
                severity_signal=Severity.INFORMATIONAL,
            )

        active = [d for d in self._detectors if d.available]
        if not active:
            logger.warning("vision.no_detectors")
            return VisionAssessment(
                image_path=str(path),
                description=(
                    "No vision model is available. Train the classifier "
                    "(python -m ml.train_damage_classifier) or configure an LLM "
                    "API key to enable image analysis."
                ),
                severity_signal=Severity.INFORMATIONAL,
            )

        # Detectors are independent — run them concurrently.
        results = await asyncio.gather(
            *(detector.analyze(path) for detector in active), return_exceptions=True
        )

        detections: list[DamageDetection] = []
        used: list[str] = []
        for detector, outcome in zip(active, results):
            if isinstance(outcome, BaseException):
                logger.error(
                    "vision.detector_failed", detector=detector.name, error=str(outcome)[:200]
                )
                continue
            used.append(detector.name)
            detections.extend(outcome)

        return self._fuse(path, detections, used, active)

    def _fuse(
        self,
        path: Path,
        detections: list[DamageDetection],
        used: list[str],
        active: list[VisionDetector],
    ) -> VisionAssessment:
        if not detections:
            return VisionAssessment(
                image_path=str(path),
                detections=[],
                dominant_class=DamageClass.NO_DAMAGE,
                severity_signal=Severity.INFORMATIONAL,
                description="No damage indicators were detected in this image.",
                models_used=used,
                ensemble_agreement=1.0 if len(used) > 1 else 0.0,
            )

        # Weighted score per class, and which detectors voted for it.
        scores: dict[DamageClass, float] = {}
        voters: dict[DamageClass, set[str]] = {}
        for detection in detections:
            weight = DETECTOR_WEIGHT.get(detection.detector, 0.8)
            scores[detection.damage_class] = (
                scores.get(detection.damage_class, 0.0) + detection.confidence * weight
            )
            voters.setdefault(detection.damage_class, set()).add(detection.detector)

        # Normalise so scores stay interpretable as confidence.
        total_weight = sum(DETECTOR_WEIGHT.get(d, 0.8) for d in set(used)) or 1.0
        normalised = {cls: score / total_weight for cls, score in scores.items()}

        dominant = max(normalised, key=lambda c: normalised[c])

        # Agreement: what fraction of the detectors that ran actually voted for
        # the dominant class. With one detector there is nothing to agree with,
        # so we report 0 rather than a misleading 1.
        agreement = (len(voters[dominant]) / len(used)) if len(used) > 1 else 0.0

        reported = sorted(
            (
                DamageDetection(
                    damage_class=cls,
                    confidence=round(min(1.0, score), 3),
                    detector="ensemble",
                    note=f"agreed by: {', '.join(sorted(voters[cls]))}",
                )
                for cls, score in normalised.items()
                if score >= REPORTING_FLOOR
            ),
            key=lambda d: d.confidence,
            reverse=True,
        )

        severity = DAMAGE_SEVERITY.get(dominant, Severity.MODERATE)

        # A confident-but-contested reading is downgraded. Acting on a disputed
        # catastrophic call wastes resources that a contested reading cannot
        # justify.
        contested = len(used) > 1 and agreement < 0.5
        if contested and severity.rank > Severity.MODERATE.rank:
            severity = Severity.from_rank(severity.rank - 1)

        description = self._describe(dominant, normalised[dominant], used, agreement, contested)

        assessment = VisionAssessment(
            image_path=str(path),
            detections=reported + [d for d in detections if d.detector != "ensemble"][:6],
            dominant_class=dominant,
            severity_signal=severity,
            description=description,
            models_used=used,
            ensemble_agreement=round(agreement, 3),
        )

        # Attach the VLM's richer narrative when we have one — it is the most
        # human-useful artefact the vision stack produces.
        for detector in active:
            if isinstance(detector, VLMAnalyst) and detector.last_report:
                report = detector.last_report
                assessment.description = (
                    f"{report.scene_description.strip()} {description}"
                ).strip()
                if report.access_notes:
                    assessment.description += f" Access: {report.access_notes.strip()}"

        logger.info(
            "vision.assessed",
            image=path.name,
            dominant=dominant.value,
            confidence=round(normalised[dominant], 3),
            agreement=round(agreement, 3),
            models=used,
        )
        return assessment

    @staticmethod
    def _describe(
        dominant: DamageClass,
        confidence: float,
        used: list[str],
        agreement: float,
        contested: bool,
    ) -> str:
        label = dominant.value.replace("_", " ")
        base = f"Primary indicator: {label} (confidence {confidence:.2f})."

        if len(used) <= 1:
            return (
                f"{base} Single-model reading from '{used[0] if used else 'none'}' — "
                "no cross-model corroboration available."
            )
        if contested:
            return (
                f"{base} MODELS DISAGREE (agreement {agreement:.0%}) — "
                "flag for human verification before acting on this image."
            )
        return f"{base} Corroborated across {len(used)} models (agreement {agreement:.0%})."


_ensemble: VisionEnsemble | None = None


def get_vision_ensemble() -> VisionEnsemble:
    global _ensemble
    if _ensemble is None:
        _ensemble = VisionEnsemble()
    return _ensemble


async def analyze_images(paths: list[str]) -> list[VisionAssessment]:
    """Analyse a batch of incident images concurrently."""
    if not paths:
        return []
    ensemble = get_vision_ensemble()
    limit = asyncio.Semaphore(3)  # bound concurrent VLM calls

    async def bounded(path: str) -> VisionAssessment:
        async with limit:
            return await ensemble.analyze(path)

    results = await asyncio.gather(*(bounded(p) for p in paths), return_exceptions=True)
    assessments: list[VisionAssessment] = []
    for path, outcome in zip(paths, results):
        if isinstance(outcome, BaseException):
            logger.error("vision.batch_item_failed", path=path, error=str(outcome)[:200])
            continue
        assessments.append(outcome)
    return assessments
