# `cloudwatch_log_group`

Small reusable module for explicitly managed CloudWatch log groups.

## Inputs

- `name`
- `retention_in_days`
- `tags`

## Outputs

- `name`
- `arn`

## Example

```hcl
module "lambda_log_group" {
  source = "../../modules/cloudwatch_log_group"

  name              = "/aws/lambda/invoice-pipeline-dev-raw-ingestion"
  retention_in_days = 30
  tags              = local.common_tags
}
```
