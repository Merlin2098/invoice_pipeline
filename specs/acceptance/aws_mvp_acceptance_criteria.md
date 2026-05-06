# AWS MVP Acceptance Criteria

## Functional

- Raw documents are stored under `raw/run_id=<run_id>/`.
- Each processed document produces bronze evidence, a silver outcome, and
  inclusion or exclusion from gold.
- Silver outputs are separated between `valid`, `rejected`, and technical
  failures.
- Gold output is written in parquet and preserves `run_id` and `document_id`.

## Operational

- `documents_processed_rate >= 0.95`
- `technical_failure_rate <= 0.05`
- `run_metrics_generated = true`
- `rejected_documents_have_reason = true`
- `traceability_by_run_id = true`

## Quality

- `vendor_completion_rate >= 0.85`
- `date_completion_rate >= 0.85`
- `amount_completion_rate >= 0.90`
- `unknown_document_type_rate <= 0.20`
- `critical_errors_in_gold = 0`

