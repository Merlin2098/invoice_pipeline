import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import requests
import yaml

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen3-vl:8b")
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


def call_ollama(prompt: str, model: str = MODEL_NAME) -> str:
    response = requests.post(
        OLLAMA_GENERATE_URL,
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=180,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload.get("response", "")).strip()


def build_extraction_prompt(text: str) -> str:
    fields = "\n".join(f"- {field}" for field in contract_field_names())
    return f"""
You are extracting structured data from noisy OCR text.

Return ONLY valid JSON. Do not include markdown, comments, explanations, or prose.
Use exactly these fields. If a field is missing or uncertain, set it to null.
Use ocr_confidence_flags as a JSON array of short warning strings.
Use document_type as one of: invoice, contribution, cost_memo, unknown.

Fields:
{fields}

OCR text:
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
