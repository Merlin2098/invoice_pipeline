# Terraform Commands

## 1. Build Lambda package
Use this first. It generates the Lambda bundle that Terraform expects to find in the artifact bucket.

```powershell
.\.venv\Scripts\python.exe scripts\package.py --package-manager uv
```

## 2. Initialize Terraform
Use this before planning or applying. It initializes the Terraform working directory and downloads providers. Use `-backend=false` when working without a configured remote backend.

```powershell
terraform -chdir=infra/envs/dev init -backend=false
```

## 3. Validate Terraform configuration
Use this after `init` and before planning. It checks that the Terraform configuration is syntactically valid.

```powershell
terraform -chdir=infra/envs/dev validate
```

## 4. Plan artifact bucket creation
Use this before the first full deploy. It creates a targeted plan only for the artifact bucket, which is needed to upload the Lambda bundle.

```powershell
terraform -chdir=infra/envs/dev plan -var-file="terraform.tfvars" -target="module.artifact_bucket" -out="tfplan-artifact"
```

## 5. Apply artifact bucket plan
Use this right after the artifact bucket plan. It creates only the artifact bucket resources.

```powershell
terraform -chdir=infra/envs/dev apply "tfplan-artifact"
```

## 6. Get artifact bucket name
Use this after creating the artifact bucket. It returns the real bucket name so you can upload the Lambda bundle.

```powershell
terraform -chdir=infra/envs/dev output -raw artifact_bucket_name
```

## 7. Upload Lambda bundle to artifact bucket
Use this after the artifact bucket exists. Replace `<artifact-bucket>` with the output from the previous command.

```powershell
aws s3 cp artifacts/lambda/control_plane_bundle.zip s3://<artifact-bucket>/artifacts/lambda/control_plane_bundle.zip
```

## 8. Plan full deployment
Use this after uploading the Lambda bundle. It creates the full Terraform execution plan for the environment.

```powershell
terraform -chdir=infra/envs/dev plan -var-file="terraform.tfvars" -out="tfplan"
```

## 9. Apply full deployment plan
Use this right after the full plan. It creates the remaining infrastructure for the AWS pipeline.

```powershell
terraform -chdir=infra/envs/dev apply "tfplan"
```

## 10. Inspect Terraform outputs
Use this after deployment to get resource names, ARNs, and other outputs needed for testing or operations.

```powershell
terraform -chdir=infra/envs/dev output
```

## 11. Plan destruction
Use this before destroying infrastructure. It creates a destroy plan so you can review what Terraform will remove.

```powershell
terraform -chdir=infra/envs/dev plan -destroy -var-file="terraform.tfvars" -out="tfplan-destroy"
```

## 12. Apply destroy plan
Use this after reviewing the destroy plan. It destroys the infrastructure described in `tfplan-destroy`.

```powershell
terraform -chdir=infra/envs/dev apply "tfplan-destroy"
```

## 13. Destroy directly
Use this only when you do not need a separate destroy plan. It destroys the environment immediately after approval.

```powershell
terraform -chdir=infra/envs/dev destroy -var-file="terraform.tfvars"
```
