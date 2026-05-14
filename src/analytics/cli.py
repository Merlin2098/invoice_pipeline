from __future__ import annotations

import argparse
import json
import os
from typing import Any

from src.analytics.athena_client import AthenaClient
from src.analytics.bedrock_sql import BedrockSqlGenerator


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _athena_client(args: argparse.Namespace) -> AthenaClient:
    return AthenaClient(
        database=args.database,
        output_location=args.output_location,
        workgroup=args.workgroup,
        region=args.region,
    )


def _print_result(result: Any) -> None:
    print(
        json.dumps(
            {
                "query_id": result.query_id,
                "status": result.status,
                "generated_sql": result.sql,
                "execution_time_ms": result.execution_time_ms,
                "athena_scan_mb": result.athena_scan_mb,
                "rows": result.rows,
            },
            indent=2,
            default=str,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Query Gold analytics with Athena.")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument(
        "--database",
        default=os.getenv("ATHENA_DATABASE", "invoice_pipeline_gold"),
    )
    parser.add_argument(
        "--workgroup",
        default=os.getenv("ATHENA_WORKGROUP", "invoice-pipeline-dev"),
    )
    parser.add_argument(
        "--output-location",
        default=os.getenv("ATHENA_OUTPUT_LOCATION"),
        required=os.getenv("ATHENA_OUTPUT_LOCATION") is None,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("repair-partitions")

    sql_parser = subparsers.add_parser("sql")
    sql_parser.add_argument("query")

    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("question")
    ask_parser.add_argument(
        "--model-id",
        default=os.getenv("BEDROCK_MODEL_ID"),
    )

    args = parser.parse_args(argv)
    athena = _athena_client(args)

    if args.command == "repair-partitions":
        _print_result(athena.repair_partitions())
        return 0
    if args.command == "sql":
        _print_result(athena.execute_sql(args.query))
        return 0
    if args.command == "ask":
        generator = BedrockSqlGenerator(
            model_id=args.model_id or _env("BEDROCK_MODEL_ID"),
            region=args.region,
        )
        validated_sql = generator.generate_sql(args.question)
        _print_result(athena.execute_validated_sql(validated_sql))
        return 0
    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

