import logging
import shutil
import time
from pathlib import Path

from src.config.pipeline_config import config_path, load_pipeline_config
from src.services.ocr_service import extract_text as ocr_extract
from src.services.ocr_service import format_ocr_markdown, supported_image_extensions
from src.utils.logging import configure_logging

_CONFIG = load_pipeline_config()
RAW_DIR = config_path(_CONFIG, "raw_dir")
BRONZE_DIR = config_path(_CONFIG, "bronze_dir")
ERRORS_DIR = config_path(_CONFIG, "errors_dir")

logger = logging.getLogger(__name__)


def move_to_errors(file_path: Path, errors_dir: Path = ERRORS_DIR) -> Path:
    errors_dir.mkdir(parents=True, exist_ok=True)
    target = errors_dir / file_path.name

    counter = 1
    while target.exists():
        target = errors_dir / f"{file_path.stem}_{counter}{file_path.suffix}"
        counter += 1

    return Path(shutil.move(str(file_path), str(target)))


def iter_raw_files(raw_dir: Path = RAW_DIR, limit: int | None = None) -> list[Path]:
    extensions = supported_image_extensions()
    files = sorted(
        path
        for path in raw_dir.iterdir()
        if path.is_file() and path.suffix.lower() in extensions
    )
    if limit is not None:
        return files[:limit]
    return files


def run_bronze_pipeline(
    raw_dir: Path = RAW_DIR, bronze_dir: Path = BRONZE_DIR, limit: int | None = None
) -> dict[str, object]:
    start = time.perf_counter()
    processed = 0
    failed = 0
    durations: list[float] = []
    bronze_dir.mkdir(parents=True, exist_ok=True)

    for file_path in iter_raw_files(raw_dir, limit=limit):
        doc_start = time.perf_counter()
        try:
            text = ocr_extract(file_path)
        except Exception:
            logger.exception("OCR failed for %s", file_path)
            move_to_errors(file_path)
            failed += 1
            durations.append(time.perf_counter() - doc_start)
            continue

        output_path = bronze_dir / f"{file_path.stem}.md"
        output_path.write_text(format_ocr_markdown(text, file_path), encoding="utf-8")
        processed += 1
        durations.append(time.perf_counter() - doc_start)
        logger.info("Wrote OCR markdown to %s", output_path)

    elapsed = time.perf_counter() - start
    total = processed + failed
    rate = processed / elapsed if elapsed else 0
    success_rate = processed / total if total else 0
    metrics = {
        "total": total,
        "succeeded": processed,
        "failed": failed,
        "success_rate": success_rate,
        "elapsed_seconds": elapsed,
        "docs_per_second": rate,
        "durations": durations,
    }
    logger.info(
        "BRONZE_METRICS total=%s succeeded=%s failed=%s success_rate=%.2f elapsed_seconds=%.2f docs_per_second=%.2f",
        total,
        processed,
        failed,
        success_rate,
        elapsed,
        rate,
    )
    return metrics


def run_ocr_pipeline(raw_dir: Path = RAW_DIR, bronze_dir: Path = BRONZE_DIR) -> None:
    run_bronze_pipeline(raw_dir=raw_dir, bronze_dir=bronze_dir)


if __name__ == "__main__":
    configure_logging("bronze.log")
    run_bronze_pipeline()
