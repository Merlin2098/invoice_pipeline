```powershell
.\.venv\Scripts\python.exe scripts\package.py --package-manager uv
```

```powershell
terraform -chdir=infra/envs/dev init -backend=false
```

```powershell
terraform -chdir=infra/envs/dev validate
```

```powershell
terraform -chdir=infra/envs/dev plan -var-file="terraform.tfvars" -target="module.artifact_bucket" -out="tfplan-artifact"
```

```powershell
terraform -chdir=infra/envs/dev apply "tfplan-artifact"
```

```powershell
terraform -chdir=infra/envs/dev output -raw artifact_bucket_name
```

```powershell
aws s3 cp artifacts/lambda/control_plane_bundle.zip s3://<artifact-bucket>/artifacts/lambda/control_plane_bundle.zip
```

```powershell
terraform -chdir=infra/envs/dev plan -var-file="terraform.tfvars" -out="tfplan"
```

```powershell
terraform -chdir=infra/envs/dev apply "tfplan"
```

```powershell
terraform -chdir=infra/envs/dev output
```

```powershell
terraform -chdir=infra/envs/dev destroy -var-file="terraform.tfvars"
```
