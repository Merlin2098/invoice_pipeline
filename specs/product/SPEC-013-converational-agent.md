## Overview

Implement a chat interface inside the web application to interact with invoice analytics.

---

## Business Goal

Provide a ChatGPT-like experience for invoice analysis.

---

## Functional Requirements

### FR-001 - Chat Interface

The system shall provide a conversational UI.

Example:

<pre class="overflow-visible! px-0!" data-start="5984" data-end="6240"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="relative"><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>┌────────────────────────────────┐</span><br/><span>│ Ask anything about invoices    │</span><br/><span>├────────────────────────────────┤</span><br/><span>│                                │</span><br/><span>│ How much did we spend in May?  │</span><br/><span>│                                │</span><br/><span>└────────────────────────────────┘</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

### FR-002 - Conversation History

The system shall display the current session conversation history.

---

### FR-003 - Loading Indicator

The system shall display a loading indicator while queries are processed.

---

### FR-004 - Response Formatting

The system shall support:

* Text responses
* Tables
* Summary metrics

Example:

<pre class="overflow-visible! px-0!" data-start="6583" data-end="6696"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="relative"><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼs ͼ16"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>Top Suppliers</span><br/><br/><span>1. Microsoft      USD 12,450</span><br/><span>2. IBM            USD 10,320</span><br/><span>3. Oracle         USD  8,900</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

## AWS Services

* Amazon S3
* Amazon CloudFront
* Amazon API Gateway
* AWS Lambda
* Amazon Bedrock
