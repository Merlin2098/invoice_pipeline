$ErrorActionPreference = "Continue"

$logsDir = Join-Path $PSScriptRoot "..\logs"
if (-not (Test-Path -LiteralPath $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logsDir "terraform_cli_env_check_$timestamp.log"

function Write-Log {
    param([string]$Message)
    Write-Host $Message
    Add-Content -LiteralPath $logFile -Value $Message
}

function Invoke-Check {
    param(
        [string]$Title,
        [scriptblock]$Action
    )

    Write-Log ""
    Write-Log "=== $Title ==="

    try {
        $output = & $Action 2>&1
        if ($null -eq $output -or $output.Count -eq 0) {
            Write-Log "(no output)"
        } else {
            $output | ForEach-Object { Write-Log $_.ToString() }
        }
    } catch {
        Write-Log "ERROR: $($_.Exception.Message)"
    }
}

Write-Log "Terraform CLI environment check"
Write-Log "Timestamp: $(Get-Date -Format o)"

Invoke-Check -Title "Get-Command terraform" -Action {
    Get-Command terraform -All | Format-List Name, CommandType, Source, Definition
}

Invoke-Check -Title "Get-Alias terraform" -Action {
    Get-Alias terraform -ErrorAction SilentlyContinue
}

Invoke-Check -Title "TF_* environment variables" -Action {
    Get-ChildItem Env: | Where-Object Name -like "TF_*"
}

Invoke-Check -Title "PowerShell profile path and existence" -Action {
    "Profile path: $PROFILE"
    "Exists: $(Test-Path $PROFILE)"
}

Invoke-Check -Title "PowerShell profile content referencing terraform" -Action {
    if (Test-Path $PROFILE) {
        Select-String -Path $PROFILE -Pattern "terraform" -ErrorAction SilentlyContinue
    } else {
        "Profile file does not exist."
    }
}

Invoke-Check -Title "terraform -chdir version (sanity check)" -Action {
    & terraform -chdir=infra/envs/dev version
    "Exit code: $LASTEXITCODE"
}

Write-Log ""
Write-Log "=== Done. Full log written to: $logFile ==="
