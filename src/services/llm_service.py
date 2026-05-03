import json
import logging
import os
import re
import time
from typing import Any

import requests

from src.config.pipeline_config import load_pipeline_config

logger = logging.getLogger(__name__)

_CONFIG = load_pipeline_config()
_LLM_CONFIG = _CONFIG["llm"]

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", str(_LLM_CONFIG["base_url"]))
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
MODEL_NAME = os.getenv("OLLAMA_MODEL", str(_LLM_CONFIG["model"]))
OLLAMA_TIMEOUT_SECONDS = int(
    os.getenv("OLLAMA_TIMEOUT_SECONDS", str(_LLM_CONFIG["timeout_seconds"]))
)
OLLAMA_NUM_PREDICT = int(
    os.getenv("OLLAMA_NUM_PREDICT", str(_LLM_CONFIG["num_predict"]))
)

MINIMAL_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "total_amount": {"type": ["number", "string", "null"]},
        "document_date": {"type": ["string", "null"]},
        "vendor_name": {"type": ["string", "null"]},
    },
    "required": ["total_amount", "document_date", "vendor_name"],
    "additionalProperties": False,
}


def list_available_models() -> list[str]:
    response = requests.get(OLLAMA_TAGS_URL, timeout=30)
    response.raise_for_status()
    payload = response.json()
    return [
        model.get("name", "")
        for model in payload.get("models", [])
        if model.get("name")
    ]


def validate_ollama_model(model: str = MODEL_NAME) -> None:
    try:
        available_models = list_available_models()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Ollama is not available at {OLLAMA_BASE_URL}: {exc}"
        ) from exc

    if model not in available_models:
        available = ", ".join(available_models) or "none"
        raise RuntimeError(
            f"Ollama model '{model}' is not installed. "
            f"Available models: {available}. "
            "Set OLLAMA_MODEL to an installed model or pull the requested model."
        )


def build_ollama_payload(prompt: str, model: str = MODEL_NAME) -> dict[str, Any]:
    return {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": MINIMAL_EXTRACTION_SCHEMA,
        "think": False,
        "options": {
            "temperature": 0,
            "num_predict": OLLAMA_NUM_PREDICT,
        },
    }


def call_ollama(
    prompt: str, model: str = MODEL_NAME, timeout: int = OLLAMA_TIMEOUT_SECONDS
) -> str:
    start = time.perf_counter()
    response = requests.post(
        OLLAMA_GENERATE_URL,
        json=build_ollama_payload(prompt, model=model),
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    elapsed = time.perf_counter() - start
    logger.info(
        "Ollama completed model=%s prompt_chars=%s elapsed_seconds=%.2f",
        model,
        len(prompt),
        elapsed,
    )
    response_text = str(
        payload.get("response") or payload.get("thinking") or ""
    ).strip()
    if not payload.get("response") and payload.get("thinking"):
        logger.warning("Ollama returned JSON in thinking field; using it as fallback")
    return response_text


def build_extraction_prompt(text: str) -> str:
    return f"""
Extract basic invoice information.

Return ONLY valid JSON:
{{
  "total_amount": number or null,
  "document_date": string or null,
  "vendor_name": string or null
}}

No explanations.
Missing values = null.

OCR:
{text}
""".strip()


def parse_json_response(response_text: str) -> dict[str, Any]:
    text = response_text.strip()
    if not text:
        return {"ocr_confidence_flags": ["empty_llm_response"]}

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    elif "{" in text and "}" in text:
        text = text[text.find("{") :]
    else:
        return {"ocr_confidence_flags": ["invalid_json_response"]}

    try:
        parsed, _ = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM JSON response")
        return {"ocr_confidence_flags": ["invalid_json_response"]}

    if not isinstance(parsed, dict):
        return {"ocr_confidence_flags": ["invalid_json_response"]}

    flags = parsed.get("ocr_confidence_flags")
    if flags is None:
        parsed["ocr_confidence_flags"] = []
    elif isinstance(flags, str):
        parsed["ocr_confidence_flags"] = [flags]
    elif not isinstance(flags, list):
        parsed["ocr_confidence_flags"] = ["invalid_ocr_confidence_flags"]

    return parsed


def extract_structured_data(text: str) -> dict[str, Any]:
    prompt = build_extraction_prompt(text)
    try:
        response_text = call_ollama(prompt)
    except requests.RequestException as exc:
        logger.warning("Ollama request failed: %s", exc)
        return {"ocr_confidence_flags": ["ollama_request_failed"]}

    return parse_json_response(response_text)
