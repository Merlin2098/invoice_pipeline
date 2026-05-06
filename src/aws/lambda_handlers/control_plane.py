from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.config.pipeline_config import load_pipeline_config


def validate_input(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    config = load_pipeline_config()
    supported = {
        extension.lower()
        for extension in config["ocr"]["supported_extensions"]
    }
    source_s3_key = str(event.get("source_s3_key") or "")
    source_file_name = str(event.get("source_file_name") or Path(source_s3_key).name)
    extension = Path(source_file_name).suffix.lower()

    errors: list[str] = []
    if not event.get("run_id"):
        errors.append("missing_run_id")
    if not source_s3_key:
        errors.append("missing_source_s3_key")
    if extension not in supported:
        errors.append("unsupported_extension")

    return {
        "valid": not errors,
        "errors": errors,
        "run_id": event.get("run_id"),
        "source_s3_key": source_s3_key,
        "source_file_name": source_file_name,
    }


def publish_run_metrics(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    namespace = os.getenv("CLOUDWATCH_NAMESPACE", "InvoicePipeline")
    metrics = list(event.get("metrics") or [])
    published = False

    try:
        import boto3  # type: ignore
    except ImportError:
        boto3 = None  # type: ignore

    if boto3 is not None and metrics:
        client = boto3.client("cloudwatch")
        client.put_metric_data(
            Namespace=namespace,
            MetricData=metrics,
        )
        published = True

    return {
        "published": published,
        "namespace": namespace,
        "metric_count": len(metrics),
        "run_id": event.get("run_id"),
    }
