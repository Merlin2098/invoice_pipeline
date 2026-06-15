param(
    [string]$TerraformDir = "infra/envs/dev",
    [string]$VarFile = "terraform.tfvars"
)

$ErrorActionPreference = "Continue"

$repoRoot = Join-Path $PSScriptRoot "..\.."
$logsDir = Join-Path $repoRoot "logs"
if (-not (Test-Path -LiteralPath $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logsDir "tf_step2_plan_output_$timestamp.log"

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

Write-Log "Terraform Step 2: plan + output"
Write-Log "Terraform dir: $TerraformDir"
Write-Log "Var file: $VarFile"
Write-Log "Timestamp: $(Get-Date -Format o)"

$planExitCode = Invoke-Step -Title "terraform plan" `
    -Arguments @("-chdir=$TerraformDir", "plan", "-var-file=$VarFile", "-out=tfplan")

if ($planExitCode -ne 0) {
    Write-Log ""
    Write-Log "=== Plan failed (exit $planExitCode). ==="
    Write-Log "=== Done. Full log written to: $logFile ==="
    exit $planExitCode
}

Write-Log ""
Write-Log "=== Plan succeeded. Saved as tfplan in $TerraformDir. Run step2b_apply.ps1 to apply it. ==="
Write-Log "=== Done. Full log written to: $logFile ==="
