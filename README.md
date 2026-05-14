# Invoice Intelligence Pipeline

## Overview

Invoice Intelligence Pipeline is an AWS and Terraform data engineering template
for document ingestion, invoice extraction, quality validation, and layered data
lake outputs. The repository keeps a local development baseline while the active
cloud MVP lives under [`infra/envs/dev`](infra/envs/dev/README.md).

The current AWS MVP is intentionally small and explicit: S3 receives raw
documents, SQS buffers upload events, Lambda starts and runs processing stages,
Step Functions coordinates the document workflow, and CloudWatch captures logs
and metrics.

## Business Problem

Invoice processing often starts with semi-structured files and ends with fragile
manual review, inconsistent fields, and limited traceability. This project
targets the gap between raw invoice files and reliable downstream data products
by making every document outcome visible, reproducible, and tied to a `run_id`.

The repository is also a bootstrap template, so the implementation favors
destroyable dev infrastructure, explicit commands, and reusable guidance for
host projects.

## Solution Architecture

The AWS MVP uses a decoupled event flow:

1. A document is uploaded to `s3://<data-lake-bucket>/raw/<file>` or
   `s3://<data-lake-bucket>/raw/run_id=<run_id>/<file>`.
2. S3 sends the upload event to the raw ingestion SQS queue.
3. The `raw-dispatch` Lambda consumes the SQS message, generates a `run_id`
   when the key does not contain one, and starts Step Functions.
4. Step Functions runs `ValidateInput -> ExtractOCR -> EnrichWithLLM -> PublishRunMetrics`.
5. The pipeline writes bronze evidence, silver outcomes, technical errors, and
   CloudWatch metrics.

The local pipeline remains useful for regression tests and fast iteration, but
the cloud target is the current architecture of record.

## Key Features

- Terraform-managed AWS dev environment under `infra/envs/dev`.
- S3 data lake prefixes for raw, bronze, silver, gold, and errors.
- SQS buffer with DLQ for raw upload events.
- Step Functions orchestration with separated OCR and LLM stages.
- Lambda handlers for dispatch, validation, OCR extraction, LLM enrichment, and
  metrics publishing.
- Textract `AnalyzeExpense` integration for invoice extraction.
- Bedrock permissioning and optional runtime normalization path.
- Canonical contracts and quality rules under `specs/`.
- `uv`-based local workflow with Makefile targets for setup, linting, tests,
  packaging, and AI context refresh.

## Architecture Diagram

Graphviz

The maintainable Graphviz source is
[`docs/resources/architecture.dot`](docs/resources/architecture.dot).

```text
S3 raw/ or raw/run_id=<run_id>/
        |
        v
SQS raw-ingestion ----> SQS DLQ
        |
        v
Lambda raw-dispatch
        |
        v
Step Functions document-pipeline
        |
        v
ValidateInput
        |
        v
ExtractOCR ----> Textract AnalyzeExpense
        |                  |
        |                  v
        |        S3 bronze/textract-json/
        v
EnrichWithLLM ----> Bedrock optional normalization
        |
        v
S3 silver/valid/ | silver/rejected/ | errors/
        |
        v
PublishRunMetrics ----> CloudWatch Logs + Metrics
```

## Processing Flow

The deployed state machine in
[`infra/envs/dev/state_machine.asl.json`](infra/envs/dev/state_machine.asl.json)
contains these runtime states:

- `ValidateInput` checks required fields, supported extensions, and `run_id`
  traceability.
- `ExtractOCR` calls Textract, writes bronze technical evidence, and returns an
  OCR candidate or a failed document.
- `EnrichWithLLM` reads the OCR candidate or bronze record, optionally calls
  Bedrock, and writes the final silver or error document.
- `PublishRunMetrics` emits custom metrics to CloudWatch.

If OCR is skipped or fails, the workflow bypasses LLM enrichment and publishes
metrics for that outcome.

## AWS Services Used

- Amazon S3 for artifact storage and layered data lake storage.
- Amazon SQS for raw ingestion buffering and DLQ routing.
- AWS Lambda for dispatch, validation, extraction, enrichment, and metrics.
- AWS Step Functions for workflow orchestration.
- Amazon Textract for invoice-focused OCR and expense extraction.
- Amazon Bedrock for optional LLM-assisted normalization.
- Amazon CloudWatch for logs and custom metrics.
- AWS IAM for scoped runtime permissions.
- AWS Budgets for dev cost tracking.

## Repository Structure

```text
ai/                 Agent guidance, skills, and context configuration
artifacts/lambda/   Generated Lambda deployment bundle
docs/               Architecture notes, runbooks, prompts, and resources
infra/envs/dev/     Executable Terraform entrypoint for the AWS MVP
infra/modules/      Focused reusable Terraform modules
scripts/windows/    Windows setup and Makefile wrapper helpers
specs/              Contracts, quality rules, metrics, and design specs
src/                Python pipeline and AWS runtime code
tests/              Unit tests, AWS smoke helpers, and reference fixtures
```

The older `infra/` root stack is kept as a transition baseline; new AWS MVP work
should use `infra/envs/dev`.

## Data Lake Layers

- `raw/`: source documents uploaded directly as `raw/<file>` or by run using
  `raw/run_id=<run_id>/<file>`.
- `bronze/textract-json/`: Textract technical evidence and extraction metadata.
- `silver/valid/`: canonical accepted documents.
- `silver/rejected/`: canonical documents rejected by quality or business rules.
- `errors/`: technical processing failures, including failed silver documents.
- `gold/documents/batch_id=<batch_id>/`: curated Parquet snapshot plus manifest
  for a completed batch. Gold preserves accepted documents and marks cross-run
  duplicates with `document_fingerprint`, `business_key`, and duplicate status
  fields.

## Current Pipeline Design

The pipeline separates deterministic extraction from probabilistic enrichment.
Textract owns invoice OCR and expense extraction. Bedrock is reserved for
normalization or ambiguity resolution after OCR succeeds. Quality rules and
contracts keep output status explicit instead of silently promoting bad records.

The currently deployed AWS run validated the control plane through S3, SQS,
Lambda, Step Functions, bronze writes, failed silver routing, and `run_id`
traceability. Gold consolidation is implemented as an explicit Parquet snapshot
step for stable `silver/valid` output, but a successful deployed extraction run
is still blocked at Textract by an AWS account or service subscription
requirement, not by Terraform wiring.

## Specs & ADRs

Specs and decision records live in [`specs/`](specs/). Key references include:

- [`SPEC-004-runtime-iam-validation.md`](specs/SPEC-004-runtime-iam-validation.md)
- [`SPEC-005-structured-logging.md`](specs/SPEC-005-structured-logging.md)
- [`SPEC-006-ocr-llm-separation.md`](specs/SPEC-006-ocr-llm-separation.md)
- [`SPEC-007-terraform-remote-state.md`](specs/SPEC-007-terraform-remote-state.md)
- [`specs/contracts/`](specs/contracts/) for canonical document schemas.
- [`specs/quality/`](specs/quality/) for bronze, silver, and gold rules.
- [`specs/metrics/pipeline_metrics.yaml`](specs/metrics/pipeline_metrics.yaml)
  for metrics expectations.

## Local Development

This repository uses Python 3.11+ and `uv` as the primary package workflow.

```powershell
make init
make lint
make test
make package
```

On restricted Windows environments, use the wrapper flow documented under
[`docs/windows_setup/`](docs/windows_setup/) or run:

```powershell
.\scripts\windows\run_make.ps1 test
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
plan and apply the full stack. Do not run `terraform apply` without explicit
approval and a reviewed plan.

Remote state is prepared through `backend.tf.example`; copy it to `backend.tf`
only when the backend bucket and state policy are intentionally configured.

## Operational Scripts

AWS smoke and validation helpers live in [`tests/aws`](tests/aws):

- `smoke-precheck.ps1` checks required local and AWS prerequisites.
- `validate-iam.ps1` validates IAM assumptions and caller identity.
- `validate-runtime-access.ps1` invokes deployed Lambdas with dry-run payloads.
- `validate-event-mappings.ps1` checks event-source mapping wiring.
- `validate-logging.ps1` checks CloudWatch log groups and retention.
- `validate-tags-budget.ps1` checks required tags and budget filters.
- `smoke-direct-raw-upload.ps1` uploads raw documents, invokes Gold finalization,
  and downloads logs plus Bronze/Silver/Gold outputs.
- `validate_run.ps1` supports deployed run validation.

Windows workflow helpers live in [`scripts/windows`](scripts/windows):

- `setup_env.ps1`
- `update_venv.ps1`
- `run_make.ps1`

## Smoke Tests

Use the AWS smoke and validation scripts after Terraform outputs are available.
The runtime dry-run check invokes each deployed Lambda with a safe payload:

```powershell
.\tests\aws\validate-runtime-access.ps1
```

To trigger the actual pipeline after deployment, upload a supported document to
the raw prefix:

```powershell
$lake = terraform -chdir=infra/envs/dev output -raw data_lake_bucket_name
aws s3 cp .\data\raw\0000089370.tif s3://$lake/raw/run_id=run-001/0000089370.tif
```

## Observability

CloudWatch log groups are explicitly managed for Lambda functions and Step
Functions. The metrics stage publishes custom document metrics such as processed,
accepted, rejected, failed, field presence, and unknown document type counts.

Current observability is useful for control-plane validation and failed-path
debugging. Successful extraction quality metrics require Textract access to be
enabled and a successful AWS run to be completed.

## Current Status

The AWS infrastructure and trigger path are viable. A first AWS execution
confirmed:

- S3 raw upload trigger.
- SQS to Lambda dispatch.
- Step Functions execution start.
- Bronze evidence write.
- Failed silver routing under `errors/`.
- `run_id` traceability.

The current blocker is account or service access to Textract `AnalyzeExpense`.
The observed failure is `SubscriptionRequiredException`, so successful
`silver/valid`, business-rule `silver/rejected`, active Bedrock normalization,
and automated gold generation remain unvalidated in the deployed AWS path.

## Roadmap

- Enable or move to an AWS account with usable Textract `AnalyzeExpense` access.
- Re-run the same reference document with a new `run_id`.
- Confirm successful outputs under `silver/valid/` or `silver/rejected/`.
- Activate Bedrock normalization only after Textract succeeds.
- Add automated gold consolidation after silver output is stable.
- Harden alarms, retries, selective reprocessing, and cost monitoring.

## Lessons Learned

- Separate OCR and LLM responsibilities to reduce retry blast radius and avoid
  paying for repeated extraction when enrichment fails.
- Treat local execution as a regression baseline, not the cloud target.
- Keep Terraform entrypoints explicit and environment-scoped.
- Validate runtime IAM and event wiring before chasing application logic.
- Route technical failures into canonical outputs so failed runs remain
  inspectable.

## License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE).
