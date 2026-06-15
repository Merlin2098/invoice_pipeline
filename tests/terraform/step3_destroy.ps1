param(
    [string]$TerraformDir = "infra/envs/dev",
    [string]$VarFile = "terraform.tfvars",
    [switch]$Confirm
)

$ErrorActionPreference = "Continue"

$repoRoot = Join-Path $PSScriptRoot "..\.."
$logsDir = Join-Path $repoRoot "logs"
if (-not (Test-Path -LiteralPath $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logsDir "tf_step3_destroy_$timestamp.log"

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

Write-Log "Terraform Step 3: destroy"
Write-Log "Terraform dir: $TerraformDir"
Write-Log "Var file: $VarFile"
Write-Log "Confirm requested: $($Confirm.IsPresent)"
Write-Log "Timestamp: $(Get-Date -Format o)"

if (-not $Confirm.IsPresent) {
    Write-Log ""
    Write-Log "=== Destroy not confirmed. Running plan -destroy (dry run) only. ==="
    Write-Log "=== Pass -Confirm to run 'terraform destroy' for real. ==="

    Invoke-Step -Title "terraform plan -destroy (dry run)" `
        -Arguments @("-chdir=$TerraformDir", "plan", "-destroy", "-var-file=$VarFile")

    Write-Log ""
    Write-Log "=== Done. Full log written to: $logFile ==="
    exit 0
}

Invoke-Step -Title "terraform destroy" `
    -Arguments @("-chdir=$TerraformDir", "destroy", "-var-file=$VarFile", "-auto-approve")

Write-Log ""
Write-Log "=== Done. Full log written to: $logFile ==="
