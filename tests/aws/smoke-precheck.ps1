# smoke-precheck.ps1
# Runs read-only runtime checks before a smoke validation.

param(
    [string]$TerraformDir = "infra/envs/dev"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )

    Write-Host "`n[precheck] $Name" -ForegroundColor Cyan
    & $Command
}

Invoke-Step "Terraform outputs" {
    Push-Location $TerraformDir
    try {
        $tf = terraform output -json | ConvertFrom-Json
    }
    finally {
        Pop-Location
    }

    $required = @(
        "data_lake_bucket_name",
        "state_machine_arn",
        "raw_ingestion_queue_arn",
        "raw_ingestion_queue_url",
        "raw_ingestion_dlq_url",
        "raw_dispatch_lambda_name",
        "validate_input_lambda_name",
        "process_document_lambda_name",
        "publish_metrics_lambda_name",
        "consolidate_gold_lambda_name"
    )

    foreach ($name in $required) {
        if (-not $tf.PSObject.Properties.Name.Contains($name)) {
            throw "Missing Terraform output: $name"
        }
    }
}

Invoke-Step "IAM effective permissions" {
    & "$scriptDir\validate-iam.ps1"
}

Invoke-Step "Lambda runtime dry runs" {
    & "$scriptDir\validate-runtime-access.ps1" -TerraformDir $TerraformDir
}

Invoke-Step "Event source mappings and DLQ" {
    & "$scriptDir\validate-event-mappings.ps1" -TerraformDir $TerraformDir
}

Invoke-Step "CloudWatch log groups" {
    & "$scriptDir\validate-logging.ps1" -TerraformDir $TerraformDir
}

Write-Host "`n[precheck] OK" -ForegroundColor Green
