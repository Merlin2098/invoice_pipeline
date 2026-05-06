import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from src.config.pipeline_config import config_path, load_pipeline_config
from src.pipeline.llm_ollama import extract_structured_data, validate_ollama_model
from src.pipeline.quality import build_local_silver_document, create_failed_document

_CONFIG = load_pipeline_config()
BRONZE_DIR = config_path(_CONFIG, "bronze_dir")
SILVER_DIR = config_path(_CONFIG, "silver_dir")
SILVER_VALID_DIR = config_path(_CONFIG, "silver_valid_dir")
SILVER_REJECTED_DIR = config_path(_CONFIG, "silver_rejected_dir")
SILVER_FAILED_DIR = config_path(_CONFIG, "silver_failed_dir")
MAX_RETRIES = int(_CONFIG["llm"]["retries"])
BLOCKING_FLAGS = {
    "invalid_json_response",
    "empty_llm_response",
    "ollama_request_failed",
}

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


def load_bronze_text(
    bronze_dir: Path = BRONZE_DIR, limit: int | None = None
) -> list[dict[str, str]]:
    records = []
    for path in sorted(bronze_dir.glob("*.md")):
        records.append(
            {
                "source_file": path.name,
                "raw_text_path": path.as_posix(),
                "text": path.read_text(encoding="utf-8"),
            }
        )
        if limit is not None and len(records) >= limit:
            break
    return records


def process_with_llm(text: str, max_retries: int = MAX_RETRIES) -> dict[str, Any]:
    last_record: dict[str, Any] = {}

    for attempt in range(max_retries + 1):
        record = extract_structured_data(text)
        flags = set(ensure_quality_flags(record))
        last_record = record
        if flags.isdisjoint(BLOCKING_FLAGS):
            return record
        logger.warning(
            "LLM extraction attempt %s failed with flags: %s",
            attempt + 1,
            sorted(flags),
        )

    return last_record


def write_silver_output(record: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(record, indent=2, sort_keys=True), encoding="utf-8"
    )


def safe_output_stem(document_id: Any) -> str:
    stem = str(document_id or "").strip()
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem)
    return stem.strip("._") or "unknown_document"


def has_blocking_flags(record: dict[str, Any]) -> bool:
    return not set(ensure_quality_flags(record)).isdisjoint(BLOCKING_FLAGS)


def parse_source_metadata(markdown_text: str, default_name: str) -> tuple[str, str]:
    file_match = re.search(r"- Source file:\s*`([^`]+)`", markdown_text)
    path_match = re.search(r"- Source path:\s*`([^`]+)`", markdown_text)
    source_file_name = file_match.group(1) if file_match else default_name
    source_path = path_match.group(1) if path_match else default_name
    return source_file_name, source_path


def run_silver_pipeline(
    bronze_dir: Path = BRONZE_DIR,
    silver_dir: Path = SILVER_VALID_DIR,
    rejected_dir: Path = SILVER_REJECTED_DIR,
    failed_dir: Path = SILVER_FAILED_DIR,
    max_retries: int = MAX_RETRIES,
    validate_model: bool = True,
    limit: int | None = None,
    run_id: str | None = None,
    llm_model_id: str | None = None,
) -> dict[str, object]:
    pipeline_start = time.perf_counter()
    succeeded = 0
    rejected = 0
    failed = 0
    durations: list[float] = []
    silver_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)
    if validate_model:
        validate_ollama_model()

    bronze_records = load_bronze_text(bronze_dir, limit=limit)
    for bronze_record in bronze_records:
        start = time.perf_counter()
        source_file = bronze_record["source_file"]
        logger.info(
            "Starting LLM extraction source_file=%s text_chars=%s",
            source_file,
            len(bronze_record["text"]),
        )
        record = process_with_llm(bronze_record["text"], max_retries=max_retries)
        flags = ensure_quality_flags(record)

        source_file_name, source_path = parse_source_metadata(
            bronze_record["text"], default_name=f"{Path(source_file).stem}.tif"
        )
        document_id = Path(source_file).stem
        if has_blocking_flags(record):
            record = create_failed_document(
                run_id=run_id or "local-run",
                document_id=document_id,
                source_s3_key=Path(source_path).as_posix(),
                source_file_name=source_file_name,
                extraction_engine="local_tesseract",
                normalization_engine="local_ollama",
                llm_model_id=llm_model_id,
                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                raw_text_path=bronze_record["raw_text_path"],
            )
            output_dir = failed_dir
        else:
            record = build_local_silver_document(
                record,
                source_file_name=source_file_name,
                raw_text_path=bronze_record["raw_text_path"],
                source_s3_key=Path(source_path).as_posix(),
                raw_text=bronze_record["text"],
                run_id=run_id or "local-run",
                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                llm_model_id=llm_model_id,
            )
            if record["processing_status"] == "rejected":
                output_dir = rejected_dir
            else:
                output_dir = silver_dir

        output_path = output_dir / f"{safe_output_stem(document_id)}.json"
        write_silver_output(record, output_path)
        elapsed = time.perf_counter() - start
        durations.append(elapsed)
        if output_dir == failed_dir:
            failed += 1
            logger.warning(
                "run_id=%s wrote failed silver extraction to %s elapsed_seconds=%.2f",
                run_id,
                output_path,
                elapsed,
            )
        elif output_dir == rejected_dir:
            rejected += 1
            logger.warning(
                "run_id=%s wrote rejected silver document to %s elapsed_seconds=%.2f",
                run_id,
                output_path,
                elapsed,
            )
        else:
            succeeded += 1
            logger.info(
                "run_id=%s wrote silver JSON to %s elapsed_seconds=%.2f",
                run_id,
                output_path,
                elapsed,
            )

    total_elapsed = time.perf_counter() - pipeline_start
    total = len(bronze_records)
    success_rate = succeeded / total if total else 0
    avg_doc_seconds = sum(durations) / len(durations) if durations else 0
    min_doc_seconds = min(durations) if durations else 0
    max_doc_seconds = max(durations) if durations else 0
    docs_per_minute = succeeded / (total_elapsed / 60) if total_elapsed else 0
    metrics = {
        "total": total,
        "succeeded": succeeded,
        "rejected": rejected,
        "failed": failed,
        "success_rate": success_rate,
        "elapsed_seconds": total_elapsed,
        "avg_doc_seconds": avg_doc_seconds,
        "min_doc_seconds": min_doc_seconds,
        "max_doc_seconds": max_doc_seconds,
        "docs_per_minute": docs_per_minute,
        "durations": durations,
        "run_id": run_id,
    }
    logger.info(
        "run_id=%s SILVER_METRICS total=%s succeeded=%s rejected=%s failed=%s success_rate=%.2f elapsed_seconds=%.2f "
        "avg_doc_seconds=%.2f min_doc_seconds=%.2f max_doc_seconds=%.2f docs_per_minute=%.2f",
        run_id,
        total,
        succeeded,
        rejected,
        failed,
        success_rate,
        total_elapsed,
        avg_doc_seconds,
        min_doc_seconds,
        max_doc_seconds,
        docs_per_minute,
    )
    return metrics
