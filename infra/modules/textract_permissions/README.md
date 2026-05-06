# `textract_permissions`

Managed policy module for future Textract execution with least-privilege S3 access.

## Scope

- `textract:AnalyzeExpense`
- Read from `raw/`
- Write to `bronze/textract-json/`

## Inputs

- `name`
- `data_lake_bucket_arn`
- `raw_prefix`
- `bronze_prefix`
- `attach_to_role_names`
- `tags`

## Outputs

- `policy_arn`
- `policy_json`

## Example

```hcl
module "textract_permissions" {
  source = "../../modules/textract_permissions"

  name                 = "invoice-pipeline-dev-textract"
  data_lake_bucket_arn = module.data_lake_bucket.bucket_arn
  raw_prefix           = "raw"
  bronze_prefix        = "bronze/textract-json"
  attach_to_role_names = [module.invoice_pipeline_state_machine.role_name]
  tags                 = local.common_tags
}
```
