param(
    [string]$Region = "us-east-1",
    [string]$GlueDatabase = "invoice_pipeline_gold",
    [string]$AthenaWorkGroup = "invoice-pipeline-dev",
    [string]$TextractPolicyName = "invoice-pipeline-dev-textract"
)

$ErrorActionPreference = "Continue"

$repoRoot = Join-Path $PSScriptRoot "..\.."
$logsDir = Join-Path $repoRoot "logs"
if (-not (Test-Path -LiteralPath $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logsDir "tf_step2d_lookup_remaining_ids_$timestamp.log"

function Write-Log {
    param([string]$Message)
    Write-Host $Message
    Add-Content -LiteralPath $logFile -Value $Message
}

function Invoke-Lookup {
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
}

Write-Log "Terraform Step 2d: lookup remaining resource IDs for imports.tf"
Write-Log "Region: $Region"
Write-Log "Timestamp: $(Get-Date -Format o)"

# 1) Glue Catalog Tables
Invoke-Lookup -Title "Glue table: gold_documents" `
    -Arguments @("glue", "get-table", "--database-name", $GlueDatabase, "--name", "gold_documents", "--region", $Region)

Invoke-Lookup -Title "Glue table: gold_invoice_summary" `
    -Arguments @("glue", "get-table", "--database-name", $GlueDatabase, "--name", "gold_invoice_summary", "--region", $Region)

# 2) Athena WorkGroup
Invoke-Lookup -Title "Athena workgroup: $AthenaWorkGroup" `
    -Arguments @("athena", "get-work-group", "--work-group", $AthenaWorkGroup, "--region", $Region)

# 3) IAM Policy (Textract)
Invoke-Lookup -Title "IAM policy: $TextractPolicyName" `
    -Arguments @("iam", "list-policies", "--scope", "Local", "--query", "Policies[?PolicyName=='$TextractPolicyName']", "--region", $Region)

Write-Log ""
Write-Log "=== Done. Full log written to: $logFile ==="
