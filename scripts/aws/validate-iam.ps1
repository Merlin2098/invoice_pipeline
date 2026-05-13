# validate-iam.ps1
# Uses IAM policy simulation against the actual Lambda execution roles.

param(
    [string]$TerraformDir = "infra/envs/dev"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location $TerraformDir
try {
    $tf = terraform output -json | ConvertFrom-Json
}
finally {
    Pop-Location
}

$bucketArn = $tf.data_lake_bucket_arn.value
$stateMachineArn = $tf.state_machine_arn.value
$queueArn = $tf.raw_ingestion_queue_arn.value
$accountId = aws sts get-caller-identity --query Account --output text
$region = aws configure get region
if (-not $region) {
    $region = "us-east-1"
}

function Get-OptionalOutputValue {
    param([string]$Name)
    if ($tf.PSObject.Properties.Name.Contains($Name)) {
        return $tf.PSObject.Properties[$Name].Value.value
    }
    return $null
}

function Get-LambdaRoleArn {
    param([string]$FunctionName)
    return aws lambda get-function-configuration `
        --function-name $FunctionName `
        --query "Role" `
        --output text
}

function Get-LambdaEnvValue {
    param(
        [string]$FunctionName,
        [string]$Name
    )
    $config = aws lambda get-function-configuration `
        --function-name $FunctionName `
        --output json | ConvertFrom-Json
    $variables = $config.Environment.Variables
    if ($variables -and $variables.PSObject.Properties.Name.Contains($Name)) {
        return $variables.PSObject.Properties[$Name].Value
    }
    return $null
}

function Get-BedrockResources {
    param([string]$FunctionName)
    $modelId = Get-LambdaEnvValue -FunctionName $FunctionName -Name "BEDROCK_MODEL_ID"
    if (-not $modelId) {
        return @()
    }
    return @(
        "arn:aws:bedrock:${region}::foundation-model/$modelId",
        "arn:aws:bedrock:${region}:${accountId}:inference-profile/$modelId",
        "arn:aws:bedrock:*::foundation-model/*"
    )
}

function Assert-Allowed {
    param(
        [string]$RoleArn,
        [string[]]$Actions,
        [string[]]$Resources,
        [string]$Label,
        [string[]]$ContextEntries = @()
    )

    $args = @(
        "iam",
        "simulate-principal-policy",
        "--policy-source-arn",
        $RoleArn,
        "--action-names"
    ) + $Actions + @(
        "--resource-arns"
    ) + $Resources

    if ($ContextEntries.Count -gt 0) {
        $args += @("--context-entries")
        $args += $ContextEntries
    }

    $simulation = aws @args --output json | ConvertFrom-Json

    $denied = @($simulation.EvaluationResults | Where-Object {
        $_.EvalDecision -ne "allowed"
    })

    if ($denied.Count -gt 0) {
        $summary = $denied | ForEach-Object {
            "$($_.EvalActionName) on $($_.EvalResourceName) => $($_.EvalDecision)"
        }
        throw "IAM validation failed for $Label ($RoleArn): $($summary -join '; ')"
    }

    Write-Host "  ok $Label"
}

$rawDispatchRole = Get-LambdaRoleArn $tf.raw_dispatch_lambda_name.value
$validateInputRole = Get-LambdaRoleArn $tf.validate_input_lambda_name.value
$processDocumentRole = Get-LambdaRoleArn $tf.process_document_lambda_name.value
$publishMetricsRole = Get-LambdaRoleArn $tf.publish_metrics_lambda_name.value
$extractOcrName = Get-OptionalOutputValue "extract_ocr_lambda_name"
$enrichLlmName = Get-OptionalOutputValue "enrich_llm_lambda_name"

Assert-Allowed `
    -RoleArn $rawDispatchRole `
    -Actions @("states:StartExecution") `
    -Resources @($stateMachineArn) `
    -Label "raw_dispatch StartExecution"

Assert-Allowed `
    -RoleArn $rawDispatchRole `
    -Actions @(
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:ChangeMessageVisibility"
    ) `
    -Resources @($queueArn) `
    -Label "raw_dispatch SQS consume"

Assert-Allowed `
    -RoleArn $processDocumentRole `
    -Actions @("s3:GetObject") `
    -Resources @(
        "$bucketArn/raw/*",
        "$bucketArn/silver/valid/*"
    ) `
    -Label "process_document S3 reads"

Assert-Allowed `
    -RoleArn $processDocumentRole `
    -Actions @("s3:ListBucket") `
    -Resources @($bucketArn) `
    -ContextEntries @("ContextKeyName=s3:prefix,ContextKeyValues=silver/valid/run_id=runtime-precheck/precheck.json,ContextKeyType=string") `
    -Label "process_document silver idempotency list"

Assert-Allowed `
    -RoleArn $processDocumentRole `
    -Actions @("s3:PutObject") `
    -Resources @(
        "$bucketArn/bronze/textract-json/*",
        "$bucketArn/silver/valid/*",
        "$bucketArn/silver/rejected/*",
        "$bucketArn/errors/*"
    ) `
    -Label "process_document S3 writes"

Assert-Allowed `
    -RoleArn $processDocumentRole `
    -Actions @("textract:AnalyzeExpense") `
    -Resources @("*") `
    -Label "process_document Textract"

$processBedrockResources = Get-BedrockResources -FunctionName $tf.process_document_lambda_name.value
if ($processBedrockResources.Count -gt 0) {
    Assert-Allowed `
        -RoleArn $processDocumentRole `
        -Actions @("bedrock:InvokeModel") `
        -Resources $processBedrockResources `
        -Label "process_document Bedrock"
}

if ($extractOcrName) {
    $extractOcrRole = Get-LambdaRoleArn $extractOcrName
    Assert-Allowed `
        -RoleArn $extractOcrRole `
        -Actions @("s3:GetObject") `
        -Resources @(
            "$bucketArn/raw/*",
            "$bucketArn/silver/valid/*"
        ) `
        -Label "extract_ocr S3 reads"

    Assert-Allowed `
        -RoleArn $extractOcrRole `
        -Actions @("s3:ListBucket") `
        -Resources @($bucketArn) `
        -ContextEntries @("ContextKeyName=s3:prefix,ContextKeyValues=silver/valid/run_id=runtime-precheck/precheck.json,ContextKeyType=string") `
        -Label "extract_ocr silver idempotency list"

    Assert-Allowed `
        -RoleArn $extractOcrRole `
        -Actions @("s3:PutObject") `
        -Resources @("$bucketArn/bronze/textract-json/*") `
        -Label "extract_ocr bronze write"

    Assert-Allowed `
        -RoleArn $extractOcrRole `
        -Actions @("textract:AnalyzeExpense") `
        -Resources @("*") `
        -Label "extract_ocr Textract"
}

if ($enrichLlmName) {
    $enrichLlmRole = Get-LambdaRoleArn $enrichLlmName
    Assert-Allowed `
        -RoleArn $enrichLlmRole `
        -Actions @("s3:GetObject") `
        -Resources @("$bucketArn/bronze/textract-json/*") `
        -Label "enrich_llm bronze read"

    Assert-Allowed `
        -RoleArn $enrichLlmRole `
        -Actions @("s3:PutObject") `
        -Resources @(
            "$bucketArn/silver/valid/*",
            "$bucketArn/silver/rejected/*",
            "$bucketArn/errors/*"
        ) `
        -Label "enrich_llm final writes"

    $enrichBedrockResources = Get-BedrockResources -FunctionName $enrichLlmName
    if ($enrichBedrockResources.Count -gt 0) {
        Assert-Allowed `
            -RoleArn $enrichLlmRole `
            -Actions @("bedrock:InvokeModel") `
            -Resources $enrichBedrockResources `
            -Label "enrich_llm Bedrock"
    }
}

Assert-Allowed `
    -RoleArn $publishMetricsRole `
    -Actions @("cloudwatch:PutMetricData") `
    -Resources @("*") `
    -Label "publish_metrics CloudWatch"
