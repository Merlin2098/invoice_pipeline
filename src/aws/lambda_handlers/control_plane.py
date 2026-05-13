from __future__ import annotations

import json
import os
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
        self.client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
            ContentType="application/json",
        )

    def read_json(self, key: str) -> dict[str, Any]:
        response = self.client.get_object(Bucket=self.bucket_name, Key=key)
        body = response["Body"].read().decode("utf-8")
        return json.loads(body)


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
