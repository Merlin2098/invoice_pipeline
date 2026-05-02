import json
import logging
import re
from pathlib import Path
from typing import Any

from src.pipeline.llm_ollama import contract_field_names, extract_structured_data
from src.utils.logging import configure_logging

BRONZE_DIR = Path("data/bronze")
SILVER_DIR = Path("data/silver")
MAX_RETRIES = 2

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
    for field in contract_field_names():
        if field == "ocr_confidence_flags":
            continue
        record.setdefault(field, None)
    ensure_quality_flags(record)
    return record


def load_bronze_text(bronze_dir: Path = BRONZE_DIR) -> list[dict[str, str]]:
    records = []
    for path in sorted(bronze_dir.glob("*.txt")):
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
    retry_flags = {"invalid_json_response", "empty_llm_response", "ollama_request_failed"}

    for attempt in range(max_retries + 1):
        record = extract_structured_data(text)
        flags = set(ensure_quality_flags(record))
        last_record = record
        if flags.isdisjoint(retry_flags):
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


def run_silver_pipeline(
    bronze_dir: Path = BRONZE_DIR,
    silver_dir: Path = SILVER_DIR,
    max_retries: int = MAX_RETRIES,
) -> None:
    silver_dir.mkdir(parents=True, exist_ok=True)

    for bronze_record in load_bronze_text(bronze_dir):
        source_file = bronze_record["source_file"]
        record = process_with_llm(bronze_record["text"], max_retries=max_retries)
        flags = ensure_quality_flags(record)

        record["source_file"] = source_file
        record["raw_text_path"] = bronze_record["raw_text_path"]
        if not record.get("document_id"):
            record["document_id"] = Path(source_file).stem
            flags.append("inferred_document_id")

        apply_contract_defaults(record)
        output_path = silver_dir / f"{safe_output_stem(record['document_id'])}.json"
        write_silver_output(record, output_path)
        logger.info("Wrote silver JSON to %s", output_path)


if __name__ == "__main__":
    configure_logging("silver.log")
    run_silver_pipeline()
