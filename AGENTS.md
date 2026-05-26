# AGENTS.md

## Purpose

This repository contains the Invoice Intelligence Pipeline: a cloud-first AWS
data engineering project for invoice ingestion, OCR extraction, quality-aware
document routing, and Gold analytics over a Terraform-managed data lake.

Agents should help keep the project ready for public GitHub presentation and
cloud operation. The current focus is the deployed AWS MVP, not local test
harnesses or repository-template bootstrapping.

---

## Knowledge Sources

Use these repository sources first:

* `README.md` for the public project narrative and operating workflow
* `docs/` for architecture notes, runbooks, deployment history, and diagrams
* `specs/` for contracts, quality rules, metrics, prompts, and design records
* `ai/skills/` for implementation guidance and best practices
* `ai/skills.yaml` and `ai/context.yaml` for AI guidance configuration

The AI guidance files are support material. They are not hidden orchestration
logic and should not become a framework.

---

## Working Style

When assisting in this repository:

1. Understand the current AWS, Terraform, and pipeline shape before editing
2. Search for existing implementations before creating files
3. Prefer explicit, readable changes over abstractions
4. Keep SQL, infrastructure, runtime code, configuration, and docs separated
5. Preserve cloud-first behavior and public-readiness of the repository
6. Validate changes with explicit commands where practical

---

## Execution Rules

Use explicit project commands only.

Preferred workflow:

* use `make <target>` when `make` is available
* in restricted Windows environments, use `scripts/windows/run_make.ps1`
* run Terraform commands directly and intentionally from `infra/envs/dev`
* generate Lambda bundles through the existing packaging script or `make package`

Do not introduce hidden automation, background orchestration, or agent-only
execution paths.

---

## Package Manager Awareness

This repository uses `uv` and `pyproject.toml` as the primary Python workflow.

Agents should:

* inspect dependency files before changing packaging
* keep `pyproject.toml` and `uv.lock` aligned
* avoid reintroducing local test dependencies unless explicitly requested
* keep Lambda-only dependencies in `requirements.lambda.txt`

---

## Approval Boundaries

### Never without explicit approval

* `terraform apply`
* `terraform destroy`
* modifying Terraform state
* deleting or overwriting user-owned data or generated artifacts

### Ask before

* IAM policy or role changes
* Terraform module interface changes
* paid AWS services or production-grade infrastructure defaults
* data contract changes
* changes that alter deployed runtime behavior

---

## Principles

* Cloud-first AWS MVP behavior is the source of truth
* Terraform remains destroyable, reproducible, low-cost, and explicit
* Runtime permissions should follow least privilege
* Data contracts and quality rules define promoted outputs
* CloudWatch logs and metrics should make every run inspectable
* Public docs should describe validated cloud behavior clearly
* Local tooling exists only to support packaging, formatting, and development

---

## Existing Code Awareness

Before generating a new file or artifact:

1. Search the repository for an existing equivalent
2. Prefer modifying or extending current files
3. Avoid duplicating Terraform modules, Lambda handlers, Glue jobs, SQL, specs,
   or configuration files

Only create new files when no equivalent exists or the user explicitly requests
one.

---

## Cloud Areas

| When the task involves... | Consult |
|---|---|
| Terraform infrastructure | `ai/skills/terraform/terraform_style.md`, `ai/skills/terraform/modules.md` |
| Terraform state or backend work | `ai/skills/terraform/state_management.md` |
| IAM permissions | `ai/skills/aws/iam_policies.md`, `ai/skills/terraform/iam_least_privilege.md` |
| Lambda handlers | `ai/skills/aws/lambda_functions.md` |
| Step Functions | `ai/skills/aws/step_functions.md` |
| S3 data lake layout | `ai/skills/aws/s3_data_lake.md` |
| Glue and Gold analytics | `ai/skills/aws/glue_jobs.md` |
| CloudWatch logging and metrics | `ai/skills/aws/cloudwatch_logging.md` |
| Data contracts and quality rules | `ai/skills/data/data_contracts.md`, `ai/skills/data/data_quality_guidance.md` |
| SQL or Athena behavior | `ai/skills/sql/sql_workflow_guidance.md` |

---

## Philosophy

Simple. Explicit. Cloud-validatable.

AI helps maintain and explain the project; it is not the system itself.
