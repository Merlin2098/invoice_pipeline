param(
    [int]$DocumentCount = 1,
    [Alias("PdfPaths")]
    [string[]]$DocumentPaths = @(),
    [Alias("PdfDataDir")]
    [string]$DocumentDataDir = "data/raw",
    [string]$TerraformDir = "infra/envs/dev",
    [int]$TimeoutSeconds = 900,
    [int]$PollIntervalSeconds = 15,
    [switch]$AllowFailedTerminalStatus
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

function Get-ApiJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri
    )

    return Invoke-RestMethod -Method Get -Uri $Uri -TimeoutSec 30
}

function Post-ApiJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [Parameter(Mandatory = $true)]
        [object]$Payload
    )

    $body = $Payload | ConvertTo-Json -Depth 10
    return Invoke-RestMethod -Method Post -Uri $Uri -ContentType "application/json" -Body $body -TimeoutSec 30
}

function Get-UploadContentType {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $extension = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
    if ($extension -eq ".pdf") {
        return "application/pdf"
    }
    if ($extension -in @(".tif", ".tiff")) {
        return "image/tiff"
    }
    throw "Unsupported upload fixture extension: $Path"
}

function Select-UploadDocuments {
    $explicitPaths = @($DocumentPaths)
    $dataDir = $DocumentDataDir
    $supportedExtensions = @(".pdf", ".tif", ".tiff")

    if ($explicitPaths.Count -gt 0) {
        $selected = @($explicitPaths | ForEach-Object {
            if (-not (Test-Path -LiteralPath $_ -PathType Leaf)) {
                throw "Upload fixture not found: $_. Pass a real PDF/TIF/TIFF path or omit explicit paths to auto-select from $dataDir."
            }
            Get-Item -LiteralPath $_
        })
    } else {
        $available = @(Get-ChildItem -Path $dataDir -File |
            Where-Object { $supportedExtensions -contains $_.Extension.ToLowerInvariant() })
        if ($available.Count -eq 0) {
            throw "No PDF/TIF/TIFF fixtures found in $dataDir. Add at least one invoice fixture, or run pre_ui_smoke_suite.ps1 with -SkipUploadApi."
        }
        $selected = @($available | Get-Random -Count $DocumentCount)
    }

    if ($selected.Count -lt $DocumentCount) {
        throw "Found $($selected.Count) supported document(s); expected $DocumentCount. Add PDF/TIF/TIFF files under $dataDir or pass explicit paths."
    }

    foreach ($document in $selected) {
        if ($supportedExtensions -notcontains $document.Extension.ToLowerInvariant()) {
            throw "Upload API smoke only accepts PDF/TIF/TIFF. Unsupported file: $($document.FullName)"
        }
        if ($document.Length -gt 20MB) {
            throw "Upload fixture exceeds 20 MB API limit: $($document.FullName)"
        }
    }
    return $selected
}

function Wait-ForInvoiceStatus {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,
        [Parameter(Mandatory = $true)]
        [string]$InvoiceId
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $terminal = @("Completed", "Failed")
    $lastStatus = $null

    while ((Get-Date) -lt $deadline) {
        try {
            $status = Get-ApiJson -Uri "$BaseUrl/invoices/$InvoiceId/status"
            $lastStatus = $status
            Write-Host "Invoice $InvoiceId status: $($status.status)"

            if ($terminal -contains $status.status) {
                return $status
            }
        } catch {
            Write-Host "Invoice $InvoiceId status not available yet."
        }

        Start-Sleep -Seconds $PollIntervalSeconds
    }

    throw "Timed out waiting for terminal status for invoice_id=$InvoiceId. Last status: $($lastStatus | ConvertTo-Json -Depth 5)"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$baseUrl = (Get-TerraformOutput "web_api_base_url").TrimEnd("/")
$documents = @(Select-UploadDocuments)

Write-Host "Web API: $baseUrl"
Write-Host "Selected upload documents:"
$documents | ForEach-Object { Write-Host " - $($_.Name) ($($_.Length) bytes)" }

$uploadRequest = @{
    files = @($documents | ForEach-Object {
        @{
            name = $_.Name
            content_type = Get-UploadContentType -Path $_.FullName
            size_bytes = $_.Length
        }
    })
}

$uploadResponse = Post-ApiJson -Uri "$baseUrl/uploads" -Payload $uploadRequest
if (-not $uploadResponse.run_id) {
    throw "Upload API response did not include run_id."
}
if (@($uploadResponse.uploads).Count -ne $documents.Count) {
    throw "Upload API returned $(@($uploadResponse.uploads).Count) upload URL(s); expected $($documents.Count)."
}

Write-Host "Upload run_id: $($uploadResponse.run_id)"

$uploads = @($uploadResponse.uploads)
for ($index = 0; $index -lt $uploads.Count; $index++) {
    $document = $documents[$index]
    $upload = $uploads[$index]
    Write-Host "Uploading via presigned URL: $($document.Name)"
    Invoke-WebRequest -Method Put -Uri $upload.upload_url -InFile $document.FullName -ContentType (Get-UploadContentType -Path $document.FullName) -TimeoutSec 300 | Out-Null
}

$statuses = @()
foreach ($document in $documents) {
    $invoiceId = [System.IO.Path]::GetFileNameWithoutExtension($document.Name)
    $status = Wait-ForInvoiceStatus -BaseUrl $baseUrl -InvoiceId $invoiceId
    if ($status.status -eq "Failed" -and -not $AllowFailedTerminalStatus) {
        throw "Invoice $invoiceId reached Failed status. Re-run with -AllowFailedTerminalStatus if this is expected for the fixture."
    }
    $statuses += $status
}

$history = Get-ApiJson -Uri "$baseUrl/invoices?limit=20"

$summary = [ordered]@{
    base_url = $baseUrl
    run_id = $uploadResponse.run_id
    uploaded_documents = @($documents | ForEach-Object { $_.Name })
    terminal_statuses = $statuses
    history_count = @($history.invoices).Count
}

Write-Host ""
Write-Host "Upload/status API smoke summary:"
$summary | ConvertTo-Json -Depth 8
