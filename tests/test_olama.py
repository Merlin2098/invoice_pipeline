import json
import logging
import os
import shutil
from pathlib import Path

import ollama
from ollama import ResponseError

from src.pipeline.ocr import ocr_extract

MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen3:8b")
ERRORS_DIR = Path("data/errors")

logger = logging.getLogger(__name__)


def list_available_models() -> list[str]:
    return [model.model for model in ollama.list().models]


def move_to_errors(file_path: Path, errors_dir: Path = ERRORS_DIR) -> Path:
    errors_dir.mkdir(parents=True, exist_ok=True)
    target = errors_dir / file_path.name

    counter = 1
    while target.exists():
        target = errors_dir / f"{file_path.stem}_{counter}{file_path.suffix}"
        counter += 1

    return Path(shutil.move(str(file_path), str(target)))


def extract_invoice(file_path: Path) -> str:
    prompt = """
You are an AI specialized in extracting structured data from invoices.

Extract the following fields and return ONLY valid JSON:

- invoice_id
- supplier_name
- invoice_date
- currency
- total_amount

Rules:
- If a field is missing, return null
- Do NOT add explanations
- Output must be valid JSON
"""

    try:
        ocr_text = ocr_extract(file_path)
    except Exception:
        logger.exception("OCR failed for %s", file_path)
        move_to_errors(file_path)
        raise

    try:
        response = ollama.chat(
            model=MODEL_NAME,
            format="json",
            messages=[
                {
                    "role": "user",
                    "content": f"{prompt}\n\nOCR text:\n{ocr_text}",
                },
            ],
        )
    except ResponseError as exc:
        available_models = list_available_models()
        raise RuntimeError(
            f"Ollama no encontro el modelo '{MODEL_NAME}'. "
            f"Modelos disponibles: {', '.join(available_models) or 'ninguno'}. "
            "Define OLLAMA_MODEL con un modelo de texto disponible antes de ejecutar la prueba."
        ) from exc

    return response["message"]["content"]


def test_invoice_extraction():
    print("--- Prueba extraccion de facturas con OCR + Ollama ---")

    file_path = Path("data/raw/ti31379007_9013.tif")

    if not file_path.exists():
        print(f"Archivo no encontrado: {file_path}")
        return

    result = extract_invoice(file_path)

    print("\n--- Respuesta cruda ---\n")
    print(result)

    try:
        parsed = json.loads(result)
        print("\n--- JSON parseado ---\n")
        print(json.dumps(parsed, indent=2))
    except Exception as e:
        print("\nError parseando JSON:", e)


if __name__ == "__main__":
    test_invoice_extraction()
