# validate-runtime-access.ps1
# Invokes each deployed Lambda with a dry-run payload so the runtime identity is checked.

param(
    [string]$TerraformDir = "infra/envs/dev"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location $TerraformDir
try {
    $tf = terraform output -json | ConvertFrom-Json
}
finally {
    Pop-Location
}

$functionOutputs = @(
    "raw_dispatch_lambda_name",
    "validate_input_lambda_name",
    "process_document_lambda_name",
    "publish_metrics_lambda_name"
)

foreach ($optionalOutput in @("extract_ocr_lambda_name", "enrich_llm_lambda_name")) {
    if ($tf.PSObject.Properties.Name.Contains($optionalOutput)) {
        $functionOutputs += $optionalOutput
    }
}

$payload = @{
    _dry_run = $true
    run_id = "runtime-precheck"
    execution_id = "runtime-precheck"
    source_s3_key = "raw/run_id=runtime-precheck/precheck.pdf"
    source_file_name = "precheck.pdf"
    created_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
} | ConvertTo-Json -Compress

$payloadFile = New-TemporaryFile
$responseFile = New-TemporaryFile
try {
    Set-Content -Path $payloadFile -Value $payload -Encoding UTF8

    foreach ($outputName in $functionOutputs) {
        $functionName = $tf.PSObject.Properties[$outputName].Value.value
        Write-Host "  invoking $functionName"
        aws lambda invoke `
            --function-name $functionName `
            --payload "fileb://$payloadFile" `
            --cli-binary-format raw-in-base64-out `
            $responseFile | Out-Null

        $response = Get-Content $responseFile -Raw | ConvertFrom-Json
        if (-not $response.dry_run) {
            throw "Lambda $functionName did not return a dry_run response"
        }
        if ($response.identity -and $response.identity.Arn) {
            Write-Host "    identity $($response.identity.Arn)"
        }
    }
}
finally {
    Remove-Item -LiteralPath $payloadFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $responseFile -Force -ErrorAction SilentlyContinue
}
