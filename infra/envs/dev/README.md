# Dev Environment

This directory is the executable Terraform entrypoint for the AWS MVP document
pipeline. It uses the focused modules under `infra/modules/` and keeps the
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
- Raw-dispatch Lambda triggered by S3 uploads
- Validate-input Lambda used by Step Functions
- Process-document Lambda that calls Textract and writes bronze/silver outputs
- Publish-metrics Lambda for CloudWatch metrics
- Step Functions state machine with logging
- Textract and Bedrock IAM policies attached to the processing role

## Trigger flow

1. Upload a document to `s3://<data-lake-bucket>/raw/run_id=<run_id>/<file>`
2. S3 invokes the raw-dispatch Lambda
3. The dispatcher starts the Step Functions state machine
4. Step Functions validates input, processes the document with Textract, writes
   bronze and silver outputs, and publishes metrics

## Suggested workflow

```powershell
.\.venv\Scripts\python.exe scripts\package.py --package-manager uv
terraform -chdir=infra/envs/dev init -backend=false
terraform -chdir=infra/envs/dev validate
terraform -chdir=infra/envs/dev plan -var-file=terraform.tfvars.example
```

After packaging, upload the generated bundle to the artifact bucket key
defined by `lambda_package_s3_key` before running `terraform apply`.

Example upload once the artifact bucket exists:

```powershell
aws s3 cp artifacts/lambda/control_plane_bundle.zip s3://<artifact-bucket>/artifacts/lambda/control_plane_bundle.zip
```

Copy `backend.tf.example` to `backend.tf` only when you are ready to configure
remote state explicitly.

Do not run `terraform apply` without explicit approval.
