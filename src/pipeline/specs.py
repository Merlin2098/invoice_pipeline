from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

SPEC_ROOT = Path("specs")
QUALITY_SPEC_PATH = SPEC_ROOT / "quality" / "bronze_to_silver_rules.yaml"
GOLD_QUALITY_SPEC_PATH = SPEC_ROOT / "quality" / "gold_quality_rules.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        loaded = yaml.safe_load(file) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Spec file must contain a YAML object: {path}")
    return loaded


def load_quality_rules(path: Path = QUALITY_SPEC_PATH) -> dict[str, Any]:
    return load_yaml(path)


def load_gold_quality_rules(path: Path = GOLD_QUALITY_SPEC_PATH) -> dict[str, Any]:
    return load_yaml(path)


def load_contract_schema(name: str) -> dict[str, Any]:
    return load_yaml(SPEC_ROOT / "contracts" / name)

