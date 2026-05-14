from __future__ import annotations

import pytest

from src.analytics.athena_client import AthenaClient, AthenaQueryError
from src.analytics.bedrock_sql import BedrockSqlGenerator, extract_sql
from src.analytics.sql_validator import SqlValidationError, validate_sql


def test_sql_validator_accepts_aggregate_query_with_limit() -> None:
    result = validate_sql(
        """
        SELECT vendor_name, sum(total_amount) AS total_spend
        FROM gold_documents
        WHERE currency = 'USD'
        GROUP BY vendor_name
        ORDER BY total_spend DESC
        LIMIT 10
        """
    )

    assert result.sql.endswith("LIMIT 10")
    assert result.limit == 10
    assert result.tables == ("gold_documents",)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM gold_documents",
        "UPDATE gold_documents SET vendor_name = 'x'",
        "DROP TABLE gold_documents",
        "ALTER TABLE gold_documents ADD COLUMNS (x string)",
        "INSERT INTO gold_documents VALUES ('x')",
        "CREATE TABLE other AS SELECT document_id FROM gold_documents",
    ],
)
def test_sql_validator_rejects_mutating_sql(sql: str) -> None:
    with pytest.raises(SqlValidationError):
        validate_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM gold_documents",
        "SELECT gold_documents.* FROM gold_documents",
    ],
)
def test_sql_validator_rejects_unrestricted_wildcards(sql: str) -> None:
    with pytest.raises(SqlValidationError):
        validate_sql(sql)


def test_sql_validator_rejects_unknown_table() -> None:
    with pytest.raises(SqlValidationError, match="Unknown table"):
        validate_sql("SELECT document_id FROM silver_documents LIMIT 10")


def test_sql_validator_rejects_unknown_column() -> None:
    with pytest.raises(SqlValidationError, match="Unknown identifier"):
        validate_sql("SELECT imaginary_column FROM gold_documents LIMIT 10")


def test_sql_validator_adds_default_limit() -> None:
    result = validate_sql("SELECT document_id FROM gold_documents")

    assert result.sql == "SELECT document_id FROM gold_documents LIMIT 100"
    assert result.limit == 100


def test_sql_validator_accepts_database_qualified_gold_table() -> None:
    result = validate_sql(
        "SELECT document_id FROM invoice_pipeline_gold.gold_documents LIMIT 5"
    )

    assert result.tables == ("gold_documents",)
    assert result.limit == 5


def test_sql_validator_rejects_excessive_limit() -> None:
    with pytest.raises(SqlValidationError, match="LIMIT"):
        validate_sql("SELECT document_id FROM gold_documents LIMIT 1001")


def test_extract_sql_handles_plain_and_fenced_responses() -> None:
    assert extract_sql("SELECT document_id FROM gold_documents") == (
        "SELECT document_id FROM gold_documents"
    )
    assert extract_sql(
        """
        ```sql
        SELECT document_id FROM gold_documents
        ```
        """
    ) == "SELECT document_id FROM gold_documents"


def test_bedrock_sql_generator_validates_generated_sql(tmp_path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Return SQL only.", encoding="utf-8")

    class FakeBedrockClient:
        def converse(self, **kwargs):
            return {
                "output": {
                    "message": {
                        "content": [
                            {
                                "text": (
                                    "```sql\n"
                                    "SELECT vendor_name, count(*) AS document_count "
                                    "FROM gold_documents GROUP BY vendor_name\n"
                                    "```"
                                )
                            }
                        ]
                    }
                }
            }

    generator = BedrockSqlGenerator(
        model_id="model",
        client=FakeBedrockClient(),
        prompt_path=prompt,
    )

    result = generator.generate_sql("How many documents per vendor?")

    assert result.sql.endswith("LIMIT 100")
    assert result.tables == ("gold_documents",)


def test_athena_client_returns_rows_for_successful_query() -> None:
    class FakePaginator:
        def paginate(self, QueryExecutionId: str):
            assert QueryExecutionId == "query-1"
            return [
                {
                    "ResultSet": {
                        "Rows": [
                            {"Data": [{"VarCharValue": "document_id"}]},
                            {"Data": [{"VarCharValue": "doc-1"}]},
                        ]
                    }
                }
            ]

    class FakeAthenaClient:
        def start_query_execution(self, **kwargs):
            assert kwargs["WorkGroup"] == "invoice-pipeline-dev"
            return {"QueryExecutionId": "query-1"}

        def get_query_execution(self, QueryExecutionId: str):
            return {
                "QueryExecution": {
                    "Status": {"State": "SUCCEEDED"},
                    "Statistics": {"DataScannedInBytes": 1048576},
                }
            }

        def get_paginator(self, name: str):
            assert name == "get_query_results"
            return FakePaginator()

    client = AthenaClient(
        database="invoice_pipeline_gold",
        output_location="s3://bucket/athena-results/",
        workgroup="invoice-pipeline-dev",
        client=FakeAthenaClient(),
        poll_seconds=0,
    )

    result = client.execute_sql("SELECT document_id FROM gold_documents LIMIT 1")

    assert result.query_id == "query-1"
    assert result.rows == [{"document_id": "doc-1"}]
    assert result.athena_scan_mb == 1.0


def test_athena_client_raises_for_failed_query() -> None:
    class FakeAthenaClient:
        def start_query_execution(self, **kwargs):
            return {"QueryExecutionId": "query-1"}

        def get_query_execution(self, QueryExecutionId: str):
            return {
                "QueryExecution": {
                    "Status": {
                        "State": "FAILED",
                        "StateChangeReason": "bad query",
                    },
                    "Statistics": {},
                }
            }

    client = AthenaClient(
        database="invoice_pipeline_gold",
        output_location="s3://bucket/athena-results/",
        workgroup="invoice-pipeline-dev",
        client=FakeAthenaClient(),
        poll_seconds=0,
    )

    with pytest.raises(AthenaQueryError, match="bad query"):
        client.execute_sql("SELECT document_id FROM gold_documents LIMIT 1")


def test_athena_client_times_out_for_running_query() -> None:
    class FakeAthenaClient:
        def start_query_execution(self, **kwargs):
            return {"QueryExecutionId": "query-1"}

        def get_query_execution(self, QueryExecutionId: str):
            return {
                "QueryExecution": {
                    "Status": {"State": "RUNNING"},
                    "Statistics": {},
                }
            }

    client = AthenaClient(
        database="invoice_pipeline_gold",
        output_location="s3://bucket/athena-results/",
        workgroup="invoice-pipeline-dev",
        client=FakeAthenaClient(),
        poll_seconds=0,
        timeout_seconds=0.001,
    )

    with pytest.raises(TimeoutError):
        client.execute_sql("SELECT document_id FROM gold_documents LIMIT 1")
