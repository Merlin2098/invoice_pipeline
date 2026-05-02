import logging
import shutil
from pathlib import Path

from src.pipeline.ocr import ocr_extract

RAW_DIR = Path("data/raw")
BRONZE_DIR = Path("data/bronze")
ERRORS_DIR = Path("data/errors")

logger = logging.getLogger(__name__)


def move_to_errors(file_path: Path, errors_dir: Path = ERRORS_DIR) -> Path:
    errors_dir.mkdir(parents=True, exist_ok=True)
    target = errors_dir / file_path.name

    counter = 1
    while target.exists():
        target = errors_dir / f"{file_path.stem}_{counter}{file_path.suffix}"
        counter += 1

    return Path(shutil.move(str(file_path), str(target)))


def run_bronze_pipeline(raw_dir: Path = RAW_DIR, bronze_dir: Path = BRONZE_DIR) -> None:
    bronze_dir.mkdir(parents=True, exist_ok=True)

    for file_path in sorted(raw_dir.glob("*.tif")):
        try:
            text = ocr_extract(file_path)
        except Exception:
            logger.exception("OCR failed for %s", file_path)
            move_to_errors(file_path)
            continue

        output_path = bronze_dir / f"{file_path.stem}.txt"
        output_path.write_text(text, encoding="utf-8")
        logger.info("Wrote OCR text to %s", output_path)


def run_ocr_pipeline(raw_dir: Path = RAW_DIR, bronze_dir: Path = BRONZE_DIR) -> None:
    run_bronze_pipeline(raw_dir=raw_dir, bronze_dir=bronze_dir)
