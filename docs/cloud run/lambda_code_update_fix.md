# Lambda Code Update Fix: source_code_hash

## Problem

After rebuilding the Lambda bundle and running `terraform apply`, AWS was not
picking up the new code. The deployed hash remained unchanged across multiple
redeploys, and the Lambda kept executing the old bundle.

## Root Cause

The Lambda module used a fixed `s3_key` (`artifacts/lambda/control_plane_bundle.zip`)
with no `source_code_hash`. Terraform compares desired state against recorded state —
if neither `s3_bucket` nor `s3_key` changes, Terraform assumes the code is unchanged
and skips `UpdateFunctionCode`, even if the ZIP content on S3 is different.

## Fix

Added `source_code_hash` in two places:

**`infra/modules/lambda_function/variables.tf`**
Added optional variable `source_code_hash` (nullable, no default).

**`infra/modules/lambda_function/main.tf`**
Passed `source_code_hash = var.source_code_hash` to `aws_lambda_function`.

**`infra/envs/dev/main.tf` — all 4 Lambda modules**
Passed the hash computed from the local ZIP:

```hcl
source_code_hash = filebase64sha256("${path.root}/../../../artifacts/lambda/control_plane_bundle.zip")
```

`filebase64sha256` reads the local ZIP, computes its SHA256 in base64, and stores
it in Terraform state. On every `terraform plan`, if the local ZIP changed, Terraform
detects the difference and forces `UpdateFunctionCode` on AWS.

## Correct deploy flow from now on

```powershell
# 1. Rebuild the bundle
.\.venv\Scripts\python.exe scripts\package.py --package-manager uv

# 2. Upload to S3
$bucket = terraform -chdir=infra/envs/dev output -raw artifact_bucket_name
aws s3 cp artifacts/lambda/control_plane_bundle.zip s3://$bucket/artifacts/lambda/control_plane_bundle.zip

# 3. Apply — Terraform detects the new hash and calls UpdateFunctionCode
terraform -chdir=infra/envs/dev plan -var-file="terraform.tfvars" -out="tfplan"
terraform -chdir=infra/envs/dev apply "tfplan"
```

The `terraform plan` output should show `4 to change` (one per Lambda) whenever
the ZIP content changes.

## Verification

```powershell
# All 4 hashes must match the local ZIP
aws lambda list-functions `
  --query "Functions[?starts_with(FunctionName, 'invoice-pipeline-dev')].{Name:FunctionName, Hash:CodeSha256}" `
  --output table

python -c "
import base64, hashlib
with open(r'artifacts\lambda\control_plane_bundle.zip', 'rb') as f:
    digest = hashlib.sha256(f.read()).digest()
print('Local ZIP hash:', base64.b64encode(digest).decode())
"
```
