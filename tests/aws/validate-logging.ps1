param(
    [string]$TerraformDir = "infra/envs/dev",
    [string]$ProjectName = "invoice-pipeline",
    [string]$Environment = "dev",
    [int]$ExpectedLambdaRetentionDays = 0,
    [int]$ExpectedStepFunctionRetentionDays = 0,
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

function Get-TfvarsNumber {
    param(
        [string]$Name,
        [int]$DefaultValue
    )
    $tfvarsPath = Join-Path (Resolve-RepoPath $TerraformDir) "terraform.tfvars"
    if (-not (Test-Path $tfvarsPath)) {
        return $DefaultValue
    }
    $content = Get-Content $tfvarsPath -Raw
    $match = [regex]::Match($content, "(?m)^\s*$([regex]::Escape($Name))\s*=\s*(\d+)\s*$")
    if (-not $match.Success) {
        return $DefaultValue
    }
    return [int]$match.Groups[1].Value
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

function Assert-LogGroup {
    param(
        [string]$Label,
        [string]$LogGroupName,
        [int]$ExpectedRetentionDays
    )
    $result = Invoke-AwsJson @(
        "logs",
        "describe-log-groups",
        "--log-group-name-prefix",
        $LogGroupName
    )
    $group = @($result.logGroups | Where-Object { $_.logGroupName -eq $LogGroupName }) | Select-Object -First 1
    if (-not $group) {
        throw "Missing log group for ${Label}: $LogGroupName"
    }
    if ([int]$group.retentionInDays -ne $ExpectedRetentionDays) {
        throw "Unexpected retention for $Label ($LogGroupName): $($group.retentionInDays)"
    }
    Write-Host "ok log group $Label ($LogGroupName) retention=$($group.retentionInDays)"
}

$prefix = ("{0}-{1}" -f $ProjectName, $Environment).ToLower().Replace("_", "-")
$lambdaRetentionDays = if ($ExpectedLambdaRetentionDays -gt 0) {
    $ExpectedLambdaRetentionDays
} else {
    Get-TfvarsNumber -Name "lambda_log_retention_in_days" -DefaultValue 30
}
$stepFunctionRetentionDays = if ($ExpectedStepFunctionRetentionDays -gt 0) {
    $ExpectedStepFunctionRetentionDays
} else {
    Get-TfvarsNumber -Name "step_function_log_retention_in_days" -DefaultValue $lambdaRetentionDays
}

$lambdaFunctions = @(
    "raw-dispatch",
    "validate-input",
    "process-document",
    "extract-ocr",
    "enrich-llm",
    "publish-metrics",
    "consolidate-gold"
)

foreach ($function in $lambdaFunctions) {
    Assert-LogGroup -Label "lambda $prefix-$function" -LogGroupName "/aws/lambda/$prefix-$function" -ExpectedRetentionDays $lambdaRetentionDays
}

$stateMachineLogGroup = "/aws/vendedlogs/states/$prefix-document-pipeline"
$stateMachine = Invoke-AwsJson @(
    "stepfunctions",
    "list-state-machines",
    "--query",
    "stateMachines[?name=='$prefix-document-pipeline'] | [0]"
)
if (-not $stateMachine) {
    throw "Missing state machine: $prefix-document-pipeline"
}
$stateMachineDescription = Invoke-AwsJson @(
    "stepfunctions",
    "describe-state-machine",
    "--state-machine-arn",
    [string]$stateMachine.stateMachineArn
)
Assert-LogGroup -Label "state machine" -LogGroupName $stateMachineLogGroup -ExpectedRetentionDays $stepFunctionRetentionDays
if (-not $stateMachineDescription.loggingConfiguration -or $stateMachineDescription.loggingConfiguration.level -ne "ALL") {
    throw "State machine logging must be enabled with level ALL"
}
Write-Host "ok state machine logging level=$($stateMachineDescription.loggingConfiguration.level)"

Write-Host "[logging] OK"
