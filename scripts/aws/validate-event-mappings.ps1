# validate-event-mappings.ps1
# Validates the SQS -> raw_dispatch Lambda mapping and DLQ wiring.

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

$functionName = $tf.raw_dispatch_lambda_name.value
$queueArn = $tf.raw_ingestion_queue_arn.value
$queueUrl = $tf.raw_ingestion_queue_url.value

$mappingJson = aws lambda list-event-source-mappings `
    --function-name $functionName `
    --event-source-arn $queueArn `
    --output json
$mappings = @((($mappingJson | ConvertFrom-Json).EventSourceMappings))

if ($mappings.Count -ne 1) {
    throw "Expected exactly one event source mapping for $functionName and $queueArn; found $($mappings.Count)"
}

$mapping = $mappings[0]
if ($mapping.State -ne "Enabled") {
    throw "Event source mapping is not enabled: State=$($mapping.State)"
}
if ([int]$mapping.BatchSize -ne 1) {
    throw "Unexpected BatchSize=$($mapping.BatchSize); expected 1"
}
if ($mapping.ScalingConfig.MaximumConcurrency -ne 5) {
    throw "Unexpected MaximumConcurrency=$($mapping.ScalingConfig.MaximumConcurrency); expected 5"
}

$redrive = aws sqs get-queue-attributes `
    --queue-url $queueUrl `
    --attribute-names RedrivePolicy `
    --query "Attributes.RedrivePolicy" `
    --output text

if (-not $redrive -or $redrive -eq "None") {
    throw "Raw ingestion queue has no RedrivePolicy"
}

Write-Host "  ok mapping=$($mapping.UUID) state=$($mapping.State) batch=$($mapping.BatchSize)"
