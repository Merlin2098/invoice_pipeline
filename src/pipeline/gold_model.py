import json
import logging
import time
from datetime import datetime
from hashlib import sha256
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
    "document_fingerprint",
    "business_key",
    "is_duplicate",
    "duplicate_of_document_id",
    "duplicate_strategy",
    "duplicate_confidence",
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


def add_flag(
    record: dict[str, Any], flag: str, key: str = "ocr_confidence_flags"
) -> None:
    flags = (
        ensure_flags(record)
        if key == "ocr_confidence_flags"
        else record.setdefault(key, [])
    )
    if not isinstance(flags, list):
        flags = ["invalid_quality_flags"]
        record[key] = flags
    if flag not in flags:
        flags.append(flag)


def load_silver_json(silver_dir: Path = SILVER_DIR) -> list[dict[str, Any]]:
    records = []
    candidate_paths = sorted(silver_dir.rglob("*.json"))
    if not candidate_paths:
        candidate_paths = sorted(config_path(_CONFIG, "silver_dir").rglob("*.json"))

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


def _normalized_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return " ".join(str(value).strip().lower().split())


def _normalized_amount(value: Any) -> str | None:
    amount = normalize_amount(value)
    if amount is None:
        return None
    return f"{amount:.2f}"


def build_business_key(record: dict[str, Any]) -> str | None:
    vendor = _normalized_text(record.get("vendor_name"))
    document_date = normalize_date(record.get("document_date"))
    amount = _normalized_amount(record.get("total_amount"))
    currency = _normalized_text(record.get("currency"))
    invoice_number = _normalized_text(record.get("invoice_number"))
    required = [vendor, document_date, amount, currency]
    if any(value is None for value in required):
        return None
    parts = ["invoice", vendor, document_date, amount, currency]
    if invoice_number:
        parts.append(invoice_number)
    return "|".join(str(part) for part in parts)


def build_document_fingerprint(record: dict[str, Any]) -> str:
    existing = record.get("document_fingerprint")
    if isinstance(existing, str) and existing.strip():
        return existing.strip()

    raw_text_path = record.get("raw_text_path")
    if raw_text_path:
        path = Path(str(raw_text_path))
        if path.exists() and path.is_file():
            return sha256(path.read_bytes()).hexdigest()

    fingerprint_payload = {
        "vendor_name": _normalized_text(record.get("vendor_name")),
        "document_date": normalize_date(record.get("document_date")),
        "total_amount": _normalized_amount(record.get("total_amount")),
        "currency": _normalized_text(record.get("currency")),
        "source_file_name": _normalized_text(record.get("source_file_name")),
    }
    payload = json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _record_identity(record: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    return (
        record.get("run_id"),
        record.get("document_id"),
        record.get("source_s3_key"),
    )


def _dedupe_reference(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": record.get("run_id"),
        "document_id": record.get("document_id"),
        "source_s3_key": record.get("source_s3_key"),
        "document_fingerprint": build_document_fingerprint(record),
        "business_key": build_business_key(record),
    }


def _is_gold_eligible(record: dict[str, Any]) -> bool:
    return (
        record.get("processing_status", "accepted") == "accepted"
        and record.get("quality_status", "accepted") in {"accepted", "warning"}
    )


def apply_duplicate_markers(
    records: list[dict[str, Any]],
    history_records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    history_records = history_records or []
    current_identities = {_record_identity(record) for record in records}
    exact_seen: dict[str, dict[str, Any]] = {}
    business_seen: dict[str, dict[str, Any]] = {}

    for record in history_records:
        if not _is_gold_eligible(record):
            continue
        if _record_identity(record) in current_identities:
            continue
        reference = _dedupe_reference(record)
        fingerprint = reference["document_fingerprint"]
        business_key = reference["business_key"]
        if fingerprint:
            exact_seen.setdefault(str(fingerprint), reference)
        if business_key:
            business_seen.setdefault(str(business_key), reference)

    marked: list[dict[str, Any]] = []
    for record in records:
        fingerprint = build_document_fingerprint(record)
        business_key = build_business_key(record)
        record["document_fingerprint"] = fingerprint
        record["business_key"] = business_key
        record["is_duplicate"] = False
        record["duplicate_of_document_id"] = None
        record["duplicate_strategy"] = "none"
        record["duplicate_confidence"] = 0.0

        duplicate = exact_seen.get(fingerprint)
        if duplicate:
            record["is_duplicate"] = True
            record["duplicate_of_document_id"] = duplicate.get("document_id")
            record["duplicate_strategy"] = "exact_fingerprint"
            record["duplicate_confidence"] = 1.0
        elif business_key and business_key in business_seen:
            duplicate = business_seen[business_key]
            record["is_duplicate"] = True
            record["duplicate_of_document_id"] = duplicate.get("document_id")
            record["duplicate_strategy"] = "business_key"
            record["duplicate_confidence"] = 0.85

        reference = _dedupe_reference(record)
        exact_seen.setdefault(fingerprint, reference)
        if business_key:
            business_seen.setdefault(business_key, reference)
        marked.append(record)

    return marked


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


def build_documents_table(
    records: list[dict[str, Any]],
    history_records: list[dict[str, Any]] | None = None,
) -> pd.DataFrame:
    eligible_records = [record for record in records if _is_gold_eligible(record)]
    documents = [
        map_to_document(record)
        for record in apply_duplicate_markers(eligible_records, history_records)
    ]
    return pd.DataFrame(documents, columns=DOCUMENT_COLUMNS)


def write_outputs(
    documents: pd.DataFrame, gold_dir: Path = GOLD_DIR, run_id: str | None = None
) -> None:
    gold_dir.mkdir(parents=True, exist_ok=True)
    output_path = gold_dir / "documents.parquet"
    documents.to_parquet(output_path, index=False)
    logger.info("Wrote gold documents table to %s", output_path)
    output_run_id = run_id
    if output_run_id is None and not documents.empty:
        output_run_id = str(documents["run_id"].iloc[0])
    if output_run_id:
        partition_dir = gold_dir / f"run_id={output_run_id}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        documents.to_parquet(partition_dir / "documents.parquet", index=False)
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
    current_records = [
        record for record in records if run_id is None or record.get("run_id") == run_id
    ]
    documents = build_documents_table(current_records, history_records=records)
    write_outputs(documents, gold_dir, run_id=run_id)
    metrics = log_gold_metrics(documents, time.perf_counter() - start)
    metrics["run_id"] = run_id
    return metrics
