import os
from pathlib import Path

import pytesseract
from PIL import Image, ImageSequence

from src.config.pipeline_config import load_pipeline_config


def supported_image_extensions() -> set[str]:
    config = load_pipeline_config()
    return {
        str(extension).lower() for extension in config["ocr"]["supported_extensions"]
    }


def configure_tesseract() -> None:
    tesseract_cmd = os.getenv("TESSERACT_CMD") or os.getenv("TESSERACT_EXE")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def clean_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def extract_text(file_path: str | Path) -> str:
    path = Path(file_path)
    if path.suffix.lower() not in supported_image_extensions():
        raise ValueError(f"Unsupported image extension: {path.suffix}")

    configure_tesseract()

    with Image.open(path) as image:
        text_parts = []
        for frame in ImageSequence.Iterator(image):
            text_parts.append(pytesseract.image_to_string(frame.copy()))

    return clean_text("\n".join(text_parts))


def format_ocr_markdown(text: str, source_file: Path) -> str:
    return f"""# OCR Extract

- Source file: `{source_file.name}`
- Source path: `{source_file.as_posix()}`

## OCR Text

```text
{text}
```
"""
