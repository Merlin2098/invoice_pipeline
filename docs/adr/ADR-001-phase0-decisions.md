# ADR-001 — Phase 0 Foundation Decisions

**Date:** 2026-05-30
**Status:** Partial — verified items closed; open items require product/team input

---

## Purpose

This record documents the Phase 0 verification findings and captures the
decisions that must be made before Phase 3 (Upload API) and Phase 5 (Frontend)
implementation can begin. See `docs/implementation_plan.md` for the full
roadmap.

---

## Verified (no action required)

### V1 — PDF support is already enabled

**Finding:** `src/config/pipeline.yaml` includes `.pdf` in
`ocr.supported_extensions`. The `validate_input` Lambda gate will accept PDF
uploads. Textract `AnalyzeExpense` supports PDF natively.

**Action:** None. End-to-end PDF smoke test is still recommended in Phase 3
(upload → pipeline → Silver) to catch any runtime edge cases.

---

### V2 — `src/analytics` is included in the Lambda bundle

**Finding:** `scripts/package.py` sets `INCLUDE_DIRS = [REPO_ROOT / "src",
REPO_ROOT / "specs"]`. The entire `src/` tree — including `src/analytics/` —
is bundled into `artifacts/lambda/control_plane_bundle.zip`. The chat Lambda
(Phase 4) can import `BedrockSqlGenerator`, `validate_sql`, and `AthenaClient`
from the same bundle without changes to the packaging script.

**Action:** None for Phase 4 functionality. See V3 for bundle size concern.

---

### V3 — `pandas` + `pyarrow` are in the Lambda bundle (size risk)

**Finding:** `requirements.lambda.txt` lists `pandas` and `pyarrow`. Together
these add approximately 100–120 MB to the zip. This is within the Lambda
deployment package limit (250 MB unzipped) but increases cold-start latency.
The chat Lambda path (`BedrockSqlGenerator` → `AthenaClient`) does **not**
import or require `pandas` at runtime — it is pulled in only by
`src/pipeline/gold_model.py` (used by `consolidate_gold`).

**Risk:** If a separate chat Lambda bundle is not used, cold starts may push
the total execution time over NFR-001 (< 10 s for `POST /chat`).

**Decision needed:** D3 (bundle strategy) — see Open Decisions below.

---

### V4 — `subtotal_amount` / `tax_amount` are not captured upstream

**Finding:** `specs/contracts/silver_document.schema.yaml` has no
`subtotal_amount` or `tax_amount` fields. `src/pipeline/gold_model.py`
`DOCUMENT_COLUMNS` does not include them. These values are not extracted by
Textract or mapped through Bedrock normalization in the current pipeline.

**Impact on SPEC-012:** `gold_invoice_summary` cannot include real subtotal or
tax values without upstream extraction work (new fields in Silver contract +
Textract/Bedrock candidate mapping + Gold model changes).

**Decision needed:** D4 — see Open Decisions below.

---

### V5 — Gold consolidation is not automated (batch close gap)

**Finding:** The Step Functions state machine ends at `PublishRunMetrics`. The
`consolidate_gold` Lambda is called out-of-band (manual / smoke finalizer).
There is no automatic batch close after uploads.

**Impact on MVP2:** After a user uploads invoices through the portal, the data
will not appear in `gold_documents` (and therefore not in `POST /chat` answers)
until `consolidate_gold` is invoked manually. This breaks the MVP2 user journey.

**Recommendation:** Add an automatic batch close trigger as part of Phase 3 or
Phase 4. Options:
- (a) EventBridge scheduled rule or SFN Wait-for-Callback pattern in the state machine.
- (b) Upload Lambda triggers `consolidate_gold` directly after presigning (simple but couples them).
- (c) Explicit "Finalize Batch" button in the UI that calls a `/batches/{run_id}/finalize` endpoint.

This is **not currently in any spec**. Flag it as a scope addition before
Phase 3 implementation starts.

---

## Open Decisions

The following decisions are **required** before implementation of the indicated
phases. Each is also listed in `specs/technical/SPEC-015-api-contracts.md`.

---

### D1 — Authentication model

**Status: ✅ DECIDED — No auth + WAF rate-limit**

No authentication layer on the API. Cost and abuse protected by:
- CloudFront + WAF rate-limiting on the distribution.
- Athena workgroup scan cutoff (100 MB/query).
- AWS Budget alarm ($20/mo).
- Presigned URL TTL (300 s) limits upload window.

IAM: API Gateway endpoints are public. No Cognito resources required.

---

### D2 — Status backing store

**Status: ✅ DECIDED — S3 object store**

Each state transition writes a small JSON object to a `status/` prefix in the
data lake bucket:

```
s3://<data-lake-bucket>/status/{invoice_id}.json
→ { "invoice_id": "...", "run_id": "...", "status": "Processing", "updated_at": "..." }
```

**Implementation:**
- Upload Lambda writes `status: Uploaded` immediately after presigning.
- `raw-dispatch` / `validate_input` / `enrich_with_llm` Lambdas overwrite the object at each state transition.
- `GET /invoices/{id}/status` endpoint does `s3:GetObject` on that key.
- `GET /invoices` lists `status/*.json` objects (paginated `ListObjectsV2`).

**IAM changes required:** add `s3:PutObject` on `status/*` to the relevant Lambda roles; `s3:GetObject` + `s3:ListBucket` on `status/*` to the status API Lambda role.

**No new AWS resources required** — reuses the existing data lake bucket with a new prefix marker.

---

### D3 — Lambda bundle strategy for chat Lambda

**Status: ✅ DECIDED — Separate `chat_bundle.zip`**

A new slim bundle is built for the chat Lambda, containing only:
- `src/analytics/` (BedrockSqlGenerator, AthenaClient, sql_validator, schema_registry)
- `src/aws/` (bedrock_client, logging_utils)
- `specs/prompts/` (bedrock_analytics_sql_prompt.md)
- Runtime deps: `boto3` (provided by Lambda runtime), `python-dateutil`, `PyYAML`.
- Explicitly excludes: `pandas`, `pyarrow`, `src/pipeline/`, `src/jobs/`.

Estimated bundle size: ~15 MB vs ~120 MB for the shared bundle.

**Implementation:** add a `--target chat` flag (or a second script) to
`scripts/package.py` that uses a restricted `INCLUDE_DIRS` list and a separate
`requirements.chat.txt`. Output: `artifacts/lambda/chat_bundle.zip`.

`make` target: `make package-chat`.

---

### D4 — `subtotal_amount` / `tax_amount` in SPEC-012

**Status: ✅ DECIDED — Null initially (Athena view)**

`gold_invoice_summary` is implemented as an **Athena view** over `gold_documents`.
Columns `subtotal_amount` and `tax_amount` are present in the view schema but
return `NULL CAST AS DECIMAL` until upstream extraction is extended.

View column mapping:

| SPEC-012 column | Source column | Notes |
|---|---|---|
| `invoice_id` | `document_id` | rename |
| `invoice_date` | `document_date` | rename |
| `supplier_name` | `vendor_name` | rename |
| `currency` | `currency` | direct |
| `total_amount` | `total_amount` | direct |
| `subtotal_amount` | — | `NULL` — future |
| `tax_amount` | — | `NULL` — future |
| `document_type` | `document_type` | direct |
| `processing_date` | `created_at` | rename |

No pipeline changes required. View is DDL-only in `analytics.tf`.

---

### D5 — Frontend framework

**Status: ✅ DECIDED — React + Vite**

Single-page application built with React + Vite.

- Source: `frontend/` (new top-level directory, separate from `src/` Python).
- Build output: `frontend/dist/` — static assets deployed to the S3 site bucket.
- Deploy mechanism: `aws s3 sync frontend/dist/ s3://<site-bucket>/` post-apply (documented in runbook; not managed as individual `aws_s3_object` resources in Terraform state).
- `make` target: `make build-frontend` → `vite build`.

Key components needed:
- Upload page (file picker, progress bars, status polling).
- Invoice history table.
- Chat interface (message history, loading indicator, table/metric formatting).

---

## Note — Terraform backend locking (Phase 1)

The `backend.tf.example` references a DynamoDB lock table. This will be replaced
with **S3 native state locking** (AWS feature, 2024), which eliminates the
DynamoDB dependency entirely. The bootstrap stack (`infra/bootstrap/`) will
provision only the state S3 bucket (versioning + SSE + public-access block).

Updated `backend.tf` shape:

```hcl
terraform {
  backend "s3" {
    bucket       = "invoice-pipeline-dev-tfstate-<account_id>"
    key          = "invoice-pipeline/dev/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true   # S3 native locking — no DynamoDB needed
    encrypt      = true
  }
}
```

This requires Terraform >= 1.10. Verify the installed version before Phase 1.

---

## Summary checklist

| Item | Status | Owner |
|---|---|---|
| V1 — PDF support confirmed | ✅ Closed | — |
| V2 — analytics bundle confirmed | ✅ Closed | — |
| V3 — bundle size risk identified | ⚠️ Tracked → D3 | Team |
| V4 — subtotal/tax gap confirmed | ⚠️ Tracked → D4 | Team |
| V5 — batch close gap identified | ⚠️ New scope item | Team |
| D1 — Auth model | ✅ Decided — No auth + WAF rate-limit | — |
| D2 — Status store | ✅ Decided — S3 objects in `status/` prefix | — |
| D3 — Bundle strategy | ✅ Decided — Separate `chat_bundle.zip` | — |
| D4 — subtotal/tax handling | ✅ Decided — Null (Athena view) | — |
| D5 — Frontend framework | ✅ Decided — React + Vite | — |
| Terraform locking | ✅ Decided — S3 native locking (no DynamoDB) | — |

**All Phase 0 decisions are closed. Phase 0 is COMPLETE.**
All phases (1–5) can proceed according to the roadmap in `docs/implementation_plan.md`.
