import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from src.pipeline.llm_ollama import extract_structured_data, validate_ollama_model
from src.pipeline.postprocess import map_to_contract
from src.utils.logging import configure_logging

BRONZE_DIR = Path("data/bronze")
SILVER_DIR = Path("data/silver")
SILVER_ERRORS_DIR = Path("data/errors/silver")
MAX_RETRIES = 1
BLOCKING_FLAGS = {"invalid_json_response", "empty_llm_response", "ollama_request_failed"}

logger = logging.getLogger(__name__)


def ensure_quality_flags(record: dict[str, Any]) -> list[str]:
    flags = record.get("ocr_confidence_flags")
    if flags is None:
        flags = []
    elif isinstance(flags, str):
        flags = [flags]
    elif not isinstance(flags, list):
        flags = ["invalid_ocr_confidence_flags"]
    record["ocr_confidence_flags"] = flags
    return flags


def apply_contract_defaults(record: dict[str, Any]) -> dict[str, Any]:
    ensure_quality_flags(record)
    return record


def load_bronze_text(bronze_dir: Path = BRONZE_DIR) -> list[dict[str, str]]:
    records = []
    for path in sorted(bronze_dir.glob("*.md")):
        records.append(
            {
                "source_file": path.name,
                "raw_text_path": path.as_posix(),
                "text": path.read_text(encoding="utf-8"),
            }
        )
    return records


def process_with_llm(text: str, max_retries: int = MAX_RETRIES) -> dict[str, Any]:
    last_record: dict[str, Any] = {}

    for attempt in range(max_retries + 1):
        record = extract_structured_data(text)
        flags = set(ensure_quality_flags(record))
        last_record = record
        if flags.isdisjoint(BLOCKING_FLAGS):
            return record
        logger.warning("LLM extraction attempt %s failed with flags: %s", attempt + 1, sorted(flags))

    return last_record


def write_silver_output(record: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")


def safe_output_stem(document_id: Any) -> str:
    stem = str(document_id or "").strip()
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem)
    return stem.strip("._") or "unknown_document"


def has_blocking_flags(record: dict[str, Any]) -> bool:
    return not set(ensure_quality_flags(record)).isdisjoint(BLOCKING_FLAGS)


def run_silver_pipeline(
    bronze_dir: Path = BRONZE_DIR,
    silver_dir: Path = SILVER_DIR,
    errors_dir: Path = SILVER_ERRORS_DIR,
    max_retries: int = MAX_RETRIES,
    validate_model: bool = True,
) -> None:
    silver_dir.mkdir(parents=True, exist_ok=True)
    errors_dir.mkdir(parents=True, exist_ok=True)
    if validate_model:
        validate_ollama_model()

    for bronze_record in load_bronze_text(bronze_dir):
        start = time.perf_counter()
        source_file = bronze_record["source_file"]
        logger.info(
            "Starting LLM extraction source_file=%s text_chars=%s",
            source_file,
            len(bronze_record["text"]),
        )
        record = process_with_llm(bronze_record["text"], max_retries=max_retries)
        flags = ensure_quality_flags(record)

        record["source_file"] = source_file
        record["raw_text_path"] = bronze_record["raw_text_path"]
        if not record.get("document_id"):
            record["document_id"] = Path(source_file).stem
            flags.append("inferred_document_id")

        if not has_blocking_flags(record):
            record = map_to_contract(
                record,
                source_file=source_file,
                raw_text_path=bronze_record["raw_text_path"],
                text=bronze_record["text"],
            )
        else:
            apply_contract_defaults(record)

        output_dir = errors_dir if has_blocking_flags(record) else silver_dir
        output_path = output_dir / f"{safe_output_stem(record['document_id'])}.json"
        write_silver_output(record, output_path)
        elapsed = time.perf_counter() - start
        if output_dir == errors_dir:
            logger.warning("Wrote failed silver extraction to %s elapsed_seconds=%.2f", output_path, elapsed)
        else:
            logger.info("Wrote silver JSON to %s elapsed_seconds=%.2f", output_path, elapsed)


if __name__ == "__main__":
    configure_logging("silver.log")
    run_silver_pipeline()
