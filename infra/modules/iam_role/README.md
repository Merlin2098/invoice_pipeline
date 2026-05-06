# `iam_role`

Generic IAM role module for service-assumed roles with least-privilege policy inputs.

## Features

- Dynamic assume-role policy from `trusted_services`
- Optional inline policies
- Optional managed policy attachments
- Outputs for downstream modules

## Inputs

- `name`
- `trusted_services`
- `inline_policies`
- `managed_policy_arns`
- `tags`

## Outputs

- `role_id`
- `role_name`
- `role_arn`

## Example

```hcl
module "raw_ingestion_role" {
  source = "../../modules/iam_role"

  name             = "invoice-pipeline-dev-raw-ingestion-role"
  trusted_services = ["lambda.amazonaws.com"]
  inline_policies = {
    logging = data.aws_iam_policy_document.lambda_logging.json
  }
  tags = local.common_tags
}
```
