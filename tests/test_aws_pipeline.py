import json
import logging
from typing import Any

from src.aws.glue_jobs.consolidate_gold import (
    consolidate_gold_documents,
    consolidate_gold_run,
    gold_metrics_preview,
)
from src.aws.glue_jobs.normalize_documents import normalize_bronze_documents
from src.aws.lambda_handlers.control_plane import (
    consolidate_gold,
    enrich_with_llm,
    extract_ocr,
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
    assert result["bedrock_invoked"] is True
    assert set(result["bedrock_completed_fields"]) == {
        "currency",
        "document_date",
        "vendor_name",
    }


def test_aws_runner_splits_ocr_and_enrichment() -> None:
    writes: dict[str, Any] = {}

    class FakeTextract:
        def analyze_expense(self, source_s3_key: str) -> dict[str, Any]:
            assert source_s3_key == "raw/run_id=run-1/sample.tif"
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

    request = AwsPipelineRequest(
        run_id="run-1",
        source_s3_key="raw/run_id=run-1/sample.tif",
        source_file_name="sample.tif",
        created_at="2026-05-05T00:00:00Z",
    )
    runner = AwsPipelineRunner(
        textract=FakeTextract(),
        object_store=FakeStore(),
        bedrock=FakeBedrock(),
        bedrock_model_id="test-model",
    )

    ocr = runner.run_ocr(request)
    silver = runner.run_enrichment(
        request,
        candidate=dict(ocr["candidate"]),
        bronze_key=str(ocr["bronze_s3_key"]),
    )

    assert ocr["bronze_s3_key"] == "bronze/textract-json/run_id=run-1/sample.json"
    assert writes["bronze/textract-json/run_id=run-1/sample.json"]["status"] == "success"
    assert silver["vendor_name"] == "Acme"
    assert silver["normalization_engine"] == "bedrock"
    assert silver["bedrock_invoked"] is True
    assert set(silver["bedrock_completed_fields"]) == {
        "currency",
        "document_date",
        "vendor_name",
    }


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


def test_consolidate_gold_returns_incomplete_without_writing(monkeypatch) -> None:
    writes: dict[str, Any] = {}

    class FakeStore:
        def key_exists(self, key: str) -> bool:
            return False

        def write_bytes(
            self,
            key: str,
            payload: bytes,
            *,
            content_type: str = "application/octet-stream",
        ) -> None:
            writes[key] = payload

        def write_json(self, key: str, payload: dict[str, Any]) -> None:
            writes[key] = payload

    monkeypatch.setattr(
        "src.aws.lambda_handlers.control_plane.S3JsonStore",
        lambda bucket_name: FakeStore(),
    )
    monkeypatch.setenv("DATA_LAKE_BUCKET", "lake-bucket")

    result = consolidate_gold(
        {
            "batch_id": "batch-1",
            "expected_documents": [
                {
                    "run_id": "run-1",
                    "document_id": "missing",
                    "source_s3_key": "raw/missing.pdf",
                }
            ],
        }
    )

    assert result["status"] == "incomplete"
    assert result["missing_documents"][0]["document_id"] == "missing"
    assert writes == {}


def test_consolidate_gold_writes_manifest_and_parquet_for_completed_batch(
    monkeypatch,
) -> None:
    objects: dict[str, Any] = {
        "silver/valid/run_id=run-old/invoice-old.json": {
            "run_id": "run-old",
            "document_id": "invoice-old",
            "source_s3_key": "raw/invoice-old.pdf",
            "source_file_name": "invoice-old.pdf",
            "document_type": "invoice",
            "document_date": "2024-01-01",
            "total_amount": 10.0,
            "vendor_name": "Acme",
            "currency": "USD",
            "processing_status": "accepted",
            "quality_status": "accepted",
            "quality_flags": [],
            "created_at": "2026-05-06T00:00:00Z",
            "document_fingerprint": "same-sha256",
        },
        "silver/valid/run_id=run-1/invoice.json": {
            "run_id": "run-1",
            "document_id": "invoice",
            "source_s3_key": "raw/invoice.pdf",
            "source_file_name": "invoice.pdf",
            "document_type": "invoice",
            "document_date": "2024-01-01",
            "total_amount": None,
            "vendor_name": "Acme",
            "currency": "USD",
            "processing_status": "accepted",
            "quality_status": "accepted",
            "quality_flags": [],
            "created_at": "2026-05-06T00:00:00Z",
            "document_fingerprint": "same-sha256",
        },
        "silver/rejected/run_id=run-2/rejected.json": {},
        "errors/silver_failed/run_id=run-3/failed.json": {},
    }
    writes: dict[str, Any] = {}

    class FakeStore:
        def key_exists(self, key: str) -> bool:
            return key in objects

        def read_json(self, key: str) -> dict[str, Any]:
            return objects[key]

        def list_json(self, prefix: str) -> list[dict[str, Any]]:
            return [
                payload
                for key, payload in objects.items()
                if key.startswith(prefix) and key.endswith(".json")
            ]

        def write_bytes(
            self,
            key: str,
            payload: bytes,
            *,
            content_type: str = "application/octet-stream",
        ) -> None:
            writes[key] = payload

        def write_json(self, key: str, payload: dict[str, Any]) -> None:
            writes[key] = payload

    monkeypatch.setattr(
        "src.aws.lambda_handlers.control_plane.S3JsonStore",
        lambda bucket_name: FakeStore(),
    )
    monkeypatch.setenv("DATA_LAKE_BUCKET", "lake-bucket")
    monkeypatch.setenv("GOLD_PREFIX", "gold/documents")

    result = consolidate_gold(
        {
            "batch_id": "batch-1",
            "expected_documents": [
                {"run_id": "run-1", "document_id": "invoice"},
                {"run_id": "run-2", "document_id": "rejected"},
                {"run_id": "run-3", "document_id": "failed"},
            ],
        }
    )

    assert result["status"] == "completed"
    assert result["valid_count"] == 1
    assert result["rejected_count"] == 1
    assert result["failed_count"] == 1
    assert result["gold_row_count"] == 1
    assert result["duplicate_count"] == 1
    assert result["missing_date_count"] == 0
    assert result["missing_amount_count"] == 1
    assert result["date_completion_rate"] == 1.0
    assert result["amount_completion_rate"] == 0.0
    assert "gold/documents/batch_id=batch-1/documents.parquet" in writes
    assert writes["gold/documents/batch_id=batch-1/manifest.json"]["gold_row_count"] == 1
    assert writes["gold/documents/batch_id=batch-1/manifest.json"]["missing_amount_count"] == 1


def test_consolidate_gold_writes_empty_parquet_when_batch_has_no_valid_documents(
    monkeypatch,
) -> None:
    objects: dict[str, Any] = {
        "silver/rejected/run_id=run-1/rejected.json": {},
        "errors/silver_failed/run_id=run-2/failed.json": {},
    }
    writes: dict[str, Any] = {}

    class FakeStore:
        def key_exists(self, key: str) -> bool:
            return key in objects

        def read_json(self, key: str) -> dict[str, Any]:
            return objects[key]

        def list_json(self, prefix: str) -> list[dict[str, Any]]:
            return []

        def write_bytes(
            self,
            key: str,
            payload: bytes,
            *,
            content_type: str = "application/octet-stream",
        ) -> None:
            writes[key] = payload

        def write_json(self, key: str, payload: dict[str, Any]) -> None:
            writes[key] = payload

    monkeypatch.setattr(
        "src.aws.lambda_handlers.control_plane.S3JsonStore",
        lambda bucket_name: FakeStore(),
    )
    monkeypatch.setenv("DATA_LAKE_BUCKET", "lake-bucket")

    result = consolidate_gold(
        {
            "batch_id": "batch-empty",
            "expected_documents": [
                {"run_id": "run-1", "document_id": "rejected"},
                {"run_id": "run-2", "document_id": "failed"},
            ],
        }
    )

    assert result["status"] == "completed"
    assert result["gold_row_count"] == 0
    assert "gold/documents/batch_id=batch-empty/documents.parquet" in writes


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
    assert '"execution_id": "run-1-sample-0"' in calls[0]["input"]


def test_start_raw_ingestion_generates_run_id_for_direct_raw_upload(monkeypatch) -> None:
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
                        "object": {"key": "raw/sample.pdf"},
                    },
                }
            ]
        }
    )

    payload = json.loads(calls[0]["input"])
    assert result["started"] == 1
    assert payload["run_id"].startswith("invoice-pipeline-aws-")
    assert payload["source_s3_key"] == "raw/sample.pdf"


def test_consolidate_gold_run_filters_current_run_and_marks_history_duplicate() -> None:
    records = [
        {
            "run_id": "run-1",
            "document_id": "invoice",
            "source_s3_key": "raw/invoice.tif",
            "source_file_name": "invoice.tif",
            "document_type": "invoice",
            "document_date": "2024-01-01",
            "total_amount": 10.0,
            "vendor_name": "Acme",
            "currency": "USD",
            "processing_status": "accepted",
            "quality_status": "accepted",
            "quality_flags": [],
            "created_at": "2026-05-06T00:00:00Z",
            "document_fingerprint": "same-sha256",
        },
        {
            "run_id": "run-2",
            "document_id": "invoice-copy",
            "source_s3_key": "raw/invoice-copy.tif",
            "source_file_name": "invoice-copy.tif",
            "document_type": "invoice",
            "document_date": "2024-01-01",
            "total_amount": 10.0,
            "vendor_name": "Acme",
            "currency": "USD",
            "processing_status": "accepted",
            "quality_status": "accepted",
            "quality_flags": [],
            "created_at": "2026-05-06T00:00:00Z",
            "document_fingerprint": "same-sha256",
        },
    ]

    gold = consolidate_gold_run(records, run_id="run-2")

    assert list(gold["document_id"]) == ["invoice-copy"]
    assert bool(gold.loc[0, "is_duplicate"]) is True
    assert gold.loc[0, "duplicate_of_document_id"] == "invoice"


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
    monkeypatch.setattr(
        "src.aws.lambda_handlers.control_plane._optional_boto3",
        lambda: None,
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


def test_split_handlers_write_bronze_then_silver(monkeypatch) -> None:
    writes: dict[str, dict[str, Any]] = {}

    class FakeStore:
        def write_json(self, key: str, payload: dict[str, Any]) -> None:
            writes[key] = payload

        def read_json(self, key: str) -> dict[str, Any]:
            return writes[key]

    class FakeTextract:
        def analyze_expense(self, source_s3_key: str) -> dict[str, Any]:
            return {
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

    monkeypatch.setattr(
        "src.aws.lambda_handlers.control_plane.S3JsonStore",
        lambda bucket_name: FakeStore(),
    )
    monkeypatch.setattr(
        "src.aws.lambda_handlers.control_plane.TextractAnalyzeExpenseClient",
        lambda bucket_name: FakeTextract(),
    )
    monkeypatch.setattr(
        "src.aws.lambda_handlers.control_plane._optional_boto3",
        lambda: None,
    )
    monkeypatch.setenv("DATA_LAKE_BUCKET", "lake-bucket")
    monkeypatch.setenv("BRONZE_PREFIX", "bronze/textract-json")
    monkeypatch.setenv("SILVER_VALID_PREFIX", "silver/valid")
    monkeypatch.setenv("SILVER_REJECTED_PREFIX", "silver/rejected")
    monkeypatch.setenv("ERRORS_PREFIX", "errors")
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)

    ocr = extract_ocr(
        {
            "run_id": "run-1",
            "execution_id": "exec-1",
            "source_s3_key": "raw/run_id=run-1/sample.pdf",
            "source_file_name": "sample.pdf",
            "created_at": "2026-05-06T00:00:00Z",
        }
    )
    enriched = enrich_with_llm(
        {
            "run_id": "run-1",
            "execution_id": "exec-1",
            "source_s3_key": "raw/run_id=run-1/sample.pdf",
            "source_file_name": "sample.pdf",
            "created_at": "2026-05-06T00:00:00Z",
            "document_id": ocr["document_id"],
            "bronze_s3_key": ocr["bronze_s3_key"],
            "candidate": ocr["candidate"],
        }
    )

    assert ocr["processing_status"] == "extracted"
    assert ocr["bronze_s3_key"] == "bronze/textract-json/run_id=run-1/sample.json"
    assert enriched["processing_status"] in {"accepted", "rejected"}
    assert "silver/valid/run_id=run-1/sample.json" in writes or "silver/rejected/run_id=run-1/sample.json" in writes


def test_structured_logging_includes_correlation_ids(caplog) -> None:
    with caplog.at_level(logging.INFO):
        result = validate_input(
            {
                "run_id": "run-1",
                "execution_id": "exec-1",
                "source_s3_key": "raw/run_id=run-1/sample.tif",
                "source_file_name": "sample.tif",
                "created_at": "2026-05-06T00:00:00Z",
            }
        )
    payload = json.loads(caplog.records[-1].message)

    assert result["valid"] is True
    assert payload["run_id"] == "run-1"
    assert payload["execution_id"] == "exec-1"
    assert payload["document_id"] == "sample"
    assert payload["stage"] == "validate_input"
