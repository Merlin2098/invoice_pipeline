import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from dateutil import parser as date_parser

CONTRACT_PATH = Path("src/config/data_contract.yaml")


def load_contract(contract_path: Path = CONTRACT_PATH) -> dict[str, Any]:
    with contract_path.open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def contract_field_names(contract: dict[str, Any] | None = None) -> list[str]:
    contract = contract or load_contract()
    names: list[str] = []
    for group in ("common", "invoice", "contribution"):
        names.extend(contract.get(group, {}).keys())
    return names


def normalize_amount(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, int | float):
        return float(value)

    text = str(value)
    spaced_cents = re.search(r"(\d[\d,]*)\s+(\d{2})(?!\d)", text)
    if spaced_cents and "." not in text:
        text = f"{spaced_cents.group(1)}.{spaced_cents.group(2)}"
    text = text.replace(",", "")
    text = re.sub(r"[\[\]\(\){}A-Za-z$]", "", text)
    text = re.sub(r"\s+", "", text)

    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None

    try:
        return float(match.group(0))
    except ValueError:
        return None


def normalize_date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value.isoformat()

    try:
        parsed = date_parser.parse(str(value).strip(), fuzzy=True)
    except (ValueError, OverflowError):
        return None

    return parsed.date().isoformat()


def clean_string(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    replacements = {
        "â€˜": "'",
        "â€™": "'",
        "â€œ": '"',
        "â€�": '"',
        "Â®": "",
        "Â": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"\s+", " ", text)
    return text.strip(" '\"\t\r\n") or None


def classify_document_type(text: str) -> str:
    normalized = text.lower()
    if "invoice" in normalized:
        return "invoice"
    if "contribution" in normalized:
        return "contribution"
    return "unknown"


def _flags(record: dict[str, Any]) -> list[str]:
    flags = record.get("ocr_confidence_flags")
    if flags is None:
        flags = []
    if isinstance(flags, str):
        flags = [flags]
    if isinstance(flags, list):
        return flags
    else:
        flags = ["invalid_ocr_confidence_flags"]
    record["ocr_confidence_flags"] = flags
    return flags


def add_flag(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def map_to_contract(
    record: dict[str, Any],
    *,
    source_file: str,
    raw_text_path: str,
    text: str,
) -> dict[str, Any]:
    mapped = {
        field: None
        for field in contract_field_names()
        if field != "ocr_confidence_flags"
    }

    document_id = Path(source_file).stem
    total_amount = normalize_amount(record.get("total_amount"))
    document_date = normalize_date(record.get("document_date"))
    vendor_name = clean_string(record.get("vendor_name"))
    flags = _flags(record)

    if record.get("total_amount") not in (None, "") and total_amount is None:
        add_flag(flags, "invalid_total_amount")
    if record.get("document_date") not in (None, "") and document_date is None:
        add_flag(flags, "invalid_document_date")

    if total_amount is None:
        add_flag(flags, "missing_total_amount")
    if document_date is None:
        add_flag(flags, "missing_document_date")
    if vendor_name is None:
        add_flag(flags, "missing_vendor_or_requester")

    document_type = classify_document_type(text)
    if document_type == "unknown":
        add_flag(flags, "unknown_document_type")

    mapped.update(
        {
            "source_file": source_file,
            "document_id": document_id,
            "document_type": document_type,
            "document_date": document_date,
            "vendor_or_requester": vendor_name,
            "total_amount": total_amount,
            "amount": total_amount,
            "currency": "USD" if "$" in text or total_amount is not None else None,
            "raw_text_path": raw_text_path,
            "ocr_confidence_flags": flags,
        }
    )
    return mapped
