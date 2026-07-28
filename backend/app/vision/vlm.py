"""Vision-language model analyst.

The CNN answers "which of the five classes I was trained on is this?". The VLM
answers "what is actually happening in this photograph?" — including scenes no
training set covered, and details that matter operationally (how deep is the
water relative to the vehicles, are people visible on rooftops, is the bridge
approach scoured).

Structured output is mandatory here. A free-text scene description cannot be
reconciled with the CNN's probabilities; a typed one can.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from app.core.config import settings
from app.core.exceptions import LLMUnavailableError
from app.core.llm import ModelTier, get_llm_engine
from app.core.logging import get_logger
from app.schemas.common import Confidence, SentinelModel
from app.schemas.enums import DamageClass
from app.schemas.intelligence import DamageDetection
from app.vision.base import VisionDetector

logger = get_logger(__name__)

SYSTEM_PROMPT = """\
You are an aerial and ground imagery analyst embedded in a disaster Emergency \
Operations Centre. You examine photographs from incident sites and report what \
is visibly present.

Rules you must follow:
- Report ONLY what is visible. Never infer damage you cannot see.
- If the image is unclear, low quality, or does not show a disaster scene, say \
so and return an empty observation list rather than guessing.
- Water depth, structural safety and casualty counts cannot be reliably \
determined from imagery. You may describe visual indicators, but you must not \
state these as determined facts.
- Your output informs evacuation and rescue decisions. Overstating damage \
wastes scarce resources; understating it costs lives. Report precisely and \
give calibrated confidence.
"""


class VisualObservation(SentinelModel):
    damage_class: DamageClass
    confidence: Confidence
    evidence: str = Field(description="The specific visual detail supporting this")


class VLMSceneReport(SentinelModel):
    """Structured output contract for image analysis."""

    is_disaster_scene: bool = Field(description="False for unclear or irrelevant images")
    scene_description: str = Field(description="2-3 sentences describing what is visible")
    observations: list[VisualObservation] = Field(default_factory=list)
    people_visible: bool = False
    people_count_estimate: int | None = Field(
        default=None, description="Only when individuals are individually countable"
    )
    access_notes: str = Field(
        default="", description="Anything visible about road/route usability"
    )
    image_quality: str = Field(default="adequate", description="good | adequate | poor")
    operational_notes: str = Field(
        default="", description="What a commander should notice in this image"
    )


class VLMAnalyst(VisionDetector):
    name = "vlm"

    def __init__(self) -> None:
        self._engine = get_llm_engine()
        self._last_report: VLMSceneReport | None = None

    @property
    def available(self) -> bool:
        return self._engine.available and settings.vision_use_vlm_ensemble

    @property
    def last_report(self) -> VLMSceneReport | None:
        return self._last_report

    async def analyze(self, image_path: Path) -> list[DamageDetection]:
        self._last_report = None
        if not self.available:
            return []

        try:
            report = await self._engine.structured(
                VLMSceneReport,
                system=SYSTEM_PROMPT,
                user=(
                    "Analyse this incident image. Identify every damage indicator "
                    "visible, note whether people are present, and describe anything "
                    "affecting access for emergency vehicles."
                ),
                images=[image_path],
                tier=ModelTier.FAST,
                agent="vision.vlm",
            )
        except LLMUnavailableError as exc:
            logger.info("vision.vlm.unavailable", error=str(exc)[:160])
            return []
        except Exception as exc:  # noqa: BLE001 - never break the pipeline
            logger.error("vision.vlm.failed", image=str(image_path), error=str(exc)[:200])
            return []

        self._last_report = report

        if not report.is_disaster_scene:
            logger.info("vision.vlm.not_disaster_scene", image=image_path.name)
            return []

        detections = [
            DamageDetection(
                damage_class=observation.damage_class,
                confidence=observation.confidence,
                detector="vlm",
                note=observation.evidence[:200],
            )
            for observation in report.observations
        ]

        # People visible is an operational signal in its own right — it changes
        # the incident from property damage to life safety.
        if report.people_visible and not any(
            d.damage_class is DamageClass.STRANDED_PEOPLE for d in detections
        ):
            detections.append(
                DamageDetection(
                    damage_class=DamageClass.STRANDED_PEOPLE,
                    confidence=0.6,
                    detector="vlm",
                    note=(
                        f"People visible in frame"
                        + (
                            f" (~{report.people_count_estimate})"
                            if report.people_count_estimate
                            else ""
                        )
                    ),
                )
            )

        return detections
