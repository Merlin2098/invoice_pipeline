import os
from pathlib import Path

import pytesseract
from PIL import Image, ImageSequence

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def configure_tesseract() -> None:
    tesseract_cmd = os.getenv("TESSERACT_CMD") or os.getenv("TESSERACT_EXE")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def clean_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def ocr_extract(file_path: str | Path) -> str:
    path = Path(file_path)
    if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image extension: {path.suffix}")

    configure_tesseract()

    with Image.open(path) as image:
        text_parts = []
        for frame in ImageSequence.Iterator(image):
            text_parts.append(pytesseract.image_to_string(frame.copy()))

    return clean_text("\n".join(text_parts))
