from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.pipeline.postprocess import clean_string, classify_document_type, normalize_amount, normalize_date
from src.pipeline.specs import load_quality_rules


def _flags(record: dict[str, Any], key: str = "quality_flags") -> list[str]:
    flags = record.get(key)
    if flags is None:
        flags = []
    elif isinstance(flags, str):
        flags = [flags]
    elif not isinstance(flags, list):
        flags = ["invalid_quality_flags"]
    record[key] = flags
    return flags


def add_flag(record: dict[str, Any], flag: str, key: str = "quality_flags") -> None:
    flags = _flags(record, key=key)
    if flag not in flags:
        flags.append(flag)


def _current_year() -> int:
    return datetime.utcnow().year


def infer_currency(raw_text: str, extracted_currency: Any, total_amount: float | None) -> str | None:
    if isinstance(extracted_currency, str) and extracted_currency.strip():
        return extracted_currency.strip().upper()

    text = raw_text.upper()
    if " PEN" in text or "S/" in text or "SOLES" in text:
        return "PEN"
    if " EUR" in text or "€" in raw_text:
        return "EUR"
    if total_amount is not None and ("$" in raw_text or " USD" in text):
        return "USD"
    return None


def _score_from_flags(flags: list[str], rejected: bool) -> float:
    penalty = min(len(set(flags)), 8) * 0.1
    score = max(0.0, 1.0 - penalty)
    if rejected:
        return min(score, 0.4)
    return score


def canonical_document_template() -> dict[str, Any]:
    return {
        "run_id": None,
        "document_id": None,
        "source_s3_key": None,
        "source_file_name": None,
        "raw_text_path": None,
        "document_type": "unknown",
        "document_type_confidence": None,
        "vendor_name": None,
        "vendor_confidence": None,
        "document_date": None,
        "document_date_confidence": None,
        "total_amount": None,
        "total_amount_confidence": None,
        "currency": None,
        "currency_confidence": None,
        "extraction_engine": None,
        "normalization_engine": None,
        "llm_model_id": None,
        "bedrock_invoked": False,
        "bedrock_completed_fields": [],
        "processing_status": "normalized",
        "quality_status": "accepted",
        "quality_score": 1.0,
        "quality_flags": [],
        "rejection_reason": None,
        "reason_code": None,
        "document_fingerprint": None,
        "business_key": None,
        "is_duplicate": False,
        "duplicate_of_document_id": None,
        "duplicate_strategy": "none",
        "duplicate_confidence": 0.0,
        "created_at": None,
    }


def _finalize_aliases(document: dict[str, Any]) -> dict[str, Any]:
    document["vendor_or_requester"] = document.get("vendor_name")
    document["ocr_confidence_flags"] = deepcopy(_flags(document))
    document["source_file"] = document.get("source_file_name")
    return document


def create_failed_document(
    *,
    run_id: str,
    document_id: str,
    source_s3_key: str,
    source_file_name: str,
    extraction_engine: str,
    normalization_engine: str | None,
    llm_model_id: str | None,
    created_at: str,
    failure_flags: list[str],
    raw_text_path: str | None = None,
) -> dict[str, Any]:
    document = canonical_document_template()
    document.update(
        {
            "run_id": run_id,
            "document_id": document_id,
            "source_s3_key": source_s3_key,
            "source_file_name": source_file_name,
            "raw_text_path": raw_text_path,
            "extraction_engine": extraction_engine,
            "normalization_engine": normalization_engine,
            "llm_model_id": llm_model_id,
            "processing_status": "failed",
            "quality_status": "rejected",
            "quality_score": 0.0,
            "quality_flags": list(failure_flags),
            "rejection_reason": "technical_processing_failure",
            "reason_code": "technical_processing_failure",
            "created_at": created_at,
        }
    )
    return _finalize_aliases(document)


def apply_quality_rules(
    document: dict[str, Any], rules: dict[str, Any] | None = None
) -> dict[str, Any]:
    rules = rules or load_quality_rules()
    flags = _flags(document)
    rejected = False
    rejection_reason: str | None = document.get("rejection_reason")

    technical_flags = set(rules.get("technical_failure_flags", []))
    if document.get("processing_status") == "failed" or not technical_flags.isdisjoint(flags):
        document["processing_status"] = "failed"
        document["quality_status"] = "rejected"
        document["quality_score"] = 0.0
        document["rejection_reason"] = "technical_processing_failure"
        document["reason_code"] = "technical_processing_failure"
        return _finalize_aliases(document)

    required_fields = rules.get("required_fields", [])
    missing_required = [field for field in required_fields if not document.get(field)]
    if missing_required:
        rejected = True
        rejection_reason = "missing_required_fields"
        for field in missing_required:
            add_flag(document, f"missing_{field}")

    minimum_fields = rules.get("minimum_acceptance", {}).get("require_at_least_one", [])
    if minimum_fields and not any(document.get(field) not in (None, "") for field in minimum_fields):
        rejected = True
        rejection_reason = rejection_reason or "minimum_acceptance_not_met"
        add_flag(document, "minimum_acceptance_not_met")

    date_rules = rules.get("document_date_rules", {})
    document_date = document.get("document_date")
    if document_date:
        parsed_date = date.fromisoformat(str(document_date))
        max_year = date_rules.get("max_year")
        max_year_value = _current_year() if max_year == "current_year" else int(max_year)
        if parsed_date.year < int(date_rules.get("min_year", 2000)) or parsed_date.year > max_year_value:
            rejected = True
            rejection_reason = date_rules.get("on_invalid_date", {}).get("reason", "document_date_out_of_allowed_range")
            add_flag(document, date_rules.get("on_invalid_date", {}).get("flag", "invalid_document_date"))
        if date_rules.get("reject_future_dates", True) and parsed_date > date.today():
            rejected = True
            rejection_reason = date_rules.get("on_invalid_date", {}).get("reason", "document_date_out_of_allowed_range")
            add_flag(document, date_rules.get("on_invalid_date", {}).get("flag", "invalid_document_date"))
    elif date_rules.get("allow_null", True):
        add_flag(document, "missing_document_date")

    amount_rules = rules.get("amount_rules", {})
    total_amount = document.get("total_amount")
    if total_amount is not None:
        if float(total_amount) < float(amount_rules.get("min_value", 0)):
            rejected = True
            rejection_reason = amount_rules.get("on_extreme_amount", {}).get("reason", "total_amount_exceeds_allowed_threshold")
            add_flag(document, amount_rules.get("on_extreme_amount", {}).get("flag", "amount_outlier"))
        if float(total_amount) > float(amount_rules.get("max_value", 1000000)):
            rejected = True
            rejection_reason = amount_rules.get("on_extreme_amount", {}).get("reason", "total_amount_exceeds_allowed_threshold")
            add_flag(document, amount_rules.get("on_extreme_amount", {}).get("flag", "amount_outlier"))
    elif amount_rules.get("allow_null", True):
        add_flag(document, "missing_total_amount")

    currency_rules = rules.get("currency_rules", {})
    currency = document.get("currency")
    if total_amount is not None and currency is None:
        add_flag(document, currency_rules.get("on_missing_currency", {}).get("flag", "currency_missing"))
    allowed_currencies = set(currency_rules.get("allowed_values", []))
    if currency and allowed_currencies and currency not in allowed_currencies:
        rejected = True
        rejection_reason = currency_rules.get("on_invalid_currency", {}).get("reason", "currency_not_allowed")
        add_flag(document, currency_rules.get("on_invalid_currency", {}).get("flag", "invalid_currency"))

    vendor_rules = rules.get("vendor_rules", {})
    vendor_name = document.get("vendor_name")
    if vendor_name is None:
        add_flag(document, vendor_rules.get("on_missing_vendor", {}).get("flag", "vendor_missing"))
    elif len(str(vendor_name).strip()) < int(vendor_rules.get("min_length", 2)):
        add_flag(document, "vendor_too_short")
    elif str(vendor_name).strip().isdigit():
        rejected = True
        rejection_reason = vendor_rules.get("on_invalid_vendor", {}).get("reason", "vendor_name_not_usable")
        add_flag(document, vendor_rules.get("on_invalid_vendor", {}).get("flag", "invalid_vendor"))

    document_type_rules = rules.get("document_type_rules", {})
    document_type = str(document.get("document_type") or "unknown")
    allowed_types = set(document_type_rules.get("allowed_values", []))
    if document_type not in allowed_types:
        rejected = True
        rejection_reason = rejection_reason or "invalid_document_type"
        add_flag(document, "invalid_document_type")
    elif document_type == "unknown":
        add_flag(document, document_type_rules.get("on_unknown_document_type", {}).get("flag", "unknown_document_type"))

    flags = _flags(document)
    document["rejection_reason"] = rejection_reason if rejected else None
    document["reason_code"] = document["rejection_reason"]
    if rejected:
        document["quality_status"] = "rejected"
        document["processing_status"] = "rejected"
    elif flags:
        document["quality_status"] = "warning"
        document["processing_status"] = "accepted"
    else:
        document["quality_status"] = "accepted"
        document["processing_status"] = "accepted"
    document["quality_score"] = _score_from_flags(flags, rejected)
    return _finalize_aliases(document)


def build_local_silver_document(
    extracted_record: dict[str, Any],
    *,
    source_file_name: str,
    raw_text_path: str,
    source_s3_key: str,
    raw_text: str,
    run_id: str,
    created_at: str,
    llm_model_id: str | None,
) -> dict[str, Any]:
    document = canonical_document_template()
    flags = extracted_record.get("ocr_confidence_flags")
    if flags is None:
        flags = []
    document.update(
        {
            "run_id": run_id,
            "document_id": Path(source_file_name).stem,
            "source_s3_key": source_s3_key,
            "source_file_name": source_file_name,
            "raw_text_path": raw_text_path,
            "document_type": classify_document_type(raw_text),
            "vendor_name": clean_string(
                extracted_record.get("vendor_name")
                or extracted_record.get("vendor_or_requester")
            ),
            "document_date": normalize_date(extracted_record.get("document_date")),
            "total_amount": normalize_amount(extracted_record.get("total_amount")),
            "currency": infer_currency(
                raw_text,
                extracted_record.get("currency"),
                normalize_amount(extracted_record.get("total_amount")),
            ),
            "extraction_engine": "local_tesseract",
            "normalization_engine": "local_ollama",
            "llm_model_id": llm_model_id,
            "created_at": created_at,
            "quality_flags": list(flags) if isinstance(flags, list) else [],
        }
    )
    if document["document_date"] is None:
        add_flag(document, "missing_document_date")
    return apply_quality_rules(document)


def build_aws_silver_document(
    candidate: dict[str, Any],
    *,
    run_id: str,
    document_id: str,
    source_s3_key: str,
    source_file_name: str,
    created_at: str,
    extraction_engine: str,
    normalization_engine: str | None,
    llm_model_id: str | None,
) -> dict[str, Any]:
    document = canonical_document_template()
    document.update(
        {
            "run_id": run_id,
            "document_id": document_id,
            "source_s3_key": source_s3_key,
            "source_file_name": source_file_name,
            "document_type": str(candidate.get("document_type") or "unknown"),
            "document_type_confidence": candidate.get("document_type_confidence"),
            "vendor_name": clean_string(candidate.get("vendor_name")),
            "vendor_confidence": candidate.get("vendor_confidence"),
            "document_date": normalize_date(candidate.get("document_date")),
            "document_date_confidence": candidate.get("document_date_confidence"),
            "total_amount": normalize_amount(candidate.get("total_amount")),
            "total_amount_confidence": candidate.get("total_amount_confidence"),
            "currency": infer_currency(
                str(candidate.get("raw_text") or ""),
                candidate.get("currency"),
                normalize_amount(candidate.get("total_amount")),
            ),
            "currency_confidence": candidate.get("currency_confidence"),
            "extraction_engine": extraction_engine,
            "normalization_engine": normalization_engine,
            "llm_model_id": llm_model_id,
            "bedrock_invoked": bool(candidate.get("bedrock_invoked", False)),
            "bedrock_completed_fields": list(candidate.get("bedrock_completed_fields") or []),
            "created_at": created_at,
            "quality_flags": list(candidate.get("quality_flags") or []),
        }
    )
    return apply_quality_rules(document)
