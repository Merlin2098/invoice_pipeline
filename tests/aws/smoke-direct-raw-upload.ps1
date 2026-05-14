param(
    [string]$TerraformDir = "infra/envs/dev",
    [string]$SourceDir = "data/raw",
    [int]$Count = 5,
    [int]$TimeoutSeconds = 900,
    [int]$PollSeconds = 15,
    [int]$GoldRetries = 10,
    [int]$GoldRetrySeconds = 20,
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

function Invoke-AwsRaw {
    param([string[]]$Arguments)
    $args = @()
    if ($AwsProfile) {
        $args += @("--profile", $AwsProfile)
    }
    $args += $Arguments
    & aws @args
    if ($LASTEXITCODE -ne 0) {
        throw "aws $($Arguments -join ' ') failed"
    }
}

function Get-TerraformOutputs {
    $resolvedTerraformDir = Resolve-RepoPath $TerraformDir
    $output = terraform "-chdir=$resolvedTerraformDir" output -json 2>&1
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

function Get-DocumentId {
    param([string]$FileName)
    return [System.IO.Path]::GetFileNameWithoutExtension($FileName)
}

$startedAt = Get-Date
$batchId = "direct-raw-smoke-{0}" -f $startedAt.ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$logRoot = Join-Path "logs" $batchId
$cloudwatchDir = Join-Path $logRoot "cloudwatch"
$s3Dir = Join-Path $logRoot "s3"
$payloadDir = Join-Path $logRoot "payloads"
New-Item -ItemType Directory -Force -Path $cloudwatchDir, $s3Dir, $payloadDir | Out-Null

$outputs = Get-TerraformOutputs
$bucket = Get-OutputValue $outputs "data_lake_bucket_name"
$stateMachineArn = Get-OutputValue $outputs "state_machine_arn"
$consolidateLambda = Get-OutputValue $outputs "consolidate_gold_lambda_name"

$files = Get-ChildItem -Path $SourceDir -File |
    Where-Object { $_.Extension.ToLowerInvariant() -in @(".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff") } |
    Select-Object -First $Count
if ($files.Count -lt $Count) {
    throw "Expected at least $Count supported documents in $SourceDir, found $($files.Count)"
}

$uploads = @()
for ($index = 0; $index -lt $files.Count; $index++) {
    $file = $files[$index]
    $safeName = $file.Name -replace "[^A-Za-z0-9._-]", "-"
    $targetName = "{0}-{1:00}-{2}" -f $batchId, ($index + 1), $safeName
    $sourceS3Key = "raw/$targetName"
    Invoke-AwsRaw @("s3", "cp", $file.FullName, "s3://$bucket/$sourceS3Key")
    $uploads += [pscustomobject]@{
        local_path       = $file.FullName
        source_s3_key   = $sourceS3Key
        source_file_name = $targetName
        document_id     = Get-DocumentId $targetName
    }
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$executionsByKey = @{}
$terminalStatuses = @("SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED")

while ((Get-Date) -lt $deadline) {
    $list = Invoke-AwsJson @(
        "stepfunctions",
        "list-executions",
        "--state-machine-arn",
        $stateMachineArn,
        "--max-results",
        "100"
    )
    foreach ($execution in ($list.executions | Where-Object { $_ })) {
        $description = Invoke-AwsJson @(
            "stepfunctions",
            "describe-execution",
            "--execution-arn",
            [string]$execution.executionArn
        )
        $inputPayload = $description.input | ConvertFrom-Json
        $sourceKey = [string]$inputPayload.source_s3_key
        if ($uploads.source_s3_key -contains $sourceKey) {
            $executionsByKey[$sourceKey] = [pscustomobject]@{
                execution_arn    = [string]$description.executionArn
                status           = [string]$description.status
                run_id           = [string]$inputPayload.run_id
                source_s3_key    = $sourceKey
                source_file_name = [string]$inputPayload.source_file_name
                document_id      = Get-DocumentId ([string]$inputPayload.source_file_name)
            }
        }
    }

    $matched = $executionsByKey.Values
    $terminal = @($matched | Where-Object { $terminalStatuses -contains $_.status })
    Write-Host ("matched executions {0}/{1}; terminal {2}/{1}" -f @($matched).Count, $uploads.Count, $terminal.Count)
    if (@($matched).Count -eq $uploads.Count -and $terminal.Count -eq $uploads.Count) {
        break
    }
    Start-Sleep -Seconds $PollSeconds
}

$executions = @($executionsByKey.Values)
if ($executions.Count -ne $uploads.Count) {
    throw "Timed out before discovering all Step Functions executions"
}
$notTerminal = @($executions | Where-Object { $terminalStatuses -notcontains $_.status })
if ($notTerminal.Count -gt 0) {
    throw "Timed out before all executions reached terminal status"
}

$expectedDocuments = @(
    $executions | ForEach-Object {
        [ordered]@{
            run_id           = $_.run_id
            document_id      = $_.document_id
            source_s3_key    = $_.source_s3_key
            source_file_name = $_.source_file_name
        }
    }
)

$goldPayloadPath = Join-Path $payloadDir "consolidate-gold-input.json"
$goldResponsePath = Join-Path $payloadDir "consolidate-gold-response.json"
$goldPayload = [ordered]@{
    batch_id           = $batchId
    expected_documents = $expectedDocuments
    run_ids            = @($executions | ForEach-Object { $_.run_id } | Sort-Object -Unique)
    data_lake_bucket   = $bucket
}
$goldPayload | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $goldPayloadPath

$goldResult = $null
for ($attempt = 1; $attempt -le $GoldRetries; $attempt++) {
    Invoke-AwsRaw @(
        "lambda",
        "invoke",
        "--function-name",
        $consolidateLambda,
        "--cli-binary-format",
        "raw-in-base64-out",
        "--payload",
        "file://$goldPayloadPath",
        $goldResponsePath
    )
    $goldResult = Get-Content $goldResponsePath -Raw | ConvertFrom-Json
    Write-Host "gold finalizer attempt $attempt -> $($goldResult.status)"
    if ($goldResult.status -ne "incomplete") {
        break
    }
    Start-Sleep -Seconds $GoldRetrySeconds
}
if ($goldResult.status -eq "incomplete") {
    throw "Gold finalizer remained incomplete after $GoldRetries attempts"
}

Invoke-AwsRaw @("s3", "sync", "s3://$bucket/gold/documents/batch_id=$batchId/", (Join-Path $s3Dir "gold"))
foreach ($execution in $executions) {
    Invoke-AwsRaw @("s3", "sync", "s3://$bucket/bronze/textract-json/run_id=$($execution.run_id)/", (Join-Path $s3Dir "bronze\run_id=$($execution.run_id)"))
    Invoke-AwsRaw @("s3", "sync", "s3://$bucket/silver/valid/run_id=$($execution.run_id)/", (Join-Path $s3Dir "silver_valid\run_id=$($execution.run_id)"))
    Invoke-AwsRaw @("s3", "sync", "s3://$bucket/silver/rejected/run_id=$($execution.run_id)/", (Join-Path $s3Dir "silver_rejected\run_id=$($execution.run_id)"))
    Invoke-AwsRaw @("s3", "sync", "s3://$bucket/errors/silver_failed/run_id=$($execution.run_id)/", (Join-Path $s3Dir "silver_failed\run_id=$($execution.run_id)"))
}

$startMillis = [DateTimeOffset]$startedAt.ToUniversalTime().ToUnixTimeMilliseconds()
$lambdaNames = @(
    "raw_dispatch_lambda_name",
    "validate_input_lambda_name",
    "extract_ocr_lambda_name",
    "enrich_llm_lambda_name",
    "publish_metrics_lambda_name",
    "consolidate_gold_lambda_name"
)
foreach ($outputName in $lambdaNames) {
    $lambdaName = Get-OutputValue $outputs $outputName
    $logFile = Join-Path $cloudwatchDir ("/aws/lambda/$lambdaName".TrimStart("/") -replace "/", "_")
    $events = Invoke-AwsJson @(
        "logs",
        "filter-log-events",
        "--log-group-name",
        "/aws/lambda/$lambdaName",
        "--start-time",
        [string]$startMillis
    )
    $events | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 "$logFile.json"
}

$summary = [ordered]@{
    batch_id    = $batchId
    bucket      = $bucket
    executions  = $executions
    gold_result = $goldResult
    output_dir  = $logRoot
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 (Join-Path $logRoot "summary.json")
$summary | ConvertTo-Json -Depth 8
