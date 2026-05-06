import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from src.config.pipeline_config import config_path, load_pipeline_config
from src.pipeline.postprocess import normalize_amount, normalize_date

_CONFIG = load_pipeline_config()
SILVER_DIR = config_path(_CONFIG, "silver_valid_dir")
GOLD_DIR = config_path(_CONFIG, "gold_dir")

DOCUMENT_COLUMNS = (
    "run_id",
    "document_id",
    "source_s3_key",
    "source_file_name",
    "document_type",
    "document_date",
    "vendor_name",
    "total_amount",
    "currency",
    "extraction_engine",
    "normalization_engine",
    "llm_model_id",
    "processing_status",
    "quality_status",
    "quality_flags",
    "rejection_reason",
    "created_at",
)

logger = logging.getLogger(__name__)


def ensure_flags(record: dict[str, Any]) -> list[str]:
    flags = record.get("ocr_confidence_flags")
    if flags is None:
        flags = []
    elif isinstance(flags, str):
        flags = [flags]
    elif not isinstance(flags, list):
        flags = ["invalid_ocr_confidence_flags"]
    record["ocr_confidence_flags"] = flags
    return flags


def add_flag(record: dict[str, Any], flag: str) -> None:
    flags = ensure_flags(record)
    if flag not in flags:
        flags.append(flag)


def load_silver_json(silver_dir: Path = SILVER_DIR) -> list[dict[str, Any]]:
    records = []
    candidate_paths = sorted(silver_dir.glob("*.json"))
    if not candidate_paths:
        candidate_paths = sorted(config_path(_CONFIG, "silver_dir").glob("*.json"))

    for path in candidate_paths:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Invalid silver JSON skipped: %s", path)
            continue

        if not isinstance(record, dict):
            logger.warning("Non-object silver JSON skipped: %s", path)
            continue

        record.setdefault("run_id", "local-run")
        record.setdefault("document_id", path.stem)
        record.setdefault("source_s3_key", Path("data/raw", f"{path.stem}.tif").as_posix())
        record.setdefault("source_file_name", f"{path.stem}.tif")
        record.setdefault("quality_flags", record.get("ocr_confidence_flags") or [])
        record.setdefault("quality_status", "accepted")
        record.setdefault("processing_status", "accepted")
        record.setdefault("created_at", datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
        records.append(record)

    return records


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    original_date = record.get("document_date")
    normalized_date = normalize_date(original_date)
    if original_date not in (None, "") and normalized_date is None:
        add_flag(record, "invalid_document_date", key="quality_flags")
    record["document_date"] = normalized_date
    record["total_amount"] = normalize_amount(record.get("total_amount"))

    for field in ("document_id", "source_s3_key", "source_file_name", "document_type"):
        if not record.get(field):
            add_flag(record, f"missing_{field}", key="quality_flags")
            logger.warning(
                "Missing critical field %s in record %s",
                field,
                record.get("source_file_name"),
            )

    return record

def _pick(record: dict[str, Any], columns: tuple[str, ...]) -> dict[str, Any]:
    return {column: record.get(column) for column in columns}


def map_to_document(record: dict[str, Any]) -> dict[str, Any]:
    normalize_record(record)
    return _pick(record, DOCUMENT_COLUMNS)


def build_documents_table(records: list[dict[str, Any]]) -> pd.DataFrame:
    documents = [map_to_document(record) for record in records]
    return pd.DataFrame(documents, columns=DOCUMENT_COLUMNS)


def write_outputs(documents: pd.DataFrame, gold_dir: Path = GOLD_DIR) -> None:
    gold_dir.mkdir(parents=True, exist_ok=True)
    output_path = gold_dir / "documents.parquet"
    documents.to_parquet(output_path, index=False)
    logger.info("Wrote gold documents table to %s", output_path)
    if not documents.empty:
        run_date = str(documents["created_at"].iloc[0]).split("T", maxsplit=1)[0]
        partition_dir = gold_dir / f"run_date={run_date}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        documents.to_parquet(partition_dir / "documents.parquet", index=False)


def log_gold_metrics(documents: pd.DataFrame, elapsed: float) -> dict[str, Any]:
    total = len(documents)
    if total == 0:
        logger.info("GOLD_METRICS rows=0 elapsed_seconds=%.2f", elapsed)
        return {
            "rows": 0,
            "elapsed_seconds": elapsed,
            "amount_completion_rate": 0,
            "date_completion_rate": 0,
            "vendor_completion_rate": 0,
            "currency_completion_rate": 0,
            "unknown_document_type_rate": 0,
            "document_type_counts": {},
        }

    complete_amount = int(documents["total_amount"].notna().sum())
    complete_date = int(documents["document_date"].notna().sum())
    complete_vendor = int(documents["vendor_name"].notna().sum())
    complete_currency = int(documents["currency"].notna().sum())
    type_counts = documents["document_type"].value_counts(dropna=False).to_dict()
    unknown_rate = float(type_counts.get("unknown", 0)) / total
    metrics = {
        "rows": total,
        "elapsed_seconds": elapsed,
        "amount_completion_rate": complete_amount / total,
        "date_completion_rate": complete_date / total,
        "vendor_completion_rate": complete_vendor / total,
        "currency_completion_rate": complete_currency / total,
        "unknown_document_type_rate": unknown_rate,
        "document_type_counts": type_counts,
    }
    logger.info(
        "GOLD_METRICS rows=%s elapsed_seconds=%.2f amount_completion_rate=%.2f "
        "date_completion_rate=%.2f vendor_completion_rate=%.2f currency_completion_rate=%.2f "
        "unknown_document_type_rate=%.2f document_type_counts=%s",
        total,
        elapsed,
        complete_amount / total,
        complete_date / total,
        complete_vendor / total,
        complete_currency / total,
        unknown_rate,
        type_counts,
    )
    return metrics


def run_gold_pipeline(
    silver_dir: Path = SILVER_DIR, gold_dir: Path = GOLD_DIR, run_id: str | None = None
) -> dict[str, Any]:
    start = time.perf_counter()
    records = load_silver_json(silver_dir)
    documents = build_documents_table(records)
    write_outputs(documents, gold_dir)
    metrics = log_gold_metrics(documents, time.perf_counter() - start)
    metrics["run_id"] = run_id
    return metrics
