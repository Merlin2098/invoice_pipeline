# `bedrock_permissions`

Managed policy module for future Bedrock model invocation.

## Scope

- `bedrock:InvokeModel`
- `bedrock:InvokeModelWithResponseStream`
- Configurable model ID or explicit model ARN

## Inputs

- `name`
- `aws_region`
- `model_id`
- `model_arn_override`
- `attach_to_role_names`
- `tags`

## Outputs

- `policy_arn`
- `policy_json`

## Example

```hcl
module "bedrock_permissions" {
  source = "../../modules/bedrock_permissions"

  name                 = "invoice-pipeline-dev-bedrock"
  aws_region           = var.aws_region
  model_id             = var.bedrock_model_id
  attach_to_role_names = [module.invoice_pipeline_state_machine.role_name]
  tags                 = local.common_tags
}
```
