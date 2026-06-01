# Invoice Intelligence Pipeline

## Overview

Invoice Intelligence Pipeline is a complete serverless Data Product on AWS: a
user uploads a PDF invoice through a web portal, the pipeline extracts and
enriches it with Textract and Bedrock, consolidates it into a Gold analytics
layer, and the user can immediately query their invoices with natural language
and receive business-friendly answers.

The project demonstrates a full production-ready stack — Data Engineering,
OCR, Lakehouse Architecture, GenAI, Conversational Analytics, and
Infrastructure as Code (Terraform) — end to end without hiding any runtime
behavior behind a framework.

## Business Problem

Invoice operations often start with semi-structured files and end with manual
review, inconsistent fields, and limited traceability. This project turns raw
invoice files into inspectable data lake outputs with explicit accepted,
rejected, and failed outcomes — and exposes them through a conversational
analytics interface any non-technical user can operate.

## MVP2 User Journey

1. Open the web portal (CloudFront HTTPS URL).
2. Upload one or more PDF invoices via the Upload page.
3. Watch processing status transition: `Uploaded → Processing → Consolidating → Completed`.
4. Switch to the Chat tab and ask a natural-language question about the invoices.
5. Receive a Bedrock-generated answer backed by a live Athena query.

## Solution Architecture

```text
Browser
  └─ CloudFront + WAF (rate-limit)
       ├─ S3 Static Site (React + Vite SPA)
       └─ API Gateway HTTP API v2
            ├─ POST /uploads  → presigned S3 PUT (raw/ prefix triggers pipeline)
            ├─ GET  /invoices → paginated status list (S3 status/ store)
            ├─ GET  /invoices/{id}/status
            └─ POST /chat     → Bedrock NL→SQL → Athena → Bedrock NL answer

S3 raw/ → SQS → Lambda raw-dispatch → Step Functions:
  ValidateInput → ExtractOCR (Textract) → EnrichWithLLM (Bedrock)
    → PublishRunMetrics → ConsolidateGold → Completed status
  Gold Parquet → Glue Catalog → Athena workgroup
```

## Key Features

- Serverless web portal (React + Vite) hosted on S3 + CloudFront + WAF.
- HTTP upload API with presigned S3 PUT URLs; browser uploads directly to S3.
- Per-invoice status tracking (`Uploaded → Processing → Consolidating → Completed | Failed`).
- Automated Gold consolidation wired into Step Functions (SPEC-016) so every
  completed invoice is immediately queryable in Athena.
- Conversational analytics: natural-language question → Bedrock SQL generation
  → validated Athena query → Bedrock NL answer.
- Semantic Gold dataset (`gold_invoice_summary`) with business-friendly column
  names for better NL→SQL accuracy (SPEC-012).
- Remote Terraform state backend in S3 with native locking (Terraform ≥ 1.10).
- S3 data lake prefixes for raw, bronze, silver, gold, manifests, errors, and status.
- SQS buffering with DLQ routing and CloudWatch alarms for DLQ depth, Lambda
  errors, and Step Functions failures.
- Canonical contracts, quality rules, metrics, and prompts under `specs/`.
- Explicit `make` workflow for packaging, Terraform, and frontend deployment.

## Extension Features

- Pluggable LLM model selection so enrichment and NL→SQL can use different
  Bedrock models as needs evolve.
- Glue job replacement path for Lambda stages when document volume exceeds
  Lambda processing limits.
- Data warehouse consolidation path for publishing Gold data into Redshift,
  Snowflake, or another warehouse.

## Architecture Diagram

See [`docs/resources/diagram.md`](docs/resources/diagram.md) for Mermaid
diagrams covering the full pipeline flow, AWS service topology, and layer detail.

```text
Browser → CloudFront + WAF
               ├─ S3 Static Site (SPA)
               └─ API Gateway v2
                    ├─ POST /uploads → S3 raw/ → SQS → Step Functions:
                    │       ValidateInput → ExtractOCR (Textract)
                    │       → EnrichWithLLM (Bedrock) → PublishRunMetrics
                    │       → ConsolidateGold → S3 gold/ → Glue → Athena
                    ├─ GET  /invoices[/{id}/status] → S3 status/
                    └─ POST /chat → Bedrock NL→SQL → Athena → Bedrock NL answer
```

## Repository Structure

```text
ai/                 Agent guidance, skills, and context configuration
artifacts/lambda/   Generated Lambda deployment bundles
docs/               Architecture notes, runbooks, deployment history, and diagrams
frontend/           React + Vite SPA (upload, history, chat UI)
infra/bootstrap/    One-time S3 remote-state bucket provisioning stack
infra/envs/dev/     Executable Terraform entrypoint for the AWS dev environment
infra/modules/      Focused reusable Terraform modules
scripts/quality/    Ruff lint and format wrappers
scripts/windows/    Windows setup and Makefile wrapper helpers
specs/              Contracts, quality rules, metrics, prompts, and design specs
src/                Python pipeline, Lambda handlers, and analytics code
```

The older `infra/` root stack is kept as a transition baseline. New work
targets `infra/envs/dev`.

## Data Lake Layers

- `raw/`: source documents uploaded directly or under `run_id=<run_id>`.
- `bronze/textract-json/`: Textract technical evidence and extraction metadata.
- `silver/valid/`: canonical accepted documents.
- `silver/rejected/`: canonical documents rejected by quality or business rules.
- `errors/`: technical processing failures and failed silver documents.
- `gold/documents/batch_id=<batch_id>/`: curated Parquet snapshots for Athena.
- `gold/manifests/batch_id=<batch_id>/`: batch manifests kept outside the table
  prefix.

## Gold Analytics Layer

The Gold layer is provisioned in
[`infra/envs/dev/analytics.tf`](infra/envs/dev/analytics.tf) and includes:

- a Glue database `invoice_pipeline_gold`,
- an external table `gold_documents` partitioned by `batch_id`,
- an Athena workgroup `invoice-pipeline-dev` with per-query scan limits,
- a Python analytics CLI under [`src/analytics/`](src/analytics/).

Example usage after deployment:

```powershell
$lake = terraform -chdir=infra/envs/dev output -raw data_lake_bucket_name
$env:ATHENA_OUTPUT_LOCATION = "s3://$lake/athena-results/"
$env:BEDROCK_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

python -m src.analytics.cli repair-partitions
python -m src.analytics.cli sql "SELECT vendor_name, COUNT(document_id) AS docs FROM gold_documents GROUP BY vendor_name"
python -m src.analytics.cli ask "How many accepted invoices per vendor in the latest batch?"
```

Generated SQL is validated by
[`src/analytics/sql_validator.py`](src/analytics/sql_validator.py). It accepts
only single `SELECT` statements, rejects unsafe operations, limits references to
known schema objects, and enforces a bounded `LIMIT`.

## Specs And Design Records

Specs and decision records live in [`specs/`](specs/). Key references include:

- [`SPEC-004-runtime-iam-validation.md`](specs/SPEC-004-runtime-iam-validation.md)
- [`SPEC-005-structured-logging.md`](specs/SPEC-005-structured-logging.md)
- [`SPEC-006-ocr-llm-separation.md`](specs/SPEC-006-ocr-llm-separation.md)
- [`SPEC-007-terraform-remote-state.md`](specs/SPEC-007-terraform-remote-state.md)
- [`SPEC-008-analythic-layer.md`](specs/SPEC-008-analythic-layer.md)
- [`specs/contracts/`](specs/contracts/) for canonical document schemas
- [`specs/quality/`](specs/quality/) for bronze, silver, and gold rules
- [`specs/metrics/pipeline_metrics.yaml`](specs/metrics/pipeline_metrics.yaml)
  for metrics expectations

## Development And Packaging

This repository uses Python 3.11+ and `uv`.

```powershell
make init
make lint
make fmt
make package
```

On restricted Windows environments, use the wrapper flow documented under
[`docs/windows_setup/`](docs/windows_setup/), for example:

```powershell
.\scripts\windows\run_make.ps1 package
```

The Lambda bundle is generated at
`artifacts/lambda/control_plane_bundle.zip`. Lambda-only dependencies are listed
in [`requirements.lambda.txt`](requirements.lambda.txt).

## Terraform Deployment

The active dev stack is under [`infra/envs/dev`](infra/envs/dev/README.md).
Typical planning commands are:

```powershell
.\.venv\Scripts\python.exe scripts\package.py --package-manager uv
terraform -chdir=infra/envs/dev init -backend=false
terraform -chdir=infra/envs/dev validate
terraform -chdir=infra/envs/dev plan -var-file=terraform.tfvars.example
```

For a real deployment, create the artifact bucket first, upload
`artifacts/lambda/control_plane_bundle.zip` to the configured artifact key, then
plan and apply the stack. Do not run `terraform apply` without explicit approval
and a reviewed plan.

Remote state is prepared through `backend.tf.example`; copy it to `backend.tf`
only when the backend bucket and state policy are intentionally configured.

## Operational Validation

After deployment, trigger the pipeline by uploading a supported document to the
raw prefix:

```powershell
$lake = terraform -chdir=infra/envs/dev output -raw data_lake_bucket_name
aws s3 cp .\data\raw\0000089370.tif s3://$lake/raw/run_id=run-001/0000089370.tif
```

Use CloudWatch Logs, Step Functions execution history, S3 output prefixes, Glue
partitions, and Athena queries to inspect results end to end.

## Current Status

The cloud MVP has validated the business idea and the operational path:

- S3 raw upload trigger.
- SQS to Lambda dispatch.
- Step Functions execution.
- Textract-backed OCR stage.
- Bedrock-ready enrichment boundary.
- Bronze, Silver, Gold, and error routing.
- `run_id` traceability.
- CloudWatch logging and metrics.
- Glue/Athena analytics over Gold outputs.

## Roadmap

- Polish public documentation and diagrams.
- Publish representative architecture and execution evidence.
- Harden alarms, retries, selective reprocessing, and cost monitoring.
- Promote environment-specific settings for future non-dev deployments.
- Keep Terraform plans small, explicit, and reviewable.

## License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE).
