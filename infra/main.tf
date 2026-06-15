data "aws_caller_identity" "current" {}

locals {
  name_prefix = lower(replace("${var.project_name}-${var.environment}", "_", "-"))
  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.tags
  )
}

module "storage" {
  source = "./modules/storage"

  account_id              = data.aws_caller_identity.current.account_id
  name_prefix             = local.name_prefix
  artifact_bucket_suffix  = var.artifact_bucket_suffix
  data_lake_bucket_suffix = var.data_lake_bucket_suffix
  raw_prefix              = var.raw_prefix
  bronze_prefix           = var.bronze_prefix
  silver_valid_prefix     = var.silver_valid_prefix
  silver_rejected_prefix  = var.silver_rejected_prefix
  gold_prefix             = var.gold_prefix
  metrics_prefix          = var.metrics_prefix
  tags                    = local.common_tags
}

module "compute" {
  source = "./modules/compute"

  name_prefix               = local.name_prefix
  artifact_bucket_name      = module.storage.artifact_bucket_name
  artifact_bucket_arn       = module.storage.artifact_bucket_arn
  data_lake_bucket_name     = module.storage.data_lake_bucket_name
  data_lake_bucket_arn      = module.storage.data_lake_bucket_arn
  lambda_package_s3_key     = var.lambda_package_s3_key
  normalize_script_s3_key   = var.normalize_script_s3_key
  consolidate_script_s3_key = var.consolidate_script_s3_key
  bedrock_model_id          = var.bedrock_model_id
  cloudwatch_namespace      = var.cloudwatch_namespace
  tags                      = local.common_tags
}

module "orchestration" {
  source = "./modules/orchestration"

  name_prefix                  = local.name_prefix
  data_lake_bucket_name        = module.storage.data_lake_bucket_name
  data_lake_bucket_arn         = module.storage.data_lake_bucket_arn
  raw_prefix                   = var.raw_prefix
  bronze_prefix                = var.bronze_prefix
  silver_valid_prefix          = var.silver_valid_prefix
  silver_rejected_prefix       = var.silver_rejected_prefix
  gold_prefix                  = var.gold_prefix
  metrics_prefix               = var.metrics_prefix
  prevalidation_lambda_arn     = module.compute.prevalidation_lambda_arn
  publish_metrics_lambda_arn   = module.compute.publish_metrics_lambda_arn
  normalize_job_name           = module.compute.normalize_job_name
  consolidate_job_name         = module.compute.consolidate_job_name
  bedrock_model_id             = var.bedrock_model_id
  state_machine_log_group_name = var.state_machine_log_group_name
  tags                         = local.common_tags
}

module "observability" {
  source = "./modules/observability"

  name_prefix = local.name_prefix
  namespace   = var.cloudwatch_namespace
  tags        = local.common_tags
}
