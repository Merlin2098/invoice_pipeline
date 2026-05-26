# Diagnóstico Smoke Test 40 documentos — SQS Layer

**Fecha:** 2026-05-12
**Run analizado:** `smoke-40-20260512T003330`
**Runs previos del mismo ciclo:** `smoke-40-20260512T000216`, `smoke-40-20260512T002150`

---

## 1. Contexto

Tras desplegar la capa SQS (cola standard + DLQ + event source mapping + idempotency guard en `process_document`), se ejecutaron tres validaciones smoke consecutivas con 40 documentos TIF cada una. Las tres exhibieron el mismo patrón de fallo: **40/40 ejecuciones fallidas con `403 Forbidden` en `HeadObject`**, 0 documentos procesados en bronze/silver, y DLQ creciendo hasta 40 mensajes.

---

## 2. Métricas observadas (run más reciente)

| Métrica | Valor | Resultado esperado |
|---|---|---|
| Step Functions SUCCEEDED (acumulado) | 80 | — |
| Step Functions FAILED (este run) | 40/40 | 0 |
| Step Functions RUNNING | 0 | 0 |
| bronze/ | 0 objetos | ~40 |
| silver/valid/ | 0 objetos | mayoría de los 40 |
| silver/rejected/ | 0 objetos | algunos |
| errors/ | 0 objetos | 0 |
| SQS cola visible | 0 | 0 |
| SQS in-flight | 0 | 0 |
| **DLQ messages** | **40** | **0** |
| Logs idempotency skips | vacío | vacío (primer run) |

---

## 3. Causa raíz

### Síntoma
Stack trace idéntico en los 40 fallos:
```
[ERROR] ClientError: An error occurred (403) when calling the HeadObject operation: Forbidden
File "/var/task/src/aws/lambda_handlers/control_plane.py", line 288, in process_document
    _s3_check.head_object(Bucket=data_lake_bucket, Key=silver_valid_key)
```

### Hallazgo crítico
La verificación manual previa al run confirmó que el permiso IAM estaba correcto:

```powershell
aws s3api head-object --bucket invoice-pipeline-dev-184670914470-lake \
  --key "silver/valid/run_id=test-perm/nonexistent.json"
# → 404 Not Found  (✓ esperado)
```

Sin embargo, el Lambda en ejecución recibió **403 Forbidden** sobre el mismo bucket y prefijo. Esto indica que:

- El usuario CLI (con permisos administrativos) **sí** tiene `s3:GetObject` sobre `silver/valid/*`
- El rol del Lambda `invoice-pipeline-dev-process-document-role` **NO** tiene `s3:GetObject` sobre `silver/valid/*` aplicado en AWS, aunque el código Terraform sí lo declara en el statement `CheckSilverIdempotency` (línea 173-179 de `infra/envs/dev/main.tf`)

### Diagnóstico

El `terraform apply` completo no actualizó efectivamente la policy `data_lake_access` del rol `process_document_role`, o el Lambda mantiene cacheado un contexto de ejecución previo a la propagación del cambio IAM.

Las tres ejecuciones consecutivas con tres `RUN_ID` diferentes descartan que sea un problema de propagación temporal (>30 minutos desde el primer fallo).

---

## 4. Evidencia secundaria

- **DLQ = 40 mensajes**: el `ReportBatchItemFailures` con `maxReceiveCount=3` reenvió cada mensaje 3 veces antes de descartarlo. Esto confirma que el error es determinístico (no transitorio) y que la cola SQS funciona correctamente.
- **bronze/ = 0**: el Lambda muere en la línea 288 antes de invocar Textract. El guard de idempotencia es la primera operación I/O del handler.
- **Concurrencia controlada**: `max_concurrency=5` y `batch_size=1` funcionaron — no hubo throttling visible, los fallos son secuenciales y limpios.

---

## 5. Comportamiento correcto verificado

A pesar del fallo del guard de idempotencia, varios componentes nuevos sí funcionaron como se diseñó:

| Componente | Estado |
|---|---|
| SQS Standard queue | OK — recibe eventos S3 |
| SQS Queue Policy (s3 → SQS) | OK — sin errores de SendMessage |
| Event Source Mapping (SQS → Lambda) | OK — Lambda consume |
| `_unwrap_sqs_records` (Python) | OK — Step Functions reciben input válido |
| `validate_input` Lambda | OK — todas pasan la validación |
| Redrive policy → DLQ | OK — 40 mensajes después de 3 retries |
| Naming + tags (budget filter) | OK — recursos rastreables |

---

## 6. Recomendaciones

### Recomendación 1 — Forzar re-creación del rol IAM (alta prioridad)

Eliminar el rol del state y dejar que Terraform lo recree:

```powershell
terraform -chdir="infra/envs/dev" state rm "module.process_document_role.aws_iam_role.this"
terraform -chdir="infra/envs/dev" plan -out=tfplan-sqs
terraform -chdir="infra/envs/dev" apply tfplan-sqs
```

Tras el apply, validar **explícitamente** que la policy contiene los 4 statements:

```powershell
aws iam get-role-policy `
  --role-name "invoice-pipeline-dev-process-document-role" `
  --policy-name "data_lake_access" `
  --query "PolicyDocument.Statement[].Sid"
```

Resultado esperado:
```
["ReadRawObjects","ListRawPrefix","CheckSilverIdempotency","WritePipelineOutputs"]
```

### Recomendación 2 — Defensive coding en el idempotency guard (media prioridad)

S3 puede responder `403` cuando un objeto no existe **y** la política no incluye `s3:ListBucket` sobre el prefijo. En lugar de tratar solo `404`/`NoSuchKey` como "no existe", aceptar también `403` cuando no se tiene `ListBucket`:

```python
except _s3_check.exceptions.ClientError as exc:
    code = exc.response["Error"]["Code"]
    if code in ("404", "NoSuchKey"):
        pass  # no existe, procesa normal
    elif code == "403":
        logger.warning("HeadObject 403 — asumo 'no existe' y continúo")
        pass
    else:
        raise
```

Esto haría el guard resiliente a configuraciones IAM mínimas y reduciría el blast radius si la policy se desvía del código.

### Recomendación 3 — Purgar la DLQ antes del próximo test

Los 40 mensajes en DLQ ya no son procesables (los archivos siguen en `raw/` pero ya pasaron `maxReceiveCount`). Limpiar:

```powershell
aws sqs purge-queue --queue-url $DLQ_URL
```

### Recomendación 4 — Hook de validación previo a validaciones smoke

Antes de subir 40 archivos, ejecutar un check rápido contra una key inexistente con el rol del Lambda (no con el usuario CLI):

```powershell
aws lambda invoke `
  --function-name "invoice-pipeline-dev-process-document" `
  --payload '{"run_id":"perm-check","source_s3_key":"raw/perm-check/_.tif","source_file_name":"_.tif","created_at":"2026-05-12T00:00:00Z"}' `
  --cli-binary-format raw-in-base64-out `
  /tmp/lambda-out.json
```

Si el invoke devuelve 200 con `processing_status` definido, el rol está correcto. Si devuelve 403, no lanzar el smoke completo.

### Recomendación 5 — Reducir `maxReceiveCount` durante debugging

`maxReceiveCount = 3` con `visibility_timeout = 360s` significa que un mensaje tarda ~18 minutos en llegar a la DLQ. Durante debugging de problemas determinísticos, considerar bajar temporalmente a `maxReceiveCount = 1` para feedback inmediato.

---

## 7. Estado final tras las correcciones esperadas

Una vez aplicada la Recomendación 1 y verificada con `get-role-policy`:

- 40 documentos deberían generar 40 ejecuciones SUCCEEDED
- ~40 objetos en `bronze/textract-json/run_id=$RUN_ID/`
- Distribución variable entre `silver/valid/` y `silver/rejected/` según calidad del OCR
- DLQ = 0
- En un re-run del mismo `RUN_ID`, los 40 documentos deberían aparecer como `processing_status=skipped` en logs (`Skipping already-processed document`)

---

## 8. Lecciones aprendidas

1. **`terraform apply -target` no garantiza idempotencia** — los applies parciales pueden dejar el state inconsistente. Para cambios de IAM siempre usar apply completo.
2. **CLI ≠ Lambda role** — verificar permisos con la identidad del consumidor real, no del operador.
3. **DLQ como señal diagnóstica** — DLQ creciendo a la velocidad del input es indicador inequívoco de error determinístico (no de throttling ni race conditions).
4. **El guard de idempotencia es lateralmente crítico** — al ser la primera operación I/O, un fallo aquí mata todo el pipeline antes incluso de Textract. Hacerlo defensivo (Recomendación 2) protege contra desvíos IAM futuros.
