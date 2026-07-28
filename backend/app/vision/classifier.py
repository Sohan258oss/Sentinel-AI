"""Fine-tuned damage classification CNN.

Transfer learning on an ImageNet-pretrained backbone. The head is retrained on
disaster imagery; the backbone is partially frozen. This is the component that
makes SentinelAI's deep-learning claim concrete rather than "we called a
multimodal API".

Design notes:

* The label set is stored **inside the checkpoint**. A model whose class order
  is defined by a constant in a separate file will eventually be loaded against
  a mismatched constant and silently produce confidently wrong labels — a
  genuinely dangerous failure in a damage-assessment system.
* Inference runs in a thread so the async event loop is never blocked.
* If no checkpoint exists the classifier reports itself unavailable rather than
  returning ImageNet predictions dressed up as damage classes.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.enums import DamageClass
from app.schemas.intelligence import DamageDetection
from app.vision.base import VisionDetector

logger = get_logger(__name__)

#: Input resolution the model was trained at.
IMAGE_SIZE = 224

#: ImageNet normalisation — matches the pretrained backbone's expectations.
NORM_MEAN = (0.485, 0.456, 0.406)
NORM_STD = (0.229, 0.224, 0.225)

#: Maps dataset folder names to the platform's damage vocabulary. Public
#: aerial disaster datasets use their own naming; this is the adapter.
DATASET_LABEL_MAP: dict[str, DamageClass] = {
    "normal": DamageClass.NO_DAMAGE,
    "no_damage": DamageClass.NO_DAMAGE,
    "fire": DamageClass.FIRE,
    "wildfire": DamageClass.FIRE,
    "smoke": DamageClass.SMOKE,
    "flood": DamageClass.FLOODED_AREA,
    "flooded": DamageClass.FLOODED_AREA,
    "flooded_areas": DamageClass.FLOODED_AREA,
    "collapsed_building": DamageClass.COLLAPSED_BUILDING,
    "collapsed_buildings": DamageClass.COLLAPSED_BUILDING,
    "destroyed": DamageClass.COLLAPSED_BUILDING,
    "damaged_building": DamageClass.DAMAGED_BUILDING,
    "damaged_infrastructure": DamageClass.DAMAGED_BUILDING,
    "traffic_incident": DamageClass.BLOCKED_ROAD,
    "blocked_road": DamageClass.BLOCKED_ROAD,
    "damaged_bridge": DamageClass.DAMAGED_BRIDGE,
}


def resolve_device(prefer: str | None = None) -> str:
    """Pick the best available compute device (CUDA > Apple MPS > CPU)."""
    import torch

    if prefer and prefer != "auto":
        return prefer
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def build_model(num_classes: int, *, pretrained: bool = True) -> Any:
    """EfficientNet-B0 backbone with a fresh classification head.

    B0 is chosen over a heavier backbone deliberately: aerial damage
    classification is texture-driven rather than fine-grained, the accuracy
    gap to larger models is small, and inference must stay fast enough to run
    per-image inside a live incident graph.
    """
    import torch.nn as nn
    from torchvision import models

    weights = models.EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None
    model = models.efficientnet_b0(weights=weights)

    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(
        nn.Dropout(p=0.3, inplace=True),
        nn.Linear(in_features, num_classes),
    )
    return model


def build_transforms(train: bool) -> Any:
    """Preprocessing pipeline. Augmentation is applied only during training."""
    from torchvision import transforms

    if train:
        # Aerial imagery has no canonical orientation, so vertical flips and
        # full rotations are legitimate augmentations here (they would not be
        # for ground-level photography).
        return transforms.Compose(
            [
                transforms.RandomResizedCrop(IMAGE_SIZE, scale=(0.7, 1.0)),
                transforms.RandomHorizontalFlip(),
                transforms.RandomVerticalFlip(),
                transforms.RandomRotation(30),
                transforms.ColorJitter(brightness=0.25, contrast=0.25, saturation=0.2),
                transforms.ToTensor(),
                transforms.Normalize(NORM_MEAN, NORM_STD),
            ]
        )

    return transforms.Compose(
        [
            transforms.Resize(int(IMAGE_SIZE * 1.14)),
            transforms.CenterCrop(IMAGE_SIZE),
            transforms.ToTensor(),
            transforms.Normalize(NORM_MEAN, NORM_STD),
        ]
    )


class DamageClassifier(VisionDetector):
    """Loads a fine-tuned checkpoint and classifies disaster imagery."""

    name = "cnn"

    def __init__(self, weights_path: Path | None = None) -> None:
        self.weights_path = weights_path or settings.vision_weights_path
        self._model: Any = None
        self._labels: list[DamageClass] = []
        self._transform: Any = None
        self._device: str = "cpu"
        self._metadata: dict[str, Any] = {}
        self._load_failed = False
        self._lock = threading.Lock()

    # -- Loading -------------------------------------------------------------

    def _ensure_loaded(self) -> bool:
        if self._model is not None:
            return True
        if self._load_failed:
            return False

        with self._lock:
            if self._model is not None:
                return True
            if self._load_failed:
                return False

            if not self.weights_path.exists():
                logger.info(
                    "vision.cnn.no_checkpoint",
                    path=str(self.weights_path),
                    detail="train with: python -m ml.train_damage_classifier",
                )
                self._load_failed = True
                return False

            try:
                import torch

                checkpoint = torch.load(
                    self.weights_path, map_location="cpu", weights_only=False
                )
                label_names: list[str] = checkpoint["labels"]
                self._labels = [DamageClass(name) for name in label_names]
                self._metadata = checkpoint.get("metadata", {})

                self._device = resolve_device()
                model = build_model(len(self._labels), pretrained=False)
                model.load_state_dict(checkpoint["state_dict"])
                model.eval()
                model.to(self._device)

                self._model = model
                self._transform = build_transforms(train=False)

                logger.info(
                    "vision.cnn.loaded",
                    device=self._device,
                    classes=len(self._labels),
                    val_accuracy=self._metadata.get("val_accuracy"),
                    epochs=self._metadata.get("epochs"),
                )
                return True
            except Exception as exc:  # noqa: BLE001 - degrade, never crash
                logger.error("vision.cnn.load_failed", error=str(exc)[:300])
                self._load_failed = True
                return False

    @property
    def available(self) -> bool:
        return self._ensure_loaded()

    @property
    def metadata(self) -> dict[str, Any]:
        self._ensure_loaded()
        return dict(self._metadata)

    # -- Inference -----------------------------------------------------------

    def _predict_sync(self, image_path: Path) -> list[DamageDetection]:
        import torch
        from PIL import Image

        with Image.open(image_path) as raw:
            image = raw.convert("RGB")
            tensor = self._transform(image).unsqueeze(0).to(self._device)

        with torch.no_grad():
            logits = self._model(tensor)
            probabilities = torch.softmax(logits, dim=1)[0]

        # Report every class above a floor, not just argmax: a scene showing
        # both flooding and a collapsed structure is common, and the commander
        # needs both signals.
        detections: list[DamageDetection] = []
        for index, probability in enumerate(probabilities.tolist()):
            if probability < 0.10:
                continue
            detections.append(
                DamageDetection(
                    damage_class=self._labels[index],
                    confidence=round(float(probability), 4),
                    detector="cnn",
                    note=f"EfficientNet-B0 fine-tuned ({self._device})",
                )
            )

        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections[:4]

    async def analyze(self, image_path: Path) -> list[DamageDetection]:
        if not self._ensure_loaded():
            return []
        try:
            # Torch inference is blocking and CPU-bound; keep it off the loop.
            return await asyncio.to_thread(self._predict_sync, image_path)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "vision.cnn.inference_failed", image=str(image_path), error=str(exc)[:200]
            )
            return []
