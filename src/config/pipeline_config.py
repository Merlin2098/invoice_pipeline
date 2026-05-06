from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

PIPELINE_CONFIG_PATH = Path("src/config/pipeline.yaml")

DEFAULT_PIPELINE_CONFIG: dict[str, Any] = {
    "execution_mode": "local",
    "paths": {
        "raw_dir": "data/raw",
        "bronze_dir": "data/bronze",
        "silver_dir": "data/silver",
        "silver_valid_dir": "data/silver/valid",
        "silver_rejected_dir": "data/silver/rejected",
        "gold_dir": "data/gold",
        "errors_dir": "data/errors",
        "silver_failed_dir": "data/errors/silver_failed",
        "metrics_dir": "logs/runs",
        "logs_dir": "logs",
    },
    "run": {
        "id_prefix": "invoice-pipeline",
        "manifest_dir": "logs/runs",
        "reference_manifest_path": "tests/fixtures/reference_documents.yaml",
        "retention_days": 30,
    },
    "ocr": {
        "supported_extensions": [".png", ".jpg", ".jpeg", ".tif", ".tiff"],
    },
    "llm": {
        "base_url": "http://localhost:11434",
        "model": "qwen3.5:4b",
        "timeout_seconds": 60,
        "num_predict": 800,
        "retries": 1,
        "concurrency": 1,
    },
    "aws": {
        "region": "us-east-1",
        "bucket": None,
        "artifact_bucket": None,
        "raw_prefix": "raw",
        "bronze_prefix": "bronze/textract-json",
        "silver_valid_prefix": "silver/valid",
        "silver_rejected_prefix": "silver/rejected",
        "gold_prefix": "gold/documents",
        "metrics_prefix": "metrics",
        "textract_feature_type": "AnalyzeExpense",
        "bedrock_model_id": "bedrock-model-id",
        "bedrock_enabled": True,
        "step_functions_state_machine": "invoice-pipeline-dev",
        "glue_jobs": {
            "normalize": "invoice-pipeline-normalize-dev",
            "consolidate": "invoice-pipeline-consolidate-dev",
        },
        "lambda_handlers": {
            "prevalidation": "invoice-pipeline-prevalidation-dev",
            "publish_metrics": "invoice-pipeline-publish-metrics-dev",
        },
        "cloudwatch": {
            "log_group": "/aws/invoice-pipeline/dev",
            "namespace": "InvoicePipeline",
        },
    },
    "quality": {
        "critical_fields": [
            "run_id",
            "document_id",
            "source_s3_key",
            "source_file_name",
            "extraction_engine",
            "created_at",
        ],
        "measured_fields": ["total_amount", "document_date", "vendor_name"],
        "advisory_flags": [
            "missing_total_amount",
            "missing_document_date",
            "vendor_missing",
            "invalid_total_amount",
            "invalid_document_date",
            "unknown_document_type",
        ],
        "spec_path": "specs/quality/bronze_to_silver_rules.yaml",
    },
    "stress": {
        "default_limit": None,
        "summary_path": "logs/stress_summary.json",
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_pipeline_config(config_path: Path = PIPELINE_CONFIG_PATH) -> dict[str, Any]:
    if not config_path.exists():
        return deepcopy(DEFAULT_PIPELINE_CONFIG)

    with config_path.open(encoding="utf-8") as file:
        loaded = yaml.safe_load(file) or {}

    if not isinstance(loaded, dict):
        raise ValueError(f"Pipeline config must be a YAML object: {config_path}")

    return _deep_merge(DEFAULT_PIPELINE_CONFIG, loaded)


def config_path(config: dict[str, Any], key: str) -> Path:
    return Path(str(config["paths"][key]))
