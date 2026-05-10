# Terraform Cheat Sheet

Use this flow from PowerShell at the repository root.

This lab expects AWS credentials in `infra\env\.env.credentials`. Keep that file
local only. Do not commit real access keys.

## 1. Load AWS Credentials

```powershell
Get-Content infra\env\.env.credentials | ForEach-Object {
  if ($_ -match "^\s*#" -or $_ -match "^\s*$") { return }

  $name, $value = $_ -split "=", 2
  [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), "Process")
}
```

Verify only non-secret values:

```powershell
$env:AWS_ACCESS_KEY_ID
$env:AWS_DEFAULT_REGION
```

Avoid printing `AWS_SECRET_ACCESS_KEY`.

## 2. Initialize Terraform

Run this before the first plan, and repeat it when providers, modules, or
backend settings change.

```powershell
terraform -chdir=infra init
```

This downloads providers and prepares the local `.terraform` directory.

## 3. Create Local Terraform Variables

Create `infra\terraform.tfvars` from the committed example file:

```powershell
Copy-Item infra\terraform.tfvars.example infra\terraform.tfvars
```

Edit `infra\terraform.tfvars` only with non-secret values, such as project name,
environment, region, and tags. This file is ignored by Git.

## 4. Validate Terraform

```powershell
terraform -chdir=infra fmt -check
terraform -chdir=infra validate
```

## 5. Create and Save a Plan

```powershell
terraform -chdir=infra plan -var-file="terraform.tfvars" -out="tfplan"
```

Review the saved plan in human-readable form:

```powershell
terraform -chdir=infra show tfplan
```

## 6. Apply the Saved Plan

Apply only the saved plan you reviewed:

```powershell
terraform -chdir=infra apply "tfplan"
```

This creates or changes real AWS resources.

## 7. Destroy Lab Resources

First create and review a destroy plan:

```powershell
terraform -chdir=infra plan -destroy -var-file="terraform.tfvars" -out="destroy.tfplan"
terraform -chdir=infra show destroy.tfplan
```

Then apply the reviewed destroy plan:

```powershell
terraform -chdir=infra apply "destroy.tfplan"
```

This deletes the AWS resources managed by this Terraform state.

## 8. Clean Local Plan Files

After apply or destroy, remove saved plan files:

```powershell
Remove-Item infra\tfplan -ErrorAction SilentlyContinue
Remove-Item infra\destroy.tfplan -ErrorAction SilentlyContinue
```

## 9. Clear Credentials From the Session

When finished, remove AWS credentials from the current PowerShell process:

```powershell
Remove-Item Env:\AWS_ACCESS_KEY_ID -ErrorAction SilentlyContinue
Remove-Item Env:\AWS_SECRET_ACCESS_KEY -ErrorAction SilentlyContinue
Remove-Item Env:\AWS_SESSION_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:\AWS_DEFAULT_REGION -ErrorAction SilentlyContinue
```

Close the terminal window too if you want to fully discard the session.
