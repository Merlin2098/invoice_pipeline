# SPEC-008 - Gold Analytics Layer with Athena + Bedrock Natural Language Querying

## Status

Proposed

---

# Context

The invoice intelligence pipeline currently contains:

* RAW ingestion layer
* Bronze OCR artifacts
* Silver validated/rejected outputs
* Gold analytics-ready datasets stored in Parquet format

The architecture already uses:

* S3
* Lambda
* SQS
* Step Functions
* Textract
* Bedrock
* Terraform

The active cloud MVP lives under `infra/envs/dev` and currently writes Gold as a
completed batch snapshot:

```text
s3://<data-lake-bucket>/gold/documents/batch_id=<batch_id>/documents.parquet
s3://<data-lake-bucket>/gold/manifests/batch_id=<batch_id>/manifest.json
```

The existing canonical Gold dataset is `gold_documents`, backed by
`specs/contracts/gold_documents.schema.yaml`.

The next evolution of the platform is enabling analytics consumption over the
existing Gold layer without introducing a heavyweight data warehouse platform.

---

# Problem Statement

The current pipeline lacks:

* centralized analytical metadata
* discoverable datasets
* query interfaces
* semantic access to analytics data
* natural language querying capabilities

Although Gold datasets exist in Parquet format, they are not yet:

* cataloged
* queryable through Athena
* consumable through AI-assisted analytics interfaces

---

# Decision

Adopt a phased, low-overhead serverless analytics layer composed of:

```text
Existing Gold Parquet Snapshots
-> AWS Glue Data Catalog
-> Amazon Athena
-> Optional Bedrock Natural Language Query Layer
```

The first implementation phase MUST catalog and query the existing
`gold_documents` Parquet snapshots instead of redesigning Gold generation.

The natural-language query capability SHOULD start as a lightweight Python
workflow or CLI before adding any deployed API surface.

The architecture will prioritize:

* low operational overhead
* serverless analytics
* schema-driven querying
* controlled LLM usage
* deterministic execution boundaries

---

# Objectives

## Primary Objectives

* Register the existing `gold_documents` dataset in Glue Data Catalog
* Enable Athena querying over current Gold Parquet snapshots
* Provide a minimal, validated path for natural language analytics querying
  using Amazon Bedrock
* Preserve serverless architecture principles
* Maintain low-cost operational footprint

## Secondary Objectives

* Improve analytics discoverability
* Demonstrate AI-assisted analytics workflows
* Enable future BI integrations
* Create a semantic consumption layer over the lakehouse

---

# Scope

## Included

### Gold Layer Analytics

* Athena-compatible `gold_documents` dataset
* Existing batch-oriented Parquet layout
* Explicit Glue table definition
* Query-ready schema

### Metadata Cataloging

* Glue database
* Explicit Glue table definition
* Schema registration
* Dataset discoverability

### Natural Language Querying

Natural language analytics flow:

```text
User Question
-> Bedrock Prompt
-> SQL Generation
-> SQL Validation
-> Athena Execution
-> Result Formatting
```

For the first implementation phase, this flow may run as a local/scripted
workflow using AWS credentials. A Lambda/API Gateway interface is intentionally
deferred.

### Security Controls

* Read-only Athena access
* SQL validation layer
* Restricted query execution
* Schema grounding

## Excluded

This spec does NOT include:

* Redshift
* Vector databases
* RAG systems
* Autonomous agents
* Multi-agent orchestration
* Semantic memory
* Self-healing SQL agents
* Dashboard generation
* Fine-tuned models
* Human-in-the-loop review systems
* API Gateway or public query endpoints
* Repartitioning the existing Gold writer as a prerequisite
* Replacing the current Gold consolidation Lambda

---

# Proposed Architecture

## Storage Layer

```text
S3 Gold Layer
|-- gold/documents/
|   `-- batch_id=<batch_id>/
|       `-- documents.parquet
`-- gold/manifests/
    `-- batch_id=<batch_id>/
        `-- manifest.json
```

Manifests MUST remain outside `gold/documents/` because Athena reads every file
inside a registered partition location as Parquet.

## Metadata Layer

Glue Data Catalog:

```text
Database:
  invoice_pipeline_gold

Tables:
  gold_documents
```

Future tables such as `gold_invoice_metrics` and `gold_processing_metrics` may
be added only after they exist as stable datasets or views. They are not part of
the first implementation phase.

## Query Layer

Amazon Athena:

* query execution
* partition-aware scans
* SQL analytics

## AI Analytics Layer

Amazon Bedrock:

* natural language to SQL translation
* analytics summarization
* schema-aware prompting

---

# Bedrock Query Design

## Query Flow

```text
Question
-> Prompt Builder
-> Bedrock
-> SQL Validator
-> Athena
-> Result Formatter
```

## Prompt Constraints

The model MUST:

* generate Athena-compatible SQL only
* use only registered schemas
* avoid hallucinated tables/columns
* avoid DDL/DML operations
* remain read-only

## SQL Validation Layer

Before execution, the system must reject:

* DELETE
* UPDATE
* DROP
* ALTER
* INSERT
* CREATE
* unrestricted SELECT *

The validator must:

* enforce table allowlists
* validate schema usage
* limit query complexity
* optionally limit scan size

For the first implementation phase, SQL validation MUST happen before Athena
execution and SHOULD be implemented as deterministic Python logic with unit
tests.

---

# Glue Catalog Requirements

## Glue Database

Example:

```text
invoice_pipeline_gold
```

## Table Strategy

Prefer:

* explicit schema definitions
* deterministic partitioning
* controlled schema evolution

Avoid:

* uncontrolled crawler drift
* schema auto-inference without review

The first implementation phase MUST use an explicit Glue table for
`gold_documents` based on the existing Gold contract.

Glue crawlers are deferred unless the project later needs broad dataset
discovery across many independently produced Gold tables.

---

# Partitioning Strategy

Current implementation partition:

```text
batch_id
```

Optional future partitions, only if the Gold writer is intentionally changed:

* run_date
* year
* month
* vendor_name
* document_type

`processing_status` is not recommended as an initial partition because current
Gold snapshots include accepted records only; rejected and failed records remain
in Silver/Error layers.

---

# Athena Requirements

## Query Output Location

Athena query outputs must persist to:

```text
s3://<bucket>/athena-results/
```

## Workgroup Strategy

Create dedicated Athena workgroups:

```text
invoice-pipeline-dev
invoice-pipeline-prod
```

with:

* enforced result location
* query limits
* cost controls

The first implementation phase SHOULD create only the dev workgroup from
`infra/envs/dev`.

---

# Bedrock Requirements

## Recommended Models

Prefer:

* Claude Sonnet
* lightweight analytical prompting models

Avoid:

* large autonomous agent frameworks
* excessive orchestration layers

## Schema Grounding

The prompt builder must inject:

* table names
* column names
* data types
* optional example records

Example:

```json
{
  "table": "gold_documents",
  "columns": [
    "document_id",
    "run_id",
    "vendor_name",
    "total_amount",
    "currency",
    "document_date",
    "batch_id"
  ]
}
```

The prompt builder MUST ground the model in `gold_documents` first. Additional
tables must be added deliberately through the schema registry.

---

# Observability Requirements

All analytics executions must log:

```json
{
  "query_id": "string",
  "user_question": "string",
  "generated_sql": "string",
  "execution_time_ms": 0,
  "athena_scan_mb": 0,
  "status": "SUCCESS|FAILED"
}
```

---

# Security Requirements

The analytics layer must remain:

* read-only
* schema-restricted
* query-validated
* cost-aware

The Bedrock layer must NEVER:

* directly access infrastructure APIs
* mutate datasets
* modify Glue schemas
* execute unrestricted SQL

---

# Expected Benefits

## Technical

* Serverless analytics
* AI-assisted querying
* Low operational overhead
* Strong lakehouse alignment
* Metadata-driven discovery

## Portfolio / Architectural

* Demonstrates modern lakehouse analytics
* Demonstrates AI-assisted BI concepts
* Demonstrates Bedrock integration beyond OCR
* Demonstrates natural language analytics workflows

---

# Risks

## Operational Risks

* LLM hallucinated SQL
* Large Athena scans
* Poor partition pruning
* Glue schema drift

## Financial Risks

* Excessive Athena scans
* Excessive Bedrock invocations

## Mitigations

* SQL validation layer
* Query allowlists
* Schema grounding
* Partitioned datasets
* Controlled prompts
* Athena workgroup limits

---

# Future Evolution

Potential future enhancements:

* Redshift Spectrum
* Semantic metrics layer
* BI dashboards
* Query caching
* Cost observability dashboards
* Confidence scoring for AI-generated SQL
* Lambda/API Gateway query endpoint
* Additional Gold metric tables or Athena views
* Revised partitioning by `run_date`, `year`, or `month`

These are intentionally out of scope for the current spec.

---

# Success Criteria

The implementation will be considered successful when:

* The existing `gold_documents` Parquet snapshots are queryable through Athena
* Glue Catalog exposes the `gold_documents` schema explicitly
* Athena uses a dedicated dev workgroup with enforced result output location
* Bedrock can generate valid Athena SQL from natural language prompts against
  `gold_documents`
* Queries remain read-only and validated
* Analytics workflows remain serverless and reproducible
* Costs remain controlled and observable
