# Terraform/AWS Guardrails for Agents

## Core Principles

- Always optimize for:

  1. destroyability
  2. low-cost dev environments
  3. reproducibility
  4. explicit resource ownership
- Never assume "enterprise defaults" are appropriate for demos/MVPs.
- Every resource created must be:

  - declared
  - tagged
  - destroyable
  - traceable

---

# Environment Rules

## DEV / SANDBOX

- Use:
  force_destroy = true
  for:

  - S3 buckets
  - non-production storage resources
- Disable S3 versioning unless explicitly required.
- Use minimal retention policies:

  - CloudWatch Logs: 1–7 days
  - S3 lifecycle expiration when possible
- Avoid expensive managed services unless explicitly approved:

  - NAT Gateway
  - MWAA
  - Redshift
  - OpenSearch
  - Bedrock production-scale configs
- Prefer serverless and free-tier-friendly architectures.

---

# Logging Rules

- NEVER rely on AWS auto-created log groups.
- Explicitly declare all CloudWatch Log Groups in Terraform.
- Define:

  - retention_in_days
  - tags
- Ensure services depend on managed log groups.

Example targets:

- Lambda
- Step Functions
- Glue
- ECS
- API Gateway

---

# S3 Rules

- Buckets must include:

  - tags
  - lifecycle considerations
  - explicit ownership
- Default:

  - versioning disabled in dev
  - encryption enabled only if required
- Avoid hidden objects outside Terraform lifecycle.

---

# Terraform Lifecycle Rules

- Every module must support:
  terraform apply
  terraform destroy
  terraform apply

without manual cleanup.

- Never create resources outside Terraform unless explicitly documented.
- Avoid orphan resources.
- Prefer explicit dependencies over implicit behavior.

---

# Cost Control Rules

- Every resource must include standard tags:

  - Environment
  - Project
  - Owner
  - ManagedBy=Terraform
- Minimize:

  - always-on resources
  - provisioned capacity
  - idle infrastructure
- Prefer:

  - on-demand
  - serverless
  - ephemeral environments

---

# Module Design Rules

- Modules must expose:

  - enable flags
  - environment-aware defaults
  - retention configuration
  - naming customization
- Separate:

  - dev
  - staging
  - prod

behavior explicitly.

---

# Agent Safety Rules

- NEVER:

  - enable versioning automatically
  - create NAT Gateway automatically
  - create expensive resources by default
  - apply infinite log retention
  - create unmanaged resources
- ALWAYS ask before:

  - IAM privilege escalation
  - production-grade persistence
  - cross-account resources
  - paid AWS services outside free tier

---

# Validation Rules

Before considering infrastructure complete, validate:

- terraform fmt
- terraform validate
- terraform plan
- terraform apply
- terraform destroy

And verify:

- no orphan log groups
- no undeleted buckets
- no residual networking resources
- no unexpected billing-risk resources

---

# Architecture Philosophy

- Demo != Production
- Simplicity > enterprise overengineering
- Destroyability is part of the architecture
- Explicit infrastructure > magical defaults
- Cost-aware engineering is mandatory
