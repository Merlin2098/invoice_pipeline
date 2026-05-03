import logging
import shutil
import time
from pathlib import Path

from src.pipeline.ocr import ocr_extract
from src.utils.logging import configure_logging

RAW_DIR = Path("data/raw")
BRONZE_DIR = Path("data/bronze")
ERRORS_DIR = Path("data/errors")

logger = logging.getLogger(__name__)


def format_ocr_markdown(text: str, source_file: Path) -> str:
    return f"""# OCR Extract

- Source file: `{source_file.name}`
- Source path: `{source_file.as_posix()}`

## OCR Text

```text
{text}
```
"""


def move_to_errors(file_path: Path, errors_dir: Path = ERRORS_DIR) -> Path:
    errors_dir.mkdir(parents=True, exist_ok=True)
    target = errors_dir / file_path.name

    counter = 1
    while target.exists():
        target = errors_dir / f"{file_path.stem}_{counter}{file_path.suffix}"
        counter += 1

    return Path(shutil.move(str(file_path), str(target)))


def run_bronze_pipeline(raw_dir: Path = RAW_DIR, bronze_dir: Path = BRONZE_DIR) -> None:
    start = time.perf_counter()
    processed = 0
    failed = 0
    bronze_dir.mkdir(parents=True, exist_ok=True)

    for file_path in sorted(raw_dir.glob("*.tif")):
        try:
            text = ocr_extract(file_path)
        except Exception:
            logger.exception("OCR failed for %s", file_path)
            move_to_errors(file_path)
            failed += 1
            continue

        output_path = bronze_dir / f"{file_path.stem}.md"
        output_path.write_text(format_ocr_markdown(text, file_path), encoding="utf-8")
        processed += 1
        logger.info("Wrote OCR markdown to %s", output_path)

    elapsed = time.perf_counter() - start
    total = processed + failed
    rate = processed / elapsed if elapsed else 0
    success_rate = processed / total if total else 0
    logger.info(
        "BRONZE_METRICS total=%s succeeded=%s failed=%s success_rate=%.2f elapsed_seconds=%.2f docs_per_second=%.2f",
        total,
        processed,
        failed,
        success_rate,
        elapsed,
        rate,
    )


def run_ocr_pipeline(raw_dir: Path = RAW_DIR, bronze_dir: Path = BRONZE_DIR) -> None:
    run_bronze_pipeline(raw_dir=raw_dir, bronze_dir=bronze_dir)


if __name__ == "__main__":
    configure_logging("bronze.log")
    run_bronze_pipeline()
