from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

PIPELINE_CONFIG_PATH = Path("src/config/pipeline.yaml")

DEFAULT_PIPELINE_CONFIG: dict[str, Any] = {
    "paths": {
        "raw_dir": "data/raw",
        "bronze_dir": "data/bronze",
        "silver_dir": "data/silver",
        "gold_dir": "data/gold",
        "errors_dir": "data/errors",
        "silver_errors_dir": "data/errors/silver",
        "logs_dir": "logs",
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
    "quality": {
        "critical_fields": ["document_id", "source_file", "raw_text_path"],
        "measured_fields": ["total_amount", "document_date", "vendor_or_requester"],
        "advisory_flags": [
            "missing_total_amount",
            "missing_document_date",
            "missing_vendor_or_requester",
            "invalid_total_amount",
            "invalid_document_date",
            "unknown_document_type",
        ],
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
