from __future__ import annotations

import json
import os
from typing import Any

from src.analytics.athena_client import AthenaClient
from src.analytics.bedrock_sql import BedrockSqlGenerator
from src.analytics.sql_validator import SqlValidationError
from src.aws.logging_utils import get_logger


_MAX_QUESTION_CHARS = 500
_CHAT_RESULT_ROW_CAP = 50
_SUMMARIZATION_MAX_TOKENS = 512


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


def _json_response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def _request_body(event: dict[str, Any]) -> dict[str, Any]:
    if isinstance(event.get("body"), str):
        return json.loads(event["body"])
    if isinstance(event.get("body"), dict):
        return event["body"]
    return event


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
        system=[
            {
                "text": (
                    "You are a helpful analytics assistant that summarizes data query "
                    "results in plain business language."
                )
            }
        ],
        messages=[{"role": "user", "content": [{"text": user_message}]}],
        inferenceConfig={"maxTokens": _SUMMARIZATION_MAX_TOKENS, "temperature": 0},
    )
    return str(response["output"]["message"]["content"][0]["text"]).strip()


def chat(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    logger = get_logger("chat")

    try:
        body = _request_body(event)
    except json.JSONDecodeError:
        return _json_response(
            400,
            {"error": "invalid_request", "message": "Request body is not valid JSON."},
        )

    question = str(body.get("question") or "").strip()
    if not question:
        return _json_response(
            400,
            {"error": "invalid_request", "message": "question is required."},
        )
    if len(question) > _MAX_QUESTION_CHARS:
        return _json_response(
            422,
            {
                "error": "invalid_request",
                "message": f"question must be {_MAX_QUESTION_CHARS} characters or less.",
            },
        )

    model_id = _env("BEDROCK_MODEL_ID")
    database = _env("GLUE_DATABASE", "invoice_pipeline_gold")
    athena_output = f"s3://{_env('DATA_LAKE_BUCKET')}/athena-results/"
    workgroup = _env("ATHENA_WORKGROUP")
    aws_region = os.getenv("AWS_REGION", "us-east-1")

    boto3 = _optional_boto3()
    if boto3 is None:
        raise RuntimeError("boto3 is required for the chat handler")

    bedrock_client = boto3.client("bedrock-runtime", region_name=aws_region)
    logger = logger.bind(user_question=question[:200])

    try:
        sql_generator = BedrockSqlGenerator(
            model_id=model_id,
            region=aws_region,
            client=bedrock_client,
        )
        validated_sql = sql_generator.generate_sql(question)
    except SqlValidationError as exc:
        return _json_response(
            400,
            {"error": "sql_validation_error", "message": str(exc)},
        )

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
        return _json_response(
            504,
            {"error": "timeout", "message": "query did not complete within the time limit."},
        )

    answer = _summarize_results(
        bedrock_client=bedrock_client,
        model_id=model_id,
        question=question,
        sql=result.sql,
        rows=result.rows,
    )

    logger.info(
        {
            "message": "Chat query completed",
            "status": result.status,
            "query_id": result.query_id,
            "user_question": question[:200],
            "generated_sql": result.sql,
            "execution_time_ms": result.execution_time_ms,
            "athena_scan_mb": result.athena_scan_mb,
        }
    )

    return _json_response(
        200,
        {
            "answer": answer,
            "generated_sql": result.sql,
            "rows": result.rows,
            "query_id": result.query_id,
            "execution_time_ms": result.execution_time_ms,
            "athena_scan_mb": result.athena_scan_mb,
        },
    )
