# Deployment Sequence

Complete ordered flow to deploy the invoice pipeline to AWS from PowerShell at the repository root.

## Phase 0 — Bootstrap (one-time, run once per AWS account)

Creates the S3 bucket that holds Terraform remote state. This step uses a local
state file inside `infra/bootstrap/` — that small local state is safe to commit
or keep locally since it manages only the state bucket itself.

### Step 0.1 — Load AWS Credentials

```powershell
Get-Content infra\env\.env.credentials | ForEach-Object {
  if ($_ -match "^\s*#" -or $_ -match "^\s*$") { return }
  $name, $value = $_ -split "=", 2
  [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), "Process")
}
```

### Step 0.2 — Create the state bucket

```powershell
make bootstrap-init
make bootstrap-apply
```

Note the `state_bucket_name` output. It follows the pattern
`invoice-pipeline-dev-tfstate-<account_id>`.

### Step 0.3 — Set the real bucket name in backend.tf

Open [infra/envs/dev/backend.tf](../../infra/envs/dev/backend.tf) and replace
`<account_id>` with the value shown in the `bootstrap-apply` output.

```hcl
terraform {
  backend "s3" {
    bucket       = "invoice-pipeline-dev-tfstate-123456789012"
    key          = "invoice-pipeline/dev/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true   # S3 native locking — requires Terraform >= 1.10
    encrypt      = true
  }
}
```

> **Note:** `use_lockfile = true` uses S3 native state locking (AWS feature,
> 2024). No DynamoDB table is required.

---

## Phase 1 — Normal Deployment

### Step 1 — Load AWS Credentials

```powershell
Get-Content infra\env\.env.credentials | ForEach-Object {
  if ($_ -match "^\s*#" -or $_ -match "^\s*$") { return }
  $name, $value = $_ -split "=", 2
  [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), "Process")
}
```

### Step 2 — Generate the Lambda Bundle

```powershell
make package
```

Verify the artifact was created:

```powershell
Get-Item artifacts\lambda\control_plane_bundle.zip
```

### Step 3 — Initialize Terraform with the remote backend

```powershell
terraform -chdir=infra/envs/dev init
```

On first run after setting up `backend.tf`, Terraform will prompt to migrate
existing local state to the remote backend. Answer `yes`.

### Step 4 — Create the Artifact Bucket First

```powershell
terraform -chdir=infra/envs/dev plan -var-file="terraform.tfvars" -target="module.artifact_bucket" -out="tfplan-artifact"
terraform -chdir=infra/envs/dev apply "tfplan-artifact"
```

### Step 5 — Upload the Bundle to S3

```powershell
$bucket = terraform -chdir=infra/envs/dev output -raw artifact_bucket_name
aws s3 cp artifacts/lambda/control_plane_bundle.zip s3://$bucket/artifacts/lambda/control_plane_bundle.zip
```

### Step 6 — Plan and Apply the Full Stack

```powershell
terraform -chdir=infra/envs/dev plan -var-file="terraform.tfvars" -out="tfplan"
terraform -chdir=infra/envs/dev apply "tfplan"
```

### Step 7 — Inspect Outputs and Trigger the Pipeline

```powershell
terraform -chdir=infra/envs/dev output
```

```powershell
$lake = terraform -chdir=infra/envs/dev output -raw data_lake_bucket_name
aws s3 cp .\data\raw\0000089370.tif s3://$lake/raw/run_id=run-001/0000089370.tif
```

---

## Why this order matters

The Lambda functions reference a ZIP file that must exist in the artifact bucket
before AWS can create them. Running a full apply without the bucket and the
uploaded ZIP first causes `NoSuchKey` errors. The correct dependency chain is:

1. State bucket exists (Phase 0 — one-time bootstrap)
2. Artifact bucket exists
3. ZIP is uploaded to that bucket
4. Full stack apply creates the Lambda functions
