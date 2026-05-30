# SPEC-016 - Automated Gold Consolidation

## Overview

Implement automatic Gold layer consolidation as part of the invoice processing lifecycle, ensuring that invoices become available for analytics immediately after successful processing.

This specification closes the current gap between document processing completion and analytics availability.

---

## Business Goal

Ensure that uploaded invoices are automatically available for:

* Athena queries
* Conversational Analytics
* Bedrock Chatbot interactions
* Invoice History API

without requiring manual execution of the Gold consolidation process.

---

## Problem Statement

Current architecture processes documents through:

```text
Raw
 ↓
Bronze
 ↓
Silver
 ↓
Completed
```

However, Gold consolidation is executed independently and is not integrated into the Step Functions workflow.

As a result:

```text
Invoice Status = Completed

≠

Invoice Available in Analytics
```

This creates an inconsistent user experience where users may receive a "Completed" status while their invoice remains unavailable for querying.

---

## Current State

### Processing Workflow

```text
Upload
 ↓
S3 Raw
 ↓
SQS
 ↓
Step Functions

ValidateInput
 ↓
ExtractOCR
 ↓
EnrichWithLLM
 ↓
PublishRunMetrics
 ↓
Success
```

### Analytics Workflow

```text
Silver
 ↓
Manual Gold Consolidation
 ↓
Gold
 ↓
Glue
 ↓
Athena
 ↓
Chatbot
```

---

## Target State

```text
Upload
 ↓
S3 Raw
 ↓
SQS
 ↓
Step Functions

ValidateInput
 ↓
ExtractOCR
 ↓
EnrichWithLLM
 ↓
PublishRunMetrics
 ↓
ConsolidateGold
 ↓
UpdateAnalyticsStatus
 ↓
Success
```

---

## Functional Requirements

### FR-001 - Automatic Consolidation

The system shall automatically execute Gold consolidation after successful completion of invoice processing.

No manual execution shall be required.

---

### FR-002 - Analytics Availability

The system shall ensure that invoices marked as Completed are queryable from Athena.

The following condition must be true:

```text
Status = Completed

implies

Available in Gold Dataset
```

---

### FR-003 - Failure Isolation

Failures during Gold consolidation shall not corrupt existing Gold datasets.

Partial writes shall be prevented.

---

### FR-004 - Status Synchronization

The status API shall expose analytics readiness.

Possible states:

```text
Uploaded
Processing
Consolidating
Completed
Failed
```

---

### FR-005 - Gold Manifest Update

The consolidation process shall generate or update:

```text
gold/manifests/
```

for every successful consolidation execution.

---

### FR-006 - Idempotency

Repeated executions of the consolidation process shall not create duplicate records.

Existing deduplication mechanisms shall be preserved.

---

## Non-Functional Requirements

### NFR-001

The solution shall reuse the existing `consolidate_gold` Lambda.

No new consolidation Lambda shall be created.

---

### NFR-002

The implementation shall preserve current Bronze, Silver, Gold and Error contracts.

---

### NFR-003

The implementation shall remain fully serverless.

---

### NFR-004

The solution shall be deployable through Terraform.

---

## Technical Design

### Option Selected

Integrate the existing `consolidate_gold` Lambda into the Step Functions workflow.

---

### State Machine Extension

Current:

```text
ValidateInput
 ↓
ExtractOCR
 ↓
EnrichWithLLM
 ↓
PublishRunMetrics
 ↓
Success
```

Target:

```text
ValidateInput
 ↓
ExtractOCR
 ↓
EnrichWithLLM
 ↓
PublishRunMetrics
 ↓
ConsolidateGold
 ↓
UpdateStatusCompleted
 ↓
Success
```

---

## AWS Services

* AWS Step Functions
* AWS Lambda
* Amazon S3
* AWS Glue
* Amazon Athena

---

## Terraform Impact

### Modified Components

```text
infra/envs/dev/state_machine.asl.json
```

### Existing Resources Reused

```text
module.consolidate_gold_lambda
```

No additional Lambda resources shall be created.

---

## API Impact

### Status Endpoint

```http
GET /invoices/{invoice_id}/status
```

Response:

```json
{
  "invoice_id": "INV-001",
  "status": "Consolidating"
}
```

---

## Acceptance Criteria

### AC-001

A newly uploaded invoice reaches Gold automatically.

---

### AC-002

No manual invocation of `consolidate_gold` is required.

---

### AC-003

A user can upload an invoice and query it through the chatbot after processing completes.

---

### AC-004

The following user journey succeeds end-to-end:

```text
Upload PDF
 ↓
Processing
 ↓
Consolidating
 ↓
Completed
 ↓
Query Invoice
 ↓
Receive Analytics Response
```

---

## Out of Scope

The following capabilities are excluded from this phase:

* Multi-user support
* Cognito authentication
* Real-time notifications
* WebSockets
* Incremental Gold compaction
* Cross-batch consolidation strategies
* Dashboard generation

These features may be addressed in future specifications.

---

## Success Definition

The phase is considered complete when:

1. Gold consolidation executes automatically.
2. Processed invoices become available in Athena without manual intervention.
3. The chatbot can immediately query newly processed invoices.
4. The status API accurately reflects analytics readiness.
5. The end-to-end Data Product workflow is fully automated.
