# Invoice Pipeline Architecture Overview

## Objective

This document describes how the document processing pipeline for the `Invoice Intelligence Pipeline` project is structured, how it runs locally, and how it operates today in AWS.

The goal is to clearly separate:

- the real document processing flow
- the configuration, contracts, and prompts that govern the logic
- the AWS services that provide execution, cataloging, security, and observability

## Overview

The project follows a `medallion` architecture extended with technical errors and an analytics layer. The current flow is:

```text
Raw -> Bronze -> Silver (valid | rejected) -> Gold -> Analytics
                                            |
                                            +-> Errors (technical failures)
```

In execution terms, the system operates in two modes:

- `local`, using Python directly on disk for regression testing
- `aws`, using `Lambda + Step Functions` orchestration

Business logic does not live hardcoded inside Lambda handlers. It is split across:

- `Python`: runtime, OCR/LLM stages, validation, materialization, and analytics CLI
- `YAML`: canonical contracts, quality rules, and metric expectations under `specs/`
- `Prompts`: Bedrock system prompts for normalization and natural-language SQL
- `Terraform`: AWS infrastructure under `infra/envs/dev`
- `ASL`: Step Functions state machine definition

## Pipeline Structure

### 1. Raw

This is the arrival zone for the source document and the pipeline trigger point in AWS.

- Locally, sample documents live under `data/raw/`
- In AWS, the document lands in the shared data lake bucket under `raw/<file>` or, preferably, `raw/run_id=<run_id>/<file>`
- The pipeline trigger is based on the creation of an object under the `raw/` prefix

Raw does not apply business transformations. It only represents the entry point and the `run_id` partitioning convention.

### 2. Bronze

Bronze captures the technical evidence produced by Textract.

The `extract-ocr` Lambda:

- reads the document key from the validated input
- calls Textract `AnalyzeExpense`
- persists the raw Textract response as JSON
- returns an OCR candidate plus the `bronze_s3_key`

Bronze output:

- `bronze/textract-json/run_id=<run_id>/<document_id>.json`

Bronze is intentionally close to the wire format so that downstream stages can be re-derived without re-paying Textract cost.

### 3. Silver

Silver is the canonical document layer.

The `enrich-llm` Lambda:

- reads the OCR candidate or the bronze record
- optionally calls Bedrock when `BEDROCK_MODEL_ID` is set, to normalize ambiguous fields
- applies quality rules from `specs/quality/`
- writes the final canonical record as JSON

Logical datasets:

- `silver/valid/run_id=<run_id>/<document_id>.json`
- `silver/rejected/run_id=<run_id>/<document_id>.json`

Technical and operational metadata included:

- `run_id`
- `document_id`
- `extraction_engine`
- `normalization_engine`
- `llm_model_id`
- `bedrock_invoked`
- `processing_status`
- `quality_status`
- `quality_flags`
- `created_at`

Write policy:

- `silver/valid`: per-document write, idempotent per `document_id`
- `silver/rejected`: per-document write, includes `rejection_reason`
- `errors/`: per-document write for technical failures (Textract subscription error, Bedrock failure, infra error)

### 4. Gold

Gold is the analytical layer.

The `consolidate-gold` Lambda runs as a post-batch finalizer:

- reads silver valid, silver rejected, and errors terminal outputs for the batch
- preserves accepted documents and marks cross-run duplicates
- writes a partitioned Parquet snapshot in `Hive-style` format

The current partition scheme is:

```text
gold/documents/batch_id=<batch_id>/
```

Logical dataset:

- `gold_documents`

Duplicate-detection metadata:

- `document_fingerprint`
- `business_key`
- `is_duplicate`
- `duplicate_of_document_id`
- `duplicate_strategy`
- `duplicate_confidence`

Manifest layout:

- `gold/manifests/batch_id=<batch_id>/` is kept outside the Athena table prefix so that `gold_documents` partitions contain only Parquet files

Write policy:

- `silver`: per-document overwrite by `document_id`
- `gold`: per-batch overwrite of the `batch_id` partition only

### 5. Analytics

The project adds a Gold analytics layer cataloged in Glue and queryable from Athena.

Provisioned in [`infra/envs/dev/analytics.tf`](../../infra/envs/dev/analytics.tf):

- Glue database `invoice_pipeline_gold`
- Glue external table `gold_documents`, partitioned by `batch_id`
- Athena workgroup `invoice-pipeline-dev` with a 100 MB per-query scan cutoff
- Athena results stored under `s3://<data_lake_bucket>/athena-results/`

Consumption flow:

- `src/analytics/cli.py` exposes `repair-partitions`, `sql`, and `ask` subcommands
- `ask` sends the user question plus the schema and the system prompt at `specs/prompts/bedrock_analytics_sql_prompt.md` to Amazon Bedrock
- the generated SQL is gated by `src/analytics/sql_validator.py` (SELECT-only, no `SELECT *`, known tables and columns, default `LIMIT 100`)
- validated SQL is executed against the Athena workgroup and results are streamed back

Current Athena path:

```text
s3://<data_lake_bucket>/athena-results/
```

Output behavior:

- format: Athena query result CSV
- layout: per-query result file written by Athena
- write mode: append (one object per query execution)
- intended consumption: analytical and natural-language questions over the Gold layer

## Files That Govern the Pipeline

The main pipeline artifacts live under `src/`, `specs/`, and `infra/`:

- [`src/pipeline/aws_runtime.py`](../../src/pipeline/aws_runtime.py): shared runtime used by Lambda handlers
- [`src/pipeline/bronze_pipeline.py`](../../src/pipeline/bronze_pipeline.py): OCR extraction and bronze write
- [`src/pipeline/silver_pipeline.py`](../../src/pipeline/silver_pipeline.py): canonical document materialization
- [`src/pipeline/quality.py`](../../src/pipeline/quality.py): quality rules and gating
- [`src/pipeline/gold_model.py`](../../src/pipeline/gold_model.py): Gold record schema and duplicate logic
- [`src/aws/lambda_handlers/control_plane.py`](../../src/aws/lambda_handlers/control_plane.py): Lambda entrypoints
- [`src/aws/glue_jobs/consolidate_gold.py`](../../src/aws/glue_jobs/consolidate_gold.py): post-batch finalizer
- [`src/analytics/`](../../src/analytics/): Athena client, SQL validator, Bedrock SQL generator, CLI
- [`specs/contracts/`](../../specs/contracts/): canonical document schemas
- [`specs/quality/`](../../specs/quality/): bronze, silver, and gold quality rules
- [`specs/metrics/pipeline_metrics.yaml`](../../specs/metrics/pipeline_metrics.yaml): metrics expectations
- [`specs/prompts/bedrock_normalization_prompt.md`](../../specs/prompts/bedrock_normalization_prompt.md): LLM enrichment prompt
- [`specs/prompts/bedrock_analytics_sql_prompt.md`](../../specs/prompts/bedrock_analytics_sql_prompt.md): natural-language SQL prompt
- [`infra/envs/dev/main.tf`](../../infra/envs/dev/main.tf): root Terraform stack for the dev environment
- [`infra/envs/dev/analytics.tf`](../../infra/envs/dev/analytics.tf): Glue + Athena analytics layer
- [`infra/envs/dev/state_machine.asl.json`](../../infra/envs/dev/state_machine.asl.json): Step Functions definition

## Local Execution

Locally, the pipeline runs without AWS by exercising the bronze and silver Python modules directly.

The main entry surface is the Lambda handler under `src/aws/lambda_handlers/control_plane.py`, which is also reusable in tests.

Local flow:

1. reads a document from `data/raw/`
2. invokes the bronze stage and persists Textract output (or a mocked equivalent) to `data/output/bronze/`
3. runs the silver stage and writes valid or rejected canonical documents under `data/output/silver/`
4. optionally consolidates a Gold snapshot locally to `data/output/gold/`

This mode allows logic, contracts, prompts, and outputs to be validated without depending on AWS Textract or Bedrock.

## AWS Execution

In AWS the pipeline operates with Lambda-based execution and Step Functions orchestration.

### Pipeline Trigger

Processing starts when a document is created in the `raw/` prefix of the data lake bucket.

Current flow:

1. S3 receives the file in `raw/<file>` or `raw/run_id=<run_id>/<file>`
2. S3 publishes the event to the raw ingestion SQS queue
3. The `raw-dispatch` Lambda consumes the SQS message and generates a `run_id` when the key does not contain one
4. `raw-dispatch` calls `StartExecution` on the Step Functions state machine
5. Step Functions executes:
   - `ValidateInput`
   - `ExtractOCR`
   - `EnrichWithLLM`
   - `PublishRunMetrics`
6. After a batch completes, the `consolidate-gold` Lambda finalizes the Gold snapshot and manifest

### AWS Services Around the Pipeline

#### S3

A single shared data lake bucket is used, with explicit prefixes:

- `raw/`
- `bronze/textract-json/`
- `silver/valid/`
- `silver/rejected/`
- `errors/`
- `gold/documents/batch_id=<batch_id>/`
- `gold/manifests/batch_id=<batch_id>/`
- `athena-results/`

A separate artifact bucket is used for the Lambda deployment package.

Responsibilities:

- storage for raw, bronze, silver, gold, and error artifacts
- storage for the Lambda deployment zip
- Athena query result storage

#### AWS Lambda

Lambda is the cloud compute layer for the document workflow.

Modeled functions:

- `raw-dispatch`
- `validate-input`
- `extract-ocr`
- `enrich-llm`
- `publish-metrics`
- `consolidate-gold`

Responsibilities:

- execute the Python pipeline handlers
- call Textract and Bedrock through the AWS SDK
- write bronze, silver, error, and gold artifacts to S3
- publish custom metrics to CloudWatch

#### AWS Step Functions

This is the main orchestrator for the per-document workflow.

Responsibilities:

- order the validate, extract, enrich, and publish-metrics sequence
- propagate `run_id`, `document_id`, and routing flags
- centralize control flow and skip enrichment when OCR is skipped or fails
- provide visibility into the state of each document execution

#### Amazon SQS

SQS is used as the buffer between S3 events and the dispatcher.

Responsibilities:

- buffer raw upload events with backoff and visibility timeout
- route poison messages to a dead letter queue after `maxReceiveCount=3`
- decouple S3 spikes from Step Functions concurrency

#### Amazon Textract

Textract is the deterministic OCR and expense extraction engine.

Responsibilities:

- run `AnalyzeExpense` on the raw document
- return structured expense fields and confidence scores

#### Amazon Bedrock

Bedrock is reserved for probabilistic enrichment.

Responsibilities:

- normalize ambiguous OCR fields when invoked from `enrich-llm`
- translate analyst natural-language questions into validated Athena SQL when invoked from `src/analytics/`

#### Glue Data Catalog

This is used to register Gold analytical datasets.

Responsibilities:

- expose the `gold_documents` external table
- serve as the Athena catalog source of truth

#### Amazon Athena

Athena is used for analytical consumption of the Gold layer.

Responsibilities:

- run validated SELECT queries against `gold_documents`
- enforce a workgroup-level scan-bytes cutoff per query
- produce result CSV objects under `athena-results/`

Analytics consumption path:

- the active Gold consumption path is the `src/analytics/cli.py` tool
- `repair-partitions` registers new `batch_id` partitions in Glue
- `sql` runs an analyst-authored SELECT through the validator
- `ask` runs the Bedrock NL -> SQL flow before executing the query

#### CloudWatch

This is used for baseline observability.

Responsibilities:

- Lambda and Step Functions logs
- custom pipeline metrics (`processed`, `accepted`, `rejected`, `failed`, field presence, unknown document type)
- Athena workgroup metrics

#### AWS Budgets

This is used for dev cost tracking.

Responsibilities:

- monitor monthly spend for the project
- surface cost drift before it impacts the next deployment

#### IAM

Scoped IAM roles back every runtime component.

Responsibilities:

- separate roles per Lambda function
- managed policies for Textract and Bedrock access
- Step Functions execution role with explicit Lambda invoke permissions

## Implementation Status

The real current status is:

- the local flow is implemented and validated for the bronze and silver stages
- the AWS control plane based on S3, SQS, Lambda, and Step Functions is implemented in code and infrastructure
- the AWS flow has been validated functionally for raw upload, SQS dispatch, Step Functions orchestration, Textract extraction, Bedrock enrichment, Silver routing, Gold consolidation, and `run_id` traceability
- the shared runtime, Lambda bundle, and analytics layer are deployed through Terraform
- Gold manifests are written outside the Athena table prefix so `gold_documents` partitions contain only Parquet files
- the Athena + Bedrock natural-language analytics path has been validated end to end against a live Gold batch

In other words:

- `local`: validated for bronze, silver, and Gold regression behavior
- `aws control plane`: exercised end to end
- `aws extraction`: working for the reference smoke batch
- `aws analytics`: validated with Glue partition repair, Athena SQL, and Bedrock NL -> SQL

## Summary

This project implements a `config-driven` document pipeline with:

- event-driven ingestion from `raw/`
- a Textract bronze layer
- a canonical silver layer split into accepted, rejected, and errors
- a partitioned Gold layer with duplicate detection
- a Glue-cataloged Athena analytics layer
- a Bedrock-assisted natural-language SQL path gated by a SELECT-only validator
- local Python execution for regression testing
- AWS execution with Lambda, Step Functions, SQS, Textract, and Bedrock
- orchestration with Step Functions
- event buffering with SQS plus DLQ
- cataloging with Glue Catalog
- analytical consumption with Athena

## Future Features

Potential future analytics integrations include:

- QuickSight in direct query mode over Athena
- Power BI through the Athena driver
- scheduled Athena queries publishing curated marts back to S3

Those remain optional future features and are not part of the active runtime path today.

Note about pipeline limits:

- the analytics SQL validator intentionally rejects DDL, DML, `SELECT *`, and unknown identifiers; questions that require new columns or new tables should be modeled in `src/analytics/schema_registry.py` first
- the source of truth for architecture remains the current repository under `src/`, `infra/`, `specs/`, and this documentation
