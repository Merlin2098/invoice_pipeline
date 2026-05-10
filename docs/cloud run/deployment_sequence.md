# Deployment Sequence

Complete ordered flow to deploy the invoice pipeline to AWS from PowerShell at the repository root.

## Step 0 — Load AWS Credentials

```powershell
Get-Content infra\env\.env.credentials | ForEach-Object {
  if ($_ -match "^\s*#" -or $_ -match "^\s*$") { return }
  $name, $value = $_ -split "=", 2
  [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), "Process")
}
```

## Step 1 — Generate the Lambda Bundle

```powershell
.\.venv\Scripts\python.exe scripts\package.py --package-manager uv
```

Verify the artifact was created:

```powershell
Get-Item artifacts\lambda\control_plane_bundle.zip
```

## Step 2 — Initialize Terraform

```powershell
terraform -chdir=infra/envs/dev init -backend=false
```

## Step 3 — Create the Artifact Bucket First

```powershell
terraform -chdir=infra/envs/dev plan -var-file="terraform.tfvars" -target="module.artifact_bucket" -out="tfplan-artifact"
terraform -chdir=infra/envs/dev apply "tfplan-artifact"
```

## Step 4 — Upload the Bundle to S3

```powershell
$bucket = terraform -chdir=infra/envs/dev output -raw artifact_bucket_name
aws s3 cp artifacts/lambda/control_plane_bundle.zip s3://$bucket/artifacts/lambda/control_plane_bundle.zip
```

## Step 5 — Plan and Apply the Full Stack

```powershell
terraform -chdir=infra/envs/dev plan -var-file="terraform.tfvars" -out="tfplan"
terraform -chdir=infra/envs/dev apply "tfplan"
```

## Step 6 — Inspect Outputs and Trigger the Pipeline

```powershell
terraform -chdir=infra/envs/dev output
```

```powershell
$lake = terraform -chdir=infra/envs/dev output -raw data_lake_bucket_name
aws s3 cp .\data\raw\0000089370.tif s3://$lake/raw/run_id=run-001/0000089370.tif
```

## Why this order matters

The Lambda functions reference a ZIP file that must exist in the artifact bucket before AWS can create them. Running a full apply without the bucket and the uploaded ZIP first causes `NoSuchKey` errors. The correct dependency chain is:

1. artifact bucket exists
2. ZIP is uploaded to that bucket
3. full stack apply creates the Lambda functions
