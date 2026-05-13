# SPEC-005 — Structured Logging & Log Retention Strategy

## Status

Proposed

---

## Context

The invoice pipeline now contains:

* SQS,
* Lambda,
* Step Functions,
* Textract,
* Bedrock,
* DLQs,
* idempotency guards.

This architecture is event-driven and distributed. Debugging failures without structured observability becomes increasingly difficult.

Current logging behavior is inconsistent and log groups may remain orphaned after Terraform destroy operations.

---

## Problem Statement

The project currently lacks:

* standardized JSON logs,
* retention policies,
* centralized operational metadata,
* correlation identifiers,
* execution traceability.

This limits:

* debugging speed,
* operational diagnosis,
* replay analysis,
* failure correlation.

---

## Decision

Adopt structured JSON logging across all Lambda handlers and explicitly manage all CloudWatch log groups using Terraform.

All log groups must define:

<pre class="overflow-visible! px-0!" data-start="3462" data-end="3494"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class="relative"><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>retention_in_days = 7</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

for development environments.

---

## Logging Standard

All runtime logs must include:

<pre class="overflow-visible! px-0!" data-start="3585" data-end="3793"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class="relative"><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>{</span><br/><span>  "run_id": </span><span class="ͼz">"string"</span><span>,</span><br/><span>  "document_id": </span><span class="ͼz">"string"</span><span>,</span><br/><span>  "execution_id": </span><span class="ͼz">"string"</span><span>,</span><br/><span>  "stage": </span><span class="ͼz">"string"</span><span>,</span><br/><span>  "status": </span><span class="ͼz">"string"</span><span>,</span><br/><span>  "duration_ms": </span><span class="ͼy">0</span><span>,</span><br/><span>  "service": </span><span class="ͼz">"string"</span><span>,</span><br/><span>  "error_code": </span><span class="ͼz">"string|null"</span><br/><span>}</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

## Correlation Requirements

The following identifiers must propagate across the entire pipeline:

* `run_id`
* `execution_id`
* `document_id`
* `source_s3_key`

---

## Terraform Requirements

All Lambda log groups must be explicitly declared.

Example:

<pre class="overflow-visible! px-0!" data-start="4056" data-end="4223"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class="relative"><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>resource "aws_cloudwatch_log_group" "process_document" {</span><br/><span>  name              = "/aws/lambda/invoice-pipeline-dev-process-document"</span><br/><span>  retention_in_days = 7</span><br/><span>}</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

## Expected Benefits

* Faster debugging
* Deterministic failure tracing
* Reduced orphaned resources
* Lower CloudWatch costs
* Better operational observability
