from typing import Any

from src.aws.glue_jobs.consolidate_gold import consolidate_gold_documents, gold_metrics_preview
from src.aws.glue_jobs.normalize_documents import normalize_bronze_documents
from src.aws.lambda_handlers.control_plane import (
    process_document,
    publish_run_metrics,
    start_raw_ingestion,
    validate_input,
)
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


def test_start_raw_ingestion_starts_step_function_from_s3_event(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    class FakeStepFunctionsClient:
        def start_execution(self, **kwargs: Any) -> dict[str, str]:
            calls.append(kwargs)
            return {"executionArn": "arn:aws:states:::execution:test"}

    class FakeBoto3:
        def client(self, service_name: str) -> FakeStepFunctionsClient:
            assert service_name == "stepfunctions"
            return FakeStepFunctionsClient()

    monkeypatch.setattr(
        "src.aws.lambda_handlers.control_plane._optional_boto3",
        lambda: FakeBoto3(),
    )
    monkeypatch.setenv("STATE_MACHINE_ARN", "arn:aws:states:::stateMachine:test")

    result = start_raw_ingestion(
        {
            "Records": [
                {
                    "eventSource": "aws:s3",
                    "s3": {
                        "bucket": {"name": "lake-bucket"},
                        "object": {"key": "raw/run_id=run-1/sample.pdf"},
                    },
                }
            ]
        }
    )

    assert result["started"] == 1
    assert calls[0]["stateMachineArn"] == "arn:aws:states:::stateMachine:test"
    assert '"run_id": "run-1"' in calls[0]["input"]


def test_process_document_writes_valid_silver_output(monkeypatch) -> None:
    writes: dict[str, dict[str, Any]] = {}

    class FakeStore:
        def write_json(self, key: str, payload: dict[str, Any]) -> None:
            writes[key] = payload

    class FakeRunner:
        def process_document(self, request: AwsPipelineRequest) -> dict[str, Any]:
            return {
                "run_id": request.run_id,
                "document_id": "sample",
                "source_s3_key": request.source_s3_key,
                "source_file_name": request.source_file_name,
                "document_type": "invoice",
                "vendor_name": "Acme",
                "document_date": "2024-01-01",
                "total_amount": 10.0,
                "currency": "USD",
                "extraction_engine": "textract_analyze_expense",
                "normalization_engine": "textract_only",
                "llm_model_id": None,
                "processing_status": "accepted",
                "quality_status": "accepted",
                "quality_score": 1.0,
                "quality_flags": [],
                "rejection_reason": None,
                "reason_code": None,
                "created_at": request.created_at,
                "vendor_or_requester": "Acme",
                "ocr_confidence_flags": [],
                "source_file": request.source_file_name,
                "raw_text_path": None,
            }

    monkeypatch.setattr(
        "src.aws.lambda_handlers.control_plane.S3JsonStore",
        lambda bucket_name: FakeStore(),
    )
    monkeypatch.setattr(
        "src.aws.lambda_handlers.control_plane.TextractAnalyzeExpenseClient",
        lambda bucket_name: object(),
    )
    monkeypatch.setattr(
        "src.aws.lambda_handlers.control_plane.AwsPipelineRunner",
        lambda **kwargs: FakeRunner(),
    )
    monkeypatch.setenv("DATA_LAKE_BUCKET", "lake-bucket")
    monkeypatch.setenv("BRONZE_PREFIX", "bronze/textract-json")
    monkeypatch.setenv("SILVER_VALID_PREFIX", "silver/valid")
    monkeypatch.setenv("SILVER_REJECTED_PREFIX", "silver/rejected")
    monkeypatch.setenv("ERRORS_PREFIX", "errors")

    result = process_document(
        {
            "run_id": "run-1",
            "source_s3_key": "raw/run_id=run-1/sample.pdf",
            "source_file_name": "sample.pdf",
            "created_at": "2026-05-06T00:00:00Z",
        }
    )

    assert result["processing_status"] == "accepted"
    assert result["output_s3_key"] == "silver/valid/run_id=run-1/sample.json"
    assert "silver/valid/run_id=run-1/sample.json" in writes
