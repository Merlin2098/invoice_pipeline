# validate_run.ps1
# Uso: .\scripts\aws\validate_run.ps1 -RunId "smoke-40-20260512T123456"
# Si se omite RunId, detecta el ultimo run subido al bucket.

param(
    [string]$RunId = "",
    [int]$WaitSeconds = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# [0/8] Precheck runtime/IAM/event wiring
# ---------------------------------------------------------------------------
Write-Host "`n[0/8] Ejecutando precheck de smoke..." -ForegroundColor Cyan
& "$PSScriptRoot\smoke-precheck.ps1"

# ---------------------------------------------------------------------------
# Constantes del entorno (leidas desde Terraform outputs)
# ---------------------------------------------------------------------------
Write-Host "`n[1/8] Leyendo outputs de Terraform..." -ForegroundColor Cyan
Push-Location "infra/envs/dev"
$tf = terraform output -json | ConvertFrom-Json
Pop-Location

$LAKE_BUCKET = $tf.data_lake_bucket_name.value
$SF_ARN      = $tf.state_machine_arn.value
$QUEUE_URL   = $tf.raw_ingestion_queue_url.value
$DLQ_URL     = $tf.raw_ingestion_dlq_url.value

# ---------------------------------------------------------------------------
# Resolver RunId si no fue provisto
# ---------------------------------------------------------------------------
if (-not $RunId) {
    Write-Host "[auto] Detectando ultimo run en s3://$LAKE_BUCKET/raw/ ..." -ForegroundColor Yellow
    $listing = aws s3 ls "s3://$LAKE_BUCKET/raw/" --output text
    $RunId = ($listing -split "`n" |
        Where-Object { $_ -match "run_id=" } |
        ForEach-Object { ($_ -split "run_id=")[1].Trim().TrimEnd("/") } |
        Sort-Object -Descending |
        Select-Object -First 1)
}

if (-not $RunId) {
    Write-Error "No se pudo determinar el RunId. Provee -RunId explicitamente."
    exit 1
}

Write-Host "[run_id] $RunId" -ForegroundColor Green

# ---------------------------------------------------------------------------
# Crear carpeta de logs
# ---------------------------------------------------------------------------
$LOG_DIR = "logs/$RunId"
New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null
Write-Host "[logs]   $LOG_DIR"

# ---------------------------------------------------------------------------
# [2/8] Esperar a que el pipeline termine
# ---------------------------------------------------------------------------
Write-Host "`n[2/8] Esperando $WaitSeconds segundos para que Step Functions complete..." -ForegroundColor Cyan
Start-Sleep -Seconds $WaitSeconds

# ---------------------------------------------------------------------------
# [3/8] Estado de Step Functions
# ---------------------------------------------------------------------------
Write-Host "`n[3/8] Consultando Step Functions..." -ForegroundColor Cyan

function Get-SfnExecutionsByStatus {
    param([string]$Status)

    $json = aws stepfunctions list-executions `
        --state-machine-arn $SF_ARN `
        --status-filter $Status `
        --query "executions[].{name:name,start:startDate,arn:executionArn}" `
        --output json
    return @($json | ConvertFrom-Json)
}

$succeeded_list = Get-SfnExecutionsByStatus "SUCCEEDED"
$failed_list    = Get-SfnExecutionsByStatus "FAILED"
$running_list   = Get-SfnExecutionsByStatus "RUNNING"

$current_succeeded = @($succeeded_list | Where-Object { $_.name -like "*$RunId*" })
$current_failed    = @($failed_list | Where-Object { $_.name -like "*$RunId*" })
$current_running   = @($running_list | Where-Object { $_.name -like "*$RunId*" })

$summary = @"
run_id:    $RunId
succeeded_this_run: $($current_succeeded.Count)
failed_this_run:    $($current_failed.Count)
running_this_run:   $($current_running.Count)
total_succeeded_visible: $($succeeded_list.Count)
total_failed_visible:    $($failed_list.Count)
total_running_visible:   $($running_list.Count)
timestamp: $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')
"@
$summary | Tee-Object "$LOG_DIR/summary.txt"

# ---------------------------------------------------------------------------
# [4/8] Detalle de ejecuciones fallidas del run actual
# ---------------------------------------------------------------------------
Write-Host "`n[4/8] Recopilando fallos del run actual..." -ForegroundColor Cyan

$current_failed | ConvertTo-Json | Out-File "$LOG_DIR/failed_executions.json"

Write-Host "  Fallos del run actual: $($current_failed.Count)"

foreach ($exec in $current_failed) {
    $safe_name = $exec.name -replace "[^a-zA-Z0-9_-]", "_"
    aws stepfunctions describe-execution `
        --execution-arn $exec.arn `
        --query "{status:status,error:error,cause:cause,input:input}" `
        --output json | Out-File "$LOG_DIR/exec_$safe_name.json"
}

# Consolidar errores
if ($current_failed.Count -gt 0) {
    $errors = foreach ($exec in $current_failed) {
        $safe_name = $exec.name -replace "[^a-zA-Z0-9_-]", "_"
        $detail = Get-Content "$LOG_DIR/exec_$safe_name.json" | ConvertFrom-Json
        $cause_msg  = try { ($detail.cause | ConvertFrom-Json).errorMessage } catch { $detail.cause }
        $input_file = try { ($detail.input | ConvertFrom-Json).source_file_name } catch { $detail.input }
        [PSCustomObject]@{
            name  = $exec.name
            error = $detail.error
            cause = $cause_msg
            file  = $input_file
        }
    }
    $errors | ConvertTo-Json | Out-File "$LOG_DIR/errors_consolidated.json"
    $errors | Format-Table -AutoSize | Tee-Object "$LOG_DIR/errors_consolidated.txt"
} else {
    Write-Host "  Sin fallos en el run actual." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# [5/8] Conteo S3 por capa
# ---------------------------------------------------------------------------
Write-Host "`n[5/8] Contando objetos en S3..." -ForegroundColor Cyan

function Count-S3 ($uri) {
    $result = aws s3 ls $uri --recursive 2>$null
    if (-not $result) { return 0 }
    return ($result | Measure-Object -Line).Lines
}

$bronze    = Count-S3 "s3://$LAKE_BUCKET/bronze/textract-json/run_id=$RunId/"
$valid     = Count-S3 "s3://$LAKE_BUCKET/silver/valid/run_id=$RunId/"
$rejected  = Count-S3 "s3://$LAKE_BUCKET/silver/rejected/run_id=$RunId/"
$errors_s3 = (aws s3 ls "s3://$LAKE_BUCKET/errors/" --recursive 2>$null |
              Select-String $RunId | Measure-Object -Line).Lines

$s3_summary = @"
bronze:          $bronze
silver/valid:    $valid
silver/rejected: $rejected
errors/:         $errors_s3
total procesado: $($valid + $rejected + $errors_s3) / $(($valid + $rejected + $errors_s3 + $current_failed.Count))
"@
$s3_summary | Tee-Object "$LOG_DIR/s3_counts.txt"

# ---------------------------------------------------------------------------
# [6/8] Cola SQS y DLQ
# ---------------------------------------------------------------------------
Write-Host "`n[6/8] Estado de colas SQS..." -ForegroundColor Cyan

$queue_attrs = aws sqs get-queue-attributes `
    --queue-url $QUEUE_URL `
    --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible `
    --query "Attributes" --output json | ConvertFrom-Json

$dlq_count = aws sqs get-queue-attributes `
    --queue-url $DLQ_URL `
    --attribute-names ApproximateNumberOfMessages `
    --query "Attributes.ApproximateNumberOfMessages" --output text

$sqs_summary = @"
queue visible:     $($queue_attrs.ApproximateNumberOfMessages)
queue in-flight:   $($queue_attrs.ApproximateNumberOfMessagesNotVisible)
dlq messages:      $dlq_count
"@
$sqs_summary | Tee-Object "$LOG_DIR/sqs_status.txt"

if ([int]$dlq_count -gt 0) {
    Write-Host "  ATENCION: $dlq_count mensajes en DLQ" -ForegroundColor Red
} else {
    Write-Host "  DLQ vacia." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# [7/8] Logs CloudWatch (errores + idempotencia)
# ---------------------------------------------------------------------------
Write-Host "`n[7/8] Descargando logs CloudWatch..." -ForegroundColor Cyan
$start_ms = [DateTimeOffset]::UtcNow.AddMinutes(-30).ToUnixTimeMilliseconds()

$cw_groups = @{
    "lambda_process_document_errors"  = @{ group = "/aws/lambda/invoice-pipeline-dev-process-document"; filter = "`"ERROR`" `"$RunId`"" }
    "lambda_extract_ocr_errors"       = @{ group = "/aws/lambda/invoice-pipeline-dev-extract-ocr";       filter = "`"ERROR`" `"$RunId`"" }
    "lambda_enrich_llm_errors"        = @{ group = "/aws/lambda/invoice-pipeline-dev-enrich-llm";        filter = "`"ERROR`" `"$RunId`"" }
    "lambda_raw_dispatch_errors"      = @{ group = "/aws/lambda/invoice-pipeline-dev-raw-dispatch";      filter = "`"ERROR`" `"$RunId`"" }
    "lambda_validate_input_errors"    = @{ group = "/aws/lambda/invoice-pipeline-dev-validate-input";    filter = "`"ERROR`" `"$RunId`"" }
    "lambda_idempotency_skips"        = @{ group = "/aws/lambda/invoice-pipeline-dev-extract-ocr";       filter = "`"skipped`" `"$RunId`"" }
}

foreach ($key in $cw_groups.Keys) {
    $cfg = $cw_groups[$key]
    aws logs filter-log-events `
        --log-group-name $cfg.group `
        --start-time $start_ms `
        --filter-pattern $cfg.filter `
        --query "events[].message" `
        --output text 2>$null | Out-File "$LOG_DIR/$key.txt"
}

Write-Host "  Logs guardados."

# ---------------------------------------------------------------------------
# Resumen final
# ---------------------------------------------------------------------------
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " RESULTADO DEL RUN: $RunId" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " SUCCEEDED (este run): $($current_succeeded.Count)"
Write-Host " FAILED    (este run): $($current_failed.Count)"
Write-Host " RUNNING   (este run): $($current_running.Count)"
Write-Host " bronze:               $bronze"
Write-Host " silver/valid:         $valid"
Write-Host " silver/rejected:      $rejected"
Write-Host " errors/:              $errors_s3"
Write-Host " DLQ:                  $dlq_count mensajes"
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Archivos en $LOG_DIR :"
Get-ChildItem $LOG_DIR | Format-Table Name, Length, LastWriteTime
