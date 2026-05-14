param(
    [string]$TerraformDir = "infra/envs/dev",
    [string]$ProjectName = "invoice-pipeline",
    [string]$Environment = "dev",
    [string]$AwsProfile = ""
)

$ErrorActionPreference = "Stop"

function Resolve-RepoPath {
    param([string]$PathValue)
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }
    $repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    return Join-Path $repoRoot $PathValue
}

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

function Get-TerraformOutputs {
    $resolvedTerraformDir = Resolve-RepoPath $TerraformDir
    $output = terraform -chdir=$resolvedTerraformDir output -json 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "terraform output failed in ${resolvedTerraformDir}: $($output -join [Environment]::NewLine)"
    }
    return ($output | Out-String | ConvertFrom-Json)
}

function Get-OutputValue {
    param(
        [object]$Outputs,
        [string]$Name
    )
    if (-not $Outputs.PSObject.Properties.Name.Contains($Name)) {
        throw "Missing Terraform output: $Name"
    }
    return [string]$Outputs.$Name.value
}

function Convert-Tags {
    param([object]$Tags)
    $converted = @{}
    if ($Tags -is [System.Collections.IDictionary]) {
        foreach ($key in $Tags.Keys) {
            $converted[[string]$key] = [string]$Tags[$key]
        }
        return $converted
    }
    if ($Tags -is [System.Management.Automation.PSCustomObject]) {
        foreach ($property in $Tags.PSObject.Properties) {
            $converted[[string]$property.Name] = [string]$property.Value
        }
        return $converted
    }
    foreach ($tag in @($Tags)) {
        if ($tag.Key) {
            $converted[[string]$tag.Key] = [string]$tag.Value
        }
    }
    return $converted
}

function Assert-RequiredTags {
    param(
        [string]$Label,
        [hashtable]$Tags
    )
    $expected = @{
        Project     = $ProjectName
        Environment = $Environment
        ManagedBy   = "terraform"
    }
    foreach ($key in $expected.Keys) {
        if (-not $Tags.ContainsKey($key) -or $Tags[$key] -ne $expected[$key]) {
            throw "Missing or unexpected tag $key for $Label"
        }
    }
    Write-Host "ok tags $Label"
}

function Get-LambdaArn {
    param([string]$FunctionName)
    $config = Invoke-AwsJson @("lambda", "get-function-configuration", "--function-name", $FunctionName)
    return [string]$config.FunctionArn
}

function Assert-LambdaTags {
    param([string]$OutputName)
    if (-not $outputs.PSObject.Properties.Name.Contains($OutputName)) {
        return
    }
    $functionName = Get-OutputValue $outputs $OutputName
    $arn = Get-LambdaArn $functionName
    $result = Invoke-AwsJson @("lambda", "list-tags", "--resource", $arn)
    Assert-RequiredTags -Label "lambda $functionName" -Tags (Convert-Tags $result.Tags)
}

$outputs = Get-TerraformOutputs
$account = Invoke-AwsJson @("sts", "get-caller-identity")
$accountId = [string]$account.Account
$prefix = ("{0}-{1}" -f $ProjectName, $Environment).ToLower().Replace("_", "-")
$budgetName = Get-OutputValue $outputs "budget_name"

$budget = Invoke-AwsJson @("budgets", "describe-budget", "--account-id", $accountId, "--budget-name", $budgetName)
$costFilters = $budget.Budget.CostFilters
if (-not $costFilters -or -not $costFilters.TagKeyValue) {
    throw "Budget $budgetName must include a Project tag filter"
}
$tagFilters = @($costFilters.TagKeyValue)
if ($tagFilters -notcontains "Project`$$ProjectName") {
    throw "Budget $budgetName must filter Project=$ProjectName"
}
Write-Host "ok budget filter $budgetName -> Project`$$ProjectName"

$artifactBucket = Get-OutputValue $outputs "artifact_bucket_name"
$dataLakeBucket = Get-OutputValue $outputs "data_lake_bucket_name"
foreach ($bucket in @($artifactBucket, $dataLakeBucket)) {
    $result = Invoke-AwsJson @("s3api", "get-bucket-tagging", "--bucket", $bucket)
    Assert-RequiredTags -Label "bucket $bucket" -Tags (Convert-Tags $result.TagSet)
}

$lambdaNameOutputs = @(
    "raw_dispatch_lambda_name",
    "validate_input_lambda_name",
    "process_document_lambda_name",
    "extract_ocr_lambda_name",
    "enrich_llm_lambda_name",
    "publish_metrics_lambda_name",
    "consolidate_gold_lambda_name"
)
foreach ($outputName in $lambdaNameOutputs) {
    Assert-LambdaTags -OutputName $outputName
}

$roleNames = @(
    "$prefix-raw-dispatch-role",
    "$prefix-validate-input-role",
    "$prefix-process-document-role",
    "$prefix-extract-ocr-role",
    "$prefix-enrich-llm-role",
    "$prefix-publish-metrics-role",
    "$prefix-consolidate-gold-role",
    "$prefix-document-pipeline-role"
)
foreach ($roleName in $roleNames) {
    $result = Invoke-AwsJson @("iam", "list-role-tags", "--role-name", $roleName)
    Assert-RequiredTags -Label "role $roleName" -Tags (Convert-Tags $result.Tags)
}

$queueOutputs = @("raw_ingestion_queue_url", "raw_ingestion_dlq_url")
foreach ($outputName in $queueOutputs) {
    $queueUrl = Get-OutputValue $outputs $outputName
    $result = Invoke-AwsJson @("sqs", "list-queue-tags", "--queue-url", $queueUrl)
    Assert-RequiredTags -Label "queue $outputName" -Tags (Convert-Tags $result.Tags)
}

$stateMachineArn = Get-OutputValue $outputs "state_machine_arn"
$stateMachineTags = Invoke-AwsJson @("stepfunctions", "list-tags-for-resource", "--resource-arn", $stateMachineArn)
Assert-RequiredTags -Label "state machine" -Tags (Convert-Tags $stateMachineTags.tags)

Write-Host "[tags-budget] OK"
