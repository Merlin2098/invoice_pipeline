from typing import Any

from src.aws.glue_jobs.consolidate_gold import consolidate_gold_documents, gold_metrics_preview
from src.aws.glue_jobs.normalize_documents import normalize_bronze_documents
from src.aws.lambda_handlers.control_plane import publish_run_metrics, validate_input
from src.pipeline.aws_runtime import AwsPipelineRequest, AwsPipelineRunner, extract_expense_candidates


def test_extract_expense_candidates_reads_textract_summary_fields() -> None:
    response = {
        "ExpenseDocuments": [
            {
                "SummaryFields": [
                    {
                        "Type": {"Text": "VENDOR_NAME"},
                        "ValueDetection": {"Text": "Acme", "Confidence": 99.0},
                    },
                    {
                        "Type": {"Text": "TOTAL"},
                        "ValueDetection": {"Text": "$10.50", "Confidence": 98.0},
                    },
                ]
            }
        ]
    }

    candidate = extract_expense_candidates(response)

    assert candidate["document_type"] == "invoice"
    assert candidate["vendor_name"] == "Acme"
    assert candidate["total_amount"] == "$10.50"


def test_aws_runner_uses_bedrock_when_candidate_is_ambiguous() -> None:
    writes: dict[str, Any] = {}

    class FakeTextract:
        def analyze_expense(self, source_s3_key: str) -> dict[str, Any]:
            return {
                "ExpenseDocuments": [
                    {
                        "SummaryFields": [
                            {
                                "Type": {"Text": "TOTAL"},
                                "ValueDetection": {"Text": "$10.50", "Confidence": 98.0},
                            }
                        ]
                    }
                ]
            }

    class FakeStore:
        def write_json(self, key: str, payload: dict[str, Any]) -> None:
            writes[key] = payload

    class FakeBedrock:
        def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
            return {
                "vendor_name": "Acme",
                "document_date": "2024-01-01",
                "currency": "USD",
            }

    runner = AwsPipelineRunner(
        textract=FakeTextract(),
        object_store=FakeStore(),
        bedrock=FakeBedrock(),
    )

    result = runner.process_document(
        AwsPipelineRequest(
            run_id="run-1",
            source_s3_key="raw/run_id=run-1/sample.tif",
            source_file_name="sample.tif",
            created_at="2026-05-05T00:00:00Z",
        )
    )

    assert any(key.endswith("sample.json") for key in writes)
    assert result["vendor_name"] == "Acme"
    assert result["normalization_engine"] == "bedrock"


def test_glue_normalization_and_gold_preview_use_shared_contract() -> None:
    bronze_records = [
        {
            "document_id": "sample",
            "source_s3_key": "raw/run_id=run-1/sample.tif",
            "source_file_name": "sample.tif",
            "textract_response": {
                "ExpenseDocuments": [
                    {
                        "SummaryFields": [
                            {
                                "Type": {"Text": "VENDOR_NAME"},
                                "ValueDetection": {"Text": "Acme", "Confidence": 99.0},
                            },
                            {
                                "Type": {"Text": "TOTAL"},
                                "ValueDetection": {"Text": "$10.50", "Confidence": 98.0},
                            },
                        ]
                    }
                ]
            },
        }
    ]

    normalized = normalize_bronze_documents(
        bronze_records,
        run_id="run-1",
        created_at="2026-05-05T00:00:00Z",
    )
    gold_df = consolidate_gold_documents(normalized)
    preview = gold_metrics_preview(normalized)

    assert len(normalized) == 1
    assert len(gold_df) == 1
    assert preview["rows"] == 1


def test_lambda_control_handlers_validate_and_publish_without_boto3(monkeypatch) -> None:
    result = validate_input(
        {
            "run_id": "run-1",
            "source_s3_key": "raw/run_id=run-1/sample.tif",
            "source_file_name": "sample.tif",
        }
    )
    publish = publish_run_metrics({"run_id": "run-1", "metrics": []})

    assert result["valid"] is True
    assert publish["published"] is False
