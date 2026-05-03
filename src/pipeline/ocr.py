from pathlib import Path

from src.services.ocr_service import (
    clean_text,
    configure_tesseract,
    extract_text,
    pytesseract,
    supported_image_extensions,
)

SUPPORTED_IMAGE_EXTENSIONS = supported_image_extensions()

__all__ = [
    "SUPPORTED_IMAGE_EXTENSIONS",
    "clean_text",
    "configure_tesseract",
    "ocr_extract",
    "pytesseract",
]


def ocr_extract(file_path: str | Path) -> str:
    return extract_text(file_path)
