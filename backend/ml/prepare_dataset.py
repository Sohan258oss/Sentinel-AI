"""Acquire and normalise the disaster-imagery training set.

Default source: **AIDER** (Aerial Image Dataset for Emergency Response
Applications), Kyrkou & Theocharides, hosted on Zenodo under CC-BY-4.0.

    https://doi.org/10.5281/zenodo.3888300
    https://github.com/ckyrkou/AIDER

The licence permits redistribution and reuse with attribution; an ATTRIBUTION
file is written alongside the extracted data so the credit travels with it.

Usage::

    python -m ml.prepare_dataset                 # download + extract + normalise
    python -m ml.prepare_dataset --verify-only   # just report what is on disk
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.vision.classifier import DATASET_LABEL_MAP  # noqa: E402

logger = get_logger(__name__)

DATASET_URL = "https://zenodo.org/records/3888300/files/AIDER.zip?download=1"
DATASET_MD5 = "1ad4eb02ed156e8dfa19986ff382e58b"
DATASETS_DIR = BACKEND_ROOT / "ml" / "datasets"
ARCHIVE_PATH = DATASETS_DIR / "AIDER.zip"
TARGET_DIR = DATASETS_DIR / "aider"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}

ATTRIBUTION = """\
AIDER — Aerial Image Dataset for Emergency Response Applications
================================================================

Source : https://doi.org/10.5281/zenodo.3888300
Repo   : https://github.com/ckyrkou/AIDER
Licence: Creative Commons Attribution 4.0 International (CC-BY-4.0)

Cite:
  C. Kyrkou and T. Theocharides, "Deep-Learning-Based Aerial Image
  Classification for Emergency Response Applications Using Unmanned Aerial
  Vehicles", CVPR Workshops, 2019.

This dataset is used in SentinelAI solely to train the damage-classification
model. It is redistributed here under the terms of CC-BY-4.0 with attribution
preserved. No modification of the source imagery has been made beyond
reorganising directory names to match the platform's damage vocabulary.
"""


def _md5(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.md5()  # noqa: S324 - integrity check only, not security
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def download(force: bool = False) -> Path:
    import httpx

    DATASETS_DIR.mkdir(parents=True, exist_ok=True)

    if ARCHIVE_PATH.exists() and not force:
        logger.info("dataset.archive_present", path=str(ARCHIVE_PATH))
        if _md5(ARCHIVE_PATH) == DATASET_MD5:
            logger.info("dataset.checksum_ok")
            return ARCHIVE_PATH
        logger.warning("dataset.checksum_mismatch", detail="re-downloading")

    logger.info("dataset.download_start", url=DATASET_URL)
    with httpx.stream("GET", DATASET_URL, follow_redirects=True, timeout=120.0) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        written = 0
        last_report = 0

        with ARCHIVE_PATH.open("wb") as handle:
            for chunk in response.iter_bytes(chunk_size=1 << 20):
                handle.write(chunk)
                written += len(chunk)
                if total and written - last_report > (20 << 20):
                    last_report = written
                    logger.info(
                        "dataset.download_progress",
                        pct=round(100 * written / total, 1),
                        mb=round(written / (1 << 20), 1),
                    )

    logger.info("dataset.download_complete", mb=round(ARCHIVE_PATH.stat().st_size / (1 << 20), 1))

    actual = _md5(ARCHIVE_PATH)
    if actual != DATASET_MD5:
        raise SystemExit(f"Checksum mismatch: expected {DATASET_MD5}, got {actual}")
    logger.info("dataset.checksum_ok")
    return ARCHIVE_PATH


def _normalise(name: str) -> str | None:
    """Map an arbitrary source folder name onto a known dataset class."""
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    if key in DATASET_LABEL_MAP:
        return key
    for known in DATASET_LABEL_MAP:
        if known in key or key in known:
            return known
    return None


def extract_and_normalise(archive: Path, force: bool = False) -> Path:
    if TARGET_DIR.exists() and not force:
        logger.info("dataset.already_extracted", path=str(TARGET_DIR))
        return TARGET_DIR

    staging = DATASETS_DIR / "_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    logger.info("dataset.extracting")
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(staging)

    # Find every directory that directly contains images — the archive's nesting
    # depth is not guaranteed, so discover it rather than assume it.
    class_dirs: dict[str, list[Path]] = {}
    for path in staging.rglob("*"):
        if not path.is_dir():
            continue
        images = [p for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES]
        if not images:
            continue
        normalised = _normalise(path.name)
        if normalised is None:
            logger.warning("dataset.unmapped_folder", folder=path.name, images=len(images))
            continue
        class_dirs.setdefault(normalised, []).extend(images)

    if not class_dirs:
        raise SystemExit("No recognisable class folders found in archive")

    if TARGET_DIR.exists():
        shutil.rmtree(TARGET_DIR)
    TARGET_DIR.mkdir(parents=True)

    counts: Counter[str] = Counter()
    for class_name, images in class_dirs.items():
        destination = TARGET_DIR / class_name
        destination.mkdir(parents=True, exist_ok=True)
        for index, image in enumerate(images):
            shutil.copy2(image, destination / f"{class_name}_{index:05d}{image.suffix.lower()}")
            counts[class_name] += 1

    (TARGET_DIR / "ATTRIBUTION.txt").write_text(ATTRIBUTION, encoding="utf-8")
    shutil.rmtree(staging, ignore_errors=True)

    logger.info("dataset.ready", path=str(TARGET_DIR), counts=dict(counts))
    return TARGET_DIR


def verify() -> bool:
    if not TARGET_DIR.exists():
        print(f"Dataset not present at {TARGET_DIR}")
        return False

    print(f"\nDataset: {TARGET_DIR}")
    print("-" * 60)
    total = 0
    for folder in sorted(p for p in TARGET_DIR.iterdir() if p.is_dir()):
        images = [p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES]
        mapped = DATASET_LABEL_MAP.get(folder.name)
        print(f"  {folder.name:<22} {len(images):>6} images  ->  {mapped.value if mapped else 'UNMAPPED'}")
        total += len(images)
    print("-" * 60)
    print(f"  {'TOTAL':<22} {total:>6} images\n")
    return total > 0


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Prepare SentinelAI vision dataset")
    parser.add_argument("--force", action="store_true", help="re-download and re-extract")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    if args.verify_only:
        return 0 if verify() else 1

    archive = download(force=args.force)
    extract_and_normalise(archive, force=args.force)
    return 0 if verify() else 1


if __name__ == "__main__":
    raise SystemExit(main())
