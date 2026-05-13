# Objective

Analyze the current AWS invoice pipeline architecture and generate a phased implementation plan for the following specs:

* SPEC-004-runtime-iam-validation.md
* SPEC-005-structured-logging.md
* SPEC-006-ocr-llm-separation.md

The goal is NOT to directly implement the specs yet.

The goal is to:

1. Review the current architecture and codebase
2. Detect dependencies and affected components
3. Identify risks and sequencing requirements
4. Produce a detailed implementation roadmap
5. Minimize blast radius during refactors
6. Respect existing architectural principles already defined in AGENTS.md

---

# Important Constraints

## Do NOT implement code yet

This task is planning + architecture analysis only.

No large refactors.
No Terraform applies.
No destructive changes.

Only:

* analysis,
* dependency mapping,
* implementation sequencing,
* risk identification,
* proposed file/module changes.

---

# Existing Context

Current architecture includes:

* S3 raw ingestion
* SQS decoupling layer
* Lambda event source mappings
* Step Functions orchestration
* Textract OCR
* Bedrock enrichment
* Bronze/Silver/Error layers
* Idempotency guards
* Terraform-managed infrastructure
* PowerShell operational scripts

The current pipeline evolved from a local OCR/LLM ETL experiment into a distributed serverless event-driven platform.

Recent smoke tests exposed:

* runtime IAM drift,
* insufficient observability,
* tight OCR/LLM coupling,
* difficult debugging.

---

# Specs To Analyze

## SPEC-004 — Runtime IAM Validation

Goals:

* preflight validation scripts,
* runtime IAM verification,
* Lambda permission checks,
* SQS mapping validation,
* operational safety before smoke tests.

Expected outputs include:

* PowerShell validation scripts,
* optional GitHub Actions integration,
* runtime invoke checks.

---

## SPEC-005 — Structured Logging

Goals:

* JSON structured logging,
* correlation IDs,
* log retention,
* Terraform-managed CloudWatch log groups,
* observability standardization.

Expected outputs include:

* logging schema,
* log propagation strategy,
* Terraform changes,
* runtime logging recommendations.

---

## SPEC-006 — OCR / LLM Separation

Goals:

* separate deterministic OCR from probabilistic LLM enrichment,
* reduce retry blast radius,
* improve operational isolation,
* reduce duplicated Textract costs.

Expected target architecture:

ValidateInput
-> ExtractOCR
-> NormalizeOCR
-> EnrichWithLLM
-> PublishMetrics

---

# Required Analysis

Please produce a detailed implementation plan covering:

## 1. Architecture Impact Analysis

For each spec:

* affected Terraform modules,
* affected Lambda handlers,
* affected Step Functions,
* affected scripts,
* affected IAM policies,
* affected packaging/deployment layers.

---

## 2. Dependency Graph

Identify:

* implementation order,
* blocking dependencies,
* shared components,
* sequencing constraints.

Determine whether SPEC-004 and SPEC-005 should be completed BEFORE SPEC-006.

---

## 3. Risk Analysis

Identify:

* operational risks,
* state drift risks,
* IAM risks,
* backward compatibility concerns,
* replay/reprocessing risks,
* deployment risks,
* observability gaps during migration.

---

## 4. Recommended Phased Rollout

Generate a phased roadmap such as:

Phase 0 — Safety Baseline
Phase 1 — IAM Validation
Phase 2 — Logging Standardization
Phase 3 — OCR/LLM Split
Phase 4 — Post-Migration Hardening

For each phase include:

* objectives,
* expected code changes,
* validation strategy,
* rollback considerations.

---

## 5. Refactor Strategy

Especially for SPEC-006:

* determine whether to split the Lambda incrementally or fully replace it,
* identify reusable code,
* determine where OCR outputs should persist,
* propose S3 layer/prefix strategy,
* recommend Step Functions changes.

---

# Operational Focus

Prioritize:

* debuggability,
* resiliency,
* observability,
* deterministic behavior,
* low blast radius,
* reproducibility.

Avoid:

* premature optimization,
* unnecessary abstractions,
* overengineering.

---

# Existing Principles

Respect current repository principles from AGENTS.md:

* spec-driven development,
* separation of concerns,
* infrastructure as code,
* reproducible workflows,
* contracts-first thinking,
* operational safety.

---

# Expected Deliverable

Produce:

1. A detailed implementation roadmap
2. Dependency and sequencing analysis
3. Risk assessment
4. Recommended migration strategy
5. Suggested repository/file changes
6. Suggested testing strategy
7. Suggested rollback strategy

The output should resemble:

* an internal architecture review,
* migration RFC,
* or senior platform engineering implementation plan.
