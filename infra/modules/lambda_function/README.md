# `lambda_function`

Reusable Lambda module for S3-based deployment packages and explicit log-group wiring.

## Features

- Runtime, handler, timeout, and memory are configurable
- Deployment package loaded from S3
- Optional layers and environment variables
- Supports an externally managed log group dependency

## Inputs

- `function_name`
- `role_arn`
- `s3_bucket`
- `s3_key`
- `runtime`
- `handler`
- `timeout`
- `memory_size`
- `layers`
- `environment_variables`
- `log_group_name`
- `tags`

## Outputs

- `lambda_arn`
- `lambda_name`
- `invoke_arn`

## Example

```hcl
module "raw_ingestion_lambda" {
  source = "../../modules/lambda_function"

  function_name = "invoice-pipeline-dev-raw-ingestion"
  role_arn      = module.raw_ingestion_role.role_arn
  s3_bucket     = module.artifact_bucket.bucket_name
  s3_key        = "artifacts/lambda/raw_ingestion.zip"
  runtime       = "python3.11"
  handler       = "src.aws.lambda_handlers.control_plane.handle_raw_ingestion"
  log_group_name = module.lambda_log_group.name
  tags          = local.common_tags
}
```
