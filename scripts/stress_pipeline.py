from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from src.config.pipeline_config import config_path, load_pipeline_config
from src.pipeline.bronze_pipeline import run_bronze_pipeline
from src.pipeline.gold_model import run_gold_pipeline, load_silver_json
from src.pipeline.run_context import build_run_context, write_run_manifest
from src.pipeline.silver_pipeline import run_silver_pipeline


def _latency_stats(durations: list[float]) -> dict[str, float]:
    if not durations:
        return {"p50": 0.0, "p95": 0.0, "max": 0.0, "avg": 0.0}
    ordered = sorted(durations)
    p50_index = min(len(ordered) - 1, round(0.50 * (len(ordered) - 1)))
    p95_index = min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))
    return {
        "p50": ordered[p50_index],
        "p95": ordered[p95_index],
        "max": ordered[-1],
        "avg": mean(ordered),
    }


def _silver_quality_summary(silver_records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(silver_records)
    if total == 0:
        return {"completion_rates": {}, "flag_counts": {}}

    completion_rates = {
        "total_amount": sum(record.get("total_amount") is not None for record in silver_records) / total,
        "document_date": sum(record.get("document_date") is not None for record in silver_records) / total,
        "vendor_name": sum(record.get("vendor_name") is not None for record in silver_records) / total,
        "currency": sum(record.get("currency") is not None for record in silver_records) / total,
    }

    flag_counts: dict[str, int] = {}
    for record in silver_records:
        for flag in record.get("quality_flags", []):
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    return {
        "completion_rates": completion_rates,
        "flag_counts": flag_counts,
    }


def run_stress_pipeline(limit: int | None = None) -> dict[str, Any]:
    config = load_pipeline_config()
    context = build_run_context(config, execution_mode="local")
    bronze_metrics = run_bronze_pipeline(limit=limit, run_id=context.run_id)
    silver_metrics = run_silver_pipeline(limit=limit, run_id=context.run_id)
    gold_metrics = run_gold_pipeline(run_id=context.run_id)
    silver_records = load_silver_json(config_path(config, "silver_valid_dir"))
    summary = {
        "run_id": context.run_id,
        "limit": limit,
        "phase_metrics": {
            "bronze": bronze_metrics,
            "silver": silver_metrics,
            "gold": gold_metrics,
        },
        "doc_latency_stats": {
            "bronze": _latency_stats(bronze_metrics.get("durations", [])),
            "silver": _latency_stats(silver_metrics.get("durations", [])),
        },
        "silver_quality": _silver_quality_summary(silver_records),
    }
    write_run_manifest(context, summary)
    summary_path = Path(str(config["stress"]["summary_path"]))
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run_stress_pipeline(), indent=2, sort_keys=True))
