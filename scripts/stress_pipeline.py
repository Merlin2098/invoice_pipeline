import argparse
import json
import logging
import statistics
import time
from pathlib import Path
from typing import Any

import pandas as pd

from src.config.pipeline_config import config_path, load_pipeline_config
from src.pipeline.bronze_pipeline import run_bronze_pipeline
from src.pipeline.gold_model import run_gold_pipeline
from src.pipeline.silver_pipeline import run_silver_pipeline
from src.utils.logging import configure_logging

logger = logging.getLogger(__name__)


def latency_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "avg": 0.0, "max": 0.0, "p95": 0.0}

    sorted_values = sorted(values)
    p95_index = max(
        0, min(len(sorted_values) - 1, round((len(sorted_values) * 0.95) - 1))
    )
    return {
        "min": min(sorted_values),
        "avg": statistics.fmean(sorted_values),
        "max": max(sorted_values),
        "p95": sorted_values[p95_index],
    }


def collect_silver_quality(
    silver_dir: Path, limit: int | None = None
) -> dict[str, Any]:
    records = []
    flags: dict[str, int] = {}
    for path in sorted(silver_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            flags["invalid_silver_json"] = flags.get("invalid_silver_json", 0) + 1
            continue

        if not isinstance(record, dict):
            flags["non_object_silver_json"] = flags.get("non_object_silver_json", 0) + 1
            continue

        records.append(record)
        record_flags = record.get("ocr_confidence_flags") or []
        if isinstance(record_flags, str):
            record_flags = [record_flags]
        if not isinstance(record_flags, list):
            record_flags = ["invalid_ocr_confidence_flags"]
        for flag in record_flags:
            flags[str(flag)] = flags.get(str(flag), 0) + 1
        if limit is not None and len(records) >= limit:
            break

    total = len(records)
    return {
        "silver_records": total,
        "completion_rates": {
            "total_amount": sum(
                record.get("total_amount") is not None for record in records
            )
            / total
            if total
            else 0,
            "document_date": sum(
                record.get("document_date") is not None for record in records
            )
            / total
            if total
            else 0,
            "vendor_or_requester": sum(
                record.get("vendor_or_requester") is not None for record in records
            )
            / total
            if total
            else 0,
        },
        "flag_counts": flags,
    }


def collect_gold_rows(gold_dir: Path) -> int:
    documents_path = gold_dir / "documents.parquet"
    if not documents_path.exists():
        return 0
    return len(pd.read_parquet(documents_path))


def write_summary(summary: dict[str, Any], summary_path: Path) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )


def run_stress_pipeline(limit: int | None = None) -> dict[str, Any]:
    config = load_pipeline_config()
    paths = {
        "raw_dir": config_path(config, "raw_dir"),
        "bronze_dir": config_path(config, "bronze_dir"),
        "silver_dir": config_path(config, "silver_dir"),
        "gold_dir": config_path(config, "gold_dir"),
    }
    summary_path = Path(str(config["stress"]["summary_path"]))

    phase_durations: dict[str, float] = {}
    total_start = time.perf_counter()

    start = time.perf_counter()
    bronze_metrics = run_bronze_pipeline(
        paths["raw_dir"], paths["bronze_dir"], limit=limit
    )
    phase_durations["bronze_seconds"] = time.perf_counter() - start

    start = time.perf_counter()
    silver_metrics = run_silver_pipeline(
        paths["bronze_dir"], paths["silver_dir"], limit=limit
    )
    phase_durations["silver_seconds"] = time.perf_counter() - start

    start = time.perf_counter()
    gold_metrics = run_gold_pipeline(paths["silver_dir"], paths["gold_dir"])
    phase_durations["gold_seconds"] = time.perf_counter() - start

    total_elapsed = time.perf_counter() - total_start
    quality = collect_silver_quality(paths["silver_dir"], limit=limit)
    processed = int(silver_metrics.get("succeeded", quality["silver_records"]))
    summary = {
        "limit": limit,
        "elapsed_seconds": total_elapsed,
        "docs_per_minute": processed / (total_elapsed / 60) if total_elapsed else 0,
        "phase_durations": phase_durations,
        "phase_metrics": {
            "bronze": {
                key: value
                for key, value in bronze_metrics.items()
                if key != "durations"
            },
            "silver": {
                key: value
                for key, value in silver_metrics.items()
                if key != "durations"
            },
            "gold": gold_metrics,
        },
        "doc_latency_stats": {
            "bronze": latency_stats(bronze_metrics.get("durations", [])),
            "silver": latency_stats(silver_metrics.get("durations", [])),
        },
        "silver_quality": quality,
        "gold_rows": collect_gold_rows(paths["gold_dir"]),
    }

    write_summary(summary, summary_path)
    logger.info("STRESS_METRICS %s", json.dumps(summary, sort_keys=True))
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an explicit local stress test for the document pipeline."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum documents to process in bronze and silver.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    configure_logging("stress.log")
    args = parse_args()
    run_stress_pipeline(limit=args.limit)
