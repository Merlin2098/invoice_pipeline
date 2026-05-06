# Dev Environment

This directory is the new executable Terraform entrypoint for the AWS MVP
foundation. It uses the focused modules under `infra/modules/` and keeps the
older `infra/` root stack as a temporary transition baseline.

## What it provisions

- Artifact bucket for Lambda packages
- Data lake bucket with canonical prefixes:
  - `raw/`
  - `bronze/textract-json/`
  - `silver/valid/`
  - `silver/rejected/`
  - `gold/documents/`
  - `errors/`
- Placeholder raw-ingestion Lambda foundation
- S3 notification for raw uploads
- Foundation Step Functions state machine with logging
- Future-ready Textract and Bedrock managed policies

## Suggested workflow

```powershell
terraform -chdir=infra/envs/dev init -backend=false
terraform -chdir=infra/envs/dev validate
terraform -chdir=infra/envs/dev plan -var-file=terraform.tfvars.example
```

Copy `backend.tf.example` to `backend.tf` only when you are ready to configure
remote state explicitly.

Do not run `terraform apply` without explicit approval.
