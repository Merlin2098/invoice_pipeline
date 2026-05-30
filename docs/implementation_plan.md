# Invoice Intelligence Pipeline — Data Product Evolution: Implementation Plan

> **Type:** Analysis & planning only. No code, infrastructure, or files were
> modified to produce this document (other than creating this file).
> **Date:** 2026-05-30
> **Scope:** Evolve the validated AWS invoice MVP into a complete serverless
> Data Product (web portal + upload APIs + conversational analytics + remote
> Terraform backend), per `specs/product/` and `specs/technical/`.
> **Evidence base:** Conclusions are grounded in repository files. Where the
> repository is silent, this is marked **ASSUMPTION** explicitly.

---

## 1. Repository Assessment

### 1.1 Current Architecture

The repository implements a **cloud-first, event-driven invoice processing
pipeline** on AWS, managed by Terraform. The validated flow
(`README.md`, `infra/envs/dev/state_machine.asl.json`) is:

```
S3 raw/ (or raw/run_id=<run_id>/)
   -> S3 event notification
   -> SQS raw-ingestion queue (with DLQ)
   -> Lambda raw-dispatch        (start_raw_ingestion)
   -> Step Functions document-pipeline:
        ValidateInput -> ExtractOCR (Textract) -> EnrichWithLLM (Bedrock) -> PublishRunMetrics
   -> S3 bronze / silver(valid|rejected) / errors
Post-batch (invoked separately, NOT in the state machine):
   -> Lambda consolidate-gold -> S3 gold/documents/batch_id=<id>/documents.parquet
                              -> S3 gold/manifests/batch_id=<id>/manifest.json
Analytics (local CLI today):
   -> Glue Catalog (invoice_pipeline_gold.gold_documents)
   -> Athena workgroup (invoice-pipeline-dev)
   -> Bedrock NL -> SQL (src/analytics CLI)
```

**Key observation:** `consolidate_gold` is **not** a state in
`state_machine.asl.json`. The state machine terminates at `PublishRunMetrics`.
Gold consolidation is an out-of-band Lambda (`module.consolidate_gold_lambda`)
called manually / by a smoke finalizer (see output description
"used by the post-batch smoke finalizer"). There is **no automated batch close**.

### 1.2 Existing Capabilities

| Capability | Evidence | Status |
|---|---|---|
| Event-driven raw ingestion (S3 → SQS → Lambda) | `infra/envs/dev/main.tf` (`aws_s3_bucket_notification.raw_upload`, `aws_lambda_event_source_mapping.raw_dispatch_sqs`) | Working (validated MVP) |
| Step Functions orchestration | `state_machine.asl.json`, `module.invoice_pipeline_state_machine` | Working |
| OCR via Textract AnalyzeExpense | `control_plane.py:TextractAnalyzeExpenseClient`, `module.textract_permissions` | Working |
| Bedrock normalization (enrichment) | `control_plane.py:enrich_with_llm`, `src/aws/bedrock_client.py`, `module.bedrock_permissions` | Working |
| Bronze/Silver/Gold/Errors layering | `control_plane.py`, `src/pipeline/gold_model.py` | Working |
| `run_id` / `execution_id` / `batch_id` traceability | `control_plane.py`, structured logging | Working |
| CloudWatch logs + custom metrics | per-Lambda log groups, `publish_run_metrics` | Working |
| Gold consolidation + dedup markers | `gold_model.py`, `consolidate_gold` | Working |
| Glue Data Catalog + explicit `gold_documents` table | `infra/envs/dev/analytics.tf` | Working |
| Athena workgroup w/ scan cutoff + enforced output | `analytics.tf:aws_athena_workgroup.analytics` | Working |
| NL→SQL with deterministic SQL validation | `src/analytics/{bedrock_sql,sql_validator,athena_client,cli}.py` | Working (CLI only) |
| Cost guardrail (AWS Budget $20/mo) | `infra/envs/dev/budget.tf` | Working |

### 1.3 Existing AWS Resources (active `infra/envs/dev`)

- **S3:** artifact bucket, data-lake bucket (with prefix markers for raw/bronze/silver/gold/manifests/errors/athena-results).
- **SQS:** `raw-ingestion` queue + DLQ (`module.sqs_queue`), with S3→SQS send policy.
- **Lambda (7):** raw-dispatch, validate-input, process-document, extract-ocr, enrich-llm, publish-metrics, consolidate-gold. All share one bundle `artifacts/lambda/control_plane_bundle.zip`.
- **Step Functions:** `invoice-pipeline-dev-document-pipeline`.
- **IAM:** per-Lambda least-privilege roles; Textract + Bedrock managed policies attached selectively.
- **CloudWatch:** per-Lambda + Step Functions log groups.
- **Glue:** database `invoice_pipeline_gold` + external table `gold_documents` (partition `batch_id`).
- **Athena:** workgroup `invoice-pipeline-dev` (100 MB scan cutoff, enforced result location).
- **Budgets:** monthly cost budget with forecasted/actual alerts.

### 1.4 Existing Terraform Structure

- **Active stack:** `infra/envs/dev/` (entrypoint per `AGENTS.md` and `README.md`).
- **Modules:** `infra/modules/{s3_bucket, sqs_queue, lambda_function, iam_role, cloudwatch_log_group, step_function, s3_notification, textract_permissions, bedrock_permissions}` — these are the modules actually consumed by `infra/envs/dev`.
- **Legacy root stack:** `infra/main.tf` references a different module set (`storage`, `compute`, `orchestration`, `observability`) and Glue-job variables (`normalize_script_s3_key`, `consolidate_script_s3_key`) **not present** in the active dev flow. `README.md` calls it a "transition baseline." **Treated as stale/legacy** in this plan.
- **Backend:** local state today. `infra/envs/dev/backend.tf.example` defines an S3 backend with a DynamoDB lock table, both placeholders (`replace-me-*`). `backend.tf` is gitignored (`.gitignore`). **No Terraform resources create the state bucket/lock table** — they are assumed pre-provisioned out-of-band.
- **Providers:** AWS `~> 5.0`, Terraform `>= 1.6.0`.

### 1.5 Existing Deployment Model

Per `README.md` and `AGENTS.md`:
1. Package Lambda bundle (`scripts/package.py` / `make package`) → `artifacts/lambda/control_plane_bundle.zip`.
2. Create artifact bucket, upload bundle to `artifacts/lambda/control_plane_bundle.zip` key.
3. `terraform -chdir=infra/envs/dev init/validate/plan` (currently `-backend=false`).
4. `terraform apply` only with explicit approval.
5. Single shared bundle drives all 7 Lambdas; `source_code_hash` derived via `filebase64sha256` on the local zip.

### 1.6 Existing Analytics Capabilities

- **Glue + Athena**: `gold_documents` queryable, partition-aware (`batch_id`), scan-capped.
- **NL→SQL**: `BedrockSqlGenerator.generate_sql()` uses `converse` API + schema-grounded prompt (`specs/prompts/bedrock_analytics_sql_prompt.md`) + `schema_registry.table_schema_prompt()`.
- **SQL validation** (`sql_validator.py`): SELECT-only, blocks DDL/DML keywords, blocks `SELECT *`, table allowlist (`gold_documents`), identifier allowlist (columns/aliases/functions/keywords), enforced `LIMIT` (default 100, max 1000).
- **Execution** (`athena_client.py`): start → poll → fetch rows; reports scan MB + elapsed.
- **CLI** (`cli.py`): `repair-partitions`, `sql <query>`, `ask <question>`.
- **Gap:** entirely **local/credentialed CLI**. No HTTP API, no result-to-natural-language summarization step (CLI returns rows + SQL as JSON).

---

## 2. Spec Review

### 2.1 Per-spec summary

| Spec | Objective | Components Impacted | Complexity |
|------|-----------|---------------------|------------|
| **SPEC-010** (product) Static Web Portal | Serverless browser UI to upload PDFs, track status, view history, access chat | S3 static site, CloudFront, API Gateway, upload Lambda, presigned URLs, **frontend app (new)**, IAM, Terraform | **High** |
| **SPEC-011** (product) Conversational Analytics | NL question → Bedrock SQL → validate → Athena → **NL response** | New chat Lambda + API GW; reuse `src/analytics` (`bedrock_sql`, `sql_validator`, `athena_client`); **add result→NL summarization**; Bedrock/Athena/Glue IAM | **Medium** |
| **SPEC-012** (product) Semantic Gold dataset | New `gold_invoice_summary` table with business-friendly columns for better NL→SQL | Gold writer (`gold_model.py`/`consolidate_gold`), Glue table, `schema_registry.py`, contract spec | **Medium** |
| **SPEC-013** (product) Conversational Agent UI | Chat UI inside the portal (history, loading, tables/metrics formatting) | Frontend (subset of SPEC-010), Chat API (SPEC-011) | **Medium** (mostly frontend; depends on 010/011) |
| **SPEC-014** (technical) Remote Backend | Terraform state in S3, versioned, gitignored, locked | `backend.tf`, state bucket + lock, deployment runbook | **Low–Medium** (state migration risk) |
| **SPEC-007** (design record) Terraform Remote State | ADR backing SPEC-014; S3 backend, versioning, SSE, public-access block, locking | Same as SPEC-014 | **Low–Medium** |
| **SPEC-008** (design record) Gold Analytics Layer | ADR backing the existing Glue/Athena/Bedrock NL→SQL CLI | Already implemented (analytics.tf + src/analytics) | **Done** (baseline) |
| **MVP2-definition** (product) | Defines "done": open web app → upload PDF → pipeline runs → NL query → NL answer | Cross-cutting acceptance gate over 010/011/012/013 | n/a (acceptance) |

### 2.2 Notable spec details & tensions

- **SPEC-008 vs SPEC-011/013:** SPEC-008 **intentionally defers** API Gateway / public query endpoints ("A Lambda/API Gateway interface is intentionally deferred", "Excluded: API Gateway or public query endpoints"). SPEC-011/013 now **require** that deferred API. This is an explicit, sanctioned evolution — not a contradiction — but the analytics code was written for a CLI, not an HTTP handler.
- **SPEC-011 FR-005 (NL response):** the current CLI does **not** convert results back to natural language. This is a genuine missing capability, not just a transport change.
- **SPEC-012 column model:** `gold_invoice_summary` columns (`supplier_name`, `subtotal_amount`, `tax_amount`, `total_amount`, `document_type`, `processing_date`, `currency`, `invoice_id`, `invoice_date`) differ from `gold_documents` (`vendor_name`, `total_amount`, `document_date`, `document_id`, `created_at`, no `subtotal_amount`/`tax_amount`). **Source data for `subtotal_amount`/`tax_amount` is not currently captured** in Silver/Gold — see Gap Analysis.
- **SPEC-010 file constraint:** PDF only, ≤ 20 MB. Current pipeline trigger suffix is configurable (`raw_trigger_suffix`, default null) and the validator's supported extensions come from `src/config/pipeline.yaml` (`ocr.supported_extensions`) — ✅ **`.pdf` is confirmed in `supported_extensions`** (Phase 0 verification).
- **SPEC-014/007 backend:** SPEC-007 example uses bucket `invoice-pipeline-dev-tfstate` and **no DynamoDB**; `backend.tf.example` **does** specify a DynamoDB lock table. Reconcile (DynamoDB locking is recommended and satisfies NFR-002).

---

## 3. Gap Analysis

> Status legend: **Implemented** (verified in code) · **Partial** (foundation
> exists, incomplete vs spec) · **Missing** (no code evidence).

### 3.1 SPEC-014 / SPEC-007 — Remote Terraform Backend

| Requirement | Status | Notes / Evidence |
|---|---|---|
| State in S3 (FR-001) | **Partial** | `backend.tf.example` defines S3 backend; `backend.tf` gitignored. No active backend; plans run `-backend=false`. |
| State bucket versioning (FR-002, NFR-001) | **Missing (as IaC)** | No Terraform resource creates/versions the state bucket. Assumed pre-provisioned manually. |
| State files not committed (FR-003) | **Implemented** | `.gitignore` excludes `*.tfstate*`, `backend.tf`, `*.tfvars`. |
| Deployments use remote backend (FR-004) | **Missing** | Active workflow uses local state / `-backend=false`. |
| State locking (NFR-002) | **Missing (as IaC)** | `backend.tf.example` references a DynamoDB lock table, but no resource creates it. |
| Encryption / public-access block on state bucket (SPEC-007) | **Missing (as IaC)** | Not provisioned by repo. |

### 3.2 SPEC-008 — Gold Analytics (baseline)

| Requirement | Status | Notes |
|---|---|---|
| Glue DB + explicit `gold_documents` table | **Implemented** | `analytics.tf`. |
| Athena dev workgroup, enforced output, scan limit | **Implemented** | `analytics.tf` (100 MB cutoff). |
| NL→SQL via Bedrock, schema-grounded | **Implemented** | `bedrock_sql.py` + prompt + registry. |
| SQL validation (SELECT-only, allowlists, LIMIT) | **Implemented** | `sql_validator.py`. |
| Read-only, cost-aware, reproducible | **Implemented** | workgroup limits + validator. |
| Observability log shape (`query_id`, `user_question`, `generated_sql`, ...) | **Partial** | CLI prints `query_id/status/generated_sql/execution_time_ms/athena_scan_mb`; `user_question` not logged in the specified structured shape. |

### 3.3 SPEC-012 — Semantic Gold Dataset (`gold_invoice_summary`)

| Requirement | Status | Notes |
|---|---|---|
| New table `gold_invoice_summary` | **Missing** | Only `gold_documents` exists (`analytics.tf`, `schema_registry.py`). |
| Business-friendly columns | **Partial** | `gold_documents` already uses readable names (`vendor_name`, `total_amount`) but **not** the SPEC-012 names (`supplier_name`) and **lacks** `subtotal_amount`, `tax_amount`. |
| Generated from Silver | **Partial** | `gold_model.build_documents_table` builds from Silver; a `summary` projection would extend this. |
| `subtotal_amount` / `tax_amount` columns | **Missing (upstream data)** | Not captured in Silver schema or Textract candidate mapping. Requires extraction work, not just a SELECT projection. |
| Registered in Glue + queryable in Athena | **Missing** | No Glue table for the summary dataset. |

### 3.4 SPEC-011 — Conversational Analytics (as a service)

| Requirement | Status | Notes |
|---|---|---|
| Accept free-text questions (FR-001) | **Partial** | Works in CLI (`ask`); no API endpoint. |
| Bedrock SQL generation (FR-002) | **Implemented** | `bedrock_sql.py`. |
| SQL validation (FR-003) | **Implemented** | `sql_validator.py` (blocks INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE; SELECT-only). |
| Execute against Athena (FR-004) | **Implemented** | `athena_client.py`. |
| Result → natural-language response (FR-005) | **Missing** | CLI returns rows+SQL JSON; no LLM summarization of results. |
| < 10 s avg response (NFR-001) | **Partial/Unverified** | Athena polls at 1 s, 60 s timeout; Bedrock + Athena round trip may exceed 10 s on cold/large scans. No measurement. |
| Only Gold exposed to Bedrock (NFR-002) | **Implemented** | Schema grounding + table allowlist = `gold_documents` only. |
| Block non-read-only SQL (NFR-003) | **Implemented** | `sql_validator.py`. |
| HTTP/API surface | **Missing** | No API Gateway / Lambda handler for analytics. |

### 3.5 SPEC-010 / SPEC-013 — Web Portal & Chat UI

| Requirement | Status | Notes |
|---|---|---|
| Static frontend app | **Missing** | No `frontend/`, `web/`, `ui/`, or `app/` directory (verified via glob). |
| S3 static hosting (NFR-003) | **Missing** | No static-site bucket/config. |
| CloudFront | **Missing** | No `aws_cloudfront_*` (verified via grep). |
| API Gateway (upload + chat) | **Missing** | No `aws_api_gateway*` / `aws_apigatewayv2*` (verified via grep). |
| Upload Lambda + presigned URLs (FR-001/002) | **Missing** | No presigned-URL code; raw uploads today are direct `aws s3 cp`. |
| Processing status (FR-003) | **Missing** | No status store/index. Pipeline writes Silver/Gold but no per-document status API/table. |
| Invoice history table (FR-004) | **Partial (data only)** | Underlying data exists in Gold; no API or UI to surface it. |
| Deployable via Terraform (NFR-002) | **Missing** | No frontend deployment IaC. |
| Fully serverless (NFR-001) | **Implemented (backend)** | Existing backend is serverless; frontend stack must follow suit. |
| Chat UI (SPEC-013 FR-001..004) | **Missing** | No UI; depends on SPEC-010 + SPEC-011 API. |

### 3.6 Cross-cutting MVP2 gaps

- **PDF support unverified:** confirm `src/config/pipeline.yaml` `ocr.supported_extensions` includes `pdf` (README operational example uses `.tif`). Textract `AnalyzeExpense` supports PDF, but the validator gate must allow it.
- **Status tracking:** no document-status registry (DynamoDB or Athena view) exists to back SPEC-010 FR-003/FR-004 in real time.
- **CORS / auth:** no API auth model defined; SPEC-010 says "non-technical users" but specs do not specify Cognito/auth. **ASSUMPTION needed** (see §4.6).
- **Automated batch close:** Gold consolidation is manual/out-of-band; a web product implies automatic batch finalization so uploaded invoices appear in analytics without operator action.

---

## 4. Architecture Recommendations

### 4.1 Static Web Portal (SPEC-010/013)
- **S3 (private) + CloudFront + Origin Access Control (OAC)** for static hosting; do not make the bucket public (aligns with `AGENTS.md` least-privilege).
- Build artifacts deployed to the site bucket via Terraform (`aws_s3_object`) or a documented post-apply sync; prefer keeping the frontend build out of Terraform state for large asset sets (use `aws s3 sync` in a runbook) — **ASSUMPTION** pending team preference (§4.6).
- New top-level `frontend/` app (static SPA; framework TBD — see §4.6). Keep it separate from `src/` Python per `AGENTS.md` separation rule.

### 4.2 Upload API (SPEC-010 FR-001/002)
- **API Gateway (HTTP API v2)** → **upload Lambda** that returns an **S3 presigned PUT URL** scoped to `raw/run_id=<run_id>/<file>.pdf`. Browser uploads directly to S3 (keeps payloads off Lambda/API GW; respects 20 MB limit cleanly).
- Reuse the **existing S3→SQX→Step Functions trigger** unchanged — presigned upload lands in `raw/` and the pipeline fires automatically. **Minimal backend refactor.**
- Add a least-privilege role for the upload Lambda: `s3:PutObject` on `raw/*` only (presign does not require broad perms; the *caller's* presigned URL inherits the Lambda role's permission to that key).

### 4.3 Conversational Analytics API (SPEC-011/013)
- **API Gateway (HTTP API) → chat Lambda** that imports the **existing** `src/analytics` package (`BedrockSqlGenerator`, `validate_sql`, `AthenaClient`).
- **Add a result-summarization step** (new): second Bedrock `converse` call that turns Athena rows into a business-friendly answer (FR-005). Keep it bounded (row cap + token cap).
- Package: the analytics modules must ship in the Lambda bundle. Today `control_plane_bundle.zip` is built from `scripts/package.py`; confirm it includes `src/analytics` and its deps (`boto3` is in the Lambda runtime; pandas is **not** needed for query path). **Avoid adding pandas to the chat Lambda.**
- IAM: chat Lambda role needs `athena:StartQueryExecution/GetQueryExecution/GetQueryResults`, `glue:GetTable/GetPartitions`, `s3` read on `gold/*` + read/write on `athena-results/*`, and `bedrock:InvokeModel` (reuse `bedrock_permissions` module pattern).

### 4.4 Bedrock Query Layer
- Reuse current schema-grounding + validation. **If SPEC-012 lands**, point NL→SQL at `gold_invoice_summary` (cleaner columns → better SQL accuracy) and register it in `schema_registry.py` + `_ALLOWED_DATABASES`/`TABLES`.
- Keep the SQL validator authoritative server-side regardless of frontend.

### 4.5 Remote Terraform Backend (SPEC-014/007)
- **Decision:** provision the state bucket + DynamoDB lock table in a **separate, minimal bootstrap stack** (`infra/bootstrap/` — new) with local state, so the main stack can adopt the S3 backend without a chicken-and-egg problem. Apply bootstrap once, then `terraform init -migrate-state` for `infra/envs/dev`.
- State bucket: versioning ON, SSE (SSE-S3 or KMS), `aws_s3_bucket_public_access_block` all true, deterministic name (`invoice-pipeline-dev-tfstate-<account_id>` to avoid global collisions).
- **Locking: S3 native state locking** (`use_lockfile = true`) — no DynamoDB required. Requires Terraform >= 1.10. Satisfies SPEC-014 NFR-002 and eliminates the DynamoDB resource from `backend.tf.example`.

### 4.6 Data Model Changes
- **SPEC-012 `gold_invoice_summary`:** add as a **projection/view over `gold_documents`** for columns that already exist (`invoice_id`←`document_id`, `supplier_name`←`vendor_name`, `invoice_date`←`document_date`, `total_amount`, `currency`, `document_type`, `processing_date`←`created_at`).
  - `subtotal_amount` / `tax_amount` have **no upstream source** today → either (a) defer/null them, or (b) extend Textract candidate extraction + Silver contract first. Recommend an **Athena view** initially (zero new pipeline risk), upgrading to a materialized Gold table only if needed.
- **Status tracking (SPEC-010 FR-003/004):** introduce a lightweight status index. Options:
  - **DynamoDB** (`invoice_id` → status), updated by the existing Lambdas (small IAM + code change), best for live status.
  - **Athena over Silver/Gold** (no new infra), but only reflects terminal states post-batch.
  - **ASSUMPTION:** DynamoDB recommended for responsive UI; confirm with team.

### 4.7 API Contracts
Full contracts are defined in [`specs/technical/SPEC-015-api-contracts.md`](../specs/technical/SPEC-015-api-contracts.md) (Phase 0 deliverable).

Summary:
- `POST /uploads` → presigned S3 PUT URLs scoped to `raw/run_id=<id>/<file>.pdf`.
- `GET /invoices` → paginated invoice history.
- `GET /invoices/{id}/status` → `{ status: Uploaded|Processing|Completed|Failed }`.
- `POST /chat` → `{ answer, generated_sql, rows, query_id, execution_time_ms, athena_scan_mb }`.

### 4.8 Security Considerations
- Presigned URLs: short TTL, content-type + key-prefix constrained, size enforced client-side and via S3 policy where possible.
- API auth: **specs do not define auth.** Recommend **Cognito Hosted UI** (or at minimum API keys / WAF) for a public portal. **DECISION NEEDED** (§ open questions).
- CloudFront: HTTPS only, OAC, restrict S3 to CloudFront.
- Maintain least privilege per `AGENTS.md`; no broad `s3:*`/`bedrock:*`.
- SQL validator remains the trust boundary for analytics; never trust frontend-side validation.

### 4.9 Open Questions / Decisions Needed

Tracked with recommendations in [`docs/adr/ADR-001-phase0-decisions.md`](adr/ADR-001-phase0-decisions.md).

| # | Decision | Recommendation | Required before |
|---|---|---|---|
| D1 | Auth model | ✅ No auth + WAF rate-limit | Phase 3 |
| D2 | Status store | ✅ S3 objects in `status/` prefix (data lake bucket) | Phase 3 |
| D3 | Lambda bundle strategy | ✅ Separate `chat_bundle.zip` (pandas-free) | Phase 4 |
| D4 | `subtotal/tax` for SPEC-012 | ✅ Null initially (Athena view) | Phase 2 |
| D5 | Frontend framework | ✅ React + Vite | Phase 5 |

Additionally, **V5 batch close gap** was identified in Phase 0: Gold consolidation
is not triggered automatically after uploads. This is now formalized as
[**SPEC-016 — Automated Gold Consolidation**](../specs/technical/SPEC-016-automated-gold.md)
and scoped as **Phase 4.5** (after the chat API exists, before the frontend), so the
portal's `Completed` status is truthful for the MVP2 user journey.

---

## 5. Implementation Roadmap

### Phase 0 — Foundation ✅ COMPLETE

- **Objective:** De-risk everything downstream; lock decisions; verify PDF path.
- **Deliverables produced:**
  - [`specs/technical/SPEC-015-api-contracts.md`](../specs/technical/SPEC-015-api-contracts.md) — full HTTP API contracts for upload, status, history, and chat endpoints.
  - [`docs/adr/ADR-001-phase0-decisions.md`](adr/ADR-001-phase0-decisions.md) — verified findings (V1–V5) and open decisions (D1–D5) with recommendations.
- **Verified findings:**
  - ✅ V1: `.pdf` confirmed in `src/config/pipeline.yaml` `ocr.supported_extensions`.
  - ✅ V2: `src/analytics` confirmed included in Lambda bundle (`INCLUDE_DIRS = [src/, specs/]`).
  - ⚠️ V3: `pandas`/`pyarrow` in `requirements.lambda.txt` (~120 MB); chat Lambda needs separate slim bundle (D3).
  - ⚠️ V4: `subtotal_amount`/`tax_amount` confirmed absent from Silver schema and Gold model (D4).
  - ⚠️ V5: Gold consolidation is not automated; uploads will not appear in analytics automatically — **new scope item** for Phase 3/4.
- **AWS services:** none changed.
- **Open decisions D1–D5:** recommendations provided in ADR-001; require team confirmation before Phase 2+ begin.

### Phase 1 — Remote Backend (SPEC-014/007)
- **Objective:** Safe, locked, versioned remote state before adding lots of new resources.
- **Deliverables:** `infra/bootstrap/` stack (state bucket + DynamoDB lock, versioning, SSE, public-access block); real `infra/envs/dev/backend.tf`; migrate state; update deployment docs.
- **Files:** new `infra/bootstrap/*.tf`; `infra/envs/dev/backend.tf` (from example); `docs/cloud run/deployment_sequence.md` update; `README.md` Terraform section.
- **AWS services:** S3, DynamoDB.
- **Risks:** **State migration** (`init -migrate-state`) — highest IaC risk. Back up `terraform.tfstate` first; do in a quiet window.
- **Dependencies:** Phase 0.
- **Effort:** M (1–2 days incl. migration + verification).

### Phase 2 — Semantic Dataset (SPEC-012)
- **Objective:** Better analytics surface for the chat layer (do before chat API to ground prompts on clean columns).
- **Deliverables:** `gold_invoice_summary` as an **Athena view** (or Glue table) mapping existing Gold columns; register in `schema_registry.py` + validator allowlists; contract spec under `specs/contracts/`.
- **Files:** `infra/envs/dev/analytics.tf` (view/table), `src/analytics/schema_registry.py`, `src/analytics/sql_validator.py`, `specs/prompts/bedrock_analytics_sql_prompt.md`, new `specs/contracts/gold_invoice_summary.schema.yaml`.
- **AWS services:** Glue, Athena.
- **Risks:** `subtotal_amount`/`tax_amount` data gap → decide null vs upstream capture.
- **Dependencies:** Phase 0; independent of backend but easier post-Phase 1.
- **Effort:** M.

### Phase 3 — Upload API (SPEC-010 backend slice)
- **Objective:** Programmatic, browser-friendly invoice upload reusing the existing pipeline trigger.
- **Deliverables:** API Gateway (HTTP) + upload Lambda (presigned PUT); status endpoint + status store (per §4.6 decision); IAM role; Terraform.
- **Files:** `infra/envs/dev/main.tf` (or new `infra/envs/dev/web_api.tf`), new Lambda handler in `src/aws/lambda_handlers/`, IAM policy docs, `scripts/package.py` if new handler added; optional DynamoDB module.
- **AWS services:** API Gateway, Lambda, S3, (DynamoDB).
- **Risks:** CORS, presign correctness, 20 MB enforcement, status freshness; verify PDF triggers Textract end-to-end.
- **Dependencies:** Phase 0 (contracts/auth); Phase 1 (backend) recommended first.
- **Effort:** M–L.

### Phase 4 — Conversational Analytics API (SPEC-011 + result-NL)
- **Objective:** HTTP chat endpoint with NL answer.
- **Deliverables:** Chat Lambda wrapping `src/analytics` + **new result-summarization** Bedrock call; API GW route; IAM (Athena/Glue/Bedrock/S3); structured analytics logging per SPEC-008 shape (`user_question`, `generated_sql`, ...).
- **Files:** new handler in `src/aws/lambda_handlers/`, possibly `src/analytics/` (add `summarize_results`), `infra/envs/dev/*.tf`, packaging.
- **AWS services:** API Gateway, Lambda, Bedrock, Athena, Glue, S3.
- **Risks:** NFR-001 (<10 s) under cold start + Athena latency; cost of double Bedrock calls; bundle bloat (keep pandas out of this Lambda).
- **Dependencies:** Phase 2 (cleaner schema) preferred; Phase 0/1.
- **Effort:** M.

### Phase 4.5 — Automated Gold Consolidation (SPEC-016)
- **Objective:** Close the **V5 gap** (Gold consolidation is manual / out-of-band):
  make uploaded invoices automatically queryable in Athena once processing
  completes, so `Status = Completed` ⇒ `Available in Gold` (SPEC-016 FR-002).
  Without this, the Phase 5 chat UI would report `Completed` for invoices that
  are not yet visible to the chat/analytics layer.
- **Deliverables:**
  - Extend `state_machine.asl.json`: after `PublishRunMetrics`, add `ConsolidateGold`
    (invoke existing `consolidate_gold` Lambda) → `UpdateStatusCompleted` → `PipelineCompleted`.
  - New status state **`Consolidating`** (SPEC-016 FR-004); status lifecycle becomes
    `Uploaded → Processing → Consolidating → Completed | Failed`.
  - Move the terminal `Completed` write **out of** `enrich_with_llm` (it currently
    writes `Completed`/`Failed` directly) so `enrich_with_llm` writes `Consolidating`
    on accept, and the **post-consolidation step writes `Completed`**. `Failed` paths
    are unchanged.
  - Reconcile the `consolidate_gold` invocation contract with the **single-document**
    state machine: the existing handler requires `batch_id` + `expected_documents`
    (a batch finalizer shape). Per-execution, derive a single-document batch
    (e.g. `batch_id = execution_id`, `expected_documents = [{run_id, document_id}]`)
    so one Lambda serves both the smoke finalizer and the inline path (NFR-001:
    no new consolidation Lambda).
  - IAM: grant the **Step Functions role** permission to invoke `consolidate_gold_lambda`
    (today the state machine role only invokes validate/extract/enrich/publish);
    grant `consolidate_gold_role` the `status/` write permission used by `_write_status`.
  - Idempotency (FR-006): rely on existing Gold dedup markers in `gold_model.py`;
    re-running a single-document batch must not duplicate rows.
  - Failure isolation (FR-003): a `ConsolidateGold` failure must not corrupt prior
    Gold; on failure, route to a status write of `Failed` (or retain `Consolidating`)
    without a partial Gold write — the existing `incomplete` short-circuit already
    avoids partial writes when a document lacks a terminal state.
- **Files:** `infra/envs/dev/state_machine.asl.json` (new states), `infra/envs/dev/main.tf`
  (state machine `templatefile` gains `consolidate_gold_lambda_arn`; SFN role IAM;
  `consolidate_gold_role` status-write policy), `src/aws/lambda_handlers/control_plane.py`
  (status-state changes + single-document batch shaping), `specs/technical/SPEC-016-automated-gold.md`
  (already authored). No frontend changes.
- **AWS services:** Step Functions, Lambda, S3, Glue, Athena (all existing; NFR-001/002/003).
- **Risks:**
  - **Changes deployed runtime behavior** (state machine definition + status semantics
    + SFN IAM) → **requires explicit approval before `terraform apply`** per `AGENTS.md`.
  - Latency: per-invoice Gold consolidation adds a Step Functions step + a pandas/pyarrow
    Lambda invocation to every document (the consolidate Lambda is the *fat* bundle,
    not the slim chat one) — watch cold starts and the AWS Budget.
  - Single-document `batch_id=<execution_id>` produces many small Parquet batches in
    `gold/documents/batch_id=*/` — acceptable for MVP2; cross-batch compaction is
    explicitly **out of scope** (SPEC-016 Out of Scope).
  - The `gold_invoice_summary` view (Phase 2) reads `gold_documents`; verify partitions
    are discoverable (run `MSCK REPAIR` / partition projection) so newly written
    `batch_id` partitions are visible to Athena without manual `repair-partitions`.
- **Dependencies:** Phase 2 (Gold/summary schema), Phase 3 (status store + `Processing`
  write), Phase 4 (chat API consumes the now-fresh Gold). Must land **before** Phase 5
  so the portal's `Completed` status is truthful (SPEC-016 AC-004).
- **Effort:** M.
- **Acceptance (SPEC-016):** AC-001..AC-004 — a freshly uploaded PDF reaches Gold with
  no manual `consolidate_gold` call, and the chatbot can query it once status is `Completed`.

### Phase 5 — Frontend Portal + Chat UI (SPEC-010 + SPEC-013) & Hardening
- **Objective:** User-facing portal: upload, status, history, chat. Plus docs/hardening.
- **Deliverables:** `frontend/` SPA (upload w/ progress, status table, history, chat w/ history+loading+table formatting); S3+CloudFront+OAC; Terraform deploy; (auth if chosen); updated `README.md`/architecture diagram; alarms/retry/cost review.
- **Files:** new `frontend/**`, `infra/envs/dev/web_portal.tf` (S3 site + CloudFront), `docs/resources/*`, `README.md`.
- **AWS services:** S3, CloudFront, (Cognito), API Gateway (consumed).
- **Risks:** Frontend/build complexity, CloudFront cache invalidation, auth integration, CORS end-to-end.
- **Dependencies:** Phases 3 & 4 (APIs must exist).
- **Effort:** L.

---

## 6. Backlog (Epic → Feature → Task)

### Epic: Remote Terraform Backend (SPEC-014/007)
- **Feature: State bootstrap stack**
  - Task: Create `infra/bootstrap/` (S3 state bucket: versioning, SSE, public-access block).
  - Task: Add DynamoDB lock table.
  - Task: Outputs for bucket/table names.
  - Task: Runbook: apply bootstrap once with local state.
- **Feature: Adopt remote backend in dev**
  - Task: Create `infra/envs/dev/backend.tf` from example (real names; account-scoped bucket).
  - Task: Back up local state; `terraform init -migrate-state`; verify plan = no-op.
  - Task: Update `docs/cloud run/deployment_sequence.md` and `README.md`.

### Epic: Semantic Gold Dataset (SPEC-012)
- **Feature: `gold_invoice_summary`**
  - Task: Decide view vs materialized table; decide `subtotal_amount`/`tax_amount` (null vs upstream).
  - Task: Create Athena view/Glue table mapping `gold_documents` → SPEC-012 columns.
  - Task: Add table to `schema_registry.py` (+ partition handling) and validator allowlists.
  - Task: Add `specs/contracts/gold_invoice_summary.schema.yaml`.
  - Task: Update NL→SQL prompt to ground on the summary table.

### Epic: Upload API (SPEC-010 backend)
- **Feature: Presigned upload**
  - Task: Upload Lambda handler returning presigned PUT (key `raw/run_id=<id>/<file>.pdf`).
  - Task: IAM role (`s3:PutObject` on `raw/*`).
  - Task: API Gateway `POST /uploads` + CORS.
  - Task: Terraform wiring; packaging update.
  - Task: Confirm `.pdf` in `ocr.supported_extensions`; e2e: upload → pipeline → Silver.
- **Feature: Status & history**
  - Task: Choose store (DynamoDB recommended).
  - Task: Emit status from existing Lambdas (Uploaded/Processing/Completed/Failed).
  - Task: `GET /invoices/{id}/status`, `GET /invoices` endpoints.

### Epic: Conversational Analytics API (SPEC-011)
- **Feature: Chat endpoint**
  - Task: Chat Lambda wrapping `BedrockSqlGenerator` + `validate_sql` + `AthenaClient`.
  - Task: New `summarize_results` Bedrock call (FR-005 NL answer).
  - Task: API Gateway `POST /chat` + CORS.
  - Task: IAM (Athena/Glue/Bedrock/S3 read gold + rw athena-results).
  - Task: Structured analytics logging (`query_id`,`user_question`,`generated_sql`,`execution_time_ms`,`athena_scan_mb`,`status`).
  - Task: Bundle hygiene (exclude pandas from chat Lambda path); latency check vs NFR-001.

### Epic: Automated Gold Consolidation (SPEC-016) — Phase 4.5
- **Feature: State machine integration**
  - Task: Add `ConsolidateGold` state after `PublishRunMetrics` invoking `consolidate_gold_lambda`.
  - Task: Pass `consolidate_gold_lambda_arn` into the `templatefile` and grant the SFN role `lambda:InvokeFunction` on it.
  - Task: Shape a single-document batch (`batch_id=<execution_id>`, `expected_documents=[{run_id, document_id}]`) for the inline path.
- **Feature: Status synchronization (FR-004)**
  - Task: Change `enrich_with_llm` to write `Consolidating` (not `Completed`) on accept; keep `Failed` path.
  - Task: Add `UpdateStatusCompleted` step (writes `Completed` post-consolidation); grant `consolidate_gold_role` (or a small status writer) the `status/` write permission.
- **Feature: Correctness guarantees**
  - Task: Verify idempotency via existing dedup markers (FR-006); no duplicate Gold rows on re-run.
  - Task: Verify failure isolation (FR-003): a consolidation failure leaves prior Gold intact, no partial write.
  - Task: Ensure new `batch_id` partitions are discoverable in Athena (partition projection or `repair-partitions`) so `gold_invoice_summary` sees fresh rows.
  - Task: E2E (AC-004): upload PDF → Processing → Consolidating → Completed → chatbot query returns the invoice.

### Epic: Static Web Portal & Chat UI (SPEC-010/013)
- **Feature: Hosting**
  - Task: Private S3 site bucket + CloudFront + OAC (HTTPS only).
  - Task: Terraform; deploy mechanism (s3 sync vs aws_s3_object).
- **Feature: Upload UI** — Task: file picker (PDF, ≤20 MB), progress bars (FR-002), call `/uploads`, PUT to S3.
- **Feature: Status & history UI** — Task: status states (FR-003); history table (FR-004).
- **Feature: Chat UI (SPEC-013)** — Task: chat input, session history (FR-002), loading indicator (FR-003), text/table/metric formatting (FR-004), call `/chat`.
- **Feature: Auth (if chosen)** — Task: Cognito Hosted UI + API authorizer.

### Epic: Hardening & Docs
- Task: CloudWatch alarms (DLQ depth, Lambda errors, Step Functions failures).
- Task: Cost review (Bedrock invocations, Athena scans, CloudFront).
- Task: Update architecture diagram (`docs/resources/architecture.dot`) + README narrative.
- Task: Update acceptance criteria for MVP2.

---

## 7. Risk Assessment

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | Terraform **state migration** corrupts/loses state | Med | High | Back up state; bootstrap stack first; verify no-op plan post-migrate; quiet window. |
| R2 | Legacy `infra/` root stack confusion (stale modules/vars) | Med | Med | Treat as legacy; do all work in `infra/envs/dev`; consider archiving/removing in a separate PR. |
| R3 | SPEC-012 `subtotal/tax` data not captured upstream | High | Med | Start as view with nulls; only add extraction if business-required. |
| R4 | Chat API misses NFR-001 (<10 s) cold-start + Athena | Med | Med | Provisioned concurrency or warmers; partition pruning; cap rows/tokens; measure. |
| R5 | Public portal without auth = open Bedrock/Athena spend | Med | High | Decide auth early (Cognito/WAF/API key); workgroup scan caps; budget alarm exists. |
| R6 | PDF not in supported extensions → uploads silently rejected | Med | Med | Verify/patch `pipeline.yaml`; e2e PDF test in Phase 3. |
| R7 | Lambda bundle bloat (pandas in chat path) → cold starts/size | Med | Low–Med | Keep query path pandas-free; consider separate bundle/layer. |
| R8 | Presigned URL/CORS misconfig blocks uploads | Med | Med | Constrain TTL/content-type/key; test CORS end-to-end. |
| R9 | SPEC-008 deferral vs SPEC-011 API expectation | Low | Low | Documented sanctioned evolution; reuse validated analytics code. |
| R10 | Gold consolidation is manual → uploads don't appear in analytics | Med | Med | **Resolved by Phase 4.5 / SPEC-016**: wire `consolidate_gold` into the state machine after `PublishRunMetrics`; add `Consolidating` status; `Completed` written only post-consolidation. |
| R11 | Per-invoice inline consolidation adds latency + many small Gold batches | Med | Low–Med | Single-document `batch_id=<execution_id>`; rely on dedup markers (FR-006); cross-batch compaction out of scope; monitor Budget + cold starts (fat consolidate bundle). |
| R12 | SFN definition + status-semantics change is deployed-runtime behavior | Med | Med | Phase 4.5 is **not** purely additive — requires explicit approval before `apply`; verify state machine diff and a single-document e2e before rollout. |

---

## 8. Recommended Execution Order

### 8.1 Recommended sequence
1. **Phase 0 — Foundation** (decisions, PDF/packaging verification).
2. **Phase 1 — Remote Backend** (do before adding many resources; one-time migration).
3. **Phase 2 — Semantic Dataset** (clean schema before grounding chat).
4. **Phase 3 — Upload API** (reuses existing trigger; low backend churn).
5. **Phase 4 — Chat API** (wraps existing analytics + NL summary).
6. **Phase 4.5 — Automated Gold Consolidation** (SPEC-016; wire `consolidate_gold` into the state machine so `Completed` ⇒ queryable).
7. **Phase 5 — Frontend + Chat UI + Hardening** (consumes the two APIs).

### 8.2 Critical path
`Phase 0 → Phase 1 → (Phase 2 ∥ Phase 3) → Phase 4 → Phase 4.5 → Phase 5`
Phases 2 and 3 can run in parallel after the backend is stable. Phase 4.5 closes the
analytics-availability loop (SPEC-016) and must precede Phase 5 so the portal's
`Completed` status is truthful. Phase 5 cannot start until both APIs (3 & 4) exist.
MVP2 acceptance gate = Phase 5 complete.

### 8.3 Potential blockers
- Undecided **auth model** (blocks Phase 5 + influences Phase 3/4 IAM).
- Undecided **status store** (blocks Phase 3 status endpoints).
- **State migration window** (blocks Phase 1 if no safe window).
- **PDF support** unverified (blocks Phase 3 e2e).
- Out-of-band **state bucket/lock** provisioning if bootstrap stack isn't adopted.

### 8.4 Rollback considerations
- **Backend:** keep the pre-migration local `terraform.tfstate` backup; reverting = restore backup + remove `backend.tf` + `init -migrate-state` back to local.
- **New resources (APIs, CloudFront, DynamoDB):** additive; `terraform destroy` of the new files / `-target` removal leaves the validated MVP intact.
- **Semantic dataset as a view:** drop the view; no data movement, no pipeline impact.
- **Frontend:** static assets + CloudFront are independently destroyable; the backend pipeline is unaffected.
- **Principle:** every phase is additive over the validated MVP; the existing `raw → SQS → Step Functions → silver/gold` path is never modified destructively (presigned upload lands in the same `raw/` prefix the pipeline already watches).

---

## Appendix A — Explicit Assumptions
1. The **legacy `infra/` root stack** is not the deployment target; all new work targets `infra/envs/dev`.
2. State bucket/lock are **not** currently provisioned by repo IaC; a bootstrap stack is the recommended way to close that gap.
3. `subtotal_amount`/`tax_amount` (SPEC-012) are **not** captured upstream today.
4. Auth, frontend framework, status store, and frontend deploy mechanism are **undecided** and require product/team input (§4.9).
5. Bedrock model availability/region (`us.anthropic.claude-sonnet-4-5-...` in `variables.tf`) is provisioned in the target account/region.

## Appendix B — Evidence Index (primary files inspected)
- Architecture/flow: `README.md`, `infra/envs/dev/state_machine.asl.json`, `src/aws/lambda_handlers/control_plane.py`
- Infra (active): `infra/envs/dev/{main,analytics,outputs,providers,variables,budget}.tf`, `backend.tf.example`, `infra/modules/*`
- Legacy infra: `infra/main.tf`
- Analytics: `src/analytics/{bedrock_sql,sql_validator,athena_client,cli,schema_registry}.py`, `specs/prompts/bedrock_analytics_sql_prompt.md`
- Data model: `src/pipeline/gold_model.py`, `specs/contracts/gold_documents.schema.yaml`
- Specs: `specs/product/{SPEC-010,SPEC-011,SPEC-012,SPEC-013,MVP2-definition}.md`, `specs/technical/SPEC-014-remote-backend.md`, `specs/{SPEC-007,SPEC-008}*.md`
- Repo hygiene: `.gitignore`, `AGENTS.md`, `CLAUDE.md`
- Negative checks (no matches): `aws_api_gateway*`, `aws_apigatewayv2*`, `cloudfront`, `cognito`, `presigned`, and `{frontend,web,ui,app}/` directories.
