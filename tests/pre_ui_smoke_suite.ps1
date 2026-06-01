param(
    [int]$DirectDocumentCount = 5,
    [int]$UploadDocumentCount = 1,
    [Alias("UploadPdfPaths")]
    [string[]]$UploadDocumentPaths = @(),
    [string[]]$ChatQuestions = @(
        "Cuantas facturas hay disponibles?",
        "Cual es el monto total de facturas por proveedor?",
        "Cuantas facturas hay por moneda?"
    ),
    [int]$TimeoutSeconds = 900,
    [switch]$SkipUploadApi,
    [switch]$SkipChatApi,
    [switch]$AllowFailedUploadTerminalStatus
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

Write-Host "Running pre-UI smoke suite..."
Write-Host ""

Write-Host "1/3 Direct AWS pipeline smoke"
& (Join-Path $PSScriptRoot "aws_e2e_smoke.ps1") `
    -DocumentCount $DirectDocumentCount `
    -TimeoutSeconds $TimeoutSeconds
if ($LASTEXITCODE -ne 0) {
    throw "Direct AWS pipeline smoke failed."
}

if (-not $SkipUploadApi) {
    Write-Host ""
    Write-Host "2/3 Upload/status API smoke"
    $uploadArgs = @{
        DocumentCount = $UploadDocumentCount
        TimeoutSeconds = $TimeoutSeconds
    }
    if ($UploadDocumentPaths.Count -gt 0) {
        $uploadArgs["DocumentPaths"] = $UploadDocumentPaths
    }
    if ($AllowFailedUploadTerminalStatus) {
        $uploadArgs["AllowFailedTerminalStatus"] = $true
    }
    & (Join-Path $PSScriptRoot "api_upload_status_smoke.ps1") @uploadArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Upload/status API smoke failed."
    }
} else {
    Write-Host "2/3 Upload/status API smoke skipped."
}

if (-not $SkipChatApi) {
    Write-Host ""
    Write-Host "3/3 Chat API smoke"
    & (Join-Path $PSScriptRoot "chat_api_smoke.ps1") -Questions $ChatQuestions
    if ($LASTEXITCODE -ne 0) {
        throw "Chat API smoke failed."
    }
} else {
    Write-Host "3/3 Chat API smoke skipped."
}

Write-Host ""
Write-Host "Pre-UI smoke suite completed."
