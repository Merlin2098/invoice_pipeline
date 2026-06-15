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
$logFile = Join-Path $logsDir "tf_step1_fmt_validate_init_$timestamp.log"

function Write-Log {
    param([string]$Message)
    Write-Host $Message
    Add-Content -LiteralPath $logFile -Value $Message
}

function Invoke-Step {
    param(
        [string]$Title,
        [string[]]$Arguments
    )

    Write-Log ""
    Write-Log "=== $Title ==="
    Write-Log "Command: terraform $($Arguments -join ' ')"

    $output = & terraform @Arguments 2>&1
    $exitCode = $LASTEXITCODE

    $output | ForEach-Object { Write-Log $_.ToString() }
    Write-Log "Exit code: $exitCode"

    return $exitCode
}

Write-Log "Terraform Step 1: fmt + validate + init"
Write-Log "Terraform dir: $TerraformDir"
Write-Log "Timestamp: $(Get-Date -Format o)"

Invoke-Step -Title "terraform fmt -recursive" `
    -Arguments @("-chdir=$TerraformDir", "fmt", "-recursive")

Invoke-Step -Title "terraform validate" `
    -Arguments @("-chdir=$TerraformDir", "validate")

Invoke-Step -Title "terraform init" `
    -Arguments @("-chdir=$TerraformDir", "init")

Write-Log ""
Write-Log "=== Done. Full log written to: $logFile ==="
