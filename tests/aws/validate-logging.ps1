# validate-logging.ps1
# Validates that runtime resources have declared CloudWatch logging.

param(
    [string]$TerraformDir = "infra/envs/dev",
    [string]$AwsRegion = "us-east-1"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if (-not $env:AWS_DEFAULT_REGION) {
    $env:AWS_DEFAULT_REGION = $AwsRegion
}

function Invoke-AwsText {
    param(
        [string[]]$Arguments,
        [string]$Label
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & aws @Arguments 2>&1
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($LASTEXITCODE -ne 0) {
        throw "AWS CLI failed for ${Label}: $($output -join [Environment]::NewLine)"
    }
    return ($output -join "`n").Trim()
}

function Invoke-AwsJson {
    param(
        [string[]]$Arguments,
        [string]$Label
    )

    $text = Invoke-AwsText -Arguments $Arguments -Label $Label
    if (-not $text) {
        throw "AWS CLI returned empty JSON for $Label"
    }
    return $text | ConvertFrom-Json
}

function Assert-LogGroup {
    param(
        [string]$LogGroupName,
        [string]$Label
    )

    $logGroup = Invoke-AwsJson `
        -Arguments @("logs", "describe-log-groups", "--log-group-name-prefix", $LogGroupName, "--query", "logGroups[?logGroupName=='$LogGroupName'] | [0]", "--output", "json") `
        -Label "CloudWatch log group lookup for $LogGroupName"
    if ($null -eq $logGroup) {
        throw "Missing CloudWatch log group for ${Label}: $LogGroupName"
    }
    if ($null -eq $logGroup.retentionInDays -or "$($logGroup.retentionInDays)" -eq "") {
        throw "CloudWatch log group has no retention for ${Label}: $LogGroupName"
    }
    Write-Host "  ok log group $Label ($LogGroupName) retention=$($logGroup.retentionInDays)"
}

function Assert-LambdaLogging {
    param([string]$FunctionName)

    $config = Invoke-AwsJson `
        -Arguments @("lambda", "get-function-configuration", "--function-name", $FunctionName, "--output", "json") `
        -Label "Lambda configuration for $FunctionName"
    if (-not $config.Role) {
        throw "Lambda $FunctionName has no execution role"
    }
    if (-not $config.LoggingConfig -or -not $config.LoggingConfig.LogGroup) {
        Assert-LogGroup -LogGroupName "/aws/lambda/$FunctionName" -Label "lambda $FunctionName"
    }
    else {
        Assert-LogGroup -LogGroupName $config.LoggingConfig.LogGroup -Label "lambda $FunctionName"
    }
}

function Assert-StateMachineLogging {
    param([string]$StateMachineArn)

    $stateMachine = Invoke-AwsJson `
        -Arguments @("stepfunctions", "describe-state-machine", "--state-machine-arn", $StateMachineArn, "--output", "json") `
        -Label "Step Functions configuration for $StateMachineArn"
    $logging = $stateMachine.loggingConfiguration
    if ($null -eq $logging -or $logging.level -eq "OFF") {
        throw "Step Functions logging is disabled for $StateMachineArn"
    }
    if (-not $logging.destinations -or $logging.destinations.Count -eq 0) {
        throw "Step Functions logging has no CloudWatch destination for $StateMachineArn"
    }

    foreach ($destination in @($logging.destinations)) {
        $arn = [string]$destination.cloudWatchLogsLogGroup.logGroupArn
        if (-not $arn) {
            throw "Step Functions logging destination is missing a log group ARN"
        }
        $logGroupName = ($arn -replace "^arn:aws:logs:[^:]+:[0-9]+:log-group:", "")
        $logGroupName = $logGroupName -replace ":\*$", ""
        Assert-LogGroup -LogGroupName $logGroupName -Label "state machine"
    }
    Write-Host "  ok state machine logging level=$($logging.level)"
}

function Assert-GlueLogging {
    param([string]$JobName)

    $job = Invoke-AwsJson `
        -Arguments @("glue", "get-job", "--job-name", $JobName, "--output", "json") `
        -Label "Glue job lookup for $JobName"
    $args = $job.Job.DefaultArguments
    if (-not $args -or $args."--enable-continuous-cloudwatch-log" -ne "true") {
        throw "Glue job $JobName does not enable continuous CloudWatch logs"
    }
    Write-Host "  ok glue logging $JobName"
}

Push-Location $TerraformDir
try {
    $tf = terraform output -json | ConvertFrom-Json
}
finally {
    Pop-Location
}

$lambdaOutputs = @(
    "raw_dispatch_lambda_name",
    "validate_input_lambda_name",
    "process_document_lambda_name",
    "extract_ocr_lambda_name",
    "enrich_llm_lambda_name",
    "publish_metrics_lambda_name"
)

foreach ($outputName in $lambdaOutputs) {
    if ($tf.PSObject.Properties.Name.Contains($outputName)) {
        Assert-LambdaLogging -FunctionName $tf.PSObject.Properties[$outputName].Value.value
    }
}

Assert-StateMachineLogging -StateMachineArn $tf.state_machine_arn.value

foreach ($optionalGlueOutput in @("normalize_job_name", "consolidate_job_name")) {
    if ($tf.PSObject.Properties.Name.Contains($optionalGlueOutput)) {
        Assert-GlueLogging -JobName $tf.PSObject.Properties[$optionalGlueOutput].Value.value
    }
}

Write-Host "`n[logging] OK" -ForegroundColor Green
