from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src.pipeline.quality import build_aws_silver_document
from src.pipeline.quality import create_failed_document
from src.pipeline.run_context import build_storage_key


class TextractExpenseExtractor(Protocol):
    def analyze_expense(self, source_s3_key: str) -> dict[str, Any]:
        ...


class BedrockNormalizer(Protocol):
    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class ObjectStore(Protocol):
    def write_json(self, key: str, payload: dict[str, Any]) -> None:
        ...


@dataclass(slots=True)
class AwsPipelineRequest:
    run_id: str
    source_s3_key: str
    source_file_name: str
    created_at: str


def extract_expense_candidates(textract_response: dict[str, Any]) -> dict[str, Any]:
    summary_fields = textract_response.get("ExpenseDocuments", [])
    if not summary_fields:
        return {
            "document_type": "unknown",
            "vendor_name": None,
            "document_date": None,
            "total_amount": None,
            "currency": None,
            "quality_flags": ["textract_no_expense_documents"],
        }

    fields = summary_fields[0].get("SummaryFields", [])
    by_type: dict[str, dict[str, Any]] = {}
    for field in fields:
        field_type = field.get("Type", {}).get("Text")
        if field_type:
            by_type[field_type] = field

    def _value(field_type: str) -> str | None:
        value = by_type.get(field_type, {}).get("ValueDetection", {}).get("Text")
        return str(value).strip() if value else None

    def _confidence(field_type: str) -> float | None:
        confidence = by_type.get(field_type, {}).get("ValueDetection", {}).get("Confidence")
        return float(confidence) if confidence is not None else None

    return {
        "document_type": "invoice",
        "document_type_confidence": 0.9,
        "vendor_name": _value("VENDOR_NAME"),
        "vendor_confidence": _confidence("VENDOR_NAME"),
        "document_date": _value("INVOICE_RECEIPT_DATE"),
        "document_date_confidence": _confidence("INVOICE_RECEIPT_DATE"),
        "total_amount": _value("TOTAL"),
        "total_amount_confidence": _confidence("TOTAL"),
        "currency": _value("CURRENCY"),
        "currency_confidence": _confidence("CURRENCY"),
        "raw_text": textract_response.get("raw_text", ""),
        "quality_flags": [],
    }


def should_use_bedrock(candidate: dict[str, Any]) -> bool:
    return (
        candidate.get("document_type") == "unknown"
        or candidate.get("vendor_name") is None
        or candidate.get("document_date") is None
        or candidate.get("currency") is None
    )


class AwsPipelineRunner:
    def __init__(
        self,
        *,
        textract: TextractExpenseExtractor,
        object_store: ObjectStore,
        bedrock: BedrockNormalizer | None = None,
        bronze_prefix: str = "bronze/textract-json",
    ) -> None:
        self.textract = textract
        self.object_store = object_store
        self.bedrock = bedrock
        self.bronze_prefix = bronze_prefix

    def process_document(self, request: AwsPipelineRequest) -> dict[str, Any]:
        document_id = Path(request.source_file_name).stem
        bronze_key = build_storage_key(self.bronze_prefix, request.run_id, f"{document_id}.json")
        try:
            textract_response = self.textract.analyze_expense(request.source_s3_key)
        except Exception as exc:
            self.object_store.write_json(
                bronze_key,
                {
                    "run_id": request.run_id,
                    "document_id": document_id,
                    "source_s3_key": request.source_s3_key,
                    "source_file_name": request.source_file_name,
                    "textract_job_id": None,
                    "textract_response_s3_key": bronze_key,
                    "textract_response": {},
                    "extraction_engine": "textract_analyze_expense",
                    "extraction_timestamp": request.created_at,
                    "status": "failed",
                    "error_message": str(exc),
                },
            )
            return create_failed_document(
                run_id=request.run_id,
                document_id=document_id,
                source_s3_key=request.source_s3_key,
                source_file_name=request.source_file_name,
                extraction_engine="textract_analyze_expense",
                normalization_engine="bedrock" if self.bedrock else "textract_only",
                llm_model_id="bedrock-model-id" if self.bedrock else None,
                created_at=request.created_at,
                failure_flags=["textract_request_failed"],
            )
        self.object_store.write_json(
            bronze_key,
            {
                "run_id": request.run_id,
                "document_id": document_id,
                "source_s3_key": request.source_s3_key,
                "source_file_name": request.source_file_name,
                "textract_job_id": None,
                "textract_response_s3_key": bronze_key,
                "textract_response": textract_response,
                "extraction_engine": "textract_analyze_expense",
                "extraction_timestamp": request.created_at,
                "status": "success",
                "error_message": None,
            },
        )

        candidate = extract_expense_candidates(textract_response)
        if self.bedrock and should_use_bedrock(candidate):
            try:
                candidate.update(self.bedrock.normalize(candidate))
            except Exception:
                candidate.setdefault("quality_flags", []).append("bedrock_request_failed")

        return build_aws_silver_document(
            candidate,
            run_id=request.run_id,
            document_id=document_id,
            source_s3_key=request.source_s3_key,
            source_file_name=request.source_file_name,
            created_at=request.created_at,
            extraction_engine="textract_analyze_expense",
            normalization_engine="bedrock" if self.bedrock else "textract_only",
            llm_model_id="bedrock-model-id" if self.bedrock else None,
        )
