param(
    [string[]]$Questions = @(
        "Cuantas facturas hay disponibles?",
        "Cual es el monto total de facturas por proveedor?",
        "Cuantas facturas hay por moneda?"
    ),
    [string]$TerraformDir = "infra/envs/dev",
    [int]$TimeoutSeconds = 90,
    [int]$MaxAverageLatencySeconds = 10
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

function Post-ChatQuestion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,
        [Parameter(Mandatory = $true)]
        [string]$Question
    )

    $payload = @{ question = $Question } | ConvertTo-Json -Depth 5
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $response = Invoke-RestMethod `
        -Method Post `
        -Uri "$BaseUrl/chat" `
        -ContentType "application/json" `
        -Body $payload `
        -TimeoutSec $TimeoutSeconds
    $timer.Stop()

    if (-not $response.answer) {
        throw "Chat response is missing answer."
    }
    if (-not $response.generated_sql) {
        throw "Chat response is missing generated_sql."
    }
    if (-not $response.query_id) {
        throw "Chat response is missing query_id."
    }

    return [pscustomobject][ordered]@{
        question = $Question
        answer = $response.answer
        generated_sql = $response.generated_sql
        query_id = $response.query_id
        execution_time_ms = $response.execution_time_ms
        athena_scan_mb = $response.athena_scan_mb
        row_count = @($response.rows).Count
        wall_clock_ms = [int64]$timer.ElapsedMilliseconds
    }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$baseUrl = (Get-TerraformOutput "web_api_base_url").TrimEnd("/")
Write-Host "Web API: $baseUrl"

$results = @()
foreach ($question in $Questions) {
    Write-Host "Asking: $question"
    $results += Post-ChatQuestion -BaseUrl $baseUrl -Question $question
}

$wallClockMeasurements = @(
    foreach ($result in $results) {
        if ($result -is [System.Collections.IDictionary]) {
            [int64]$result["wall_clock_ms"]
        }
        else {
            [int64]$result.wall_clock_ms
        }
    }
)
$averageLatencyMs = [math]::Round((($wallClockMeasurements | Measure-Object -Average).Average), 0)
$maxAverageLatencyMs = $MaxAverageLatencySeconds * 1000

$summary = [ordered]@{
    base_url = $baseUrl
    question_count = $results.Count
    average_wall_clock_ms = $averageLatencyMs
    max_average_latency_seconds = $MaxAverageLatencySeconds
    results = $results
}

Write-Host ""
Write-Host "Chat API smoke summary:"
$summary | ConvertTo-Json -Depth 8

if ($averageLatencyMs -gt $maxAverageLatencyMs) {
    Write-Warning "Average chat latency exceeded $MaxAverageLatencySeconds seconds. This is a Phase 5 readiness risk, not necessarily a functional failure."
}
