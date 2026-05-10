# Post-Bundle Deployment Steps

## Purpose
This guide explains what to do after generating the Lambda zip bundle.

## Important note
In this repository, the generated zip is uploaded to an S3 artifact bucket and then referenced by Terraform for Lambda deployment.

At the moment, this flow does **not** publish the bundle as a dedicated Lambda Layer.

## Order of execution

## 1. Generate the Lambda bundle
Run this from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\package.py --package-manager uv
```

This creates:

```text
artifacts/lambda/control_plane_bundle.zip
```

## 2. Initialize Terraform
Use this if the environment has not been initialized yet:

```powershell
terraform -chdir=infra/envs/dev init -backend=false
```

## 3. Create the artifact bucket first
The bundle must be uploaded to the artifact bucket before the full deployment.

```powershell
terraform -chdir=infra/envs/dev plan -var-file="terraform.tfvars" -target="module.artifact_bucket" -out="tfplan-artifact"
```

```powershell
terraform -chdir=infra/envs/dev apply "tfplan-artifact"
```

## 4. Get the artifact bucket name
Use the Terraform output to retrieve the real bucket name:

```powershell
terraform -chdir=infra/envs/dev output -raw artifact_bucket_name
```

## 5. Upload the bundle to the artifact bucket
Replace `<artifact-bucket>` with the value returned by the previous command:

```powershell
aws s3 cp artifacts/lambda/control_plane_bundle.zip s3://<artifact-bucket>/artifacts/lambda/control_plane_bundle.zip
```

## 6. Plan the full deployment
Once the bundle is in S3, generate the full Terraform plan:

```powershell
terraform -chdir=infra/envs/dev plan -var-file="terraform.tfvars" -out="tfplan"
```

## 7. Apply the full deployment
Apply the reviewed plan:

```powershell
terraform -chdir=infra/envs/dev apply "tfplan"
```

## 8. Inspect deployed outputs
After deployment, inspect outputs such as bucket names, Lambda names, and the Step Functions ARN:

```powershell
terraform -chdir=infra/envs/dev output
```

## 9. Trigger the pipeline
After deployment, upload a test file to the raw prefix in the data lake bucket:

```powershell
aws s3 cp .\data\raw\0000089370.tif s3://<data-lake-bucket>/raw/run_id=run-001/0000089370.tif
```

Replace `<data-lake-bucket>` with the value from:

```powershell
terraform -chdir=infra/envs/dev output -raw data_lake_bucket_name
```

## Summary
The expected flow is:

1. build the zip
2. create the artifact bucket
3. upload the zip to S3
4. apply the full Terraform stack
5. upload a test document to the data lake bucket

