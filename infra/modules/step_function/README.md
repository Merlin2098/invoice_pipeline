# `step_function`

Reusable Step Functions module that includes the state machine, its IAM role, and execution logging.

## Features

- Creates the Step Functions role automatically
- Adds the CloudWatch Logs delivery policy required by AWS
- Creates and wires the execution log group
- Accepts additional inline policies for workflow-specific permissions

## Inputs

- `state_machine_name`
- `definition`
- `log_group_name`
- `log_retention_in_days`
- `additional_inline_policies`
- `managed_policy_arns`
- `tags`

## Outputs

- `state_machine_arn`
- `state_machine_name`
- `role_name`
- `role_arn`
- `log_group_name`

## Notes

This module is intentionally foundation-only for the MVP baseline. The detailed
invoice workflow should be added later, once the Lambda handlers and document
contracts are ready.

## Example

```hcl
module "invoice_pipeline_state_machine" {
  source = "../../modules/step_function"

  state_machine_name = "invoice-pipeline-dev-foundation"
  definition         = templatefile("${path.module}/state_machine.asl.json", {})
  log_group_name     = "/aws/vendedlogs/states/invoice-pipeline-dev-foundation"
  additional_inline_policies = {
    lambda_invoke = data.aws_iam_policy_document.step_function_lambda_invoke.json
  }
  tags = local.common_tags
}
```
