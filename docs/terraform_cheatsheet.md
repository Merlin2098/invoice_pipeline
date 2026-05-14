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
terraform -chdir=infra/envs/dev init
```

This downloads providers and prepares the local `.terraform` directory.

## 3. Create Local Terraform Variables

Create `infra\envs\dev\terraform.tfvars` from the committed example file:

```powershell
Copy-Item infra\envs\dev\terraform.tfvars.example infra\envs\dev\terraform.tfvars
```

Edit `infra\envs\dev\terraform.tfvars` only with non-secret values, such as project name,
environment, region, and tags. This file is ignored by Git.

## 4. Validate Terraform

```powershell
terraform -chdir=infra/envs/dev fmt -check
terraform -chdir=infra/envs/dev validate
```

## 5. Create and Save a Plan

```powershell
terraform -chdir=infra/envs/dev plan -var-file="terraform.tfvars" -out="tfplan"
```

If PowerShell or the local Terraform binary returns:

```text
Error: Too many command line arguments
To specify a working directory for the plan, use the global -chdir flag.
```

run the command from the environment directory instead of using `-chdir`:

```powershell
Push-Location .\infra\envs\dev
terraform plan -var-file="terraform.tfvars" -out="tfplan"
Pop-Location
```

Keep `-out="tfplan"` as a single argument in PowerShell.

Review the saved plan in human-readable form:

```powershell
terraform -chdir=infra/envs/dev show tfplan
```

## 6. Apply the Saved Plan

Apply only the saved plan you reviewed:

```powershell
terraform -chdir=infra/envs/dev apply "tfplan"
```

If you created the plan with `Push-Location`, apply it the same way:

```powershell
Push-Location .\infra\envs\dev
terraform apply "tfplan"
Pop-Location
```

This creates or changes real AWS resources.

## 7. Destroy Lab Resources

First create and review a destroy plan:

```powershell
terraform -chdir=infra/envs/dev plan -destroy -var-file="terraform.tfvars" -out="destroy.tfplan"
terraform -chdir=infra/envs/dev show destroy.tfplan
```

Then apply the reviewed destroy plan:

```powershell
terraform -chdir=infra/envs/dev apply "destroy.tfplan"
```

This deletes the AWS resources managed by this Terraform state.

## 8. Clean Local Plan Files

After apply or destroy, remove saved plan files:

```powershell
Remove-Item infra\envs\dev\tfplan -ErrorAction SilentlyContinue
Remove-Item infra\envs\dev\destroy.tfplan -ErrorAction SilentlyContinue
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
