param(
    [string]$TerraformDir = "infra/envs/dev",
    [string]$BucketName = "invoice-pipeline-dev-tfstate-184670914470",
    [string]$StateKey = "invoice-pipeline/dev/terraform.tfstate",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Continue"

$repoRoot = Join-Path $PSScriptRoot "..\.."
$logsDir = Join-Path $repoRoot "logs"
if (-not (Test-Path -LiteralPath $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logsDir "tf_step2c_check_lock_$timestamp.log"

function Write-Log {
    param([string]$Message)
    Write-Host $Message
    Add-Content -LiteralPath $logFile -Value $Message
}

Write-Log "Terraform Step 2c: check state lock"
Write-Log "Terraform dir: $TerraformDir"
Write-Log "Bucket: $BucketName"
Write-Log "State key: $StateKey"
Write-Log "Timestamp: $(Get-Date -Format o)"

# 1) Read the S3 native lock object (use_lockfile = true -> "<state-key>.tflock")
$lockKey = "$StateKey.tflock"
$tmpLockFile = Join-Path $env:TEMP "tfstate_lock_$timestamp.json"

Write-Log ""
Write-Log "=== Reading S3 lock object: s3://$BucketName/$lockKey ==="
$output = & aws s3api get-object --bucket $BucketName --key $lockKey --region $Region $tmpLockFile 2>&1
$exitCode = $LASTEXITCODE
$output | ForEach-Object { Write-Log $_.ToString() }
Write-Log "Exit code: $exitCode"

if ($exitCode -eq 0 -and (Test-Path -LiteralPath $tmpLockFile)) {
    Write-Log ""
    Write-Log "=== Lock file content ==="
    $lockContent = Get-Content -LiteralPath $tmpLockFile -Raw
    Write-Log $lockContent
    Remove-Item -LiteralPath $tmpLockFile -ErrorAction SilentlyContinue
} else {
    Write-Log ""
    Write-Log "=== No lock object found (state is not locked, or different lock mechanism). ==="
}

# 2) Re-run terraform apply to capture the full lock error message (including LockID)
Write-Log ""
Write-Log "=== terraform apply tfplan (capturing full output via Out-String) ==="
Write-Log "Command: terraform -chdir=$TerraformDir apply tfplan"

$applyOutput = & terraform -chdir=$TerraformDir apply tfplan 2>&1 | Out-String
$applyExitCode = $LASTEXITCODE

Write-Log $applyOutput
Write-Log "Exit code: $applyExitCode"

Write-Log ""
Write-Log "=== Done. Full log written to: $logFile ==="
