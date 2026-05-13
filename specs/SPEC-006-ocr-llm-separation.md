# SPEC-006 — OCR and LLM Processing Separation

## Status

Proposed

---

## Context

The current `process_document` Lambda performs:

* idempotency validation,
* Textract OCR extraction,
* optional Bedrock enrichment,
* S3 persistence.

This creates a tightly coupled processing unit with mixed responsibilities.

---

## Problem Statement

Combining OCR and LLM enrichment inside the same Lambda introduces:

* higher execution times,
* larger deployment packages,
* difficult debugging,
* increased retry blast radius,
* duplicated OCR costs when Bedrock fails.

The architecture currently lacks separation between:

* deterministic extraction,
* probabilistic AI enrichment.

---

## Decision

Split the processing layer into independent stages:

<pre class="overflow-visible! px-0!" data-start="5145" data-end="5243"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="relative"><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>ValidateInput</span><br/><span>  -> ExtractOCR</span><br/><span>  -> NormalizeOCR</span><br/><span>  -> EnrichWithLLM</span><br/><span>  -> PublishMetrics</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

## New Architecture

### OCR Stage

Responsibilities:

* Textract execution
* OCR normalization
* Bronze persistence
* OCR metadata generation

Output:

<pre class="overflow-visible! px-0!" data-start="5402" data-end="5435"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="relative"><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>bronze/textract-json/</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### LLM Enrichment Stage

Responsibilities:

* semantic enrichment,
* field normalization,
* AI-assisted extraction fallback,
* confidence scoring.

Output:

<pre class="overflow-visible! px-0!" data-start="5599" data-end="5649"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="relative"><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>silver/valid/</span><br/><span>silver/rejected/</span><br/><span>errors/</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

## Benefits

### Operational

* Reduced Lambda complexity
* Faster cold starts
* Smaller deployment artifacts
* Independent retries

### Financial

* Avoid repeated Textract charges
* Reduce unnecessary Bedrock invocations

### Architectural

* Better separation of concerns
* Easier replay strategies
* Easier debugging

---

## Non-Goals

This spec does not introduce:

* vector databases,
* RAG,
* multi-model orchestration,
* human-in-the-loop review systems.
