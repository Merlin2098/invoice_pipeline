param(
    [string]$TerraformDir = "infra/envs/dev"
)

$ErrorActionPreference = "Continue"

$repoRoot = Join-Path $PSScriptRoot "..\.."
$logsDir = Join-Path $repoRoot "logs"
if (-not (Test-Path -LiteralPath $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logsDir "tf_step4_get_portal_url_$timestamp.log"

function Write-Log {
    param([string]$Message)
    Write-Host $Message
    Add-Content -LiteralPath $logFile -Value $Message
}

Write-Log "Terraform Step 4: get CloudFront portal URL"
Write-Log "Terraform dir: $TerraformDir"
Write-Log "Timestamp: $(Get-Date -Format o)"

# Build the -chdir argument as its own string first. On PowerShell 5.1, passing
# "-chdir=$TerraformDir" inline to a native exe via & can reach terraform.exe
# without expanding $TerraformDir, producing "chdir $TerraformDir: ...".
$chdirArg = "-chdir=$TerraformDir"

# 1) Portal URL (https://<cloudfront-domain>)
Write-Log ""
Write-Log "=== terraform output portal_url ==="
Write-Log "Command: terraform $chdirArg output -raw portal_url"
$portalUrl = & terraform $chdirArg output -raw portal_url 2>&1
$exitCode = $LASTEXITCODE
Write-Log $portalUrl
Write-Log "Exit code: $exitCode"

# 2) CloudFront distribution ID (useful for cache invalidation)
Write-Log ""
Write-Log "=== terraform output cloudfront_distribution_id ==="
Write-Log "Command: terraform $chdirArg output -raw cloudfront_distribution_id"
$distributionId = & terraform $chdirArg output -raw cloudfront_distribution_id 2>&1
$distExitCode = $LASTEXITCODE
Write-Log $distributionId
Write-Log "Exit code: $distExitCode"

if ($exitCode -eq 0) {
    Write-Log ""
    Write-Log "=== Portal URL ==="
    Write-Log $portalUrl
}

Write-Log ""
Write-Log "=== Done. Full log written to: $logFile ==="
