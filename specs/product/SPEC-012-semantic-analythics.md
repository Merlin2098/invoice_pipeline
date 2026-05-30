# SPEC-012 - Semantic Analytics Dataset

## Overview

Create a conversational-friendly Gold dataset optimized for LLM-generated SQL.

This dataset will act as the primary source for analytics queries.

---

## Business Goal

Improve SQL generation accuracy by exposing business-friendly column names.

---

## Dataset

### Table Name

<pre class="overflow-visible! px-0!" data-start="4815" data-end="4847"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="relative"><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>gold_invoice_summary</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### Columns

| Column          | Type      |
| --------------- | --------- |
| invoice_id      | STRING    |
| invoice_date    | DATE      |
| supplier_name   | STRING    |
| currency        | STRING    |
| subtotal_amount | DECIMAL   |
| tax_amount      | DECIMAL   |
| total_amount    | DECIMAL   |
| document_type   | STRING    |
| processing_date | TIMESTAMP |

---

## Functional Requirements

### FR-001

The Gold dataset shall be generated from the existing Silver layer.

---

### FR-002

Column names shall be business-readable.

Example:

Preferred:

<pre class="overflow-visible! px-0!" data-start="5342" data-end="5393"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="relative"><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>supplier_name</span><br/><span>total_amount</span><br/><span>invoice_date</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

Avoid:

<pre class="overflow-visible! px-0!" data-start="5403" data-end="5437"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="relative"><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>SUPP_NM</span><br/><span>TOT_AMT</span><br/><span>INV_DT</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### FR-003

The dataset shall be registered in AWS Glue Catalog.

---

### FR-004

The dataset shall be queryable from Athena.

---

## AWS Services

* AWS Glue
* Amazon Athena
* Amazon S3
