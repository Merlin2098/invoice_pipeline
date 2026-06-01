# Invoice Pipeline Architecture Diagram

## Objective

This document shows the current invoice pipeline architecture diagram, both as a functional flow and as the surrounding AWS services that support it.

## 1. General Pipeline Flow

```mermaid
flowchart LR
    A["Browser / Portal"] --> UP["Upload API<br/>POST /uploads"]
    UP --> B["validate-input"]
    B --> C["extract-ocr<br/>Textract AnalyzeExpense"]
    C --> D["enrich-llm<br/>optional Bedrock"]
    D --> E["Silver Documents<br/>valid | rejected"]
    E --> F["consolidate-gold<br/>(inline — SPEC-016)"]
    F --> G["Gold Parquet Dataset"]
    G --> H["Glue Catalog / Athena"]
    H --> CH["Chat API<br/>POST /chat"]
    CH --> A
```

## 2. Current AWS Architecture

```mermaid
flowchart TB
    USR["User Browser"] --> CF["CloudFront + WAF<br/>HTTPS / rate-limit"]
    CF --> S3SITE["S3 Static Site Bucket<br/>React + Vite SPA"]
    CF --> APIGW["API Gateway HTTP API v2"]

    APIGW --> UPL["Lambda upload<br/>POST /uploads"]
    APIGW --> STAT["Lambda invoice-status<br/>GET /invoices/{id}/status"]
    APIGW --> LIST["Lambda list-invoices<br/>GET /invoices"]
    APIGW --> CHAT["Lambda chat<br/>POST /chat"]

    UPL --> S3R["S3 Data Lake Bucket<br/>raw/run_id=&lt;run_id&gt;/"]
    UPL --> S3ST["S3 Data Lake Bucket<br/>status/"]
    STAT --> S3ST
    LIST --> S3ST

    CHAT --> BSQ["Amazon Bedrock<br/>NL → SQL generation"]
    CHAT --> ATH["Amazon Athena<br/>workgroup invoice-pipeline-dev"]
    CHAT --> BR2["Amazon Bedrock<br/>result summarization"]
    ATH --> S3AR["S3 Data Lake Bucket<br/>athena-results/"]
    ATH --> GC["Glue Data Catalog<br/>gold_documents · gold_invoice_summary"]

    U["Source Document Upload<br/>PDF / TIFF / PNG / JPG"] --> S3R
    S3R --> EV["S3 Object Created Event"]
    EV --> SQS["SQS Queue<br/>raw-ingestion"]
    SQS --> DLQ["SQS DLQ<br/>maxReceiveCount=3"]
    SQS --> RD["Lambda<br/>raw-dispatch"]
    RD --> SF["Step Functions<br/>document-pipeline"]

    SF --> L1["Lambda<br/>validate-input"]
    L1 --> L2["Lambda<br/>extract-ocr"]
    L2 --> TX["Amazon Textract<br/>AnalyzeExpense"]
    L2 --> S3B["S3 Data Lake Bucket<br/>bronze/textract-json/"]
    L2 --> L3["Lambda<br/>enrich-llm"]
    L3 --> BR["Amazon Bedrock<br/>optional normalization"]
    L3 --> S3SV["S3 Data Lake Bucket<br/>silver/valid/"]
    L3 --> S3SR["S3 Data Lake Bucket<br/>silver/rejected/"]
    L3 --> S3E["S3 Data Lake Bucket<br/>errors/"]
    L3 --> L4["Lambda<br/>publish-metrics"]

    S3SV --> L5["Lambda<br/>consolidate-gold"]
    S3SR --> L5
    S3E --> L5
    L5 --> S3G["S3 Data Lake Bucket<br/>gold/documents/batch_id=&lt;batch_id&gt;/"]
    L5 --> S3GM["S3 Data Lake Bucket<br/>gold/manifests/batch_id=&lt;batch_id&gt;/"]

    S3G --> GC["Glue Data Catalog<br/>invoice_pipeline_gold.gold_documents"]
    GC --> ATH["Amazon Athena<br/>workgroup invoice-pipeline-dev"]
    ATH --> S3AR["S3 Data Lake Bucket<br/>athena-results/"]

    CW["CloudWatch Logs + Metrics + Alarms"] --> SF
    CW --> RD
    CW --> L1
    CW --> L2
    CW --> L3
    CW --> L4
    CW --> L5

    BUD["AWS Budgets"] --> CW
    IAM["IAM Roles / Policies"] --> SF
    IAM --> RD
    IAM --> L1
    IAM --> L2
    IAM --> L3
    IAM --> L4
    IAM --> L5
```

## 3. Layer Detail

```mermaid
flowchart LR
    R["Raw<br/>Document arrival and trigger"] --> BZ["Bronze<br/>Textract technical evidence"]
    BZ --> SI["Silver<br/>Canonical valid or rejected"]
    SI --> GO["Gold<br/>Curated batch Parquet"]
    GO --> AN["Analytics<br/>Athena + Bedrock SQL"]
```

- `Raw`: entry point for the document and pipeline trigger.
- `Bronze`: Textract `AnalyzeExpense` JSON evidence and extraction metadata.
- `Silver`: canonical document records, split into accepted and rejected.
- `Gold`: per-batch Parquet snapshot with duplicate markers and business keys.
- `Analytics`: Glue-cataloged Athena queries, optionally generated from natural language by Bedrock.

## 4. Local Execution Diagram

```mermaid
flowchart LR
    DOC["data/raw/&lt;document&gt;"] --> BP["bronze_pipeline.py"]
    BP --> BR["data/output/bronze/"]
    BR --> SP["silver_pipeline.py"]
    SP --> SV["data/output/silver/valid/"]
    SP --> SR["data/output/silver/rejected/"]
    SV --> GP["consolidate_gold (local)"]
    GP --> GO["data/output/gold/documents/"]
```

## 5. Assets and Logic Diagram

```mermaid
flowchart TB
    CFG["pipeline_config.py"] --> RT["aws_runtime.py"]
    CON["specs/contracts/"] --> RT
    QR["specs/quality/"] --> RT
    PRO["specs/prompts/<br/>bedrock_normalization_prompt.md<br/>bedrock_analytics_sql_prompt.md"] --> RT
    RT --> E1["validate-input handler"]
    RT --> E2["extract-ocr handler"]
    RT --> E3["enrich-llm handler"]
    RT --> E4["publish-metrics handler"]
    RT --> E5["consolidate-gold handler"]
    RT --> E6["src/analytics CLI"]
```

This reflects the separation of responsibilities in the project:

- `Python`: Lambda handlers, runtime, validation, materialization
- `YAML`: contracts, quality rules, and metric definitions under `specs/`
- `Prompts`: Bedrock system prompts for normalization and analytics SQL
- `Terraform`: AWS infrastructure under `infra/envs/dev`
- `ASL`: Step Functions state machine definition

## 6. Summary

The invoice pipeline architecture combines:

- a clear `medallion` flow (Raw → Bronze → Silver → Gold) extended with `errors/` and inline Gold consolidation (SPEC-016)
- a serverless web portal (React + Vite on S3 + CloudFront + WAF) as the user-facing entry point
- HTTP API layer (API Gateway v2 + Lambda) for upload, status, history, and conversational analytics
- analytical consumption with `Glue Catalog + Athena + Bedrock NL → SQL + NL result summarization`
- security and observability with `IAM + CloudWatch Alarms + AWS Budgets + WAF rate-limiting`

The diagram represents the current deployed architecture across Phases 0–5. The MVP is complete: open portal → upload PDF → pipeline runs → NL query → NL answer is validated end to end on AWS.
