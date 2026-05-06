import json
import logging
import shutil
from pathlib import Path

import jsonschema
import pandas as pd
import yaml
from PIL import Image

import run_pipeline
from scripts import stress_pipeline
from src.config.pipeline_config import load_pipeline_config
from src.pipeline.bronze_pipeline import format_ocr_markdown, run_bronze_pipeline
from src.pipeline.gold_model import build_documents_table, run_gold_pipeline
from src.pipeline.llm_ollama import MINIMAL_EXTRACTION_SCHEMA, MODEL_NAME, build_ollama_payload
from src.pipeline.postprocess import clean_string, classify_document_type, normalize_amount, normalize_date
from src.pipeline.quality import build_local_silver_document, create_failed_document
from src.pipeline.run_context import build_run_context
from src.pipeline.silver_pipeline import process_with_llm, run_silver_pipeline
from src.pipeline.specs import load_contract_schema
from src.pipeline import llm_ollama
from src.services import llm_service
from src.utils import logging as pipeline_logging


TEST_ROOT = Path("data/test_tmp")


def clean_test_dir(name: str) -> Path:
    path = TEST_ROOT / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def test_pipeline_config_loads_new_defaults() -> None:
    config = load_pipeline_config()

    assert config["execution_mode"] == "local"
    assert config["paths"]["silver_valid_dir"] == "data/silver/valid"
    assert config["paths"]["silver_rejected_dir"] == "data/silver/rejected"
    assert config["paths"]["silver_failed_dir"] == "data/errors/silver_failed"
    assert config["run"]["manifest_dir"] == "logs/runs"
    assert config["aws"]["glue_jobs"]["normalize"] == "invoice-pipeline-normalize-dev"


def test_reference_fixture_and_specs_exist() -> None:
    reference_manifest = yaml.safe_load(
        Path("tests/fixtures/reference_documents.yaml").read_text(encoding="utf-8")
    )
    expected_rows = Path("tests/fixtures/expected_documents.csv").read_text(
        encoding="utf-8"
    ).splitlines()

    assert reference_manifest["reference_documents"]["run_label"] == "baseline_local_vs_aws"
    assert len(reference_manifest["reference_documents"]["files"]) == 4
    assert len(expected_rows) == 5
    assert load_contract_schema("silver_document.schema.yaml")["title"] == "silver_document"


def test_bronze_pipeline_reads_raw_and_writes_bronze(monkeypatch, caplog) -> None:
    test_dir = clean_test_dir("bronze_pipeline")
    raw_dir = test_dir / "raw"
    bronze_dir = test_dir / "bronze"
    raw_dir.mkdir()
    (raw_dir / "invoice.tif").write_text("fake image bytes", encoding="utf-8")

    monkeypatch.setattr(
        "src.pipeline.bronze_pipeline.ocr_extract", lambda path: f"OCR for {path.stem}"
    )

    with caplog.at_level(logging.INFO):
        metrics = run_bronze_pipeline(
            raw_dir=raw_dir,
            bronze_dir=bronze_dir,
            run_id="test-run",
        )

    output = (bronze_dir / "invoice.md").read_text(encoding="utf-8")
    assert "# OCR Extract" in output
    assert "OCR for invoice" in output
    assert metrics["run_id"] == "test-run"
    assert "run_id=test-run BRONZE_METRICS total=1 succeeded=1 failed=0" in caplog.text


def test_ocr_markdown_includes_source_metadata() -> None:
    markdown = format_ocr_markdown("OCR body", Path("data/raw/invoice.tif"))

    assert "- Source file: `invoice.tif`" in markdown
    assert "- Source path: `data/raw/invoice.tif`" in markdown
    assert "```text\nOCR body\n```" in markdown


def test_root_pipeline_runs_phases_and_writes_manifest(monkeypatch) -> None:
    context = build_run_context(load_pipeline_config())

    monkeypatch.setattr(
        run_pipeline,
        "build_run_context",
        lambda config, execution_mode=None: context,
    )
    monkeypatch.setattr(
        run_pipeline, "run_bronze_pipeline", lambda **kwargs: {"total": 2, "run_id": context.run_id}
    )
    monkeypatch.setattr(
        run_pipeline,
        "run_silver_pipeline",
        lambda **kwargs: {
            "succeeded": 1,
            "rejected": 1,
            "failed": 0,
            "run_id": context.run_id,
        },
    )
    monkeypatch.setattr(
        run_pipeline,
        "run_gold_pipeline",
        lambda **kwargs: {
            "vendor_completion_rate": 0.5,
            "date_completion_rate": 0.5,
            "amount_completion_rate": 1.0,
            "currency_completion_rate": 1.0,
            "unknown_document_type_rate": 0.5,
            "run_id": context.run_id,
        },
    )

    summary = run_pipeline.run_pipeline()
    manifest = json.loads(Path(context.manifest_path).read_text(encoding="utf-8"))

    assert summary["run_id"] == context.run_id
    assert summary["documents_received"] == 2
    assert manifest["run"]["run_id"] == context.run_id
    assert manifest["summary"]["documents_rejected"] == 1


def test_parse_json_response_handles_common_shapes() -> None:
    assert llm_ollama.parse_json_response('{"total_amount": 10}')["total_amount"] == 10
    assert (
        llm_ollama.parse_json_response(
            '```json\n{"vendor_name": "Acme"}\n``` trailing text'
        )["vendor_name"]
        == "Acme"
    )
    assert llm_ollama.parse_json_response("")["ocr_confidence_flags"] == [
        "empty_llm_response"
    ]
    assert llm_ollama.parse_json_response("not json")["ocr_confidence_flags"] == [
        "invalid_json_response"
    ]


def test_ollama_payload_forces_json_and_bounded_output() -> None:
    payload = build_ollama_payload("extract this")

    assert payload["model"] == MODEL_NAME
    assert payload["format"] == MINIMAL_EXTRACTION_SCHEMA
    assert payload["think"] is False
    assert payload["stream"] is False
    assert payload["options"]["temperature"] == 0


def test_validate_ollama_model_fails_fast_for_missing_model(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.services.llm_service.list_available_models", lambda: ["deepseek-r1:8b"]
    )

    try:
        llm_service.validate_ollama_model("qwen3.5:4b")
    except RuntimeError as exc:
        assert "Available models: deepseek-r1:8b" in str(exc)
    else:
        raise AssertionError("Expected missing Ollama model to fail fast")


def test_llm_service_call_ollama_uses_mocked_requests(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "response": '{"total_amount": 10, "document_date": null, "vendor_name": "Acme"}'
            }

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("src.services.llm_service.requests.post", fake_post)

    response = llm_service.call_ollama("OCR", timeout=12)

    assert response.startswith('{"total_amount"')
    assert captured["timeout"] == 12
    assert captured["json"]["format"] == MINIMAL_EXTRACTION_SCHEMA


def test_process_with_llm_retries_invalid_json(monkeypatch) -> None:
    responses = [
        {"ocr_confidence_flags": ["invalid_json_response"]},
        {"document_type": "invoice", "ocr_confidence_flags": []},
    ]

    monkeypatch.setattr(
        "src.pipeline.silver_pipeline.extract_structured_data",
        lambda text: responses.pop(0),
    )

    assert process_with_llm("INVOICE", max_retries=2)["document_type"] == "invoice"


def test_local_quality_builds_warning_and_rejection_documents() -> None:
    warning = build_local_silver_document(
        {
            "total_amount": "$10.00",
            "document_date": None,
            "vendor_name": "Acme",
            "ocr_confidence_flags": [],
        },
        source_file_name="sample.tif",
        raw_text_path="data/bronze/sample.md",
        source_s3_key="data/raw/sample.tif",
        raw_text="Invoice total $10.00",
        run_id="run-1",
        created_at="2026-05-05T00:00:00Z",
        llm_model_id="qwen3.5:4b",
    )
    rejected = build_local_silver_document(
        {
            "total_amount": "1084432400.0",
            "document_date": "2075-05-02",
            "vendor_name": None,
            "ocr_confidence_flags": [],
        },
        source_file_name="sample.tif",
        raw_text_path="data/bronze/sample.md",
        source_s3_key="data/raw/sample.tif",
        raw_text="plain memo",
        run_id="run-1",
        created_at="2026-05-05T00:00:00Z",
        llm_model_id="qwen3.5:4b",
    )

    assert warning["processing_status"] == "accepted"
    assert warning["quality_status"] == "warning"
    assert rejected["processing_status"] == "rejected"
    assert rejected["rejection_reason"] in {
        "document_date_out_of_allowed_range",
        "total_amount_exceeds_allowed_threshold",
    }


def test_failed_document_uses_canonical_failure_shape() -> None:
    failed = create_failed_document(
        run_id="run-1",
        document_id="sample",
        source_s3_key="raw/run_id=run-1/sample.tif",
        source_file_name="sample.tif",
        extraction_engine="local_tesseract",
        normalization_engine="local_ollama",
        llm_model_id="qwen",
        created_at="2026-05-05T00:00:00Z",
        failure_flags=["invalid_json_response"],
    )

    schema = load_contract_schema("silver_document.schema.yaml")
    jsonschema.validate(failed, schema)
    assert failed["processing_status"] == "failed"
    assert failed["reason_code"] == "technical_processing_failure"


def test_silver_pipeline_routes_valid_rejected_and_failed(monkeypatch) -> None:
    test_dir = clean_test_dir("silver_pipeline")
    bronze_dir = test_dir / "bronze"
    silver_valid_dir = test_dir / "silver" / "valid"
    silver_rejected_dir = test_dir / "silver" / "rejected"
    silver_failed_dir = test_dir / "errors" / "silver_failed"
    bronze_dir.mkdir(parents=True)
    (bronze_dir / "valid.md").write_text(
        "# OCR Extract\n- Source file: `valid.tif`\n- Source path: `data/raw/valid.tif`\n\nINVOICE\nTOTAL $10.00",
        encoding="utf-8",
    )
    (bronze_dir / "reject.md").write_text(
        "# OCR Extract\n- Source file: `reject.tif`\n- Source path: `data/raw/reject.tif`\n\nplain memo",
        encoding="utf-8",
    )
    (bronze_dir / "failed.md").write_text(
        "# OCR Extract\n- Source file: `failed.tif`\n- Source path: `data/raw/failed.tif`\n\nINVOICE",
        encoding="utf-8",
    )

    responses = {
        "valid": {
            "total_amount": "$10.00",
            "document_date": "2005-01-01",
            "vendor_name": "Acme",
            "ocr_confidence_flags": [],
        },
        "reject": {
            "total_amount": None,
            "document_date": None,
            "vendor_name": None,
            "ocr_confidence_flags": [],
        },
        "failed": {"ocr_confidence_flags": ["invalid_json_response"]},
    }

    def fake_extract(text: str) -> dict:
        if "TOTAL" in text:
            return responses["valid"]
        if "plain memo" in text:
            return responses["reject"]
        return responses["failed"]

    monkeypatch.setattr(
        "src.pipeline.silver_pipeline.extract_structured_data", fake_extract
    )

    metrics = run_silver_pipeline(
        bronze_dir=bronze_dir,
        silver_dir=silver_valid_dir,
        rejected_dir=silver_rejected_dir,
        failed_dir=silver_failed_dir,
        max_retries=0,
        validate_model=False,
        run_id="test-run",
        llm_model_id="qwen3.5:4b",
    )

    assert (silver_valid_dir / "valid.json").exists()
    assert (silver_rejected_dir / "reject.json").exists()
    assert (silver_failed_dir / "failed.json").exists()
    assert metrics["succeeded"] == 1
    assert metrics["rejected"] == 1
    assert metrics["failed"] == 1


def test_normalizers_handle_ocr_noise() -> None:
    assert normalize_amount("$700 00") == 700.0
    assert normalize_amount("[5200.00 J") == 5200.0
    assert normalize_date("October 26, 1998") == "1998-10-26"
    assert classify_document_type("INVOICE TOTAL") == "invoice"
    assert (
        classify_document_type("POLITICAL CAMPAIGN CONTRIBUTION REQUEST")
        == "contribution"
    )
    assert clean_string(" Ã¢â‚¬ËœVendorÃ‚Â®  Name ") == "Vendor Name"


def test_gold_pipeline_writes_partitioned_parquet_outputs() -> None:
    test_dir = clean_test_dir("gold_pipeline")
    silver_dir = test_dir / "silver" / "valid"
    gold_dir = test_dir / "gold"
    silver_dir.mkdir(parents=True)
    (silver_dir / "invoice.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "source_s3_key": "raw/run_id=run-1/invoice.tif",
                "source_file_name": "invoice.tif",
                "document_type": "invoice",
                "document_id": "invoice",
                "document_date": "2024-05-13",
                "total_amount": 12.34,
                "vendor_name": "Acme",
                "currency": "USD",
                "extraction_engine": "local_tesseract",
                "normalization_engine": "local_ollama",
                "llm_model_id": "qwen",
                "processing_status": "accepted",
                "quality_status": "accepted",
                "quality_flags": [],
                "rejection_reason": None,
                "created_at": "2026-05-05T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    metrics = run_gold_pipeline(silver_dir=silver_dir, gold_dir=gold_dir, run_id="run-1")

    assert (gold_dir / "documents.parquet").exists()
    assert (gold_dir / "run_date=2026-05-05" / "documents.parquet").exists()
    assert metrics["currency_completion_rate"] == 1.0


def test_gold_mapping_builds_documents_table() -> None:
    documents = build_documents_table(
        [
            {
                "run_id": "run-1",
                "source_s3_key": "raw/run_id=run-1/invoice.tif",
                "source_file_name": "invoice.tif",
                "document_type": "invoice",
                "document_id": "invoice",
                "document_date": "5/13/94",
                "total_amount": "$481.58",
                "vendor_name": "Acme",
                "currency": "USD",
                "extraction_engine": "local_tesseract",
                "normalization_engine": "local_ollama",
                "llm_model_id": "qwen",
                "processing_status": "accepted",
                "quality_status": "warning",
                "quality_flags": ["currency_missing"],
                "rejection_reason": None,
                "created_at": "2026-05-05T00:00:00Z",
            }
        ]
    )

    assert len(documents) == 1
    assert documents.loc[0, "document_id"] == "invoice"
    assert documents.loc[0, "total_amount"] == 481.58


def test_configure_logging_writes_to_logs_dir(monkeypatch) -> None:
    test_dir = clean_test_dir("logging")
    monkeypatch.setattr(pipeline_logging, "LOGS_DIR", test_dir / "logs")

    pipeline_logging.configure_logging("test.log")
    logging.getLogger("test_logger").info("hello logs")
    logging.shutdown()

    assert (test_dir / "logs" / "test.log").read_text(encoding="utf-8")


def test_stress_pipeline_writes_summary(monkeypatch) -> None:
    test_dir = clean_test_dir("stress_pipeline")
    silver_dir = test_dir / "silver" / "valid"
    gold_dir = test_dir / "gold"
    logs_dir = test_dir / "logs"
    silver_dir.mkdir(parents=True)
    gold_dir.mkdir()
    (silver_dir / "sample.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "source_s3_key": "raw/run_id=run-1/sample.tif",
                "source_file_name": "sample.tif",
                "document_type": "unknown",
                "document_id": "sample",
                "document_date": "1998-09-11",
                "total_amount": 10.0,
                "vendor_name": "Acme",
                "currency": "USD",
                "extraction_engine": "local_tesseract",
                "normalization_engine": "local_ollama",
                "llm_model_id": "qwen",
                "processing_status": "accepted",
                "quality_status": "warning",
                "quality_flags": ["unknown_document_type"],
                "rejection_reason": None,
                "created_at": "2026-05-05T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame([{"document_id": "sample"}]).to_parquet(
        gold_dir / "documents.parquet", index=False
    )

    monkeypatch.setattr(
        stress_pipeline,
        "load_pipeline_config",
        lambda: {
            "execution_mode": "local",
            "paths": {
                "raw_dir": str(test_dir / "raw"),
                "bronze_dir": str(test_dir / "bronze"),
                "silver_dir": str(test_dir / "silver"),
                "silver_valid_dir": str(silver_dir),
                "silver_rejected_dir": str(test_dir / "silver" / "rejected"),
                "gold_dir": str(gold_dir),
                "errors_dir": str(test_dir / "errors"),
                "silver_failed_dir": str(test_dir / "errors" / "silver_failed"),
                "logs_dir": str(logs_dir),
            },
            "run": {
                "id_prefix": "invoice-pipeline",
                "manifest_dir": str(logs_dir / "runs"),
                "reference_manifest_path": str(
                    Path("tests/fixtures/reference_documents.yaml")
                ),
            },
            "stress": {"summary_path": str(logs_dir / "stress_summary.json")},
        },
    )
    monkeypatch.setattr(
        stress_pipeline,
        "run_bronze_pipeline",
        lambda *args, **kwargs: {
            "total": 1,
            "succeeded": 1,
            "failed": 0,
            "success_rate": 1,
            "elapsed_seconds": 0.1,
            "durations": [0.1],
        },
    )
    monkeypatch.setattr(
        stress_pipeline,
        "run_silver_pipeline",
        lambda *args, **kwargs: {
            "total": 1,
            "succeeded": 1,
            "rejected": 0,
            "failed": 0,
            "success_rate": 1,
            "elapsed_seconds": 0.2,
            "durations": [0.2],
        },
    )
    monkeypatch.setattr(
        stress_pipeline, "run_gold_pipeline", lambda *args, **kwargs: {"rows": 1}
    )

    summary = stress_pipeline.run_stress_pipeline(limit=100)

    assert summary["limit"] == 100
    assert summary["phase_metrics"]["bronze"]["succeeded"] == 1
    assert summary["doc_latency_stats"]["silver"]["p95"] == 0.2
    assert summary["silver_quality"]["completion_rates"]["total_amount"] == 1
    assert summary["silver_quality"]["flag_counts"]["unknown_document_type"] == 1
    assert (logs_dir / "stress_summary.json").exists()


def test_supported_image_extensions_with_real_file(monkeypatch) -> None:
    test_dir = clean_test_dir("ocr")
    image_path = test_dir / "sample.tif"
    Image.new("RGB", (10, 10), color="white").save(image_path)

    monkeypatch.setattr(
        "src.pipeline.ocr.pytesseract.image_to_string", lambda image: " A \n\n B "
    )

    from src.pipeline.ocr import clean_text as ocr_clean_text
    from src.pipeline.ocr import ocr_extract

    assert ocr_clean_text(" A \n\n B ") == "A\nB"
    assert ocr_extract(image_path) == "A\nB"
