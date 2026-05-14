from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from src.analytics.sql_validator import ValidatedSql, validate_sql


class AthenaQueryError(RuntimeError):
    """Raised when Athena cannot complete a query successfully."""


@dataclass(frozen=True)
class AthenaQueryResult:
    query_id: str
    rows: list[dict[str, str | None]]
    execution_time_ms: int
    athena_scan_mb: float
    status: str
    sql: str


class AthenaClient:
    def __init__(
        self,
        database: str,
        output_location: str,
        workgroup: str,
        region: str = "us-east-1",
        client: Any | None = None,
        poll_seconds: float = 1.0,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.database = database
        self.output_location = output_location
        self.workgroup = workgroup
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        if client is None:
            import boto3

            client = boto3.client("athena", region_name=region)
        self.client = client

    def repair_partitions(self) -> AthenaQueryResult:
        return self.execute_validated_sql(
            ValidatedSql(
                sql="MSCK REPAIR TABLE gold_documents",
                tables=("gold_documents",),
                limit=0,
            ),
            validate=False,
        )

    def execute_sql(self, sql: str) -> AthenaQueryResult:
        return self.execute_validated_sql(validate_sql(sql))

    def execute_validated_sql(
        self,
        validated_sql: ValidatedSql,
        *,
        validate: bool = True,
    ) -> AthenaQueryResult:
        if validate:
            validated_sql = validate_sql(validated_sql.sql)

        started_at = time.perf_counter()
        start_response = self.client.start_query_execution(
            QueryString=validated_sql.sql,
            QueryExecutionContext={"Database": self.database},
            ResultConfiguration={"OutputLocation": self.output_location},
            WorkGroup=self.workgroup,
        )
        query_id = start_response["QueryExecutionId"]
        execution = self._wait_for_completion(query_id)
        status = execution["Status"]["State"]
        statistics = execution.get("Statistics", {})
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        scan_mb = float(statistics.get("DataScannedInBytes", 0)) / 1024 / 1024
        rows = self._fetch_rows(query_id) if status == "SUCCEEDED" else []

        return AthenaQueryResult(
            query_id=query_id,
            rows=rows,
            execution_time_ms=elapsed_ms,
            athena_scan_mb=scan_mb,
            status=status,
            sql=validated_sql.sql,
        )

    def _wait_for_completion(self, query_id: str) -> dict[str, Any]:
        deadline = time.perf_counter() + self.timeout_seconds
        while time.perf_counter() < deadline:
            response = self.client.get_query_execution(QueryExecutionId=query_id)
            execution = response["QueryExecution"]
            state = execution["Status"]["State"]
            if state == "SUCCEEDED":
                return execution
            if state in {"FAILED", "CANCELLED"}:
                reason = execution["Status"].get("StateChangeReason", state)
                raise AthenaQueryError(f"Athena query {query_id} {state}: {reason}")
            time.sleep(self.poll_seconds)
        raise TimeoutError(f"Athena query {query_id} timed out.")

    def _fetch_rows(self, query_id: str) -> list[dict[str, str | None]]:
        paginator = self.client.get_paginator("get_query_results")
        rows: list[dict[str, str | None]] = []
        columns: list[str] | None = None
        for page in paginator.paginate(QueryExecutionId=query_id):
            for row in page.get("ResultSet", {}).get("Rows", []):
                values = [
                    cell.get("VarCharValue")
                    for cell in row.get("Data", [])
                ]
                if columns is None:
                    columns = [str(value) for value in values]
                    continue
                rows.append(dict(zip(columns, values, strict=False)))
        return rows

