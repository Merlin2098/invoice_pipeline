import json
import logging
import re
from pathlib import Path
from typing import Any

import requests
import yaml

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3:8b"
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


def call_ollama(prompt: str) -> str:
    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL_NAME, "prompt": prompt, "stream": False},
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
