from __future__ import annotations

import json
import os
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus

from src.aws.bedrock_client import BedrockNormalizerClient
from src.aws.logging_utils import get_logger
from src.config.pipeline_config import load_pipeline_config
from src.pipeline.aws_runtime import (
    AwsPipelineRequest,
    AwsPipelineRunner,
    extract_expense_candidates,
)
from src.pipeline.quality import create_failed_document
from src.pipeline.run_context import build_storage_key


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


def _document_id(source_file_name: str, source_s3_key: str = "") -> str:
    name = source_file_name or Path(source_s3_key).name
    return Path(name).stem


def _bound_logger(
    stage: str,
    event: dict[str, Any],
    *,
    document_id: str | None = None,
):
    return get_logger(stage).bind(
        run_id=event.get("run_id"),
        execution_id=event.get("execution_id"),
        document_id=document_id or event.get("document_id"),
        source_s3_key=event.get("source_s3_key"),
    )


def _dry_run_response(event: dict[str, Any], stage: str) -> dict[str, Any] | None:
    if not event.get("_dry_run"):
        return None

    identity: dict[str, Any] = {}
    boto3 = _optional_boto3()
    if boto3 is not None:
        identity = boto3.client("sts").get_caller_identity()

    logger = _bound_logger(stage, event)
    logger.info({"message": "Runtime access dry run succeeded", "status": "ok"})
    return {
        "dry_run": True,
        "stage": stage,
        "identity": identity,
    }


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
                "sqs_message_id": str(record.get("_sqs_message_id") or ""),
            }
        )
    return records


def _unwrap_sqs_records(event: dict[str, Any]) -> list[dict[str, Any]]:
    unwrapped: list[dict[str, Any]] = []
    logger = get_logger("raw_dispatch")
    for record in event.get("Records", []) or []:
        if record.get("eventSource") == "aws:sqs":
            try:
                body = json.loads(record.get("body") or "{}")
                for s3_record in body.get("Records", []):
                    s3_record["_sqs_message_id"] = record.get("messageId")
                    unwrapped.append(s3_record)
            except (json.JSONDecodeError, AttributeError):
                logger.warning(
                    {
                        "message": "Could not parse SQS record body",
                        "status": "warning",
                        "error_code": "invalid_sqs_body",
                    }
                )
        else:
            unwrapped.append(record)
    return unwrapped


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
        "sqs_message_id": str(event.get("sqs_message_id") or ""),
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
            raise RuntimeError("boto3 is required to access AWS pipeline outputs")
        self.bucket_name = bucket_name
        self.client = boto3.client("s3")

    def write_json(self, key: str, payload: dict[str, Any]) -> None:
        self.write_bytes(
            key,
            json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
            content_type="application/json",
        )

    def write_bytes(
        self,
        key: str,
        payload: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> None:
        self.client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=payload,
            ContentType=content_type,
        )

    def read_json(self, key: str) -> dict[str, Any]:
        response = self.client.get_object(Bucket=self.bucket_name, Key=key)
        body = response["Body"].read().decode("utf-8")
        return json.loads(body)

    def key_exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except self.client.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def list_json(self, prefix: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
            for item in page.get("Contents", []) or []:
                key = str(item.get("Key") or "")
                if key.endswith(".json"):
                    records.append(self.read_json(key))
        return records


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


class _NoopTextractClient:
    def analyze_expense(self, source_s3_key: str) -> dict[str, Any]:
        raise RuntimeError(f"Textract is not available in this stage: {source_s3_key}")


def validate_input(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    dry_run = _dry_run_response(event, "validate_input")
    if dry_run is not None:
        return dry_run

    config = load_pipeline_config()
    supported = {
        extension.lower()
        for extension in config["ocr"]["supported_extensions"]
    }
    source_s3_key = str(event.get("source_s3_key") or "")
    source_file_name = str(event.get("source_file_name") or Path(source_s3_key).name)
    extension = Path(source_file_name).suffix.lower()
    document_id = _document_id(source_file_name, source_s3_key)
    logger = _bound_logger("validate_input", event, document_id=document_id)

    errors: list[str] = []
    if not event.get("run_id"):
        errors.append("missing_run_id")
    if not source_s3_key:
        errors.append("missing_source_s3_key")
    if extension not in supported:
        errors.append("unsupported_extension")

    result = {
        "valid": not errors,
        "errors": errors,
        "run_id": event.get("run_id"),
        "execution_id": event.get("execution_id"),
        "source_s3_key": source_s3_key,
        "source_file_name": source_file_name,
        "created_at": event.get("created_at"),
    }

    data_lake_bucket = os.getenv("DATA_LAKE_BUCKET")
    if data_lake_bucket and result["valid"] and document_id:
        try:
            _write_status(
                S3JsonStore(data_lake_bucket),
                invoice_id=document_id,
                run_id=str(event.get("run_id") or ""),
                status="Processing",
            )
        except Exception:
            pass  # status write is best-effort; never fail the pipeline

    logger.info(
        {
            "message": "Input validation completed",
            "status": "accepted" if result["valid"] else "rejected",
        }
    )
    return result


def start_raw_ingestion(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    dry_run = _dry_run_response(event, "raw_dispatch")
    if dry_run is not None:
        return dry_run

    records = _s3_event_records({"Records": _unwrap_sqs_records(event)})
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
            "execution_id": sanitized_name,
            "source_s3_key": record["source_s3_key"],
            "source_file_name": record["source_file_name"],
            "created_at": record["created_at"],
            "bucket_name": record["bucket_name"],
            "sqs_message_id": record["sqs_message_id"],
        }
        response = client.start_execution(
            stateMachineArn=state_machine_arn,
            name=sanitized_name,
            input=json.dumps(payload),
        )
        executions.append(
            {
                "execution_arn": str(response["executionArn"]),
                "execution_id": sanitized_name,
                "run_id": record["run_id"],
                "source_s3_key": record["source_s3_key"],
            }
        )
        get_logger("raw_dispatch").bind(
            run_id=record["run_id"],
            execution_id=sanitized_name,
            document_id=_document_id(record["source_file_name"]),
            source_s3_key=record["source_s3_key"],
        ).info(
            {
                "message": "Started Step Functions execution",
                "status": "started",
            }
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


def _request_from_event(event: dict[str, Any]) -> AwsPipelineRequest:
    source_s3_key = str(event.get("source_s3_key") or "")
    return AwsPipelineRequest(
        run_id=str(event.get("run_id") or ""),
        source_s3_key=source_s3_key,
        source_file_name=str(event.get("source_file_name") or Path(source_s3_key).name),
        created_at=str(event.get("created_at") or _utc_now_iso()),
    )


def _silver_prefixes() -> dict[str, str]:
    return {
        "silver_valid_prefix": _env("SILVER_VALID_PREFIX", "silver/valid"),
        "silver_rejected_prefix": _env("SILVER_REJECTED_PREFIX", "silver/rejected"),
        "errors_prefix": _env("ERRORS_PREFIX", "errors"),
    }


def _write_final_document(
    *,
    object_store: S3JsonStore,
    silver_document: dict[str, Any],
    request: AwsPipelineRequest,
) -> dict[str, Any]:
    output_key = _process_output_key(
        silver_document=silver_document,
        document_id=str(silver_document["document_id"]),
        run_id=request.run_id,
        **_silver_prefixes(),
    )
    object_store.write_json(output_key, silver_document)
    metrics = _build_metrics(silver_document)
    return {
        "run_id": request.run_id,
        "source_s3_key": request.source_s3_key,
        "source_file_name": request.source_file_name,
        "document_id": silver_document["document_id"],
        "processing_status": silver_document["processing_status"],
        "quality_status": silver_document["quality_status"],
        "output_s3_key": output_key,
        "metrics": metrics,
    }


def _silver_valid_key(request: AwsPipelineRequest) -> str:
    return build_storage_key(
        _env("SILVER_VALID_PREFIX", "silver/valid"),
        request.run_id,
        f"{_document_id(request.source_file_name, request.source_s3_key)}.json",
    )


def _s3_key_exists(bucket_name: str, key: str) -> bool:
    boto3 = _optional_boto3()
    if boto3 is None:
        return False
    client = boto3.client("s3")
    try:
        client.head_object(Bucket=bucket_name, Key=key)
        return True
    except client.exceptions.ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def _bedrock_client() -> BedrockNormalizerClient | None:
    bedrock_model_id = os.environ.get("BEDROCK_MODEL_ID")
    return BedrockNormalizerClient(bedrock_model_id) if bedrock_model_id else None


def process_document(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    dry_run = _dry_run_response(event, "process_document")
    if dry_run is not None:
        return dry_run

    request = _request_from_event(event)
    execution_id = str(event.get("execution_id") or "")
    document_id = _document_id(request.source_file_name, request.source_s3_key)
    logger = _bound_logger("process_document", event, document_id=document_id)
    data_lake_bucket = _env("DATA_LAKE_BUCKET")
    bronze_prefix = _env("BRONZE_PREFIX", "bronze/textract-json")
    silver_valid_key = _silver_valid_key(request)

    if _s3_key_exists(data_lake_bucket, silver_valid_key):
        logger.info({"message": "Skipping already-processed document", "status": "skipped"})
        return {
            "run_id": request.run_id,
            "execution_id": execution_id,
            "source_s3_key": request.source_s3_key,
            "source_file_name": request.source_file_name,
            "document_id": document_id,
            "processing_status": "skipped",
            "quality_status": "skipped",
            "output_s3_key": silver_valid_key,
            "metrics": [],
        }

    object_store = S3JsonStore(data_lake_bucket)
    runner = AwsPipelineRunner(
        textract=TextractAnalyzeExpenseClient(data_lake_bucket),
        object_store=object_store,
        bedrock=_bedrock_client(),
        bedrock_model_id=os.environ.get("BEDROCK_MODEL_ID"),
        bronze_prefix=bronze_prefix,
        logger_adapter=logger,
    )

    try:
        silver_document = runner.process_document(request)
    except Exception as exc:
        silver_document = create_failed_document(
            run_id=request.run_id,
            document_id=document_id,
            source_s3_key=request.source_s3_key,
            source_file_name=request.source_file_name,
            extraction_engine="textract_analyze_expense",
            normalization_engine="textract_only",
            llm_model_id=None,
            created_at=request.created_at,
            failure_flags=["textract_request_failed"],
        )
        logger.exception(
            {
                "message": "Document processing failed",
                "status": "failed",
                "error_code": exc.__class__.__name__,
            }
        )

    result = _write_final_document(
        object_store=object_store,
        silver_document=silver_document,
        request=request,
    )
    result["execution_id"] = execution_id
    logger.info(
        {
            "message": "Document processing completed",
            "status": result["processing_status"],
        }
    )
    return result


def extract_ocr(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    dry_run = _dry_run_response(event, "extract_ocr")
    if dry_run is not None:
        return dry_run

    request = _request_from_event(event)
    execution_id = str(event.get("execution_id") or "")
    document_id = _document_id(request.source_file_name, request.source_s3_key)
    logger = _bound_logger("extract_ocr", event, document_id=document_id)
    data_lake_bucket = _env("DATA_LAKE_BUCKET")
    bronze_prefix = _env("BRONZE_PREFIX", "bronze/textract-json")
    silver_valid_key = _silver_valid_key(request)

    if _s3_key_exists(data_lake_bucket, silver_valid_key):
        logger.info({"message": "Skipping already-processed document", "status": "skipped"})
        return {
            "run_id": request.run_id,
            "execution_id": execution_id,
            "source_s3_key": request.source_s3_key,
            "source_file_name": request.source_file_name,
            "document_id": document_id,
            "processing_status": "skipped",
            "quality_status": "skipped",
            "output_s3_key": silver_valid_key,
            "metrics": [],
        }

    object_store = S3JsonStore(data_lake_bucket)
    runner = AwsPipelineRunner(
        textract=TextractAnalyzeExpenseClient(data_lake_bucket),
        object_store=object_store,
        bedrock=None,
        bronze_prefix=bronze_prefix,
        logger_adapter=logger,
    )
    ocr_result = runner.run_ocr(request)
    failed_document = ocr_result.get("failed_document")
    if failed_document:
        result = _write_final_document(
            object_store=object_store,
            silver_document=failed_document,
            request=request,
        )
        result["execution_id"] = execution_id
        logger.info({"message": "OCR extraction failed", "status": "failed"})
        return result

    logger.info({"message": "OCR extraction completed", "status": "extracted"})
    return {
        "run_id": request.run_id,
        "execution_id": execution_id,
        "source_s3_key": request.source_s3_key,
        "source_file_name": request.source_file_name,
        "document_id": ocr_result["document_id"],
        "bronze_s3_key": ocr_result["bronze_s3_key"],
        "candidate": ocr_result["candidate"],
        "processing_status": ocr_result["processing_status"],
        "metrics": [],
    }


def enrich_with_llm(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    dry_run = _dry_run_response(event, "enrich_with_llm")
    if dry_run is not None:
        return dry_run

    request = _request_from_event(event)
    execution_id = str(event.get("execution_id") or "")
    document_id = _document_id(request.source_file_name, request.source_s3_key)
    logger = _bound_logger("enrich_with_llm", event, document_id=document_id)
    data_lake_bucket = _env("DATA_LAKE_BUCKET")
    bronze_prefix = _env("BRONZE_PREFIX", "bronze/textract-json")
    bronze_key = str(
        event.get("bronze_s3_key")
        or build_storage_key(bronze_prefix, request.run_id, f"{document_id}.json")
    )
    object_store = S3JsonStore(data_lake_bucket)
    candidate = event.get("candidate")

    if not isinstance(candidate, dict):
        bronze_record = object_store.read_json(bronze_key)
        if bronze_record.get("status") == "failed":
            silver_document = create_failed_document(
                run_id=request.run_id,
                document_id=document_id,
                source_s3_key=request.source_s3_key,
                source_file_name=request.source_file_name,
                extraction_engine="textract_analyze_expense",
                normalization_engine="textract_only",
                llm_model_id=None,
                created_at=request.created_at,
                failure_flags=["textract_request_failed"],
            )
        else:
            candidate = extract_expense_candidates(
                dict(bronze_record.get("textract_response") or {})
            )
            runner = AwsPipelineRunner(
                textract=_NoopTextractClient(),
                object_store=object_store,
                bedrock=_bedrock_client(),
                bedrock_model_id=os.environ.get("BEDROCK_MODEL_ID"),
                bronze_prefix=bronze_prefix,
                logger_adapter=logger,
            )
            silver_document = runner.run_enrichment(
                request,
                candidate=candidate,
                bronze_key=bronze_key,
            )
    else:
        runner = AwsPipelineRunner(
            textract=_NoopTextractClient(),
            object_store=object_store,
            bedrock=_bedrock_client(),
            bedrock_model_id=os.environ.get("BEDROCK_MODEL_ID"),
            bronze_prefix=bronze_prefix,
            logger_adapter=logger,
        )
        silver_document = runner.run_enrichment(
            request,
            candidate=dict(candidate),
            bronze_key=bronze_key,
        )

    result = _write_final_document(
        object_store=object_store,
        silver_document=silver_document,
        request=request,
    )
    result["execution_id"] = execution_id

    # Accepted documents proceed to ConsolidateGold in the state machine, which
    # writes the final Completed status. Rejected/failed paths skip consolidation
    # and remain terminal here.
    terminal_status = "Consolidating" if result["processing_status"] in ("accepted",) else "Failed"
    try:
        _write_status(
            object_store,
            invoice_id=str(silver_document.get("document_id") or document_id),
            run_id=request.run_id,
            status=terminal_status,
        )
    except Exception:
        pass  # status write is best-effort; never fail the pipeline

    logger.info(
        {
            "message": "LLM enrichment completed",
            "status": result["processing_status"],
        }
    )
    return result


def publish_run_metrics(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    dry_run = _dry_run_response(event, "publish_metrics")
    if dry_run is not None:
        return dry_run

    namespace = os.getenv("CLOUDWATCH_NAMESPACE", "InvoicePipeline")
    metrics = list(event.get("metrics") or [])
    published = False
    logger = _bound_logger("publish_metrics", event)

    boto3 = _optional_boto3()

    if boto3 is not None and metrics:
        client = boto3.client("cloudwatch")
        client.put_metric_data(
            Namespace=namespace,
            MetricData=metrics,
        )
        published = True

    logger.info(
        {
            "message": "Run metrics publish completed",
            "status": "published" if published else "skipped",
        }
    )
    return {
        "published": published,
        "namespace": namespace,
        "metric_count": len(metrics),
        "run_id": event.get("run_id"),
        "execution_id": event.get("execution_id"),
    }


STATUS_PREFIX = "status"
_MAX_FILES_PER_UPLOAD = 10
_MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB
_PRESIGN_TTL_SECONDS = 300
_DEFAULT_UPLOAD_ALLOWED_EXTENSIONS = ".pdf,.tif,.tiff"
_DEFAULT_UPLOAD_ALLOWED_CONTENT_TYPES = (
    "application/pdf,image/tiff,image/tif,application/octet-stream"
)


def _csv_env_set(name: str, default: str) -> set[str]:
    return {
        item.strip().lower()
        for item in os.getenv(name, default).split(",")
        if item.strip()
    }


def _allowed_upload_extensions() -> set[str]:
    return _csv_env_set("UPLOAD_ALLOWED_EXTENSIONS", _DEFAULT_UPLOAD_ALLOWED_EXTENSIONS)


def _allowed_upload_content_types() -> set[str]:
    return _csv_env_set(
        "UPLOAD_ALLOWED_CONTENT_TYPES",
        _DEFAULT_UPLOAD_ALLOWED_CONTENT_TYPES,
    )


def _write_status(
    object_store: S3JsonStore,
    *,
    invoice_id: str,
    run_id: str,
    status: str,
) -> None:
    key = f"{STATUS_PREFIX}/{invoice_id}.json"
    object_store.write_json(
        key,
        {
            "invoice_id": invoice_id,
            "run_id": run_id,
            "status": status,
            "updated_at": _utc_now_iso(),
        },
    )


def generate_upload_urls(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if isinstance(event.get("body"), str):
        try:
            body = json.loads(event["body"])
        except json.JSONDecodeError:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "invalid_request", "message": "Request body is not valid JSON."}),
            }
    elif isinstance(event.get("body"), dict):
        body = event["body"]
    else:
        body = event

    files = body.get("files") or []
    if not isinstance(files, list) or not files:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "invalid_request", "message": "files must be a non-empty array."}),
        }
    if len(files) > _MAX_FILES_PER_UPLOAD:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "invalid_request", "message": f"Maximum {_MAX_FILES_PER_UPLOAD} files per request."}),
        }

    allowed_extensions = _allowed_upload_extensions()
    allowed_content_types = _allowed_upload_content_types()

    for file_entry in files:
        file_name = str(file_entry.get("name") or "").strip()
        extension = Path(file_name).suffix.lower()
        content_type = str(file_entry.get("content_type") or "").strip().lower()
        if not file_name or extension not in allowed_extensions:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "unsupported_file_type", "message": "only PDF and TIFF invoice files are accepted."}),
            }
        if content_type not in allowed_content_types:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "unsupported_file_type", "message": "unsupported content_type for invoice upload."}),
            }
        size_bytes = file_entry.get("size_bytes")
        if isinstance(size_bytes, (int, float)) and int(size_bytes) > _MAX_FILE_SIZE_BYTES:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "invalid_request", "message": "file size exceeds 20 MB limit."}),
            }

    boto3 = _optional_boto3()
    if boto3 is None:
        raise RuntimeError("boto3 is required for presigned URL generation")

    data_lake_bucket = _env("DATA_LAKE_BUCKET")
    raw_prefix = _env("RAW_PREFIX", "raw")
    run_id = _fallback_run_id()
    s3_client = boto3.client("s3")
    object_store = S3JsonStore(data_lake_bucket)

    uploads = []
    for file_entry in files:
        file_name = str(file_entry.get("name") or "")
        content_type = str(file_entry.get("content_type") or "").strip().lower()
        invoice_id = Path(file_name).stem
        key = f"{raw_prefix}/run_id={run_id}/{file_name}"
        upload_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": data_lake_bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=_PRESIGN_TTL_SECONDS,
        )
        _write_status(object_store, invoice_id=invoice_id, run_id=run_id, status="Uploaded")
        uploads.append({
            "name": file_name,
            "upload_url": upload_url,
            "key": key,
            "expires_in_seconds": _PRESIGN_TTL_SECONDS,
        })

    get_logger("upload").bind(run_id=run_id).info({
        "message": "Presigned upload URLs generated",
        "status": "generated",
        "file_count": len(uploads),
    })
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"run_id": run_id, "uploads": uploads}),
    }


def get_invoice_status(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    path_parameters = event.get("pathParameters") or {}
    invoice_id = str(path_parameters.get("invoice_id") or "").strip()
    if not invoice_id:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "invalid_request", "message": "invoice_id is required."}),
        }

    data_lake_bucket = _env("DATA_LAKE_BUCKET")
    object_store = S3JsonStore(data_lake_bucket)
    key = f"{STATUS_PREFIX}/{invoice_id}.json"
    try:
        record = object_store.read_json(key)
    except Exception as exc:
        error_code = getattr(getattr(exc, "response", None), "get", lambda k, d=None: d)("Error", {}).get("Code", "")
        if error_code in ("404", "NoSuchKey", "NotFound") or "NoSuchKey" in str(exc):
            return {
                "statusCode": 404,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "not_found", "message": "invoice not found."}),
            }
        raise

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(record),
    }


def list_invoices(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    query = event.get("queryStringParameters") or {}
    status_filter = str(query.get("status") or "").strip() or None
    try:
        limit = min(int(query.get("limit") or 20), 100)
    except (ValueError, TypeError):
        limit = 20
    next_token = str(query.get("next_token") or "").strip() or None

    data_lake_bucket = _env("DATA_LAKE_BUCKET")
    boto3 = _optional_boto3()
    if boto3 is None:
        raise RuntimeError("boto3 is required to list invoices")

    s3_client = boto3.client("s3")
    list_kwargs: dict[str, Any] = {
        "Bucket": data_lake_bucket,
        "Prefix": f"{STATUS_PREFIX}/",
        "MaxKeys": limit,
    }
    if next_token:
        list_kwargs["ContinuationToken"] = next_token

    page = s3_client.list_objects_v2(**list_kwargs)
    object_store = S3JsonStore(data_lake_bucket)
    invoices = []
    for item in page.get("Contents") or []:
        key = str(item.get("Key") or "")
        if not key.endswith(".json"):
            continue
        try:
            record = object_store.read_json(key)
        except Exception:
            continue
        if status_filter and record.get("status") != status_filter:
            continue
        invoices.append(record)

    response_next_token = None
    if page.get("IsTruncated"):
        response_next_token = page.get("NextContinuationToken")

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"invoices": invoices, "next_token": response_next_token}),
    }


_MAX_QUESTION_CHARS = 500
_CHAT_RESULT_ROW_CAP = 50
_SUMMARIZATION_MAX_TOKENS = 512


def _summarize_results(
    bedrock_client: Any,
    model_id: str,
    question: str,
    sql: str,
    rows: list[dict[str, Any]],
) -> str:
    rows_text = json.dumps(rows[:_CHAT_RESULT_ROW_CAP], ensure_ascii=False)
    user_message = (
        f"The user asked: {question}\n\n"
        f"The SQL executed was:\n{sql}\n\n"
        f"The Athena result rows (up to {_CHAT_RESULT_ROW_CAP}):\n{rows_text}\n\n"
        "Write a concise business-friendly answer in one or two sentences. "
        "Include relevant numbers and currency if present. "
        "Do not mention SQL or technical details."
    )
    response = bedrock_client.converse(
        modelId=model_id,
        system=[{"text": "You are a helpful analytics assistant that summarizes data query results in plain business language."}],
        messages=[{"role": "user", "content": [{"text": user_message}]}],
        inferenceConfig={"maxTokens": _SUMMARIZATION_MAX_TOKENS, "temperature": 0},
    )
    return str(response["output"]["message"]["content"][0]["text"]).strip()


def chat(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    from src.analytics.bedrock_sql import BedrockSqlGenerator
    from src.analytics.athena_client import AthenaClient
    from src.analytics.sql_validator import SqlValidationError

    body: dict[str, Any] = {}
    if isinstance(event.get("body"), str):
        try:
            body = json.loads(event["body"])
        except json.JSONDecodeError:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "invalid_request", "message": "Request body is not valid JSON."}),
            }
    elif isinstance(event.get("body"), dict):
        body = event["body"]
    else:
        body = event

    question = str(body.get("question") or "").strip()
    if not question:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "invalid_request", "message": "question is required."}),
        }
    if len(question) > _MAX_QUESTION_CHARS:
        return {
            "statusCode": 422,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "invalid_request", "message": f"question must be {_MAX_QUESTION_CHARS} characters or less."}),
        }

    model_id = _env("BEDROCK_MODEL_ID")
    database = _env("GLUE_DATABASE", "invoice_pipeline_gold")
    athena_output = f"s3://{_env('DATA_LAKE_BUCKET')}/athena-results/"
    workgroup = _env("ATHENA_WORKGROUP")
    aws_region = os.getenv("AWS_REGION", "us-east-1")

    boto3 = _optional_boto3()
    if boto3 is None:
        raise RuntimeError("boto3 is required for the chat handler")

    bedrock_client = boto3.client("bedrock-runtime", region_name=aws_region)
    logger = get_logger("chat").bind(user_question=question[:200])

    try:
        sql_generator = BedrockSqlGenerator(model_id=model_id, region=aws_region, client=bedrock_client)
        validated_sql = sql_generator.generate_sql(question)
    except SqlValidationError as exc:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "sql_validation_error", "message": str(exc)}),
        }

    athena = AthenaClient(
        database=database,
        output_location=athena_output,
        workgroup=workgroup,
        region=aws_region,
        poll_seconds=1.0,
        timeout_seconds=55.0,
    )

    try:
        result = athena.execute_validated_sql(validated_sql)
    except TimeoutError:
        return {
            "statusCode": 504,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "timeout", "message": "query did not complete within the time limit."}),
        }

    answer = _summarize_results(
        bedrock_client=bedrock_client,
        model_id=model_id,
        question=question,
        sql=result.sql,
        rows=result.rows,
    )

    logger.info({
        "message": "Chat query completed",
        "status": result.status,
        "query_id": result.query_id,
        "user_question": question[:200],
        "generated_sql": result.sql,
        "execution_time_ms": result.execution_time_ms,
        "athena_scan_mb": result.athena_scan_mb,
    })

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "answer": answer,
            "generated_sql": result.sql,
            "rows": result.rows,
            "query_id": result.query_id,
            "execution_time_ms": result.execution_time_ms,
            "athena_scan_mb": result.athena_scan_mb,
        }),
    }


def _normalize_expected_document(document: dict[str, Any]) -> dict[str, Any]:
    source_s3_key = str(document.get("source_s3_key") or "")
    source_file_name = str(
        document.get("source_file_name") or Path(source_s3_key).name
    )
    run_id = str(document.get("run_id") or "")
    document_id = str(
        document.get("document_id") or _document_id(source_file_name, source_s3_key)
    )
    if not run_id:
        raise ValueError("expected_documents entries must include run_id")
    if not document_id:
        raise ValueError("expected_documents entries must include document_id or file name")
    return {
        "run_id": run_id,
        "document_id": document_id,
        "source_s3_key": source_s3_key,
        "source_file_name": source_file_name,
    }


def _gold_prefixes() -> dict[str, str]:
    prefixes = _silver_prefixes()
    prefixes["gold_prefix"] = _env("GOLD_PREFIX", "gold/documents")
    prefixes["gold_manifest_prefix"] = _env("GOLD_MANIFEST_PREFIX", "gold/manifests")
    return prefixes


def _terminal_document_keys(
    *,
    run_id: str,
    document_id: str,
    silver_valid_prefix: str,
    silver_rejected_prefix: str,
    errors_prefix: str,
) -> dict[str, str]:
    return {
        "valid": build_storage_key(silver_valid_prefix, run_id, f"{document_id}.json"),
        "rejected": build_storage_key(
            silver_rejected_prefix,
            run_id,
            f"{document_id}.json",
        ),
        "failed": build_storage_key(
            f"{errors_prefix.strip('/')}/silver_failed",
            run_id,
            f"{document_id}.json",
        ),
    }


def _dataframe_to_parquet_bytes(documents: Any) -> bytes:
    buffer = BytesIO()
    documents.to_parquet(buffer, index=False)
    return buffer.getvalue()


def consolidate_gold(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    from src.pipeline.gold_model import build_documents_table

    dry_run = _dry_run_response(event, "consolidate_gold")
    if dry_run is not None:
        return dry_run

    batch_id = str(event.get("batch_id") or "").strip()
    if not batch_id:
        raise ValueError("Missing required field: batch_id")

    expected_documents_payload = event.get("expected_documents") or []
    if not isinstance(expected_documents_payload, list) or not expected_documents_payload:
        raise ValueError("expected_documents must be a non-empty list")

    expected_documents = [
        _normalize_expected_document(dict(document))
        for document in expected_documents_payload
    ]
    data_lake_bucket = str(event.get("data_lake_bucket") or _env("DATA_LAKE_BUCKET"))
    prefixes = _gold_prefixes()
    object_store = S3JsonStore(data_lake_bucket)
    logger = get_logger("consolidate_gold").bind(batch_id=batch_id)

    terminal: dict[str, list[dict[str, Any]]] = {
        "valid": [],
        "rejected": [],
        "failed": [],
    }
    valid_records: list[dict[str, Any]] = []
    missing_documents: list[dict[str, Any]] = []

    for document in expected_documents:
        keys = _terminal_document_keys(
            run_id=document["run_id"],
            document_id=document["document_id"],
            **{
                key: str(prefixes[key])
                for key in (
                    "silver_valid_prefix",
                    "silver_rejected_prefix",
                    "errors_prefix",
                )
            },
        )
        terminal_status = None
        terminal_key = None
        for status, key in keys.items():
            if object_store.key_exists(key):
                terminal_status = status
                terminal_key = key
                break

        if terminal_status is None or terminal_key is None:
            missing_documents.append(document)
            continue

        terminal[terminal_status].append({**document, "output_s3_key": terminal_key})
        if terminal_status == "valid":
            valid_records.append(object_store.read_json(terminal_key))

    if missing_documents:
        logger.info(
            {
                "message": "Gold batch incomplete",
                "status": "incomplete",
                "missing_count": len(missing_documents),
            }
        )
        return {
            "status": "incomplete",
            "batch_id": batch_id,
            "expected_count": len(expected_documents),
            "valid_count": len(terminal["valid"]),
            "rejected_count": len(terminal["rejected"]),
            "failed_count": len(terminal["failed"]),
            "missing_documents": missing_documents,
        }

    history_records = object_store.list_json(f"{prefixes['silver_valid_prefix'].strip('/')}/")
    documents = build_documents_table(valid_records, history_records=history_records)
    gold_row_count = int(len(documents))
    duplicate_count = (
        int(documents["is_duplicate"].fillna(False).sum())
        if "is_duplicate" in documents
        else 0
    )
    missing_date_count = (
        int(documents["document_date"].isna().sum())
        if "document_date" in documents
        else 0
    )
    missing_amount_count = (
        int(documents["total_amount"].isna().sum())
        if "total_amount" in documents
        else 0
    )
    bedrock_invoked_count = (
        int(documents["bedrock_invoked"].fillna(False).sum())
        if "bedrock_invoked" in documents
        else 0
    )
    gold_prefix = prefixes["gold_prefix"].strip("/")
    gold_manifest_prefix = prefixes["gold_manifest_prefix"].strip("/")
    parquet_key = f"{gold_prefix}/batch_id={batch_id}/documents.parquet"
    manifest_key = f"{gold_manifest_prefix}/batch_id={batch_id}/manifest.json"
    manifest = {
        "status": "completed",
        "batch_id": batch_id,
        "expected_count": len(expected_documents),
        "valid_count": len(terminal["valid"]),
        "rejected_count": len(terminal["rejected"]),
        "failed_count": len(terminal["failed"]),
        "gold_row_count": gold_row_count,
        "duplicate_count": duplicate_count,
        "missing_date_count": missing_date_count,
        "missing_amount_count": missing_amount_count,
        "date_completion_rate": (
            (gold_row_count - missing_date_count) / gold_row_count
            if gold_row_count
            else 0
        ),
        "amount_completion_rate": (
            (gold_row_count - missing_amount_count) / gold_row_count
            if gold_row_count
            else 0
        ),
        "bedrock_invoked_count": bedrock_invoked_count,
        "run_ids": sorted({document["run_id"] for document in expected_documents}),
        "missing_documents": [],
        "created_at": _utc_now_iso(),
        "parquet_s3_key": parquet_key,
        "manifest_s3_key": manifest_key,
    }

    object_store.write_bytes(
        parquet_key,
        _dataframe_to_parquet_bytes(documents),
        content_type="application/vnd.apache.parquet",
    )
    object_store.write_json(manifest_key, manifest)
    logger.info(
        {
            "message": "Gold batch consolidation completed",
            "status": "completed",
            "gold_row_count": manifest["gold_row_count"],
        }
    )

    if event.get("write_completed_status"):
        for document in expected_documents:
            try:
                _write_status(
                    object_store,
                    invoice_id=document["document_id"],
                    run_id=document["run_id"],
                    status="Completed",
                )
            except Exception:
                pass  # best-effort; consolidation already succeeded

    return manifest
