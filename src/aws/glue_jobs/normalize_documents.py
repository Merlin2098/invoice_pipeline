from __future__ import annotations

from typing import Any

from src.pipeline.aws_runtime import extract_expense_candidates
from src.pipeline.quality import build_aws_silver_document


def normalize_bronze_documents(
    bronze_records: list[dict[str, Any]], *, run_id: str, created_at: str
) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for bronze_record in bronze_records:
        candidate = extract_expense_candidates(bronze_record["textract_response"])
        documents.append(
            build_aws_silver_document(
                candidate,
                run_id=run_id,
                document_id=str(bronze_record["document_id"]),
                source_s3_key=str(bronze_record["source_s3_key"]),
                source_file_name=str(bronze_record["source_file_name"]),
                created_at=created_at,
                extraction_engine="textract_analyze_expense",
                normalization_engine="glue_normalize",
                llm_model_id=None,
            )
        )
    return documents

