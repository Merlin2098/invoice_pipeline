# SPEC-004 — Runtime IAM Validation & Preflight Checks

## Status

Proposed

---

## Context

Recent smoke tests failed with deterministic `403 Forbidden` errors during the `HeadObject` idempotency check executed by the `process_document` Lambda runtime role. The AWS CLI user possessed the required permissions, but the Lambda execution role did not.

This incident exposed a critical operational gap:

* Infrastructure deployment succeeded
* Terraform state appeared healthy
* Manual CLI validation passed
* Runtime identity validation was never executed

As a result, 40 messages were routed into the DLQ despite the infrastructure appearing healthy from an operator perspective.

---

## Problem Statement

The project currently lacks automated runtime validation for:

* Lambda execution roles
* Attached IAM policies
* Effective permissions at execution time
* Cross-service access validation
* Event source mapping health

This creates a high risk of:

* deterministic failures,
* false-positive infrastructure deployments,
* wasted Bedrock/Textract runs,
* DLQ pollution,
* difficult debugging cycles.

---

## Decision

Introduce a mandatory preflight validation layer before smoke tests and deployments.

Validation will be implemented using:

* PowerShell operational scripts,
* optional GitHub Actions workflows,
* runtime AWS CLI validations executed against actual Lambda identities.

---

## Scope

### Runtime validations

Validate:

* S3 `GetObject`
* S3 `PutObject`
* S3 `HeadObject`
* Textract `AnalyzeExpense`
* Bedrock `InvokeModel`
* Step Functions `StartExecution`
* SQS consumption permissions

---

### Infrastructure validations

Validate:

* IAM role existence
* Attached inline policies
* Required policy statements
* Event source mappings
* DLQ configuration
* CloudWatch log group existence

---

## Expected Scripts

<pre class="overflow-visible! px-0!" data-start="1919" data-end="2039"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="relative"><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>scripts/</span><br/><span>  validate-iam.ps1</span><br/><span>  validate-runtime-access.ps1</span><br/><span>  validate-event-mappings.ps1</span><br/><span>  smoke-precheck.ps1</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

## Expected Behavior

Before executing a smoke test:

<pre class="overflow-visible! px-0!" data-start="2100" data-end="2146"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class="relative"><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>.\</span><span class="ͼ11">scripts</span><span>\</span><span class="ͼ11">smoke-precheck</span><span>.</span><span class="ͼ11">ps1</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

The script must:

1. Validate Terraform outputs
2. Validate IAM role policies
3. Invoke runtime permission checks
4. Validate SQS mappings
5. Validate CloudWatch log groups
6. Abort execution if any validation fails

---

## Non-Goals

This spec does not include:

* production CI/CD pipelines,
* SCP validation,
* cross-account role validation,
* organization-wide governance.
