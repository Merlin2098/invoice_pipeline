# AWS Migration Status: current vs target

This document consolidates:

- `docs/project_spec_driven_development.md`
- `docs/local run/mvp_local_ollama_hallazgos.md`
- `docs/local run/aws_target_architecture.md`

The goal is to keep the local pipeline as a living baseline while making the
AWS target explicit, measurable, and incremental.

## Phase-by-phase comparison

| Phase | Current state | Desired state | Gap to close | Exit criterion |
|---|---|---|---|---|
| Raw | Filesystem ingestion under `data/raw` without run manifests | `S3 raw/run_id=<run_id>/` with metadata and controlled formats | Add run context, manifest, and metadata validation | Every run has `run_id`, allowed extensions, and an input manifest |
| Bronze | Local Tesseract writes Markdown OCR to `data/bronze` | Textract technical evidence stored in `bronze/textract-json/` | Introduce a canonical bronze schema and AWS extractor adapter | Bronze output conforms to `specs/contracts/bronze_textract.schema.yaml` |
| Silver | Local Ollama extracts three fields with light validation | Canonical silver document with contract validation and `valid/rejected/failed` separation | Move quality logic into shared validators and add canonical schema | Each document lands in one explicit outcome with `quality_flags` and reason codes |
| Gold | Single local parquet without run partitioning | Glue-first gold consolidation in S3 with full traceability | Move to canonical columns and run-level metrics | Gold excludes rejected/failed docs and preserves lineage fields |
| Observability | Mixed local logs and aggregate metrics | CloudWatch metrics/logs by phase and `run_id` | Add manifest, per-run metrics, and AWS observability resources | Every run publishes comparable metrics for local and AWS modes |

## Living baseline

The local implementation is still useful for:

- regression tests
- prompt or rule experiments
- AWS quality comparison on the same document subset
- fast offline iteration when cloud changes are not needed

It should not be treated as the target architecture.

## Reference subset for comparison

The repository now freezes a small comparison subset in:

- `tests/fixtures/reference_documents.yaml`
- `tests/fixtures/expected_documents.csv`

This subset is used for local vs AWS comparison with the same expected fields.

## Contract equivalence matrix

| Legacy local field | Canonical target field | Notes |
|---|---|---|
| `source_file` | `source_file_name` | Keep file identity while moving away from Markdown-specific naming |
| `raw_text_path` | `raw_text_path` | Preserved for local lineage only |
| `vendor_or_requester` | `vendor_name` | Canonical naming for local and AWS outputs |
| `ocr_confidence_flags` | `quality_flags` | Shared semantics for rule-based quality |
| local document JSON | silver canonical document | Local output remains valid through an adapter, not as the contract of record |

## Implementation milestones

### Hito 1

- canonical specs created
- local pipeline adapted to the canonical silver/gold shape
- shared quality validation introduced

### Hito 2

- Terraform modules for the dev AWS MVP
- Glue scripts, Lambda control handlers, and Step Functions orchestration
- AWS pipeline adapters using the same canonical silver rules

### Hito 3

- alarms, retries, and selective reprocessing
- higher-volume posture with the same contract and metrics model

