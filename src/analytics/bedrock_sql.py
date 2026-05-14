from __future__ import annotations

from pathlib import Path
from typing import Any

from src.analytics.schema_registry import table_schema_prompt
from src.analytics.sql_validator import ValidatedSql, validate_sql

PROMPT_PATH = (
    Path(__file__).parent.parent.parent
    / "specs"
    / "prompts"
    / "bedrock_analytics_sql_prompt.md"
)


def extract_sql(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        if len(parts) >= 3:
            cleaned = parts[1].strip()
            if cleaned.lower().startswith("sql"):
                cleaned = cleaned[3:].strip()
    return cleaned.strip()


class BedrockSqlGenerator:
    def __init__(
        self,
        model_id: str,
        region: str = "us-east-1",
        client: Any | None = None,
        prompt_path: Path = PROMPT_PATH,
    ) -> None:
        self._model_id = model_id
        self._prompt_path = prompt_path
        if client is None:
            import boto3

            client = boto3.client("bedrock-runtime", region_name=region)
        self._client = client

    def generate_sql(self, question: str) -> ValidatedSql:
        prompt = self._prompt_path.read_text(encoding="utf-8")
        user_message = (
            f"{table_schema_prompt()}\n\n"
            f"User question:\n{question.strip()}\n\n"
            "Return only Athena SQL."
        )
        response = self._client.converse(
            modelId=self._model_id,
            system=[{"text": prompt}],
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            inferenceConfig={"maxTokens": 512, "temperature": 0},
        )
        sql = extract_sql(response["output"]["message"]["content"][0]["text"])
        return validate_sql(sql)

