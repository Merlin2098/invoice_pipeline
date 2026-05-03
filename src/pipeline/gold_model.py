import json
import logging
import time
from pathlib import Path
from typing import Any

import pandas as pd
from src.config.pipeline_config import config_path, load_pipeline_config
from src.pipeline.postprocess import normalize_amount, normalize_date
from src.utils.logging import configure_logging

_CONFIG = load_pipeline_config()
SILVER_DIR = config_path(_CONFIG, "silver_dir")
GOLD_DIR = config_path(_CONFIG, "gold_dir")

NUMERIC_FIELDS = (
    "amount",
    "total_amount",
    "tax_amount",
    "subtotal_amount",
    "amount_due",
)
DOCUMENT_COLUMNS = (
    "document_id",
    "source_file",
    "document_type",
    "document_date",
    "vendor_or_requester",
    "amount",
    "total_amount",
    "currency",
    "raw_text_path",
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
    for path in sorted(silver_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Invalid silver JSON skipped: %s", path)
            continue

        if not isinstance(record, dict):
            logger.warning("Non-object silver JSON skipped: %s", path)
            continue

        record.setdefault("source_file", f"{path.stem}.md")
        record.setdefault(
            "raw_text_path", Path("data/bronze", f"{path.stem}.md").as_posix()
        )
        record.setdefault("document_id", path.stem)
        records.append(record)

    return records


def normalize_currency(record: dict[str, Any]) -> str | None:
    currency = record.get("currency")
    if isinstance(currency, str) and currency.strip():
        return currency.strip().upper()

    for field in NUMERIC_FIELDS:
        value = record.get(field)
        if isinstance(value, str) and "$" in value:
            return "USD"

    if any(record.get(field) is not None for field in NUMERIC_FIELDS):
        return "USD"
    return None


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    ensure_flags(record)

    for field in NUMERIC_FIELDS:
        original = record.get(field)
        normalized = normalize_amount(original)
        if original not in (None, "") and normalized is None:
            add_flag(record, f"invalid_{field}")
        record[field] = normalized

    original_date = record.get("document_date")
    normalized_date = normalize_date(original_date)
    if original_date not in (None, "") and normalized_date is None:
        add_flag(record, "invalid_document_date")
    record["document_date"] = normalized_date
    record["currency"] = normalize_currency(record)

    for field in ("document_id", "source_file", "raw_text_path", "document_type"):
        if not record.get(field):
            add_flag(record, f"missing_{field}")
            logger.warning(
                "Missing critical field %s in record %s",
                field,
                record.get("source_file"),
            )

    if record.get("total_amount") is None:
        add_flag(record, "missing_total_amount")
    if record.get("document_date") is None:
        add_flag(record, "missing_document_date")
    if record.get("vendor_or_requester") is None:
        add_flag(record, "missing_vendor_or_requester")
    if record.get("document_type") == "unknown":
        add_flag(record, "unknown_document_type")

    return record


def classify_document_type(record: dict[str, Any]) -> str:
    raw_type = str(record.get("document_type") or "").strip().lower()
    raw_type = raw_type.replace(" ", "_").replace("-", "_")
    if raw_type in {"invoice", "invoice_statement", "statement"}:
        return "invoice"
    if raw_type in {"contribution", "campaign_contribution", "political_contribution"}:
        return "contribution"
    if raw_type in {"cost_memo", "memo", "cost_breakdown", "recap"}:
        return "cost_memo"

    text_parts = [
        record.get("description"),
        record.get("invoice_number"),
        record.get("account_code"),
        record.get("check_payable_to"),
        record.get("project_name"),
        record.get("line_items_text"),
    ]
    text = " ".join(str(part or "") for part in text_parts).lower()
    if "check payable" in text or record.get("account_code") or record.get("party"):
        add_flag(record, "inferred_document_type")
        return "contribution"
    if record.get("invoice_number") or record.get("amount_due") is not None:
        add_flag(record, "inferred_document_type")
        return "invoice"
    if "cost" in text or "memo" in text:
        add_flag(record, "inferred_document_type")
        return "cost_memo"

    add_flag(record, "inferred_document_type")
    return "unknown"


def _pick(record: dict[str, Any], columns: tuple[str, ...]) -> dict[str, Any]:
    return {column: record.get(column) for column in columns}


def map_to_document(record: dict[str, Any]) -> dict[str, Any]:
    if not record.get("document_id") and record.get("source_file"):
        record["document_id"] = Path(str(record["source_file"])).stem
        add_flag(record, "inferred_document_id")

    record["document_type"] = classify_document_type(record)
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
            "document_type_counts": {},
        }

    complete_amount = int(documents["total_amount"].notna().sum())
    complete_date = int(documents["document_date"].notna().sum())
    complete_vendor = int(documents["vendor_or_requester"].notna().sum())
    type_counts = documents["document_type"].value_counts(dropna=False).to_dict()
    metrics = {
        "rows": total,
        "elapsed_seconds": elapsed,
        "amount_completion_rate": complete_amount / total,
        "date_completion_rate": complete_date / total,
        "vendor_completion_rate": complete_vendor / total,
        "document_type_counts": type_counts,
    }
    logger.info(
        "GOLD_METRICS rows=%s elapsed_seconds=%.2f amount_completion_rate=%.2f "
        "date_completion_rate=%.2f vendor_completion_rate=%.2f document_type_counts=%s",
        total,
        elapsed,
        complete_amount / total,
        complete_date / total,
        complete_vendor / total,
        type_counts,
    )
    return metrics


def run_gold_pipeline(
    silver_dir: Path = SILVER_DIR, gold_dir: Path = GOLD_DIR
) -> dict[str, Any]:
    start = time.perf_counter()
    records = load_silver_json(silver_dir)
    documents = build_documents_table(records)
    write_outputs(documents, gold_dir)
    return log_gold_metrics(documents, time.perf_counter() - start)


if __name__ == "__main__":
    configure_logging("gold.log")
    run_gold_pipeline()
