import json
import logging
import shutil
from pathlib import Path

import yaml
from PIL import Image

import run_pipeline
from src.pipeline import llm_ollama
from src.pipeline.bronze_pipeline import run_bronze_pipeline
from src.pipeline.gold_model import build_tables, normalize_amount, normalize_date, run_gold_pipeline
from src.pipeline.ocr import clean_text, ocr_extract
from src.pipeline.silver_pipeline import process_with_llm
from src.pipeline.silver_pipeline import run_silver_pipeline
from src.utils import logging as pipeline_logging


TEST_ROOT = Path("data/test_tmp")


def clean_test_dir(name: str) -> Path:
    path = TEST_ROOT / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def test_data_contract_contains_required_groups() -> None:
    contract = yaml.safe_load(Path("src/config/data_contract.yaml").read_text(encoding="utf-8"))

    assert {"common", "invoice", "contribution"}.issubset(contract)
    assert "Original source files loaded into data/raw" in contract["contract"]["medallion_layers"]["raw"]
    assert "Plain OCR text files generated from raw files" in contract["contract"]["medallion_layers"]["bronze"]
    assert contract["common"]["document_id"]["nullable"] is False
    assert contract["invoice"]["amount_due"]["type"] == "float"
    assert contract["contribution"]["party"]["type"] == "string"


def test_raw_to_bronze_ocr_helpers_support_tif(monkeypatch) -> None:
    test_dir = clean_test_dir("ocr")
    image_path = test_dir / "sample.tif"
    Image.new("RGB", (10, 10), color="white").save(image_path)

    monkeypatch.setattr("src.pipeline.ocr.pytesseract.image_to_string", lambda image: " A \n\n B ")

    assert clean_text(" A \n\n B ") == "A\nB"
    assert ocr_extract(image_path) == "A\nB"


def test_bronze_pipeline_reads_raw_and_writes_bronze(monkeypatch) -> None:
    test_dir = clean_test_dir("bronze_pipeline")
    raw_dir = test_dir / "raw"
    bronze_dir = test_dir / "bronze"
    raw_dir.mkdir()
    (raw_dir / "invoice.tif").write_text("fake image bytes", encoding="utf-8")

    monkeypatch.setattr("src.pipeline.bronze_pipeline.ocr_extract", lambda path: f"OCR for {path.stem}")

    run_bronze_pipeline(raw_dir=raw_dir, bronze_dir=bronze_dir)

    assert (bronze_dir / "invoice.txt").read_text(encoding="utf-8") == "OCR for invoice"


def test_root_pipeline_runs_phases_in_order(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(run_pipeline, "run_bronze_pipeline", lambda: calls.append("bronze"))
    monkeypatch.setattr(run_pipeline, "run_silver_pipeline", lambda: calls.append("silver"))
    monkeypatch.setattr(run_pipeline, "run_gold_pipeline", lambda: calls.append("gold"))

    run_pipeline.run_pipeline()

    assert calls == ["bronze", "silver", "gold"]


def test_configure_logging_writes_to_logs_dir(monkeypatch) -> None:
    test_dir = clean_test_dir("logging")
    monkeypatch.setattr(pipeline_logging, "LOGS_DIR", test_dir / "logs")

    pipeline_logging.configure_logging("test.log")
    logging.getLogger("test_logger").info("hello logs")
    logging.shutdown()

    assert (test_dir / "logs" / "test.log").read_text(encoding="utf-8")


def test_parse_json_response_handles_common_shapes() -> None:
    assert llm_ollama.parse_json_response('{"document_type": "invoice"}')["document_type"] == "invoice"
    assert (
        llm_ollama.parse_json_response('```json\n{"document_type": "contribution"}\n```')["document_type"]
        == "contribution"
    )
    assert llm_ollama.parse_json_response("")["ocr_confidence_flags"] == ["empty_llm_response"]
    assert llm_ollama.parse_json_response("not json")["ocr_confidence_flags"] == ["invalid_json_response"]


def test_silver_pipeline_writes_one_json_per_bronze_file(monkeypatch) -> None:
    test_dir = clean_test_dir("silver_pipeline")
    bronze_dir = test_dir / "bronze"
    silver_dir = test_dir / "silver"
    bronze_dir.mkdir()
    (bronze_dir / "sample.txt").write_text("INVOICE\nTOTAL $10.00", encoding="utf-8")

    def fake_extract(text: str) -> dict:
        assert "TOTAL" in text
        return {"document_type": "invoice", "amount": "$10.00", "ocr_confidence_flags": []}

    monkeypatch.setattr("src.pipeline.silver_pipeline.extract_structured_data", fake_extract)

    run_silver_pipeline(bronze_dir=bronze_dir, silver_dir=silver_dir, max_retries=0)

    output = json.loads((silver_dir / "sample.json").read_text(encoding="utf-8"))
    assert output["source_file"] == "sample.txt"
    assert output["document_id"] == "sample"
    assert output["recipient_name"] is None
    assert output["raw_text_path"].endswith("sample.txt")


def test_silver_pipeline_writes_output_by_document_id(monkeypatch) -> None:
    test_dir = clean_test_dir("silver_pipeline_document_id")
    bronze_dir = test_dir / "bronze"
    silver_dir = test_dir / "silver"
    bronze_dir.mkdir()
    (bronze_dir / "source_name.txt").write_text("POLITICAL CAMPAIGN CONTRIBUTION REQUEST", encoding="utf-8")

    monkeypatch.setattr(
        "src.pipeline.silver_pipeline.extract_structured_data",
        lambda text: {"document_id": "TI1712-0087", "document_type": "contribution"},
    )

    run_silver_pipeline(bronze_dir=bronze_dir, silver_dir=silver_dir, max_retries=0)

    assert (silver_dir / "TI1712-0087.json").exists()


def test_process_with_llm_retries_invalid_json(monkeypatch) -> None:
    responses = [
        {"ocr_confidence_flags": ["invalid_json_response"]},
        {"document_type": "invoice", "ocr_confidence_flags": []},
    ]

    monkeypatch.setattr("src.pipeline.silver_pipeline.extract_structured_data", lambda text: responses.pop(0))

    assert process_with_llm("INVOICE", max_retries=2)["document_type"] == "invoice"


def test_normalizers_handle_ocr_noise() -> None:
    assert normalize_amount("$700 00") == 700.0
    assert normalize_amount("[5200.00 J") == 5200.0
    assert normalize_date("October 26, 1998") == "1998-10-26"


def test_gold_mapping_builds_documents_and_child_tables() -> None:
    tables = build_tables(
        [
            {
                "source_file": "invoice.txt",
                "document_type": "invoice",
                "document_id": "invoice",
                "document_date": "5/13/94",
                "invoice_number": "27011",
                "amount_due": "$481.58",
                "ocr_confidence_flags": [],
            },
            {
                "source_file": "contribution.txt",
                "document_type": "contribution",
                "document_id": "contribution",
                "document_date": "9/11/98",
                "party": "Democrat",
                "amount": "$200.00",
                "ocr_confidence_flags": [],
            },
        ]
    )

    assert list(tables) == ["documents", "invoices", "contributions"]
    assert len(tables["documents"]) == 2
    assert len(tables["invoices"]) == 1
    assert len(tables["contributions"]) == 1
    assert tables["invoices"].iloc[0]["amount_due"] == 481.58


def test_gold_pipeline_writes_parquet_outputs() -> None:
    test_dir = clean_test_dir("gold_pipeline")
    silver_dir = test_dir / "silver"
    gold_dir = test_dir / "gold"
    silver_dir.mkdir()
    (silver_dir / "invoice.json").write_text(
        json.dumps(
            {
                "source_file": "invoice.txt",
                "document_type": "invoice",
                "document_id": "invoice",
                "invoice_number": "1",
                "amount_due": "$12.34",
                "ocr_confidence_flags": [],
            }
        ),
        encoding="utf-8",
    )

    run_gold_pipeline(silver_dir=silver_dir, gold_dir=gold_dir)

    assert (gold_dir / "documents.parquet").exists()
    assert (gold_dir / "invoices.parquet").exists()
    assert (gold_dir / "contributions.parquet").exists()
