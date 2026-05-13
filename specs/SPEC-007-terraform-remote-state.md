# SPEC-007 — Terraform Remote State Backend

## Status

Proposed

---

## Context

The project currently uses local Terraform state files.

As the infrastructure evolved to include:

* Lambda,
* SQS,
* DLQs,
* Step Functions,
* IAM policies,
* CloudWatch,
* Textract integrations,

the risk of state drift and inconsistent deployments increased significantly.

---

## Problem Statement

Local Terraform state creates risks related to:

* accidental deletion,
* inconsistent state tracking,
* unreproducible deployments,
* partial applies,
* IAM drift,
* poor collaboration readiness.

---

## Decision

Adopt a centralized Terraform remote backend using Amazon S3.

---

## Backend Requirements

### S3 Bucket

The backend bucket must:

* enable versioning,
* enable server-side encryption,
* restrict public access,
* use deterministic naming.

Example:

<pre class="overflow-visible! px-0!" data-start="6978" data-end="7018"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="relative"><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>invoice-pipeline-dev-tfstate</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

## Backend Configuration Example

<pre class="overflow-visible! px-0!" data-start="7059" data-end="7215"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class="relative"><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>terraform {</span><br/><span>  backend "s3" {</span><br/><span>    bucket = "invoice-pipeline-dev-tfstate"</span><br/><span>    key    = "envs/dev/terraform.tfstate"</span><br/><span>    region = "us-east-1"</span><br/><span>  }</span><br/><span>}</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

## Security Requirements

The backend bucket must:

* block public access,
* enforce encryption,
* restrict access to approved IAM identities.

---

## Operational Requirements

Terraform operations must use:

<pre class="overflow-visible! px-0!" data-start="7431" data-end="7494"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class="relative"><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span class="ͼ11">terraform</span><span></span><span class="ͼ11">init</span><br/><span class="ͼ11">terraform</span><span></span><span class="ͼ11">plan</span><br/><span class="ͼ11">terraform</span><span></span><span class="ͼ11">apply</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

against the remote backend only.

Local `.tfstate` files must be gitignored.

---

## Non-Goals

This spec does not include:

* multi-account state management,
* Terraform Cloud,
* OpenTofu migration,
* enterprise locking strategies,
* cross-region replication.
