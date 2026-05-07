# `s3_bucket`

Reusable S3 bucket module for the Terraform MVP foundation.

## Features

- AES256 server-side encryption
- Public access blocked
- Optional lifecycle rule placeholders
- Optional bucket policy

## Inputs

- `bucket_name`: globally unique bucket name
- `force_destroy`: dev-only cleanup flag
- `create_object_prefixes`: prefixes such as `raw/` or `bronze/textract-json/`
- `lifecycle_rules`: placeholder lifecycle rules
- `policy_json`: optional bucket policy
- `tags`: resource tags

## Outputs

- `bucket_id`
- `bucket_arn`
- `bucket_name`

## Example

```hcl
module "data_lake_bucket" {
  source = "../../modules/s3_bucket"

  bucket_name = "invoice-pipeline-dev-123456789012-lake"
  create_object_prefixes = [
    "raw/",
    "bronze/textract-json/",
    "silver/valid/",
    "silver/rejected/",
    "gold/documents/",
    "errors/",
  ]
  tags = local.common_tags
}
```
