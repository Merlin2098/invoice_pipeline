import logging
import time

from src.config.pipeline_config import load_pipeline_config
from src.pipeline.bronze_pipeline import run_bronze_pipeline
from src.pipeline.gold_model import run_gold_pipeline
from src.pipeline.run_context import build_run_context, write_run_manifest
from src.pipeline.silver_pipeline import run_silver_pipeline
from src.utils.logging import configure_logging

logger = logging.getLogger(__name__)


def run_pipeline(execution_mode: str | None = None) -> dict[str, object]:
    config = load_pipeline_config()
    context = build_run_context(config, execution_mode=execution_mode)
    start = time.perf_counter()
    logger.info("run_id=%s execution_mode=%s starting pipeline", context.run_id, context.execution_mode)

    if context.execution_mode != "local":
        raise NotImplementedError(
            "The direct CLI runner currently supports only local execution. "
            "AWS execution is implemented through shared contracts, AWS adapters, "
            "Glue scripts, Lambda handlers, and Terraform orchestration."
        )

    logger.info("run_id=%s starting RAW to BRONZE OCR phase", context.run_id)
    bronze_metrics = run_bronze_pipeline(run_id=context.run_id)
    logger.info("run_id=%s starting BRONZE to SILVER LLM extraction phase", context.run_id)
    silver_metrics = run_silver_pipeline(run_id=context.run_id)
    logger.info("run_id=%s starting SILVER to GOLD relational phase", context.run_id)
    gold_metrics = run_gold_pipeline(run_id=context.run_id)
    elapsed = time.perf_counter() - start

    summary = {
        "run_id": context.run_id,
        "execution_mode": context.execution_mode,
        "elapsed_seconds_total": elapsed,
        "documents_received": bronze_metrics["total"],
        "documents_processed": silver_metrics["succeeded"] + silver_metrics["rejected"],
        "documents_accepted": silver_metrics["succeeded"],
        "documents_rejected": silver_metrics["rejected"],
        "documents_failed": silver_metrics["failed"],
        "phase_metrics": {
            "bronze": bronze_metrics,
            "silver": silver_metrics,
            "gold": gold_metrics,
        },
        "vendor_completion_rate": gold_metrics.get("vendor_completion_rate", 0),
        "date_completion_rate": gold_metrics.get("date_completion_rate", 0),
        "amount_completion_rate": gold_metrics.get("amount_completion_rate", 0),
        "currency_completion_rate": gold_metrics.get("currency_completion_rate", 0),
        "unknown_document_type_rate": gold_metrics.get("unknown_document_type_rate", 0),
        "estimated_textract_cost": 0,
        "estimated_bedrock_cost": 0,
        "estimated_total_cost": 0,
    }
    write_run_manifest(context, summary)
    logger.info("run_id=%s PIPELINE_METRICS elapsed_seconds=%.2f", context.run_id, elapsed)
    return summary


if __name__ == "__main__":
    configure_logging("pipeline.log")
    run_pipeline()
