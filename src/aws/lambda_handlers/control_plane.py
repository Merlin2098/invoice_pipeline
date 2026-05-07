from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus

from src.config.pipeline_config import load_pipeline_config
from src.pipeline.aws_runtime import AwsPipelineRequest, AwsPipelineRunner
from src.pipeline.quality import create_failed_document
from src.pipeline.run_context import build_storage_key

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _optional_boto3():
    try:
        import boto3  # type: ignore
    except Exception:
        return None
    return boto3


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _extract_run_id_from_key(source_s3_key: str) -> str | None:
    for part in Path(source_s3_key).as_posix().split("/"):
        if part.startswith("run_id="):
            run_id = part.split("=", maxsplit=1)[1].strip()
            if run_id:
                return run_id
    return None


def _fallback_run_id(prefix: str = "invoice-pipeline-aws") -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{timestamp}"


def _s3_event_records(event: dict[str, Any]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for record in event.get("Records", []) or []:
        if record.get("eventSource") != "aws:s3":
            continue
        bucket_name = str(record.get("s3", {}).get("bucket", {}).get("name") or "")
        source_s3_key = unquote_plus(
            str(record.get("s3", {}).get("object", {}).get("key") or "")
        )
        source_file_name = Path(source_s3_key).name
        records.append(
            {
                "bucket_name": bucket_name,
                "source_s3_key": source_s3_key,
                "source_file_name": source_file_name,
                "run_id": _extract_run_id_from_key(source_s3_key) or _fallback_run_id(),
                "created_at": _utc_now_iso(),
            }
        )
    return records


def _direct_record(event: dict[str, Any]) -> dict[str, str]:
    source_s3_key = str(event.get("source_s3_key") or "")
    source_file_name = str(event.get("source_file_name") or Path(source_s3_key).name)
    return {
        "bucket_name": str(event.get("bucket_name") or os.getenv("DATA_LAKE_BUCKET") or ""),
        "source_s3_key": source_s3_key,
        "source_file_name": source_file_name,
        "run_id": str(
            event.get("run_id")
            or _extract_run_id_from_key(source_s3_key)
            or _fallback_run_id()
        ),
        "created_at": str(event.get("created_at") or _utc_now_iso()),
    }


def _cloudwatch_metric(name: str, value: float, unit: str = "Count") -> dict[str, Any]:
    return {
        "MetricName": name,
        "Value": value,
        "Unit": unit,
    }


class S3JsonStore:
    def __init__(self, bucket_name: str) -> None:
        boto3 = _optional_boto3()
        if boto3 is None:
            raise RuntimeError("boto3 is required to write AWS pipeline outputs")
        self.bucket_name = bucket_name
        self.client = boto3.client("s3")

    def write_json(self, key: str, payload: dict[str, Any]) -> None:
        self.client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
            ContentType="application/json",
        )


class TextractAnalyzeExpenseClient:
    def __init__(self, bucket_name: str) -> None:
        boto3 = _optional_boto3()
        if boto3 is None:
            raise RuntimeError("boto3 is required to call Textract")
        self.bucket_name = bucket_name
        self.client = boto3.client("textract")

    def analyze_expense(self, source_s3_key: str) -> dict[str, Any]:
        response = self.client.analyze_expense(
            Document={
                "S3Object": {
                    "Bucket": self.bucket_name,
                    "Name": source_s3_key,
                }
            }
        )
        return json.loads(json.dumps(response, default=str))


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
        "created_at": event.get("created_at"),
    }


def start_raw_ingestion(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    records = _s3_event_records(event)
    if not records:
        records = [_direct_record(event)]

    state_machine_arn = _env("STATE_MACHINE_ARN")
    boto3 = _optional_boto3()
    if boto3 is None:
        raise RuntimeError("boto3 is required to start Step Functions executions")
    client = boto3.client("stepfunctions")

    executions: list[dict[str, str]] = []
    for index, record in enumerate(records):
        execution_name = f"{record['run_id']}-{Path(record['source_file_name']).stem}-{index}"
        sanitized_name = "".join(
            character if character.isalnum() or character in "-_" else "-"
            for character in execution_name
        )[:80]
        payload = {
            "run_id": record["run_id"],
            "source_s3_key": record["source_s3_key"],
            "source_file_name": record["source_file_name"],
            "created_at": record["created_at"],
            "bucket_name": record["bucket_name"],
        }
        response = client.start_execution(
            stateMachineArn=state_machine_arn,
            name=sanitized_name,
            input=json.dumps(payload),
        )
        executions.append(
            {
                "execution_arn": str(response["executionArn"]),
                "run_id": record["run_id"],
                "source_s3_key": record["source_s3_key"],
            }
        )
        logger.info(
            "Started Step Functions execution run_id=%s source_s3_key=%s execution_arn=%s",
            record["run_id"],
            record["source_s3_key"],
            response["executionArn"],
        )

    return {
        "started": len(executions),
        "executions": executions,
    }


def _process_output_key(
    *,
    silver_document: dict[str, Any],
    document_id: str,
    run_id: str,
    silver_valid_prefix: str,
    silver_rejected_prefix: str,
    errors_prefix: str,
) -> str:
    if silver_document.get("processing_status") == "failed":
        return build_storage_key(
            f"{errors_prefix.strip('/')}/silver_failed",
            run_id,
            f"{document_id}.json",
        )
    if silver_document.get("processing_status") == "rejected":
        return build_storage_key(silver_rejected_prefix, run_id, f"{document_id}.json")
    return build_storage_key(silver_valid_prefix, run_id, f"{document_id}.json")


def _build_metrics(document: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = [_cloudwatch_metric("DocumentsProcessed", 1)]
    status = str(document.get("processing_status") or "")
    if status == "accepted":
        metrics.append(_cloudwatch_metric("DocumentsAccepted", 1))
    elif status == "rejected":
        metrics.append(_cloudwatch_metric("DocumentsRejected", 1))
    elif status == "failed":
        metrics.append(_cloudwatch_metric("DocumentsFailed", 1))

    if document.get("vendor_name"):
        metrics.append(_cloudwatch_metric("VendorFieldPresent", 1))
    if document.get("document_date"):
        metrics.append(_cloudwatch_metric("DateFieldPresent", 1))
    if document.get("total_amount") is not None:
        metrics.append(_cloudwatch_metric("AmountFieldPresent", 1))
    if document.get("document_type") == "unknown":
        metrics.append(_cloudwatch_metric("UnknownDocumentType", 1))
    return metrics


def process_document(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    run_id = str(event.get("run_id") or "")
    source_s3_key = str(event.get("source_s3_key") or "")
    source_file_name = str(event.get("source_file_name") or Path(source_s3_key).name)
    created_at = str(event.get("created_at") or _utc_now_iso())
    data_lake_bucket = _env("DATA_LAKE_BUCKET")
    bronze_prefix = _env("BRONZE_PREFIX", "bronze/textract-json")
    silver_valid_prefix = _env("SILVER_VALID_PREFIX", "silver/valid")
    silver_rejected_prefix = _env("SILVER_REJECTED_PREFIX", "silver/rejected")
    errors_prefix = _env("ERRORS_PREFIX", "errors")

    object_store = S3JsonStore(data_lake_bucket)
    runner = AwsPipelineRunner(
        textract=TextractAnalyzeExpenseClient(data_lake_bucket),
        object_store=object_store,
        bedrock=None,
        bronze_prefix=bronze_prefix,
    )

    request = AwsPipelineRequest(
        run_id=run_id,
        source_s3_key=source_s3_key,
        source_file_name=source_file_name,
        created_at=created_at,
    )

    try:
        silver_document = runner.process_document(request)
    except Exception as exc:
        silver_document = create_failed_document(
            run_id=run_id,
            document_id=Path(source_file_name).stem,
            source_s3_key=source_s3_key,
            source_file_name=source_file_name,
            extraction_engine="textract_analyze_expense",
            normalization_engine="textract_only",
            llm_model_id=None,
            created_at=created_at,
            failure_flags=["textract_request_failed"],
        )
        logger.exception(
            "Document processing failed run_id=%s source_s3_key=%s error=%s",
            run_id,
            source_s3_key,
            exc,
        )

    output_key = _process_output_key(
        silver_document=silver_document,
        document_id=str(silver_document["document_id"]),
        run_id=run_id,
        silver_valid_prefix=silver_valid_prefix,
        silver_rejected_prefix=silver_rejected_prefix,
        errors_prefix=errors_prefix,
    )
    object_store.write_json(output_key, silver_document)
    metrics = _build_metrics(silver_document)

    return {
        "run_id": run_id,
        "source_s3_key": source_s3_key,
        "source_file_name": source_file_name,
        "document_id": silver_document["document_id"],
        "processing_status": silver_document["processing_status"],
        "quality_status": silver_document["quality_status"],
        "output_s3_key": output_key,
        "metrics": metrics,
    }


def publish_run_metrics(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    namespace = os.getenv("CLOUDWATCH_NAMESPACE", "InvoicePipeline")
    metrics = list(event.get("metrics") or [])
    published = False

    boto3 = _optional_boto3()

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
