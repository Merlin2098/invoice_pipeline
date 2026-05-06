# `s3_notification`

Reusable S3 notification module for prefix/suffix filtered Lambda triggers.

## Features

- Adds the required `aws_lambda_permission`
- Configures `aws_s3_bucket_notification`
- Supports prefix and suffix filters

## Inputs

- `bucket_id`
- `bucket_arn`
- `lambda_arn`
- `lambda_name`
- `events`
- `filter_prefix`
- `filter_suffix`

## Outputs

- `bucket_id`

## Example

```hcl
module "raw_notification" {
  source = "../../modules/s3_notification"

  bucket_id     = module.data_lake_bucket.bucket_id
  bucket_arn    = module.data_lake_bucket.bucket_arn
  lambda_arn    = module.raw_ingestion_lambda.lambda_arn
  lambda_name   = module.raw_ingestion_lambda.lambda_name
  filter_prefix = "raw/"
}
```
