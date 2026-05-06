# Spec Driven Development para Pipeline de Extracción de Facturas en AWS

## 1. Objetivo

Este documento define una estrategia de **Spec Driven Development** para evolucionar el MVP local de extracción de facturas hacia una arquitectura en AWS basada en contratos, reglas explícitas de calidad y validaciones por fase.

La meta es evitar migrar el pipeline como una simple sustitución de herramientas —por ejemplo, reemplazar Ollama por Bedrock— y construir una solución más robusta, trazable y medible.

El enfoque propuesto busca que cada etapa del pipeline tenga una especificación clara antes de implementar código o infraestructura.

---

## 2. Principio central

El pipeline no debe aceptar datos únicamente porque un modelo generó una respuesta válida en formato JSON.

Una fila solo debe avanzar si cumple reglas explícitas de contrato, calidad y trazabilidad.

```text
raw document
→ technical extraction
→ contract validation
→ business quality validation
→ accepted silver record
→ gold analytical model
```

---

## 3. Alcance del Spec Driven Development

El desarrollo estará guiado por especificaciones para:

1. Estructura esperada de documentos.
2. Metadatos técnicos por corrida.
3. Salida esperada de Textract.
4. Salida esperada de Bedrock.
5. Reglas de validación Bronze → Silver.
6. Reglas de aceptación y rechazo.
7. Métricas por corrida.
8. Criterios de aceptación del MVP AWS.

---

## 4. Estructura sugerida del repositorio

```text
project-root/
├── specs/
│   ├── contracts/
│   │   ├── bronze_textract.schema.yaml
│   │   ├── silver_document.schema.yaml
│   │   └── gold_documents.schema.yaml
│   ├── quality/
│   │   ├── bronze_to_silver_rules.yaml
│   │   └── gold_quality_rules.yaml
│   ├── prompts/
│   │   └── bedrock_normalization_prompt.md
│   ├── metrics/
│   │   └── pipeline_metrics.yaml
│   └── acceptance/
│       └── aws_mvp_acceptance_criteria.md
│
├── src/
│   ├── pipeline/
│   │   ├── bronze_to_silver.py
│   │   ├── silver_to_gold.py
│   │   └── run_pipeline.py
│   ├── services/
│   │   ├── textract_service.py
│   │   ├── bedrock_service.py
│   │   └── s3_service.py
│   ├── validation/
│   │   ├── contract_validator.py
│   │   ├── quality_validator.py
│   │   └── rules_engine.py
│   └── models/
│       └── document.py
│
├── infra/
│   ├── modules/
│   └── envs/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
└── docs/
    ├── adr/
    └── architecture/
```

---

## 5. Especificación de capas del pipeline

## 5.1 Raw

### Objetivo

Recibir documentos originales sin alteración.

### Ubicación AWS

```text
s3://<bucket>/raw/run_id=<run_id>/source_file
```

### Reglas

- No modificar el archivo original.
- Todo documento debe tener `run_id`.
- Todo documento debe tener `source_s3_key`.
- Todo documento debe tener `ingestion_timestamp`.
- Se deben aceptar únicamente formatos definidos.

### Formatos permitidos

```yaml
allowed_extensions:
  - .pdf
  - .png
  - .jpg
  - .jpeg
  - .tif
  - .tiff
```

---

## 5.2 Bronze

### Objetivo

Guardar la extracción técnica original generada por Textract.

### Ubicación AWS

```text
s3://<bucket>/bronze/textract-json/run_id=<run_id>/<document_id>.json
```

### Responsabilidad

Bronze no debe interpretar negocio. Solo debe conservar evidencia técnica de extracción.

### Campos mínimos esperados

```yaml
bronze_record:
  run_id: string
  document_id: string
  source_s3_key: string
  textract_job_id: string | null
  textract_response_s3_key: string
  extraction_engine: textract_analyze_expense
  extraction_timestamp: datetime
  status: success | failed
  error_message: string | null
```

---

## 5.3 Silver

### Objetivo

Convertir la extracción técnica en un documento estructurado, validado y listo para modelado.

### Ubicación AWS

```text
s3://<bucket>/silver/valid/run_id=<run_id>/<document_id>.json
s3://<bucket>/silver/rejected/run_id=<run_id>/<document_id>.json
```

### Responsabilidad

Silver debe contener datos interpretados, normalizados y validados.

### Contrato sugerido

```yaml
document:
  run_id: string
  document_id: string
  source_s3_key: string
  source_file_name: string

  document_type: string
  document_type_confidence: float

  vendor_name: string | null
  vendor_confidence: float | null

  document_date: date | null
  document_date_confidence: float | null

  total_amount: decimal | null
  total_amount_confidence: float | null

  currency: string | null
  currency_confidence: float | null

  extraction_engine: string
  normalization_engine: string | null
  llm_model_id: string | null

  quality_status: accepted | rejected | warning
  quality_score: float
  quality_flags: list[string]
  rejection_reason: string | null

  created_at: datetime
```

---

## 5.4 Gold

### Objetivo

Consolidar documentos válidos en formato analítico.

### Ubicación AWS

```text
s3://<bucket>/gold/documents/run_date=YYYY-MM-DD/documents.parquet
```

### Responsabilidad

Gold debe ser consumible por Athena, BI o análisis downstream.

### Reglas

- No debe contener documentos rechazados como válidos.
- Debe preservar `run_id` y `document_id`.
- Debe exponer `quality_status` y `quality_flags`.
- Debe permitir auditoría hacia raw, bronze y silver.

---

# 6. Reglas de Data Quality: Bronze → Silver

## 6.1 Reglas de estructura

```yaml
required_fields:
  - run_id
  - document_id
  - source_s3_key
  - source_file_name
  - extraction_engine
  - created_at
```

Si alguno de estos campos falta, el documento debe ir a:

```text
silver/rejected/
```

---

## 6.2 Reglas de aceptación mínima

Un documento puede avanzar a `silver/valid` si cumple al menos una condición fuerte:

```yaml
minimum_acceptance:
  require_at_least_one:
    - vendor_name
    - document_date
    - total_amount
```

Y además no debe tener errores críticos.

---

## 6.3 Reglas para fechas

```yaml
document_date_rules:
  allow_null: true
  min_year: 2000
  max_year: current_year
  reject_future_dates: true
  reject_invalid_calendar_dates: true
```

### Casos a rechazar

```text
2075-05-02
2074-09-29
2070-12-31
0703-04-02
```

### Acción recomendada

```yaml
on_invalid_date:
  status: rejected
  flag: invalid_document_date
  reason: document_date_out_of_allowed_range
```

---

## 6.4 Reglas para montos

```yaml
amount_rules:
  allow_null: true
  min_value: 0
  max_value: 1000000
  reject_negative_amounts: true
  reject_extreme_outliers: true
```

### Casos a marcar o rechazar

```text
total_amount = 1084432400.0
```

### Acción recomendada

```yaml
on_extreme_amount:
  status: rejected
  flag: amount_outlier
  reason: total_amount_exceeds_allowed_threshold
```

El valor máximo debe ser parametrizable por caso de negocio.

---

## 6.5 Reglas para moneda

```yaml
currency_rules:
  allow_null: true
  allowed_values:
    - PEN
    - USD
    - EUR
  infer_from_text: true
  default_if_missing: null
```

### Reglas adicionales

- Si el monto existe pero la moneda no, marcar `currency_missing`.
- No inventar moneda si no hay evidencia.
- Si hay símbolos ambiguos, enviar a Bedrock para resolución.

---

## 6.6 Reglas para vendor

```yaml
vendor_rules:
  allow_null: true
  min_length: 2
  reject_numeric_only: true
  normalize_whitespace: true
```

### Casos a marcar

```yaml
on_missing_vendor:
  status: warning
  flag: vendor_missing
```

El vendor faltante no siempre debe rechazar el documento si existen fecha y monto confiables.

---

## 6.7 Reglas para document_type

```yaml
document_type_rules:
  allowed_values:
    - invoice
    - receipt
    - contribution
    - credit_note
    - unknown
  allow_unknown: true
  max_unknown_rate_per_run: 0.20
```

### Acción por documento

```yaml
on_unknown_document_type:
  status: warning
  flag: unknown_document_type
```

### Acción por corrida

Si más del 20% cae en `unknown`, la corrida debe quedar con estado:

```text
completed_with_quality_warning
```

---

# 7. Especificación para uso de Bedrock

## 7.1 Cuándo usar Bedrock

Bedrock debe utilizarse solo cuando agregue valor semántico:

```yaml
use_bedrock_when:
  - multiple_vendor_candidates
  - ambiguous_date
  - conflicting_amounts
  - unknown_document_type
  - currency_ambiguous
```

## 7.2 Cuándo no usar Bedrock

```yaml
do_not_use_bedrock_for:
  - raw OCR
  - primary invoice total extraction if Textract already provides it
  - parsing simple deterministic fields
  - replacing business rules
```

---

## 7.3 Contrato de salida Bedrock

```yaml
bedrock_output:
  document_type: string
  vendor_name: string | null
  document_date: string | null
  total_amount: number | null
  currency: string | null
  confidence_summary:
    document_type: float
    vendor_name: float | null
    document_date: float | null
    total_amount: float | null
    currency: float | null
  reasoning_flags:
    - string
```

La salida debe validarse siempre. El modelo no es fuente de verdad final.

---

# 8. Estados del documento

Cada documento debe terminar en uno de estos estados:

```yaml
processing_status:
  - received
  - extracted
  - normalized
  - accepted
  - rejected
  - failed
```

## Definición

| Estado | Significado |
|---|---|
| received | Documento recibido en raw. |
| extracted | Textract generó salida técnica. |
| normalized | Se aplicó normalización determinística o LLM. |
| accepted | Pasó reglas de contrato y calidad. |
| rejected | Falló reglas de negocio o calidad. |
| failed | Error técnico de procesamiento. |

---

# 9. Métricas por corrida

Cada ejecución debe publicar métricas a CloudWatch o a un archivo de resumen.

```yaml
run_metrics:
  run_id: string
  documents_received: integer
  documents_processed: integer
  documents_accepted: integer
  documents_rejected: integer
  documents_failed: integer

  elapsed_seconds_total: number
  latency_p50_seconds: number
  latency_p95_seconds: number
  latency_max_seconds: number

  vendor_completion_rate: number
  date_completion_rate: number
  amount_completion_rate: number
  currency_completion_rate: number
  unknown_document_type_rate: number

  estimated_textract_cost: number
  estimated_bedrock_cost: number
  estimated_total_cost: number
```

---

# 10. Fases del MVP en AWS

## Fase 1: Cloud MVP controlado

### Objetivo

Probar la arquitectura mínima en AWS con una muestra pequeña.

### Alcance

```text
S3 + Step Functions + Textract + Lambda + Bedrock + CloudWatch
```

### Entregables

- Carga de documentos en S3 raw.
- Ejecución batch con Step Functions.
- Respuesta Textract guardada en bronze.
- Silver validado y separado entre `valid` y `rejected`.
- Gold parquet generado en S3.
- Métricas por corrida.

### Criterios de aceptación

```yaml
acceptance_criteria:
  documents_processed_rate: ">= 0.95"
  technical_failure_rate: "<= 0.05"
  gold_generated: true
  run_metrics_generated: true
  rejected_documents_have_reason: true
```

---

## Fase 2: Evaluación de calidad

### Objetivo

Comparar el MVP local contra AWS usando el mismo subconjunto de documentos.

### Dataset requerido

Crear un archivo esperado manualmente:

```text
tests/fixtures/expected_documents.csv
```

Con columnas:

```yaml
expected_columns:
  - source_file_name
  - expected_vendor_name
  - expected_document_date
  - expected_total_amount
  - expected_currency
  - expected_document_type
```

### Métricas de comparación

```yaml
quality_targets:
  vendor_completion_rate: ">= 0.85"
  date_completion_rate: ">= 0.85"
  amount_completion_rate: ">= 0.90"
  unknown_document_type_rate: "<= 0.20"
  critical_errors_in_gold: 0
```

---

## Fase 3: Endurecimiento operativo

### Objetivo

Preparar el pipeline para lotes mayores y reprocesamiento selectivo.

### Alcance

- Reintentos por documento.
- Alarmas de CloudWatch.
- Cost tracking por corrida.
- Reprocesamiento desde bronze o silver.
- SQS si el volumen lo justifica.
- Particionamiento de gold.

### Criterios de aceptación

```yaml
operational_acceptance:
  retry_by_document_enabled: true
  run_id_traceability_enabled: true
  cloudwatch_alarms_enabled: true
  cost_metric_enabled: true
  selective_reprocessing_enabled: true
```

---

# 11. Testing guiado por specs

## 11.1 Unit tests

Validan reglas individuales:

```text
tests/unit/test_date_rules.py
tests/unit/test_amount_rules.py
tests/unit/test_currency_rules.py
tests/unit/test_vendor_rules.py
```

## 11.2 Contract tests

Validan que JSONs cumplan schemas:

```text
tests/unit/test_silver_contract.py
tests/unit/test_bedrock_output_contract.py
```

## 11.3 Integration tests

Validan flujo completo con fixtures:

```text
tests/integration/test_bronze_to_silver_flow.py
tests/integration/test_silver_to_gold_flow.py
```

## 11.4 Regression tests

Validan que errores conocidos no vuelvan a aparecer:

```text
tests/regression/test_invalid_future_dates.py
tests/regression/test_extreme_amounts.py
tests/regression/test_unknown_document_type_rate.py
```

---

# 12. Definition of Done

Una fase del pipeline se considera lista solo si cumple:

```yaml
definition_of_done:
  - spec_created
  - schema_defined
  - quality_rules_defined
  - unit_tests_created
  - contract_tests_created
  - logs_include_run_id
  - errors_have_reason_code
  - metrics_are_generated
  - documentation_updated
```

---

# 13. ADRs recomendados

Crear ADRs para las siguientes decisiones:

```text
docs/adr/001-use-textract-for-primary-extraction.md
docs/adr/002-use-bedrock-only-for-normalization-and-ambiguity.md
docs/adr/003-separate-silver-valid-and-silver-rejected.md
docs/adr/004-use-step-functions-for-document-orchestration.md
docs/adr/005-use-spec-driven-development-for-quality-gates.md
```

---

# 14. Recomendación de implementación inicial

El primer entregable no debería ser infraestructura completa, sino los specs base:

```text
1. silver_document.schema.yaml
2. bronze_to_silver_rules.yaml
3. pipeline_metrics.yaml
4. aws_mvp_acceptance_criteria.md
5. bedrock_normalization_prompt.md
```

Una vez definidos estos archivos, Codex puede implementar el pipeline con menor ambigüedad y mayor control.

---

# 15. Resultado esperado

Con este enfoque, el proyecto pasa de ser un MVP experimental de extracción con IA a un sistema document intelligence gobernado por contratos:

```text
No se confía ciegamente en el modelo.
No se acepta JSON solo porque parsea.
No se manda todo a gold sin control.
Cada documento tiene estado, evidencia, reglas, métricas y trazabilidad.
```

Ese es el salto que convierte el pipeline en una arquitectura cloud defendible para un entorno real.

