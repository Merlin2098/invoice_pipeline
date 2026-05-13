# Phased Implementation Plan — SPEC-004, SPEC-005, SPEC-006

**Status:** Planning only (per [specs/prompts/ejecutar_hoy.md](specs/prompts/ejecutar_hoy.md) — no code, infra, or destructive changes)
**Date:** 2026-05-12

---

## Context

The invoice pipeline grew from a local OCR/LLM ETL experiment into a distributed serverless platform: S3 raw → SQS (`raw-ingestion`) → `raw_dispatch` Lambda → Step Functions → Textract + optional Bedrock → Bronze/Silver/Error layers. Recent smoke tests surfaced three structural weaknesses that the user wants to address through a coordinated, low-blast-radius rollout:

1. **Runtime IAM drift** — 40 messages went to DLQ during smoke because the Lambda execution role's effective permissions diverged from what passed CLI checks. No automated *runtime* IAM verification exists today.
2. **Insufficient observability** — Stdlib `logging` with `%`-format strings, no correlation IDs (`run_id`, `execution_id`, `document_id`, `source_s3_key`), and no `retention_in_days` on the four CloudWatch log groups.
3. **OCR/LLM coupling** — `process_document` mixes Textract OCR with Bedrock enrichment in one Lambda. Bedrock failure forces re-running Textract on retry (cost + blast radius); debugging the combined unit is hard.

This document is an internal architecture review / migration RFC. It is the answer the user asked for — a phased roadmap, dependency map, risk analysis, refactor strategy, and rollback plan — not an implementation.

---

## Executive Summary

**Phase order (non-negotiable):** Phase 0 baseline → SPEC-004 → SPEC-005 → SPEC-006 → Phase 4 hardening. Five phases total.

**Why this order:** SPEC-006 doubles the IAM surface and adds an inter-Lambda handoff. Doing it before SPEC-004/005 makes failures opaque and unsafe. SPEC-004 is pure-script (zero infra risk) and catches drift before each smoke run. SPEC-005 ships `execution_id` propagation that makes the split debuggable end-to-end.

**Three key decisions, locked:**
1. **Fuse `NormalizeOCR` into `ExtractOCR`** — final ASL is 4 task states (`ValidateInput → ExtractOCR → EnrichWithLLM → PublishRunMetrics`), not 5. `extract_expense_candidates` is 40 LOC of pure Python with no AWS calls; promoting it to a Lambda buys nothing.
2. **Incremental cutover for SPEC-006** — keep `process_document` deployed alongside the new Lambdas through Phase 3; delete in Phase 4. Sub-3-minute rollback via ASL revert.
3. **Delete the unwired legacy ASL** at [infra/modules/orchestration/state_machine.asl.json](infra/modules/orchestration/state_machine.asl.json) in Phase 0 — it references Glue states no one wired up and is a foot-gun.

**Top risks:** (a) IAM mis-split between `extract_ocr_role` and `enrich_llm_role`; (b) ASL atomic replacement stranding in-flight executions; (c) idempotency regression when HeadObject moves across the new state boundary; (d) correlation-ID gaps during the migration window.

**Note on the original HeadObject failure:** S3 enforces `HeadObject` as `s3:GetObject`. The current `process_document_data_lake_access` policy ([infra/envs/dev/main.tf:174-179](infra/envs/dev/main.tf#L174)) grants `s3:GetObject` on `silver/valid/*` (`CheckSilverIdempotency` statement), so HeadObject *should* succeed today. The 403 likely came from a prior state, a missing prefix scope, or a transient drift. SPEC-004 is the right defense regardless: validate *effective* permissions at runtime, not the policy document.

---

## 1. Architecture Impact (per spec)

### SPEC-004 — Runtime IAM Validation
- **TF modules:** none.
- **Lambda handlers:** none (optional `_dry_run` branch returning `sts.get_caller_identity()`).
- **ASL:** none.
- **Scripts (NEW):** [scripts/aws/validate-iam.ps1](scripts/aws/validate-iam.ps1), [scripts/aws/validate-runtime-access.ps1](scripts/aws/validate-runtime-access.ps1), [scripts/aws/validate-event-mappings.ps1](scripts/aws/validate-event-mappings.ps1), [scripts/aws/smoke-precheck.ps1](scripts/aws/smoke-precheck.ps1).
- **Modified:** [scripts/aws/validate_run.ps1](scripts/aws/validate_run.ps1) — call `smoke-precheck.ps1` as step 0.
- **IAM:** read-only consumer (`iam:SimulatePrincipalPolicy`, `lambda:GetFunctionConfiguration`, `lambda:ListEventSourceMappings`). No mutations.
- **Packaging:** none.

### SPEC-005 — Structured Logging
- **TF:** [infra/envs/dev/main.tf](infra/envs/dev/main.tf) — set `retention_in_days = 14` on the four existing `aws_cloudwatch_log_group` resources (lines ~60–90, per the cloudwatch_log_group module).
- **NEW:** `src/aws/logging_utils.py` — single helper `get_logger(stage)` + `bind(**kwargs)` returning a `LoggerAdapter` that emits `json.dumps({"ts","level","service","stage","run_id","execution_id","document_id","status","duration_ms","error_code","message"})`.
- **Handlers:** [src/aws/lambda_handlers/control_plane.py](src/aws/lambda_handlers/control_plane.py) — replace `%`-format `logger.info/exception` calls (notably lines 289–293 and 340–345). Each handler reads `execution_id` from the event and binds it.
- **raw_dispatch:** `start_raw_ingestion` ([src/aws/lambda_handlers/control_plane.py:180](src/aws/lambda_handlers/control_plane.py#L180)) — include `execution_id` in the SFN StartExecution input (use the SFN-generated name) and include `sqs_message_id`.
- **ASL:** [infra/envs/dev/state_machine.asl.json](infra/envs/dev/state_machine.asl.json) — every `Payload` block adds `"execution_id.$": "$$.Execution.Name"`.
- **Runner:** [src/pipeline/aws_runtime.py:161](src/pipeline/aws_runtime.py#L161) — remove module-level `logger.exception`; accept a caller-bound adapter.
- **Packaging:** rebuild `artifacts/lambda/control_plane_bundle.zip` (no new deps).

### SPEC-006 — OCR/LLM Separation
- **TF:** [infra/envs/dev/main.tf](infra/envs/dev/main.tf) — add 2 `aws_lambda_function`, 2 `aws_iam_role`, 2 inline policies, 2 `aws_cloudwatch_log_group` (`retention_in_days = 14`). Extend the SFN role's `lambda:InvokeFunction` resource list ([infra/envs/dev/main.tf:203-216](infra/envs/dev/main.tf#L203)). Keep `process_document` resources through Phase 3.
- **Permission modules:** attach [infra/modules/textract_permissions/main.tf](infra/modules/textract_permissions/main.tf) to `extract_ocr_role` only; attach [infra/modules/bedrock_permissions/main.tf](infra/modules/bedrock_permissions/main.tf) to `enrich_llm_role` only. Detach from `process_document_role` in Phase 4.
- **Handlers:** [src/aws/lambda_handlers/control_plane.py](src/aws/lambda_handlers/control_plane.py) — add `extract_ocr` and `enrich_with_llm` handlers. Keep `process_document` unchanged through Phase 3.
- **Runner:** [src/pipeline/aws_runtime.py](src/pipeline/aws_runtime.py) — split `AwsPipelineRunner.process_document` (lines 106–174) into `run_ocr()` and `run_enrichment()`.
- **ASL:** [infra/envs/dev/state_machine.asl.json](infra/envs/dev/state_machine.asl.json) — replace `ProcessDocument` with `ExtractOCR → OcrSkipped? → EnrichWithLLM` (Choice short-circuits on idempotency skip).
- **Packaging:** one bundle, two extra function configs pointing to new handler names. No packaging change.

---

## 2. Dependency Graph & Sequencing

```
Phase 0 (baseline + cleanup)
  └─► Phase 1: SPEC-004 (preflight scripts)
        └─► Phase 2: SPEC-005 (JSON logs + execution_id propagation)
              └─► Phase 3: SPEC-006 (OCR/LLM split, ASL flip)
                    └─► Phase 4: hardening (delete legacy)
```

- **SPEC-004 → SPEC-005:** SPEC-004 ships only scripts, so SPEC-005's bundle rebuild can't break it.
- **SPEC-005 → SPEC-006:** the split introduces an inter-Lambda handoff (`Bronze` written by A, read by B). Tracing it requires `execution_id` to be in every log line. Doing SPEC-006 first means debugging the new flow blind.
- **SPEC-004 is independent of SPEC-005** in theory, but stays first because it's the cheapest insurance and unblocks confident smoke runs throughout the migration.

---

## 3. Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `enrich_llm_role` cannot read Bronze written by `extract_ocr_role` | M | H | Phase 3 extends `validate-iam.ps1` with the new role pair; preflight gates the ASL flip |
| ASL atomic replacement strands in-flight executions | L | H | Drain check: `aws stepfunctions list-executions --status-filter RUNNING` must be empty pre-deploy |
| Idempotency regression (HeadObject across new boundary) | M | H | Keep HeadObject in `extract_ocr` (primary, same as today); add Bronze re-read fallback in `enrich_with_llm` for retry safety |
| CloudWatch cost from never-expiring log groups | H | L | `retention_in_days = 14` set in Phase 2 on all log groups |
| Correlation-ID gaps during migration | M | M | SPEC-005 ships before SPEC-006; validation gate is "100% of log lines for a smoke run carry `execution_id`" |
| Replay semantics change | L | M | Replay is driven by re-dropping to `raw/` — unchanged by the split. Documented in runbook |
| Bundle artifact drift between phases | M | M | Phase 0 records the current bundle SHA256 in `infra/envs/dev/versions.lock.md` |
| Dead ASL mistaken for active | H | L | Phase 0 deletes [infra/modules/orchestration/state_machine.asl.json](infra/modules/orchestration/state_machine.asl.json) |
| New IAM roles + policies require human approval per AGENTS.md | H | L | Surface explicitly in each phase's PR description |

---

## 4. Phased Rollout

### Phase 0 — Safety Baseline (no behavior change)
**Objectives:** create a recoverable baseline.
**Changes:**
- Record current `control_plane_bundle.zip` SHA256 in NEW `infra/envs/dev/versions.lock.md`.
- DELETE [infra/modules/orchestration/state_machine.asl.json](infra/modules/orchestration/state_machine.asl.json) (verified unwired — active ASL is [infra/envs/dev/state_machine.asl.json](infra/envs/dev/state_machine.asl.json)).
- NEW `docs/runbook/rollback.md` skeleton.
- Snapshot the deployed ASL via `aws stepfunctions describe-state-machine` into NEW `docs/snapshots/state_machine.<git-sha>.asl.json`.

**Validation:** run [scripts/aws/validate_run.ps1](scripts/aws/validate_run.ps1) on one fixture; output identical to today's baseline.
**Rollback:** none needed.

### Phase 1 — SPEC-004 Runtime IAM Validation
**Objectives:** every smoke run fails fast on IAM or runtime drift.
**Changes (all NEW unless noted):**
- `scripts/aws/validate-iam.ps1` — `aws iam simulate-principal-policy` for each role against the action set in [SPEC-004](specs/SPEC-004-runtime-iam-validation.md).
- `scripts/aws/validate-runtime-access.ps1` — invokes each Lambda with `{"_dry_run": true}`; handler short-circuits and returns identity.
- `scripts/aws/validate-event-mappings.ps1` — checks `State==Enabled`, `BatchSize`, `MaximumConcurrency==5`, DLQ ARN non-null.
- `scripts/aws/smoke-precheck.ps1` — orchestrator that gates [scripts/aws/validate_run.ps1](scripts/aws/validate_run.ps1).
- MODIFIED: [scripts/aws/validate_run.ps1](scripts/aws/validate_run.ps1) — call `smoke-precheck.ps1` as step 0.
- OPTIONAL: `_dry_run` branch in [src/aws/lambda_handlers/control_plane.py](src/aws/lambda_handlers/control_plane.py) for each handler.

**Validation:** detach a policy in a scratch branch and confirm `smoke-precheck.ps1` exits non-zero naming the missing action.
**Rollback:** delete the new scripts; no infra state.

### Phase 2 — SPEC-005 Structured Logging & Correlation
**Objectives:** every log line is JSON, every line carries `run_id` + `execution_id` + `document_id`, log groups have retention.
**Changes:**
- NEW: `src/aws/logging_utils.py`.
- MODIFIED: [src/aws/lambda_handlers/control_plane.py](src/aws/lambda_handlers/control_plane.py) — replace every `logger.info/exception` with `get_logger(stage).bind(...).info({...})`. `start_raw_ingestion` adds `execution_id` to the SFN StartExecution input.
- MODIFIED: [src/pipeline/aws_runtime.py](src/pipeline/aws_runtime.py) — accept an injected adapter; drop module-level `logger.exception` ([line 161](src/pipeline/aws_runtime.py#L161)).
- MODIFIED: [infra/envs/dev/state_machine.asl.json](infra/envs/dev/state_machine.asl.json) — every `Payload` block forwards `"execution_id.$": "$$.Execution.Name"`.
- MODIFIED: [infra/envs/dev/main.tf](infra/envs/dev/main.tf) — `retention_in_days = 14` on the four `aws_cloudwatch_log_group` resources.

**Validation:**
- pytest captures one record per handler and asserts JSON-parseable + required keys.
- Post-deploy: CloudWatch Insights `stats count() by execution_id, stage` returns exactly one row per (execution_id, stage) for a smoke run.
- `aws logs describe-log-groups` confirms `retentionInDays == 14`.

**Rollback:** revert bundle to Phase 0 SHA256; `terraform apply` reverts `retention_in_days` and ASL payload additions. Observability-only — no data-plane risk.

### Phase 3 — SPEC-006 OCR/LLM Split (highest risk)
**Objectives:** replace `ProcessDocument` with `ExtractOCR → EnrichWithLLM`. Incremental cutover.

**Step 3a — Code (no infra flip yet):**
- MODIFIED: [src/pipeline/aws_runtime.py](src/pipeline/aws_runtime.py) — split `AwsPipelineRunner.process_document` ([lines 106–174](src/pipeline/aws_runtime.py#L106)):
  - NEW `run_ocr(request) -> {bronze_key, candidate, failed_doc?}`: lines 107–156 (Textract call + Bronze write + `extract_expense_candidates`).
  - NEW `run_enrichment(request, candidate, bronze_key) -> silver_document`: lines 157–174 (Bedrock + `build_aws_silver_document`).
- MODIFIED: [src/aws/lambda_handlers/control_plane.py](src/aws/lambda_handlers/control_plane.py):
  - NEW handler `extract_ocr`: idempotency HeadObject ([lines 283–306 verbatim](src/aws/lambda_handlers/control_plane.py#L283)), call `runner.run_ocr(...)`, write Bronze, return `{run_id, execution_id, document_id, bronze_s3_key, candidate, processing_status}`.
  - NEW handler `enrich_with_llm`: read `candidate` from event (fallback: re-read Bronze for retry safety), Bedrock + Silver build, PutObject to silver/errors prefix.
  - `process_document` retained unchanged.

**Step 3b — Infra:**
- MODIFIED: [infra/envs/dev/main.tf](infra/envs/dev/main.tf):
  - 2 new `aws_lambda_function` (handlers `src.aws.lambda_handlers.control_plane.extract_ocr` and `.enrich_with_llm`), same bundle.
  - 2 new `aws_iam_role` + inline policies:
    - `extract_ocr_role`: `s3:GetObject` on `raw/*` and `silver/valid/*` (HeadObject); `s3:ListBucket` on `raw/*`; `s3:PutObject` on `bronze/*`.
    - `enrich_llm_role`: `s3:GetObject` on `bronze/*`; `s3:PutObject` on `silver/valid/*`, `silver/rejected/*`, `errors/*`; Bedrock InvokeModel.
  - 2 new `aws_cloudwatch_log_group` (`retention_in_days = 14`).
  - SFN role `lambda:InvokeFunction` list ([lines 203–216](infra/envs/dev/main.tf#L203)) gains the two new ARNs. Keep `process_document_lambda` ARN through Phase 4.
- MODIFIED: [infra/envs/dev/state_machine.asl.json](infra/envs/dev/state_machine.asl.json):
  ```
  ValidateInput → InputValid?
                    ├─ true  → ExtractOCR → OcrSkipped?
                    │                         ├─ true  → PublishRunMetrics
                    │                         └─ false → EnrichWithLLM → PublishRunMetrics
                    └─ false → ValidationFailed
  ```
  `ExtractOCR.ResultPath = $.ocr`; `EnrichWithLLM` payload combines `$.ocr.Payload` (`bronze_s3_key`, `candidate`, `document_id`) with `$.validation.Payload` (`run_id`, `source_s3_key`, `source_file_name`, `created_at`, `execution_id`).
- MODIFIED: `scripts/aws/validate-iam.ps1` — add new roles to the action matrix.

**Validation:**
- Pre-deploy: `aws stepfunctions list-executions --status-filter RUNNING` empty.
- Post-deploy: smoke run; CloudTrail confirms Bronze written by `extract_ocr_role`, Silver by `enrich_llm_role`.
- Idempotency: redrop same `raw/` object; `OcrSkipped?` takes `true` branch; Bedrock `InvocationCount` delta = 0.
- Retry: simulate `enrich_with_llm` failure; redrive; Bronze re-read path succeeds.

**Rollback:** `aws stepfunctions update-state-machine --definition file://docs/snapshots/state_machine.<phase0-sha>.asl.json`. Legacy `process_document` is still deployed and wired by that snapshot. RTO ~2 min. New Lambdas left orphaned (harmless, no triggers).

### Phase 4 — Post-Migration Hardening
**Objectives:** retire legacy, finalize docs.
**Changes:**
- DELETE `process_document` handler from [src/aws/lambda_handlers/control_plane.py](src/aws/lambda_handlers/control_plane.py).
- DELETE `AwsPipelineRunner.process_document` from [src/pipeline/aws_runtime.py](src/pipeline/aws_runtime.py).
- DELETE `process_document_lambda`, `process_document_role`, `process_document_data_lake_access`, and the SFN role grant for the legacy ARN from [infra/envs/dev/main.tf](infra/envs/dev/main.tf).
- Detach Textract/Bedrock module attachments from `process_document_role`.
- Update `docs/runbook/rollback.md` to point at the new ASL snapshot.

**Validation:** full smoke + replay. `validate_run.ps1` green.
**Rollback:** revert the deletion commit; prior bundle SHA pinned in `versions.lock.md` allows TF to recreate the legacy Lambda.

---

## 5. SPEC-006 Refactor Strategy (locked decisions)

- **Cutover:** incremental coexistence (confirmed).
- **NormalizeOCR:** fused into `ExtractOCR` (confirmed). `extract_expense_candidates` ([src/pipeline/aws_runtime.py:38-78](src/pipeline/aws_runtime.py#L38)) is pure synchronous Python with zero AWS calls. Promoting it to a Lambda adds ~100ms cold-start, a third IAM role, an extra ASL hop, and another `lambda:InvokeFunction` grant — for code that executes in-process in under 1ms.
- **Idempotency:** two layers, asymmetric.
  - Primary: HeadObject on `silver_valid_key` in `extract_ocr` (same as today's [line 288](src/aws/lambda_handlers/control_plane.py#L288)). When hit, the `OcrSkipped?` Choice skips `enrich_with_llm`. Preserves "skip entire pipeline if final output exists".
  - Secondary: in `enrich_with_llm`, if `candidate` is absent (SFN retry after partial failure), HeadObject + GetObject on `bronze_key` to reload — avoids re-billing Textract.
- **S3 prefixes:** no new prefixes. `bronze/textract-json/run_id=<run>/<doc>.json` (via [build_storage_key](src/pipeline/run_context.py#L57)), `silver/valid/`, `silver/rejected/`, `errors/`. The split is a Lambda boundary, not a data-layout change.
- **Reusable code map:**

| Today | New home |
|---|---|
| `TextractAnalyzeExpenseClient` ([control_plane.py:132](src/aws/lambda_handlers/control_plane.py#L132)) | `extract_ocr` |
| `extract_expense_candidates` ([aws_runtime.py:38](src/pipeline/aws_runtime.py#L38)) | `run_ocr` (fused) |
| Bronze write ([aws_runtime.py:139-154](src/pipeline/aws_runtime.py#L139)) | `run_ocr` |
| `BedrockNormalizerClient` ([bedrock_client.py](src/aws/bedrock_client.py)) | `enrich_with_llm` |
| `should_use_bedrock` ([aws_runtime.py:81](src/pipeline/aws_runtime.py#L81)) | `run_enrichment` |
| `build_aws_silver_document` ([quality.py](src/pipeline/quality.py)) | `run_enrichment` |
| `create_failed_document` ([quality.py](src/pipeline/quality.py)) | both (Textract failure in `extract_ocr`, Bedrock failure in `enrich_with_llm`) |
| `_process_output_key` + final PutObject ([control_plane.py:347-355](src/aws/lambda_handlers/control_plane.py#L347)) | `enrich_with_llm` |
| HeadObject idempotency ([control_plane.py:285-306](src/aws/lambda_handlers/control_plane.py#L285)) | `extract_ocr` (primary) + `enrich_with_llm` Bronze re-read (secondary) |

---

## 6. File Change Index (per phase)

**Phase 0:**
- NEW: `infra/envs/dev/versions.lock.md`, `docs/runbook/rollback.md`, `docs/snapshots/state_machine.<sha>.asl.json`
- DELETE: [infra/modules/orchestration/state_machine.asl.json](infra/modules/orchestration/state_machine.asl.json)

**Phase 1 (SPEC-004):**
- NEW: `scripts/aws/validate-iam.ps1`, `scripts/aws/validate-runtime-access.ps1`, `scripts/aws/validate-event-mappings.ps1`, `scripts/aws/smoke-precheck.ps1`
- MODIFIED: [scripts/aws/validate_run.ps1](scripts/aws/validate_run.ps1)
- OPTIONAL: [src/aws/lambda_handlers/control_plane.py](src/aws/lambda_handlers/control_plane.py) (`_dry_run` branch)

**Phase 2 (SPEC-005):**
- NEW: `src/aws/logging_utils.py`
- MODIFIED: [src/aws/lambda_handlers/control_plane.py](src/aws/lambda_handlers/control_plane.py), [src/pipeline/aws_runtime.py](src/pipeline/aws_runtime.py), [infra/envs/dev/state_machine.asl.json](infra/envs/dev/state_machine.asl.json), [infra/envs/dev/main.tf](infra/envs/dev/main.tf)

**Phase 3 (SPEC-006):**
- MODIFIED: [src/pipeline/aws_runtime.py](src/pipeline/aws_runtime.py), [src/aws/lambda_handlers/control_plane.py](src/aws/lambda_handlers/control_plane.py), [infra/envs/dev/main.tf](infra/envs/dev/main.tf), [infra/envs/dev/state_machine.asl.json](infra/envs/dev/state_machine.asl.json), `scripts/aws/validate-iam.ps1`

**Phase 4:**
- MODIFIED: [src/aws/lambda_handlers/control_plane.py](src/aws/lambda_handlers/control_plane.py) (delete legacy handler), [src/pipeline/aws_runtime.py](src/pipeline/aws_runtime.py) (delete fused method), [infra/envs/dev/main.tf](infra/envs/dev/main.tf) (delete legacy Lambda/role/policy)

---

## 7. Testing Strategy

- **Unit (all phases):** existing pytest suite stays green. SPEC-006 adds tests for `run_ocr` and `run_enrichment` independently using the `TextractExpenseExtractor` and `BedrockNormalizer` protocols already defined in [src/pipeline/aws_runtime.py:15-22](src/pipeline/aws_runtime.py#L15).
- **IAM (Phase 1+):** `simulate-principal-policy` is dry-run by definition — zero spend. Negative test: detach a policy in a scratch branch, confirm preflight fails naming the action.
- **Logging (Phase 2):** pytest with `caplog` asserts every record is JSON-parseable with the required key set. End-to-end: CloudWatch Insights `stats count() by execution_id, stage` returns exactly one row per (execution_id, stage) for a smoke run.
- **Local integration (Phase 3):** `LocalJsonStore` + mock Textract returning canned `ExpenseDocuments` + mock Bedrock — exercises the split without AWS spend.
- **Idempotency (Phase 3):** redrop the same `raw/` object; second run's Step Functions history shows `OcrSkipped? → true → PublishRunMetrics`; Bedrock `InvocationCount` delta = 0.

---

## 8. Rollback Strategy

| Phase | Rollback | RTO |
|---|---|---|
| 0 | N/A (additive/dead-code removal) | — |
| 1 | Delete the new scripts | < 1 min |
| 2 | Revert bundle to Phase 0 SHA256; `terraform apply` reverts `retention_in_days` and ASL payload additions | ~5 min |
| 3 | `aws stepfunctions update-state-machine --definition file://docs/snapshots/state_machine.<phase0-sha>.asl.json` — legacy `process_document` still deployed | ~2 min |
| 4 | Revert the deletion commit; TF recreates the legacy Lambda from the SHA pinned in `versions.lock.md` | ~5–10 min |

---

## 9. Approval Boundaries (per [AGENTS.md](AGENTS.md))

These phases create IAM changes and Terraform module changes — they require user approval before each `terraform apply`:
- Phase 2: log group `retention_in_days` additions (TF module change).
- Phase 3: two new IAM roles + new inline policies + new Lambda resources + permission module re-attachments + SFN role grant extension (IAM + module changes).
- Phase 4: IAM role and Lambda resource deletions.

No `terraform apply`, `terraform destroy`, or state mutation is performed by this plan — only proposed.

---

## Critical Files for Implementation

- [src/aws/lambda_handlers/control_plane.py](src/aws/lambda_handlers/control_plane.py) — all Lambda handlers (split target)
- [src/pipeline/aws_runtime.py](src/pipeline/aws_runtime.py) — `AwsPipelineRunner.process_document` (split target)
- [infra/envs/dev/state_machine.asl.json](infra/envs/dev/state_machine.asl.json) — active ASL (replaced in Phase 3)
- [infra/envs/dev/main.tf](infra/envs/dev/main.tf) — Lambdas, roles, policies, log groups, SFN
- [scripts/aws/validate_run.ps1](scripts/aws/validate_run.ps1) — smoke test entry point
- [infra/modules/textract_permissions/main.tf](infra/modules/textract_permissions/main.tf), [infra/modules/bedrock_permissions/main.tf](infra/modules/bedrock_permissions/main.tf) — service permission modules to re-attach
- [src/aws/bedrock_client.py](src/aws/bedrock_client.py), [src/pipeline/quality.py](src/pipeline/quality.py), [src/pipeline/run_context.py](src/pipeline/run_context.py) — reusable building blocks
