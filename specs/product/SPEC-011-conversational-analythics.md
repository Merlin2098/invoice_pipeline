# SPEC-011 - Conversational Invoice Analytics

## Overview

Implement a conversational analytics layer that allows users to query invoice data using natural language.

The feature will transform user questions into Athena SQL queries using Amazon Bedrock.

---

## Business Goal

Allow business users to obtain insights without SQL knowledge.

Examples:

> How much did we spend with Microsoft?

> What were the top 10 suppliers this month?

> How many invoices were processed last week?

---

## Architecture

<pre class="overflow-visible! px-0!" data-start="2948" data-end="3250"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="relative"><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>User Question</span><br/><span>       |</span><br/><span>       v</span><br/><br/><span>API Gateway</span><br/><br/><span>       |</span><br/><span>       v</span><br/><br/><span>Lambda</span><br/><br/><span>       |</span><br/><span>       v</span><br/><br/><span>Amazon Bedrock</span><br/><br/><span>       |</span><br/><span>       v</span><br/><br/><span>SQL Generation</span><br/><br/><span>       |</span><br/><span>       v</span><br/><br/><span>Amazon Athena</span><br/><br/><span>       |</span><br/><span>       v</span><br/><br/><span>Query Results</span><br/><br/><span>       |</span><br/><span>       v</span><br/><br/><span>Amazon Bedrock</span><br/><br/><span>       |</span><br/><span>       v</span><br/><br/><span>Natural Language Response</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

## Functional Requirements

### FR-001 - Natural Language Queries

The system shall accept free-text business questions.

Examples:

<pre class="overflow-visible! px-0!" data-start="3390" data-end="3508"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="relative"><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>How much did we spend in May?</span><br/><br/><span>Which supplier generated the highest cost?</span><br/><br/><span>Show invoices above USD 10,000.</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### FR-002 - SQL Generation

The system shall use Amazon Bedrock to generate Athena-compatible SQL.

---

### FR-003 - SQL Validation

The system shall validate generated SQL before execution.

Allowed:

<pre class="overflow-visible! px-0!" data-start="3719" data-end="3736"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class="relative"><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span class="ͼv">SELECT</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

Forbidden:

<pre class="overflow-visible! px-0!" data-start="3750" data-end="3801"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute inset-x-4 top-12 bottom-4"><div class="pointer-events-none sticky z-40 shrink-0 z-1!"><div class="sticky bg-token-border-light"></div></div></div><div class="relative"><div class=""><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span class="ͼv">INSERT</span><br/><span class="ͼv">UPDATE</span><br/><span class="ͼv">DELETE</span><br/><span class="ͼv">DROP</span><br/><span class="ͼv">ALTER</span><br/><span>TRUNCATE</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### FR-004 - Query Execution

The system shall execute validated SQL queries against Athena.

---

### FR-005 - Natural Language Response

The system shall convert query results into business-friendly responses.

Example:

<pre class="overflow-visible! px-0!" data-start="4031" data-end="4116"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="relative"><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>The total spend with Microsoft in 2026 was USD 12,450 across 27 invoices.</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

## Non-Functional Requirements

### NFR-001

Average response time shall be below 10 seconds.

---

### NFR-002

Only curated Gold datasets shall be exposed to Bedrock.

---

### NFR-003

The solution shall prevent execution of non-read-only SQL statements.

---

## AWS Services

* Amazon Bedrock
* AWS Lambda
* Amazon Athena
* AWS Glue Data Catalog
