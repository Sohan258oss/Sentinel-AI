"""Computer vision subsystem.

Public surface is intentionally small: callers analyse images and receive
:class:`VisionAssessment` objects. Which models were available, how they were
weighted and how they were reconciled is an internal concern.
"""

from __future__ import annotations

from app.vision.base import DAMAGE_SEVERITY, VisionDetector
from app.vision.classifier import DamageClassifier
from app.vision.ensemble import VisionEnsemble, analyze_images, get_vision_ensemble
from app.vision.vlm import VLMAnalyst, VLMSceneReport

__all__ = [
    "DAMAGE_SEVERITY",
    "DamageClassifier",
    "VLMAnalyst",
    "VLMSceneReport",
    "VisionDetector",
    "VisionEnsemble",
    "analyze_images",
    "get_vision_ensemble",
]
