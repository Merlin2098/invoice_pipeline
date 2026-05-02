import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import requests
import yaml

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen3.5:4b")
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "800"))
CONTRACT_PATH = Path("src/config/data_contract.yaml")

logger = logging.getLogger(__name__)


def load_contract(contract_path: Path = CONTRACT_PATH) -> dict[str, Any]:
    with contract_path.open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def contract_field_names(contract: dict[str, Any] | None = None) -> list[str]:
    contract = contract or load_contract()
    names: list[str] = []
    for group in ("common", "invoice", "contribution"):
        names.extend(contract.get(group, {}).keys())
    return names


def list_available_models() -> list[str]:
    response = requests.get(OLLAMA_TAGS_URL, timeout=30)
    response.raise_for_status()
    payload = response.json()
    return [model.get("name", "") for model in payload.get("models", []) if model.get("name")]


def validate_ollama_model(model: str = MODEL_NAME) -> None:
    try:
        available_models = list_available_models()
    except requests.RequestException as exc:
        raise RuntimeError(f"Ollama is not available at {OLLAMA_BASE_URL}: {exc}") from exc

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
        "format": "json",
        "options": {
            "temperature": 0,
            "num_predict": OLLAMA_NUM_PREDICT,
        },
    }


def call_ollama(prompt: str, model: str = MODEL_NAME, timeout: int = OLLAMA_TIMEOUT_SECONDS) -> str:
    start = time.perf_counter()
    response = requests.post(
        OLLAMA_GENERATE_URL,
        json=build_ollama_payload(prompt, model=model),
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    elapsed = time.perf_counter() - start
    logger.info("Ollama completed model=%s prompt_chars=%s elapsed_seconds=%.2f", model, len(prompt), elapsed)
    return str(payload.get("response", "")).strip()


def build_extraction_prompt(text: str) -> str:
    fields = ", ".join(contract_field_names())
    return f"""
Extract fields from noisy OCR text.
Return one JSON object only. No markdown. No explanations.
Use exactly these keys: {fields}
Missing or uncertain values must be null.
document_type must be one of: invoice, contribution, cost_memo, unknown.
Dates must use YYYY-MM-DD when possible.
Amounts must be numbers, not strings. Use currency "USD" if the text uses "$".
ocr_confidence_flags must be an array of short strings.

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
        text = text[text.find("{") : text.rfind("}") + 1]

    try:
        parsed = json.loads(text)
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
