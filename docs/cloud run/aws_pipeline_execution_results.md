# AWS Pipeline Execution Results

## Context

This document records the observed results of the first end-to-end AWS pipeline
execution using the Terraform stack under `infra/envs/dev`.

Test document:

- `data/raw/0000089370.tif`

Uploaded to:

- `s3://invoice-pipeline-dev-184670914470-lake/raw/run_id=run-001/0000089370.tif`

## Observed Results

The deployed AWS path was triggered successfully:

1. S3 upload under `raw/run_id=run-001/`
2. Raw-dispatch Lambda invocation
3. Step Functions execution start
4. Document processing Lambda execution
5. Bronze output write
6. Technical failure routing to `errors/silver_failed`

Observed output objects:

- `bronze/textract-json/run_id=run-001/0000089370.json`
- `errors/silver_failed/run_id=run-001/0000089370.json`

## Bronze Result

Source:

- `logs/debug/bronze.json`

Observed payload summary:

- `status = failed`
- `extraction_engine = textract_analyze_expense`
- `run_id = run-001`
- `source_s3_key = raw/run_id=run-001/0000089370.tif`

Exact failure message:

```text
An error occurred (SubscriptionRequiredException) when calling the AnalyzeExpense operation: The AWS Access Key Id needs a subscription for the service
```

Interpretation:

- The pipeline reached Textract correctly.
- The AWS account or access key used for the run does not currently have
  usable access to `Textract AnalyzeExpense`.
- The failure is commercial or account-entitlement related, not caused by S3,
  Lambda, Step Functions, or Terraform wiring.

## Silver Failure Result

Source:

- `logs/debug/silver.json`

Observed payload summary:

- `processing_status = failed`
- `quality_status = rejected`
- `reason_code = technical_processing_failure`
- `quality_flags = ["textract_request_failed"]`
- `normalization_engine = textract_only`

Interpretation:

- Error handling worked as designed.
- The pipeline converted the Textract technical failure into a canonical failed
  silver document and routed it into `errors/silver_failed`.
- This confirms that the bronze-to-silver error path is functional.

## What Was Validated Successfully

The following parts of the cloud pipeline were validated:

- Terraform deployment path is operational
- S3 upload trigger is operational
- Raw-dispatch Lambda is operational
- Step Functions orchestration is operational
- Process-document Lambda is operational
- Bronze technical evidence write is operational
- Failed silver routing is operational
- `run_id` traceability is operational

## What Is Not Yet Validated

The following remain unvalidated in a successful AWS run:

- Successful `Textract AnalyzeExpense` extraction
- Canonical `silver/valid` output generation from AWS
- Canonical `silver/rejected` output generation from AWS business-rule failures
- Automatic `gold/documents.parquet` generation in the deployed AWS path
- Active Bedrock-based normalization in runtime

## Current Viability Assessment

Current status:

- The AWS infrastructure and trigger path are viable.
- The current account setup is not yet viable for the intended Textract-based
  document extraction path.

This means:

- the project is technically deployable
- the cloud control-plane behaves correctly
- the extraction path is blocked by account/service access, not by code

## Recommendations

### Recommendation 1: Enable a usable Textract account path

Use one of these options:

- move this workload to an AWS account with paid access to Textract
- upgrade the current AWS account so `AnalyzeExpense` can be invoked
- validate region and billing settings for the same access key used by the run

This is the preferred path if the project should stay aligned with the target
architecture described in the specs.

### Recommendation 2: Keep the current architecture target

Do not redesign around the current account limitation.

The current implementation already matches the intended service split:

- Lambda for control
- Step Functions for orchestration
- Textract for extraction
- Bronze and silver canonical outputs

That architecture remains the correct target for the project.

### Recommendation 3: Add a development fallback for continued testing

If access to paid Textract cannot be enabled immediately, add a temporary dev
fallback so the project can keep moving:

- fallback to Textract `DetectDocumentText`
- or fallback to local OCR for `dev`
- keep `AnalyzeExpense` as the target path for production-ready runs

This would allow continued validation of:

- S3 triggers
- Step Functions executions
- bronze and silver writes
- metrics publishing
- failure and retry behavior

without requiring immediate billing changes.

### Recommendation 4: Defer Bedrock activation until Textract succeeds

Bedrock is not the current bottleneck.

At this stage:

- Bedrock IAM preparation exists
- Bedrock runtime invocation is not yet enabled in the deployed processing path
- the current blocker happens before any Bedrock step

The next meaningful runtime milestone is:

1. successful Textract extraction
2. successful silver output
3. only then Bedrock-assisted normalization where ambiguity requires it

### Recommendation 5: Add gold only after successful silver validation

The deployed AWS path currently stops at bronze and silver plus metrics.

This is acceptable for the current maturity level because:

- the extraction dependency is not yet fully usable in the account
- successful silver outputs should be proven first
- gold consolidation should be added only once per-document success is stable

## Recommended Next Steps

1. Enable or move to an AWS account with usable Textract access.
2. Re-run the same test document with a new `run_id`.
3. Confirm that the output lands in `silver/valid` or `silver/rejected`.
4. Add Bedrock runtime integration only after successful Textract runs.
5. Add automated gold generation after silver success becomes stable.

## Acceptance Status Against Current Run

Functional acceptance:

- Raw documents stored under `raw/run_id=<run_id>/`: yes
- Bronze evidence produced: yes
- Silver outcome produced: yes, but as technical failure
- Gold produced: no

Operational acceptance:

- `run_metrics_generated`: partially validated through deployed metrics path
- `traceability_by_run_id`: yes
- `rejected_documents_have_reason`: yes
- `documents_processed_rate >= 0.95`: not met in this run
- `technical_failure_rate <= 0.05`: not met in this run

Quality acceptance:

- not yet assessable because extraction did not succeed
