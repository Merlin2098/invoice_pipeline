param(
    [int]$DocumentCount = 5,
    [string]$RunId = "",
    [string]$TerraformDir = "infra/envs/dev",
    [string]$RawDataDir = "data/raw",
    [int]$TimeoutSeconds = 900,
    [int]$PollIntervalSeconds = 15,
    [switch]$SkipExecutionWait
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-JsonCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Command
    )

    $output = & $Command[0] $Command[1..($Command.Length - 1)]
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $($Command -join ' ')"
    }
    if (-not $output) {
        return $null
    }
    return ($output | Out-String | ConvertFrom-Json)
}

function Invoke-TextCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Command
    )

    $output = & $Command[0] $Command[1..($Command.Length - 1)]
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $($Command -join ' ')"
    }
    return ($output | Out-String).Trim()
}

function Get-TerraformOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    return Invoke-TextCommand -Command @("terraform", "-chdir=$TerraformDir", "output", "-raw", $Name)
}

function Get-S3Keys {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Bucket,
        [Parameter(Mandatory = $true)]
        [string]$Prefix
    )

    $response = Invoke-JsonCommand -Command @(
        "aws", "s3api", "list-objects-v2",
        "--bucket", $Bucket,
        "--prefix", $Prefix,
        "--max-keys", "1000"
    )
    if ($null -eq $response -or -not ($response.PSObject.Properties.Name -contains "Contents")) {
        return @()
    }
    return @($response.Contents | ForEach-Object { $_.Key })
}

function Get-RecentExecutionsForRun {
    param(
        [Parameter(Mandatory = $true)]
        [string]$StateMachineArn,
        [Parameter(Mandatory = $true)]
        [string]$RunId
    )

    $response = Invoke-JsonCommand -Command @(
        "aws", "stepfunctions", "list-executions",
        "--state-machine-arn", $StateMachineArn,
        "--max-results", "100"
    )
    if ($null -eq $response -or -not ($response.PSObject.Properties.Name -contains "executions")) {
        return @()
    }
    return @($response.executions | Where-Object { $_.name -like "$RunId-*" })
}

function Wait-ForPipelineExecutions {
    param(
        [Parameter(Mandatory = $true)]
        [string]$StateMachineArn,
        [Parameter(Mandatory = $true)]
        [string]$RunId,
        [Parameter(Mandatory = $true)]
        [int]$ExpectedCount
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $terminalStates = @("SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED")

    while ((Get-Date) -lt $deadline) {
        $executions = @(Get-RecentExecutionsForRun -StateMachineArn $StateMachineArn -RunId $RunId)
        $terminal = @($executions | Where-Object { $terminalStates -contains $_.status })

        Write-Host ("Executions: {0}/{1} observed, {2}/{1} terminal" -f $executions.Count, $ExpectedCount, $terminal.Count)

        if ($executions.Count -ge $ExpectedCount -and $terminal.Count -ge $ExpectedCount) {
            return $executions
        }

        Start-Sleep -Seconds $PollIntervalSeconds
    }

    throw "Timed out waiting for $ExpectedCount Step Functions executions for run_id=$RunId"
}

function Wait-ForTerminalS3Outputs {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Bucket,
        [Parameter(Mandatory = $true)]
        [string]$RunId,
        [Parameter(Mandatory = $true)]
        [int]$ExpectedCount
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        $valid = @(Get-S3Keys -Bucket $Bucket -Prefix "silver/valid/run_id=$RunId/")
        $rejected = @(Get-S3Keys -Bucket $Bucket -Prefix "silver/rejected/run_id=$RunId/")
        $failed = @(Get-S3Keys -Bucket $Bucket -Prefix "errors/silver_failed/run_id=$RunId/")
        $terminalCount = $valid.Count + $rejected.Count + $failed.Count

        Write-Host ("Terminal S3 outputs: {0}/{1} (valid={2}, rejected={3}, failed={4})" -f $terminalCount, $ExpectedCount, $valid.Count, $rejected.Count, $failed.Count)

        if ($terminalCount -ge $ExpectedCount) {
            return @{
                valid = @($valid)
                rejected = @($rejected)
                failed = @($failed)
            }
        }

        Start-Sleep -Seconds $PollIntervalSeconds
    }

    throw "Timed out waiting for $ExpectedCount terminal S3 outputs for run_id=$RunId"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

if ([string]::IsNullOrWhiteSpace($RunId)) {
    $RunId = "e2e-smoke-$((Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'))"
}

Write-Host "Run ID: $RunId"
Write-Host "Reading Terraform outputs..."

$dataLakeBucket = Get-TerraformOutput "data_lake_bucket_name"
$stateMachineArn = Get-TerraformOutput "state_machine_arn"

Write-Host "Data lake bucket: $dataLakeBucket"
Write-Host "State machine: $stateMachineArn"

$documents = @(Get-ChildItem -Path $RawDataDir -File |
    Where-Object { $_.Extension.ToLowerInvariant() -in @(".pdf", ".tif", ".tiff", ".png", ".jpg", ".jpeg") } |
    Get-Random -Count $DocumentCount)

if ($documents.Count -lt $DocumentCount) {
    throw "Only found $($documents.Count) supported documents in $RawDataDir; expected $DocumentCount"
}

Write-Host "Selected documents:"
$documents | ForEach-Object { Write-Host " - $($_.Name)" }

foreach ($document in $documents) {
    $destination = "s3://$dataLakeBucket/raw/run_id=$RunId/$($document.Name)"
    Write-Host "Uploading $($document.Name) -> $destination"
    & aws s3 cp $document.FullName $destination
    if ($LASTEXITCODE -ne 0) {
        throw "Upload failed for $($document.FullName)"
    }
}

if (-not $SkipExecutionWait) {
    $executions = @(Wait-ForPipelineExecutions `
        -StateMachineArn $stateMachineArn `
        -RunId $RunId `
        -ExpectedCount $DocumentCount)
} else {
    $executions = @()
}

$outputs = Wait-ForTerminalS3Outputs `
    -Bucket $dataLakeBucket `
    -RunId $RunId `
    -ExpectedCount $DocumentCount

$bronze = @(Get-S3Keys -Bucket $dataLakeBucket -Prefix "bronze/textract-json/run_id=$RunId/")
$gold = @(Get-S3Keys -Bucket $dataLakeBucket -Prefix "gold/documents/")
$manifests = @(Get-S3Keys -Bucket $dataLakeBucket -Prefix "gold/manifests/")

$summary = [ordered]@{
    run_id = $RunId
    uploaded_documents = @($documents | ForEach-Object { $_.Name })
    data_lake_bucket = $dataLakeBucket
    state_machine_arn = $stateMachineArn
    execution_count = $executions.Count
    execution_statuses = @($executions | Group-Object status | ForEach-Object {
        [ordered]@{ status = $_.Name; count = $_.Count }
    })
    bronze_count = $bronze.Count
    silver_valid_count = $outputs.valid.Count
    silver_rejected_count = $outputs.rejected.Count
    failed_count = $outputs.failed.Count
    recent_gold_object_count = $gold.Count
    recent_manifest_count = $manifests.Count
}

Write-Host ""
Write-Host "E2E smoke summary:"
$summary | ConvertTo-Json -Depth 5

if ($outputs.failed.Count -gt 0) {
    Write-Warning "One or more documents produced failed outputs. Inspect errors/silver_failed/run_id=$RunId/."
}
