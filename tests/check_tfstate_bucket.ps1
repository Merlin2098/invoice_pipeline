param(
    [string]$BucketName = "invoice-pipeline-dev-tfstate-184670914470",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Continue"

$logsDir = Join-Path $PSScriptRoot "..\logs"
if (-not (Test-Path -LiteralPath $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logsDir "tfstate_bucket_check_$timestamp.log"

function Write-Log {
    param([string]$Message)
    Write-Host $Message
    Add-Content -LiteralPath $logFile -Value $Message
}

function Invoke-Check {
    param(
        [string]$Title,
        [string[]]$Arguments
    )

    Write-Log ""
    Write-Log "=== $Title ==="
    Write-Log "Command: aws $($Arguments -join ' ')"

    $output = & aws @Arguments 2>&1
    $exitCode = $LASTEXITCODE

    $output | ForEach-Object { Write-Log $_.ToString() }
    Write-Log "Exit code: $exitCode"

    return $exitCode
}

Write-Log "Terraform state bucket check"
Write-Log "Bucket: $BucketName"
Write-Log "Region: $Region"
Write-Log "Timestamp: $(Get-Date -Format o)"

Invoke-Check -Title "head-bucket (existence check)" `
    -Arguments @("s3api", "head-bucket", "--bucket", $BucketName, "--region", $Region)

Invoke-Check -Title "list objects (current state)" `
    -Arguments @("s3", "ls", "s3://$BucketName/", "--recursive")

Invoke-Check -Title "list object versions (versioned state, leftover deletes)" `
    -Arguments @("s3api", "list-object-versions", "--bucket", $BucketName, "--region", $Region)

Write-Log ""
Write-Log "=== Done. Full log written to: $logFile ==="
