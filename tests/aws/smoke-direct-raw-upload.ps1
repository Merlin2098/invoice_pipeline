# smoke-direct-raw-upload.ps1
# Uploads documents directly to raw/ without run_id folders, then downloads
# matching execution details, CloudWatch logs, and S3 outputs for analysis.

param(
    [string]$TerraformDir = "infra/envs/dev",
    [string]$SourceDir = "data/raw",
    [int]$Limit = 5,
    [int]$WaitSeconds = 180,
    [string]$AwsRegion = "us-east-1",
    [string]$OutputRoot = "logs"
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

function Copy-S3Prefix {
    param(
        [string]$SourceUri,
        [string]$DestinationPath,
        [string]$Label
    )

    New-Item -ItemType Directory -Force -Path $DestinationPath | Out-Null
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & aws s3 sync $SourceUri $DestinationPath 2>&1
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  warn could not sync $Label from $SourceUri" -ForegroundColor Yellow
        ($output -join [Environment]::NewLine) | Out-File (Join-Path $DestinationPath "_sync_error.txt")
        return
    }
    Write-Host "  ok downloaded $Label"
}

function Get-ExecutionsByStatus {
    param(
        [string]$StateMachineArn,
        [string]$Status
    )

    $result = Invoke-AwsJson `
        -Arguments @(
            "stepfunctions",
            "list-executions",
            "--state-machine-arn",
            $StateMachineArn,
            "--status-filter",
            $Status,
            "--max-results",
            "100",
            "--output",
            "json"
        ) `
        -Label "Step Functions executions $Status"
    return @($result.executions)
}

function Write-CloudWatchLogs {
    param(
        [string[]]$RunIds,
        [string]$OutputDir,
        [int64]$StartMs
    )

    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    $groups = @(
        "/aws/lambda/invoice-pipeline-dev-raw-dispatch",
        "/aws/lambda/invoice-pipeline-dev-validate-input",
        "/aws/lambda/invoice-pipeline-dev-extract-ocr",
        "/aws/lambda/invoice-pipeline-dev-enrich-llm",
        "/aws/lambda/invoice-pipeline-dev-publish-metrics",
        "/aws/vendedlogs/states/invoice-pipeline-dev-document-pipeline"
    )

    foreach ($group in $groups) {
        $safeName = ($group -replace "[^a-zA-Z0-9_-]", "_").Trim("_")
        $target = Join-Path $OutputDir "$safeName.txt"
        $allMessages = New-Object System.Collections.Generic.List[string]
        foreach ($runId in $RunIds) {
            $messages = Invoke-AwsText `
                -Arguments @(
                    "logs",
                    "filter-log-events",
                    "--log-group-name",
                    $group,
                    "--start-time",
                    "$StartMs",
                    "--filter-pattern",
                    "`"$runId`"",
                    "--query",
                    "events[].message",
                    "--output",
                    "text"
                ) `
                -Label "CloudWatch logs $group $runId"
            if ($messages) {
                $allMessages.Add("===== run_id=$runId =====")
                $allMessages.Add($messages)
            }
        }
        $allMessages | Out-File $target
    }
}

Push-Location $TerraformDir
try {
    $tf = terraform output -json | ConvertFrom-Json
}
finally {
    Pop-Location
}

$lakeBucket = $tf.data_lake_bucket_name.value
$stateMachineArn = $tf.state_machine_arn.value
$smokeId = "direct-raw-smoke-$(Get-Date -Format 'yyyyMMddTHHmmss')"
$outputDir = Join-Path $OutputRoot $smokeId
$executionDir = Join-Path $outputDir "executions"
$s3Dir = Join-Path $outputDir "s3"
$cwDir = Join-Path $outputDir "cloudwatch"
New-Item -ItemType Directory -Force -Path $executionDir, $s3Dir, $cwDir | Out-Null

$files = @(Get-ChildItem -Path $SourceDir -File | Select-Object -First $Limit)
if ($files.Count -eq 0) {
    throw "No files found in $SourceDir"
}
if ($files.Count -lt $Limit) {
    Write-Host "  warn requested $Limit files but found only $($files.Count)" -ForegroundColor Yellow
}

$startMs = [DateTimeOffset]::UtcNow.AddMinutes(-2).ToUnixTimeMilliseconds()
$uploaded = @()

Write-Host "`n[1/6] Uploading $($files.Count) document(s) directly to raw/ ..." -ForegroundColor Cyan
foreach ($file in $files) {
    $key = "raw/$($file.Name)"
    $uri = "s3://$lakeBucket/$key"
    aws s3 cp $file.FullName $uri | Out-Host
    $uploaded += [PSCustomObject]@{
        file = $file.Name
        source_s3_key = $key
        s3_uri = $uri
    }
}
$uploaded | ConvertTo-Json -Depth 4 | Out-File (Join-Path $outputDir "uploaded_manifest.json")

Write-Host "`n[2/6] Waiting $WaitSeconds seconds for the pipeline ..." -ForegroundColor Cyan
Start-Sleep -Seconds $WaitSeconds

Write-Host "`n[3/6] Discovering generated run_id values from Step Functions ..." -ForegroundColor Cyan
$uploadedKeys = @($uploaded | ForEach-Object { $_.source_s3_key })
$statuses = @("RUNNING", "SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED")
$matched = New-Object System.Collections.Generic.List[object]

foreach ($status in $statuses) {
    $executions = Get-ExecutionsByStatus -StateMachineArn $stateMachineArn -Status $status
    foreach ($execution in $executions) {
        $detail = Invoke-AwsJson `
            -Arguments @("stepfunctions", "describe-execution", "--execution-arn", $execution.executionArn, "--output", "json") `
            -Label "Step Functions execution detail $($execution.name)"
        $inputPayload = $null
        try {
            $inputPayload = $detail.input | ConvertFrom-Json
        }
        catch {
            continue
        }
        if ($uploadedKeys -contains $inputPayload.source_s3_key) {
            $safeName = $execution.name -replace "[^a-zA-Z0-9_-]", "_"
            $detail | ConvertTo-Json -Depth 10 | Out-File (Join-Path $executionDir "$safeName.json")
            $matched.Add([PSCustomObject]@{
                name = $execution.name
                status = $detail.status
                execution_arn = $execution.executionArn
                run_id = $inputPayload.run_id
                source_s3_key = $inputPayload.source_s3_key
                source_file_name = $inputPayload.source_file_name
                start_date = $detail.startDate
                stop_date = $detail.stopDate
            })
        }
    }
}

if ($matched.Count -eq 0) {
    throw "No Step Functions executions were found for uploaded keys. Check raw-dispatch logs in AWS."
}

$matched | Sort-Object source_s3_key, start_date -Descending |
    ConvertTo-Json -Depth 6 |
    Out-File (Join-Path $outputDir "matched_executions.json")

$runIds = @($matched | ForEach-Object { $_.run_id } | Sort-Object -Unique)
$runIds | Out-File (Join-Path $outputDir "run_ids.txt")
Write-Host "  found run_id(s): $($runIds -join ', ')"

Write-Host "`n[4/6] Downloading CloudWatch logs into $cwDir ..." -ForegroundColor Cyan
Write-CloudWatchLogs -RunIds $runIds -OutputDir $cwDir -StartMs $startMs

Write-Host "`n[5/6] Downloading S3 outputs by generated run_id ..." -ForegroundColor Cyan
foreach ($runId in $runIds) {
    $runDir = Join-Path $s3Dir "run_id=$runId"
    Copy-S3Prefix -SourceUri "s3://$lakeBucket/bronze/textract-json/run_id=$runId/" -DestinationPath (Join-Path $runDir "bronze") -Label "bronze $runId"
    Copy-S3Prefix -SourceUri "s3://$lakeBucket/silver/valid/run_id=$runId/" -DestinationPath (Join-Path $runDir "silver_valid") -Label "silver valid $runId"
    Copy-S3Prefix -SourceUri "s3://$lakeBucket/silver/rejected/run_id=$runId/" -DestinationPath (Join-Path $runDir "silver_rejected") -Label "silver rejected $runId"
    Copy-S3Prefix -SourceUri "s3://$lakeBucket/gold/documents/run_id=$runId/" -DestinationPath (Join-Path $runDir "gold") -Label "gold parquet $runId"
}

Write-Host "`n[6/6] Summary" -ForegroundColor Cyan
$summary = [PSCustomObject]@{
    smoke_id = $smokeId
    uploaded_count = $uploaded.Count
    matched_execution_count = $matched.Count
    run_ids = $runIds
    output_dir = $outputDir
}
$summary | ConvertTo-Json -Depth 5 | Tee-Object (Join-Path $outputDir "summary.json")

Write-Host "`nDirect raw upload smoke artifacts written to: $outputDir" -ForegroundColor Green
