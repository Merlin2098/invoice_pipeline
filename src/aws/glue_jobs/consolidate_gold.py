from __future__ import annotations

from typing import Any

import pandas as pd

from src.pipeline.gold_model import build_documents_table


def consolidate_gold_documents(silver_records: list[dict[str, Any]]) -> pd.DataFrame:
    return build_documents_table(silver_records)


def consolidate_gold_run(
    silver_records: list[dict[str, Any]],
    *,
    run_id: str,
    history_records: list[dict[str, Any]] | None = None,
) -> pd.DataFrame:
    current_records = [
        record for record in silver_records if record.get("run_id") == run_id
    ]
    return build_documents_table(
        current_records,
        history_records=history_records or silver_records,
    )


def gold_metrics_preview(silver_records: list[dict[str, Any]]) -> dict[str, Any]:
    table = build_documents_table(silver_records)
    total = len(table)
    if total == 0:
        return {"rows": 0}
    return {
        "rows": total,
        "vendor_completion_rate": float(table["vendor_name"].notna().sum()) / total,
        "date_completion_rate": float(table["document_date"].notna().sum()) / total,
        "amount_completion_rate": float(table["total_amount"].notna().sum()) / total,
    }
