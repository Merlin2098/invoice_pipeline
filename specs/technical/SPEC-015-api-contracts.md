# SPEC-015 — Web API Contracts

## Status

Draft — Phase 0

---

## Context

SPEC-010 (Upload Portal), SPEC-011 (Conversational Analytics), and SPEC-013
(Chat UI) require HTTP API endpoints. This spec defines the contract for those
endpoints so that the frontend and backend can be developed in parallel with a
shared interface.

All endpoints are served through **Amazon API Gateway HTTP API (v2)** backed by
AWS Lambda. The base URL is environment-specific and emitted as a Terraform
output.

---

## Base URL

```
https://<api-id>.execute-api.<region>.amazonaws.com
```

Emitted by Terraform as `web_api_base_url`.

---

## Authentication

> **OPEN DECISION** — Auth model is not yet finalized (see `docs/implementation_plan.md` §4.9).
>
> Current assumption for Phase 3 development: **no auth** (API keys or Cognito
> to be layered in Phase 5 hardening). Do NOT expose the API publicly without
> resolving this before Phase 5 deploy.

---

## CORS

All endpoints must respond to preflight `OPTIONS` requests with:

```
Access-Control-Allow-Origin: <cloudfront-domain>
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type
```

The allowed origin is the CloudFront distribution URL, not `*`.

---

## Endpoints

### POST /uploads

Generate presigned S3 PUT URLs for one or more invoice files.

**Request**

```json
{
  "files": [
    { "name": "invoice_001.pdf", "content_type": "application/pdf", "size_bytes": 1048576 },
    { "name": "invoice_002.pdf", "content_type": "application/pdf", "size_bytes": 2097152 }
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `files` | array | yes | 1–10 files per call |
| `files[].name` | string | yes | Original filename, used in key construction |
| `files[].content_type` | string | yes | Must be `application/pdf` |
| `files[].size_bytes` | integer | yes | Must be ≤ 20971520 (20 MB) |

**Response 200**

```json
{
  "run_id": "invoice-pipeline-aws-20260530T120000Z",
  "uploads": [
    {
      "name": "invoice_001.pdf",
      "upload_url": "https://s3.amazonaws.com/...",
      "key": "raw/run_id=invoice-pipeline-aws-20260530T120000Z/invoice_001.pdf",
      "expires_in_seconds": 300
    }
  ]
}
```

| Field | Notes |
|---|---|
| `run_id` | Shared run ID for all files in this batch |
| `upload_url` | Presigned S3 PUT URL; browser PUTs directly to S3 |
| `key` | S3 key; can be used to derive `document_id` (stem) and poll status |
| `expires_in_seconds` | Presigned URL TTL (300 s default) |

**Response 400**

```json
{ "error": "invalid_request", "message": "file size exceeds 20 MB limit" }
```

**Response 400 — unsupported file type**

```json
{ "error": "unsupported_file_type", "message": "only application/pdf is accepted" }
```

**Notes**

- The upload Lambda generates a single `run_id` for all files in the batch.
- After the browser PUTs each file to the presigned URL, the S3 event
  notification fires automatically, triggering the existing pipeline
  (`SQS → raw-dispatch Lambda → Step Functions`). No additional trigger is needed.
- The Lambda role needs only `s3:PutObject` on `raw/*` plus
  `s3:GeneratePresignedUrl` (implied by the role's own PutObject permission).

---

### GET /invoices

List processed invoices with summary status.

**Query parameters**

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `status` | string | (all) | Filter: `Uploaded`, `Processing`, `Completed`, `Failed` |
| `limit` | integer | 20 | Max 100 |
| `next_token` | string | — | Pagination cursor from previous response |

**Response 200**

```json
{
  "invoices": [
    {
      "invoice_id": "0000089370",
      "run_id": "invoice-pipeline-aws-20260530T120000Z",
      "supplier_name": "Acme Corp",
      "invoice_date": "2026-05-15",
      "total_amount": 12450.00,
      "currency": "USD",
      "status": "Completed",
      "processing_date": "2026-05-30T12:05:22Z"
    }
  ],
  "next_token": null
}
```

**Notes**

- Backed by S3 objects at `status/*.json` in the data lake bucket. Each Lambda
  that changes document state overwrites `status/{invoice_id}.json`.
- Completed records can optionally be enriched from `gold_documents` via Athena
  for supplier name, amount, etc.
- `invoice_id` = `document_id` (filename stem).
- Terminal states (`Completed`, `Failed`) come from Gold/Silver; transient
  states (`Uploaded`, `Processing`) require the DynamoDB status store.

---

### GET /invoices/{invoice_id}/status

Real-time status for a single invoice.

**Path parameters**

| Parameter | Type | Notes |
|---|---|---|
| `invoice_id` | string | `document_id` (filename stem) |

**Response 200**

```json
{
  "invoice_id": "0000089370",
  "run_id": "invoice-pipeline-aws-20260530T120000Z",
  "status": "Processing",
  "updated_at": "2026-05-30T12:02:10Z"
}
```

**Status values**

| Value | Meaning |
|---|---|
| `Uploaded` | File reached S3 raw prefix; pipeline not yet triggered |
| `Processing` | Step Functions execution in progress |
| `Completed` | Silver valid or Gold record written |
| `Failed` | Step Functions failed or document landed in `errors/` |

**Response 404**

```json
{ "error": "not_found", "message": "invoice not found" }
```

---

### POST /chat

Submit a natural-language question about invoice data.

**Request**

```json
{
  "question": "How much did we spend with Microsoft in May 2026?"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `question` | string | yes | Free-text; max 500 characters |

**Response 200**

```json
{
  "answer": "You spent USD 12,450 with Microsoft across 3 invoices in May 2026.",
  "generated_sql": "SELECT SUM(total_amount) AS total, COUNT(document_id) AS invoices FROM gold_documents WHERE lower(vendor_name) = 'microsoft' AND document_date BETWEEN '2026-05-01' AND '2026-05-31' LIMIT 100",
  "rows": [
    { "total": "12450.0", "invoices": "3" }
  ],
  "query_id": "abc123",
  "execution_time_ms": 2840,
  "athena_scan_mb": 0.12
}
```

| Field | Notes |
|---|---|
| `answer` | Natural-language summary generated by Bedrock from Athena rows |
| `generated_sql` | Validated SQL that was executed (informational) |
| `rows` | Raw Athena result rows (key-value strings) |
| `query_id` | Athena execution ID for audit/tracing |
| `execution_time_ms` | Wall-clock time including Bedrock + Athena + summarization |
| `athena_scan_mb` | Data scanned; visible to user for transparency |

**Response 400 — SQL validation failed**

```json
{
  "error": "sql_validation_error",
  "message": "Only SELECT queries are allowed."
}
```

**Response 422 — question too long**

```json
{ "error": "invalid_request", "message": "question must be 500 characters or less" }
```

**Response 504 — timeout**

```json
{ "error": "timeout", "message": "query did not complete within the time limit" }
```

**Notes**

- The Lambda reuses `src/analytics.BedrockSqlGenerator`, `validate_sql`, and
  `AthenaClient` exactly as the existing CLI does.
- A **second Bedrock call** summarizes Athena rows into `answer` (SPEC-011
  FR-005). This is the only new code required beyond wrapping the existing stack.
- NFR-001: target < 10 s total. Bedrock `converse` + Athena polling + Bedrock
  summarization must fit within the Lambda timeout (recommend 30 s for this
  handler, measured against NFR-001 in Phase 4 load test).
- `pandas` is **not** required in the chat Lambda path. The bundle for this
  handler must exclude it (separate Lambda or Lambda layer strategy — see
  open decision below).

---

## Error envelope

All error responses use a consistent shape:

```json
{
  "error": "<machine_code>",
  "message": "<human_readable>"
}
```

HTTP status codes follow REST conventions: 400 bad input, 404 not found,
422 unprocessable, 504 upstream timeout.

---

## Decisions (all closed — Phase 0 complete)

| # | Decision | Resolution |
|---|---|---|
| D1 | Auth model | ✅ No auth + WAF rate-limit |
| D2 | Status backing store | ✅ S3 objects in `status/` prefix of data lake bucket |
| D3 | Bundle strategy for chat Lambda | ✅ Separate `chat_bundle.zip` (~15 MB, pandas-free) |
| D4 | `subtotal_amount` / `tax_amount` in SPEC-012 | ✅ NULL in Athena view (no pipeline change) |
| D5 | Frontend framework | ✅ React + Vite |

Full decision rationale in [`docs/adr/ADR-001-phase0-decisions.md`](../../docs/adr/ADR-001-phase0-decisions.md).
