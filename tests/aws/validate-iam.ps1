param(
    [string]$ProjectName = "invoice-pipeline",
    [string]$Environment = "dev",
    [string]$AwsProfile = ""
)

$ErrorActionPreference = "Stop"

function Invoke-AwsJson {
    param([string[]]$Arguments)
    $args = @()
    if ($AwsProfile) {
        $args += @("--profile", $AwsProfile)
    }
    $args += $Arguments
    $output = & aws @args
    if ($LASTEXITCODE -ne 0) {
        throw "aws $($Arguments -join ' ') failed"
    }
    if (-not $output) {
        return $null
    }
    return ($output | Out-String | ConvertFrom-Json)
}

function Assert-InlinePolicies {
    param(
        [string]$Label,
        [string]$RoleName,
        [string[]]$ExpectedPolicies
    )
    $result = Invoke-AwsJson @("iam", "list-role-policies", "--role-name", $RoleName)
    $actual = @($result.PolicyNames)
    $missing = @($ExpectedPolicies | Where-Object { $actual -notcontains $_ })
    if ($missing.Count -gt 0) {
        throw "Missing inline IAM policies for $Label ($RoleName): $($missing -join ', ')"
    }
    Write-Host "ok inline policies $Label ($RoleName) -> $($ExpectedPolicies -join ', ')"
}

$prefix = ("{0}-{1}" -f $ProjectName, $Environment).ToLower().Replace("_", "-")

$roles = @(
    @{ label = "raw_dispatch"; role = "$prefix-raw-dispatch-role"; policies = @("logging", "start_execution", "sqs_consume") },
    @{ label = "validate_input"; role = "$prefix-validate-input-role"; policies = @("logging") },
    @{ label = "process_document"; role = "$prefix-process-document-role"; policies = @("logging", "data_lake_access") },
    @{ label = "extract_ocr"; role = "$prefix-extract-ocr-role"; policies = @("logging", "data_lake_access") },
    @{ label = "enrich_llm"; role = "$prefix-enrich-llm-role"; policies = @("logging", "data_lake_access") },
    @{ label = "publish_metrics"; role = "$prefix-publish-metrics-role"; policies = @("logging", "cloudwatch_write") },
    @{ label = "consolidate_gold"; role = "$prefix-consolidate-gold-role"; policies = @("logging", "data_lake_access") },
    @{ label = "step_functions"; role = "$prefix-document-pipeline-role"; policies = @("$prefix-document-pipeline-logging", "lambda_invoke") }
)

foreach ($item in $roles) {
    Assert-InlinePolicies -Label $item.label -RoleName $item.role -ExpectedPolicies $item.policies
}

Write-Host "[iam] OK"
