locals {
  analytics_database_name            = "invoice_pipeline_gold"
  analytics_gold_documents_name      = "gold_documents"
  analytics_gold_invoice_summary_name = "gold_invoice_summary"
  athena_results_prefix              = "athena-results"
  athena_workgroup_name              = local.name_prefix
  athena_scan_limit_bytes            = 104857600
}

resource "aws_glue_catalog_database" "gold" {
  name        = local.analytics_database_name
  description = "Analytics catalog for invoice pipeline Gold datasets."
}

resource "aws_glue_catalog_table" "gold_documents" {
  name          = local.analytics_gold_documents_name
  database_name = aws_glue_catalog_database.gold.name
  description   = "Gold document snapshots produced under ${local.gold_prefix}/batch_id=<batch_id>/."
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL       = "TRUE"
    classification = "parquet"
  }

  partition_keys {
    name = "batch_id"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${module.data_lake_bucket.bucket_name}/${local.gold_prefix}/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "run_id"
      type = "string"
    }

    columns {
      name = "document_id"
      type = "string"
    }

    columns {
      name = "source_s3_key"
      type = "string"
    }

    columns {
      name = "source_file_name"
      type = "string"
    }

    columns {
      name = "document_type"
      type = "string"
    }

    columns {
      name = "document_date"
      type = "string"
    }

    columns {
      name = "vendor_name"
      type = "string"
    }

    columns {
      name = "total_amount"
      type = "double"
    }

    columns {
      name = "currency"
      type = "string"
    }

    columns {
      name = "extraction_engine"
      type = "string"
    }

    columns {
      name = "normalization_engine"
      type = "string"
    }

    columns {
      name = "llm_model_id"
      type = "string"
    }

    columns {
      name = "bedrock_invoked"
      type = "boolean"
    }

    columns {
      name = "bedrock_completed_fields"
      type = "array<string>"
    }

    columns {
      name = "processing_status"
      type = "string"
    }

    columns {
      name = "quality_status"
      type = "string"
    }

    columns {
      name = "quality_flags"
      type = "array<string>"
    }

    columns {
      name = "rejection_reason"
      type = "string"
    }

    columns {
      name = "created_at"
      type = "string"
    }

    columns {
      name = "document_fingerprint"
      type = "string"
    }

    columns {
      name = "business_key"
      type = "string"
    }

    columns {
      name = "is_duplicate"
      type = "boolean"
    }

    columns {
      name = "duplicate_of_document_id"
      type = "string"
    }

    columns {
      name = "duplicate_strategy"
      type = "string"
    }

    columns {
      name = "duplicate_confidence"
      type = "double"
    }
  }
}

resource "aws_glue_catalog_table" "gold_invoice_summary" {
  name          = local.analytics_gold_invoice_summary_name
  database_name = aws_glue_catalog_database.gold.name
  description   = "Business-friendly view over gold_documents with SPEC-012 column names."
  table_type    = "VIRTUAL_VIEW"

  parameters = {
    comment    = "Presto View"
    presto_view = "true"
  }

  # view_original_text encodes the Athena/Presto view DDL in the Glue metastore format.
  # The /* Presto View: <base64> */ wrapper is required by Athena to recognise the table
  # as a view. The inner JSON describes the columns and the original SQL.
  view_original_text = "/* Presto View: ${base64encode(jsonencode({
    originalSql = "SELECT document_id AS invoice_id, document_date AS invoice_date, vendor_name AS supplier_name, currency, total_amount, CAST(NULL AS DECIMAL(18,2)) AS subtotal_amount, CAST(NULL AS DECIMAL(18,2)) AS tax_amount, document_type, created_at AS processing_date FROM ${local.analytics_database_name}.${local.analytics_gold_documents_name}"
    catalog     = "awsdatacatalog"
    schema      = local.analytics_database_name
    columns = [
      { name = "invoice_id",       type = "varchar" },
      { name = "invoice_date",     type = "varchar" },
      { name = "supplier_name",    type = "varchar" },
      { name = "currency",         type = "varchar" },
      { name = "total_amount",     type = "double" },
      { name = "subtotal_amount",  type = "decimal(18,2)" },
      { name = "tax_amount",       type = "decimal(18,2)" },
      { name = "document_type",    type = "varchar" },
      { name = "processing_date",  type = "varchar" },
    ]
  }))} */"

  storage_descriptor {
    columns {
      name = "invoice_id"
      type = "string"
    }
    columns {
      name = "invoice_date"
      type = "string"
    }
    columns {
      name = "supplier_name"
      type = "string"
    }
    columns {
      name = "currency"
      type = "string"
    }
    columns {
      name = "total_amount"
      type = "double"
    }
    columns {
      name = "subtotal_amount"
      type = "decimal(18,2)"
    }
    columns {
      name = "tax_amount"
      type = "decimal(18,2)"
    }
    columns {
      name = "document_type"
      type = "string"
    }
    columns {
      name = "processing_date"
      type = "string"
    }

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }
  }
}

resource "aws_athena_workgroup" "analytics" {
  name          = local.athena_workgroup_name
  description   = "Athena workgroup for invoice pipeline Gold analytics."
  state         = "ENABLED"
  force_destroy = true
  tags          = local.common_tags

  configuration {
    bytes_scanned_cutoff_per_query     = local.athena_scan_limit_bytes
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${module.data_lake_bucket.bucket_name}/${local.athena_results_prefix}/"
    }
  }
}
