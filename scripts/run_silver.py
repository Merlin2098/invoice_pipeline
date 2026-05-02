import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.pipeline.silver_pipeline import run_silver_pipeline  # noqa: E402
from src.utils.logging import configure_logging  # noqa: E402


if __name__ == "__main__":
    configure_logging("silver.log")
    run_silver_pipeline()
