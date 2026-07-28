"""Fine-tune the SentinelAI disaster damage classifier.

Usage::

    python -m ml.train_damage_classifier --data-dir ml/datasets/aider --epochs 8

Expects an ImageFolder layout::

    <data-dir>/
        fire/            *.jpg
        flooded_areas/   *.jpg
        collapsed_building/
        traffic_incident/
        normal/

Folder names are mapped onto the platform's ``DamageClass`` vocabulary by
``DATASET_LABEL_MAP`` so the checkpoint speaks the product's language, not the
dataset's.

Training decisions worth stating:

* **Two-phase schedule.** Phase 1 trains only the new head with the backbone
  frozen, so large random-head gradients cannot wreck pretrained features.
  Phase 2 unfreezes the last backbone block at a 10x lower learning rate.
  On datasets of a few thousand images this reliably beats end-to-end
  fine-tuning from the start.
* **Class-weighted loss.** Public disaster datasets are heavily imbalanced —
  "normal" typically outnumbers every damage class. Unweighted training
  produces a model that scores well on accuracy while being useless at the
  only thing that matters: recognising damage.
* **Selection on macro-F1, not accuracy.** Same reason.
* **Labels stored in the checkpoint**, so inference can never desynchronise.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _ensure_ssl_certificates() -> None:
    """Point OpenSSL at certifi's CA bundle.

    python.org macOS builds ship without a system CA bundle wired up, so
    torchvision's pretrained-weight download fails with CERTIFICATE_VERIFY_FAILED.
    certifi is already present as a transitive dependency; using it here removes
    a setup step that would otherwise block every fresh clone on macOS.
    """
    if os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi

        os.environ["SSL_CERT_FILE"] = certifi.where()
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except ImportError:  # pragma: no cover - certifi is a hard transitive dep
        pass


_ensure_ssl_certificates()

from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.schemas.enums import DamageClass  # noqa: E402
from app.vision.classifier import (  # noqa: E402
    DATASET_LABEL_MAP,
    build_model,
    build_transforms,
    resolve_device,
)

logger = get_logger(__name__)


def discover_classes(data_dir: Path) -> tuple[list[str], list[DamageClass]]:
    """Map dataset folders onto the platform damage vocabulary."""
    folders = sorted(p.name for p in data_dir.iterdir() if p.is_dir())
    if not folders:
        raise SystemExit(f"No class folders found in {data_dir}")

    unmapped = [f for f in folders if f.lower() not in DATASET_LABEL_MAP]
    if unmapped:
        raise SystemExit(
            f"Unmapped dataset folders: {unmapped}. "
            f"Add them to DATASET_LABEL_MAP in app/vision/classifier.py."
        )

    labels = [DATASET_LABEL_MAP[f.lower()] for f in folders]
    return folders, labels


def build_loaders(
    data_dir: Path, batch_size: int, val_split: float, workers: int
) -> tuple[Any, Any, list[str], list[int]]:
    import torch
    from torch.utils.data import DataLoader, random_split
    from torchvision.datasets import ImageFolder

    train_ds_full = ImageFolder(str(data_dir), transform=build_transforms(train=True))
    val_ds_full = ImageFolder(str(data_dir), transform=build_transforms(train=False))

    total = len(train_ds_full)
    val_size = max(1, int(total * val_split))
    train_size = total - val_size

    generator = torch.Generator().manual_seed(1337)  # reproducible split
    train_indices, val_indices = random_split(
        range(total), [train_size, val_size], generator=generator
    )

    from torch.utils.data import Subset

    train_ds = Subset(train_ds_full, list(train_indices))
    val_ds = Subset(val_ds_full, list(val_indices))

    counts = Counter(train_ds_full.targets[i] for i in train_indices)
    per_class = [counts.get(i, 0) for i in range(len(train_ds_full.classes))]

    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True, num_workers=workers, pin_memory=False
    )
    val_loader = DataLoader(
        val_ds, batch_size=batch_size, shuffle=False, num_workers=workers, pin_memory=False
    )
    return train_loader, val_loader, train_ds_full.classes, per_class


def macro_f1(confusion: list[list[int]]) -> float:
    """Unweighted mean F1 across classes."""
    scores: list[float] = []
    for index in range(len(confusion)):
        tp = confusion[index][index]
        fp = sum(confusion[r][index] for r in range(len(confusion))) - tp
        fn = sum(confusion[index]) - tp
        if tp == 0:
            scores.append(0.0)
            continue
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return sum(scores) / len(scores) if scores else 0.0


def evaluate(model: Any, loader: Any, device: str, num_classes: int) -> tuple[float, float, list[list[int]]]:
    import torch

    model.eval()
    confusion = [[0] * num_classes for _ in range(num_classes)]
    correct = 0
    total = 0

    with torch.no_grad():
        for images, targets in loader:
            images, targets = images.to(device), targets.to(device)
            predictions = model(images).argmax(dim=1)
            for actual, predicted in zip(targets.tolist(), predictions.tolist()):
                confusion[actual][predicted] += 1
            correct += (predictions == targets).sum().item()
            total += targets.size(0)

    accuracy = correct / total if total else 0.0
    return accuracy, macro_f1(confusion), confusion


def train(args: argparse.Namespace) -> int:
    import torch
    import torch.nn as nn

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        raise SystemExit(
            f"Dataset not found at {data_dir}. Run: python -m ml.prepare_dataset"
        )

    folders, damage_labels = discover_classes(data_dir)
    device = resolve_device(args.device)
    logger.info("train.start", device=device, classes=folders, epochs=args.epochs)

    train_loader, val_loader, class_names, per_class_counts = build_loaders(
        data_dir, args.batch_size, args.val_split, args.workers
    )
    num_classes = len(class_names)
    logger.info(
        "train.dataset",
        train_batches=len(train_loader),
        val_batches=len(val_loader),
        per_class=dict(zip(class_names, per_class_counts)),
    )

    model = build_model(num_classes, pretrained=True).to(device)

    # Inverse-frequency class weights, normalised to mean 1.
    total_samples = sum(per_class_counts) or 1
    raw_weights = [
        total_samples / (num_classes * count) if count else 1.0 for count in per_class_counts
    ]
    mean_weight = sum(raw_weights) / len(raw_weights)
    weights = torch.tensor([w / mean_weight for w in raw_weights], dtype=torch.float, device=device)
    logger.info("train.class_weights", weights=[round(w, 3) for w in weights.tolist()])

    criterion = nn.CrossEntropyLoss(weight=weights, label_smoothing=0.05)

    def set_backbone_trainable(trainable: bool) -> None:
        for name, param in model.named_parameters():
            if name.startswith("classifier"):
                param.requires_grad = True
            elif trainable and (".7." in name or ".8." in name):
                # Only the final blocks unfreeze — earlier layers hold generic
                # features that a few thousand images cannot improve on.
                param.requires_grad = True
            else:
                param.requires_grad = trainable and False

    set_backbone_trainable(False)

    head_epochs = max(1, args.epochs // 3)
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=args.lr, weight_decay=1e-4
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    best_f1 = -1.0
    best_state: dict[str, Any] | None = None
    best_metrics: dict[str, Any] = {}
    history: list[dict[str, Any]] = []
    started = time.time()

    for epoch in range(1, args.epochs + 1):
        if epoch == head_epochs + 1:
            logger.info("train.phase2", detail="unfreezing final backbone blocks")
            set_backbone_trainable(True)
            optimizer = torch.optim.AdamW(
                [p for p in model.parameters() if p.requires_grad],
                lr=args.lr / 10,
                weight_decay=1e-4,
            )
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                optimizer, T_max=max(1, args.epochs - head_epochs)
            )

        model.train()
        running_loss = 0.0
        seen = 0

        for batch_index, (images, targets) in enumerate(train_loader, start=1):
            images, targets = images.to(device), targets.to(device)
            optimizer.zero_grad()
            loss = criterion(model(images), targets)
            loss.backward()
            optimizer.step()

            running_loss += loss.item() * targets.size(0)
            seen += targets.size(0)

            if batch_index % 20 == 0:
                logger.info(
                    "train.progress",
                    epoch=epoch,
                    batch=f"{batch_index}/{len(train_loader)}",
                    loss=round(running_loss / max(seen, 1), 4),
                )

        scheduler.step()
        accuracy, f1, confusion = evaluate(model, val_loader, device, num_classes)
        epoch_record = {
            "epoch": epoch,
            "train_loss": round(running_loss / max(seen, 1), 4),
            "val_accuracy": round(accuracy, 4),
            "val_macro_f1": round(f1, 4),
        }
        history.append(epoch_record)
        logger.info("train.epoch_complete", **epoch_record)

        if f1 > best_f1:
            best_f1 = f1
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            best_metrics = {
                "val_accuracy": round(accuracy, 4),
                "val_macro_f1": round(f1, 4),
                "confusion_matrix": confusion,
                "best_epoch": epoch,
            }
            logger.info("train.new_best", macro_f1=round(f1, 4), accuracy=round(accuracy, 4))

    if best_state is None:
        raise SystemExit("Training produced no checkpoint")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    torch.save(
        {
            "state_dict": best_state,
            # Platform vocabulary, aligned to the folder order used in training.
            "labels": [d.value for d in damage_labels],
            "dataset_classes": class_names,
            "metadata": {
                **best_metrics,
                "architecture": "efficientnet_b0",
                "epochs": args.epochs,
                "device": device,
                "train_samples": sum(per_class_counts),
                "per_class_counts": dict(zip(class_names, per_class_counts)),
                "training_seconds": round(time.time() - started, 1),
                "history": history,
            },
        },
        output_path,
    )

    logger.info(
        "train.saved",
        path=str(output_path),
        macro_f1=best_metrics["val_macro_f1"],
        accuracy=best_metrics["val_accuracy"],
    )

    report_path = output_path.with_suffix(".report.json")
    report_path.write_text(
        json.dumps(
            {
                "labels": [d.value for d in damage_labels],
                "dataset_classes": class_names,
                **best_metrics,
                "history": history,
            },
            indent=2,
        )
    )
    print(f"\nBest macro-F1: {best_metrics['val_macro_f1']}  accuracy: {best_metrics['val_accuracy']}")
    print(f"Checkpoint: {output_path}\nReport: {report_path}\n")
    return 0


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Train SentinelAI damage classifier")
    parser.add_argument("--data-dir", default=str(BACKEND_ROOT / "ml" / "datasets" / "aider"))
    parser.add_argument("--output", default=str(BACKEND_ROOT / "ml" / "artifacts" / "sentinel_cnn.pt"))
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--val-split", type=float, default=0.2)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--device", default="auto")
    return train(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
