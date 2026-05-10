Act as a senior AWS + Terraform platform engineer.

Your task is to implement the initial Terraform infrastructure foundation for a Document Intelligence Platform based on the repository docs, ADRs and specs.

IMPORTANT:
Do NOT implement business logic yet.
Focus ONLY on infrastructure modules and contracts required for the MVP cloud architecture.

# Context

This project follows:

* Medallion architecture
* Spec Driven Development
* AWS serverless-first approach
* Terraform modular design
* Traceability and observability by default

The repository already contains:

* docs/
* specs/
* ADRs
* contracts
* quality rules
* MVP AWS architecture definitions

Read and use all relevant markdown/yaml specs before implementing anything.

The architecture target is:

S3 raw
→ Lambda trigger
→ Textract AnalyzeExpense
→ Bronze JSON
→ Bedrock normalization
→ Silver valid/rejected
→ Gold parquet

# Main Objective

Create the Terraform module foundation required to support the MVP cloud implementation.

# Constraints

* Terraform >= 1.6
* AWS Provider latest stable
* Modular design only
* Environment-ready structure
* No hardcoded ARNs
* No hardcoded account IDs
* Use variables and outputs properly
* Least privilege IAM
* Tags required everywhere
* CloudWatch logging mandatory
* Avoid overengineering
* MVP-first

# Expected Repository Structure

Implement:

infra/
├── modules/
│ ├── s3_bucket/
│ ├── lambda_function/
│ ├── iam_role/
│ ├── cloudwatch_log_group/
│ ├── step_function/
│ ├── s3_notification/
│ ├── textract_permissions/
│ └── bedrock_permissions/
│
├── envs/
│ └── dev/
│ ├── main.tf
│ ├── variables.tf
│ ├── outputs.tf
│ ├── providers.tf
│ ├── terraform.tfvars.example
│ └── backend.tf.example

# Implementation Requirements

## 1. S3 Buckets

Implement reusable module for medallion buckets:

* raw
* bronze
* silver
* gold
* errors

Requirements:

* versioning enabled
* SSE encryption
* lifecycle rules placeholder
* configurable bucket policy
* tagging support
* optional force_destroy for dev only

Outputs:

* bucket_id
* bucket_arn
* bucket_name

## 2. IAM Roles

Create reusable IAM role module supporting:

* Lambda
* Step Functions
* Textract access
* Bedrock invocation
* S3 access
* CloudWatch logs

Requirements:

* least privilege
* policy attachment support
* assume role policy generated dynamically

## 3. Lambda Module

Create generic Lambda module with:

* runtime configurable
* handler configurable
* timeout configurable
* memory configurable
* environment variables
* CloudWatch integration
* optional layers
* S3 deployment package support

Outputs:

* lambda_arn
* lambda_name
* invoke_arn

## 4. CloudWatch

Create reusable log group module:

* retention configurable
* tags required
* naming convention aligned to project

## 5. S3 Notifications

Implement reusable S3 → Lambda notification module.

Requirements:

* support suffix filtering
* support prefix filtering
* dependency-safe implementation

## 6. Textract Permissions

Create module/policies required for:

* Textract AnalyzeExpense
* reading raw bucket
* writing bronze outputs

## 7. Bedrock Permissions

Create module/policies required for:

* InvokeModel
* model configurable by variable
* future support for structured outputs

# Architecture Alignment

Terraform resources MUST align with the specs:

* raw/
* bronze/
* silver/valid/
* silver/rejected/
* gold/
* errors/

Use naming conventions consistent with docs and specs.

# Observability Requirements

All modules must support:

* tags
* run_id traceability readiness
* structured logging readiness
* CloudWatch integration

# Deliverables

Generate:

1. Terraform module files
2. Variables and outputs
3. Example dev environment
4. README.md per module
5. Recommended naming conventions
6. Suggested tags structure
7. Example terraform.tfvars.example
8. Dependency graph explanation
9. Notes about future Step Functions integration

# Important

Do NOT:

* implement Glue yet
* implement Athena yet
* implement ECS yet
* implement production networking yet
* implement complex CI/CD yet

Focus on a clean MVP infrastructure baseline.

# Additional Requirement

Before implementing:

1. Analyze all specs and docs
2. Infer contracts between layers
3. Explain infra decisions briefly
4. Then generate the Terraform implementation

Prefer maintainability and clarity over excessive abstraction.
