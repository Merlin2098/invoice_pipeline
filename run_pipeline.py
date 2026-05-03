import logging
import time

from src.pipeline.bronze_pipeline import run_bronze_pipeline
from src.pipeline.gold_model import run_gold_pipeline
from src.pipeline.silver_pipeline import run_silver_pipeline
from src.utils.logging import configure_logging

logger = logging.getLogger(__name__)


def run_pipeline() -> None:
    start = time.perf_counter()
    logger.info("Starting RAW to BRONZE OCR phase")
    run_bronze_pipeline()
    logger.info("Starting BRONZE to SILVER LLM extraction phase")
    run_silver_pipeline()
    logger.info("Starting SILVER to GOLD relational phase")
    run_gold_pipeline()
    logger.info("PIPELINE_METRICS elapsed_seconds=%.2f", time.perf_counter() - start)


if __name__ == "__main__":
    configure_logging("pipeline.log")
    run_pipeline()
