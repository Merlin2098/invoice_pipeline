from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_PATH = Path("src/jobs/example_job_config.yaml")


@dataclass(slots=True)
class ExampleJobConfig:
    job_name: str
    transformation_sql: str
    contract_path: str


def load_config(config_path: Path = CONFIG_PATH) -> ExampleJobConfig:
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return ExampleJobConfig(
        job_name=str(payload["job_name"]),
        transformation_sql=str(payload["transformation_sql"]),
        contract_path=str(payload["contract_path"]),
    )


def build_job_plan(config: ExampleJobConfig) -> dict[str, object]:
    sql_path = Path(config.transformation_sql)
    contract_path = Path(config.contract_path)
    return {
        "job_name": config.job_name,
        "transformation_sql": sql_path.read_text(encoding="utf-8"),
        "contract": yaml.safe_load(contract_path.read_text(encoding="utf-8")),
    }

