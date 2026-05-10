from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import boto3

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent.parent / "specs" / "prompts" / "bedrock_normalization_prompt.md"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


class BedrockNormalizerClient:
    """Implements BedrockNormalizer Protocol using Claude via Amazon Bedrock."""

    def __init__(self, model_id: str, region: str = "us-east-1") -> None:
        self._model_id = model_id
        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._system_prompt = _load_prompt()

    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_message = json.dumps(payload, ensure_ascii=False, default=str)
        response = self._client.converse(
            modelId=self._model_id,
            system=[{"text": self._system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            inferenceConfig={"maxTokens": 1024},
        )
        text = response["output"]["message"]["content"][0]["text"].strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text)
        confidence = result.pop("confidence_summary", {})
        for field, value in confidence.items():
            result[f"{field}_confidence"] = value
        result.pop("reasoning_flags", None)
        return result
