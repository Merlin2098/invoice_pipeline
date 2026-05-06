# Dev Environment

This repository keeps Terraform execution explicit from `infra/`.

Use the dev example vars file as the starting point:

```powershell
terraform -chdir=infra init
terraform -chdir=infra validate
terraform -chdir=infra plan -var-file=envs/dev/terraform.tfvars.example
```

Do not run `terraform apply` without explicit approval.

