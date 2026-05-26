```text
invoice_pipeline/
|-- .claude/
|   `-- settings.json
|-- artifacts/
|   `-- lambda/
|-- docs/
|   |-- cloud run/
|   |   |-- aws_pipeline_execution_results.md
|   |   |-- deployment_sequence.md
|   |   |-- lambda_bundle_generation.md
|   |   |-- lambda_code_update_fix.md
|   |   |-- post_bundle_deployment_steps.md
|   |   `-- smoke_test_40_diagnostico.md
|   |-- local run/
|   |   |-- aws_target_architecture.md
|   |   `-- mvp_local_ollama_hallazgos.md
|   |-- resources/
|   |   |-- architecture.dot
|   |   |-- architecture_diagram.png
|   |   |-- diagram.md
|   |   |-- invoice-pipeline-architecture.html
|   |   `-- overview.md
|   |-- windows_setup/
|   |   |-- make_cheatlist.md
|   |   |-- make_install.md
|   |   `-- uv_install.md
|   |-- terra_principles.md
|   |-- terraform_cheatsheet.md
|   `-- terraform_commands.md
|-- infra/
|   |-- env/
|   |-- envs/
|   |   `-- dev/
|   |       |-- .terraform.lock.hcl
|   |       |-- analytics.tf
|   |       |-- backend.tf.example
|   |       |-- budget.tf
|   |       |-- main.tf
|   |       |-- outputs.tf
|   |       |-- providers.tf
|   |       |-- README.md
|   |       |-- state_machine.asl.json
|   |       |-- terraform.tfvars.example
|   |       |-- variables.tf
|   |       `-- versions.lock.md
|   |-- modules/
|   |   |-- bedrock_permissions/
|   |   |   |-- main.tf
|   |   |   |-- outputs.tf
|   |   |   |-- README.md
|   |   |   `-- variables.tf
|   |   |-- cloudwatch_log_group/
|   |   |   |-- main.tf
|   |   |   |-- outputs.tf
|   |   |   |-- README.md
|   |   |   `-- variables.tf
|   |   |-- compute/
|   |   |   |-- main.tf
|   |   |   |-- outputs.tf
|   |   |   `-- variables.tf
|   |   |-- iam_role/
|   |   |   |-- main.tf
|   |   |   |-- outputs.tf
|   |   |   |-- README.md
|   |   |   `-- variables.tf
|   |   |-- lambda_function/
|   |   |   |-- main.tf
|   |   |   |-- outputs.tf
|   |   |   |-- README.md
|   |   |   `-- variables.tf
|   |   |-- observability/
|   |   |   |-- main.tf
|   |   |   `-- variables.tf
|   |   |-- orchestration/
|   |   |   |-- main.tf
|   |   |   |-- outputs.tf
|   |   |   |-- state_machine.asl.json
|   |   |   `-- variables.tf
|   |   |-- s3_bucket/
|   |   |   |-- main.tf
|   |   |   |-- outputs.tf
|   |   |   |-- README.md
|   |   |   `-- variables.tf
|   |   |-- s3_notification/
|   |   |   |-- main.tf
|   |   |   |-- outputs.tf
|   |   |   |-- README.md
|   |   |   `-- variables.tf
|   |   |-- sqs_queue/
|   |   |   |-- main.tf
|   |   |   |-- outputs.tf
|   |   |   `-- variables.tf
|   |   |-- step_function/
|   |   |   |-- main.tf
|   |   |   |-- outputs.tf
|   |   |   |-- README.md
|   |   |   `-- variables.tf
|   |   |-- storage/
|   |   |   |-- main.tf
|   |   |   |-- outputs.tf
|   |   |   `-- variables.tf
|   |   `-- textract_permissions/
|   |       |-- main.tf
|   |       |-- outputs.tf
|   |       |-- README.md
|   |       `-- variables.tf
|   |-- .terraform.lock.hcl
|   |-- main.tf
|   |-- outputs.tf
|   |-- providers.tf
|   |-- terraform.tfvars.example
|   `-- variables.tf
|-- scripts/
|   |-- hooks/
|   |   |-- ai_refresh.py
|   |   `-- sync_dependencies.py
|   |-- quality/
|   |   |-- run_ruff_check.py
|   |   `-- run_ruff_format.py
|   |-- windows/
|   |   |-- run_make.ps1
|   |   |-- setup_env.ps1
|   |   `-- update_venv.ps1
|   |-- generate_treemap.py
|   |-- package.py
|   |-- run_pip_init.py
|   |-- run_uv_sync.py
|   `-- stress_pipeline.py
|-- specs/
|   |-- acceptance/
|   |   `-- aws_mvp_acceptance_criteria.md
|   |-- contracts/
|   |   |-- bronze_textract.schema.yaml
|   |   |-- gold_documents.schema.yaml
|   |   `-- silver_document.schema.yaml
|   |-- metrics/
|   |   `-- pipeline_metrics.yaml
|   |-- prompts/
|   |   |-- bedrock_analytics_sql_prompt.md
|   |   |-- bedrock_normalization_prompt.md
|   |   |-- ejecutar_hoy.md
|   |   `-- implementation_plan_spec004_005_006.md
|   |-- quality/
|   |   |-- bronze_to_silver_rules.yaml
|   |   `-- gold_quality_rules.yaml
|   |-- SPEC-004-runtime-iam-validation.md
|   |-- SPEC-005-structured-logging.md
|   |-- SPEC-006-ocr-llm-separation.md
|   |-- SPEC-007-terraform-remote-state.md
|   `-- SPEC-008-analythic-layer.md
|-- src/
|   |-- analytics/
|   |   |-- __init__.py
|   |   |-- athena_client.py
|   |   |-- bedrock_sql.py
|   |   |-- cli.py
|   |   |-- schema_registry.py
|   |   `-- sql_validator.py
|   |-- aws/
|   |   |-- glue_jobs/
|   |   |   |-- __init__.py
|   |   |   |-- consolidate_gold.py
|   |   |   `-- normalize_documents.py
|   |   |-- lambda_handlers/
|   |   |   |-- __init__.py
|   |   |   `-- control_plane.py
|   |   |-- __init__.py
|   |   |-- bedrock_client.py
|   |   `-- logging_utils.py
|   |-- config/
|   |   |-- __init__.py
|   |   |-- data_contract.yaml
|   |   |-- pipeline.yaml
|   |   `-- pipeline_config.py
|   |-- jobs/
|   |   |-- contracts/
|   |   |   `-- orders_curated.yaml
|   |   |-- sql/
|   |   |   `-- orders_curated.sql
|   |   |-- __init__.py
|   |   |-- example_job.py
|   |   `-- example_job_config.yaml
|   |-- pipeline/
|   |   |-- __init__.py
|   |   |-- aws_runtime.py
|   |   |-- bronze_pipeline.py
|   |   |-- gold_model.py
|   |   |-- llm_ollama.py
|   |   |-- ocr.py
|   |   |-- postprocess.py
|   |   |-- quality.py
|   |   |-- run_context.py
|   |   |-- silver_pipeline.py
|   |   `-- specs.py
|   |-- services/
|   |   |-- __init__.py
|   |   |-- llm_service.py
|   |   `-- ocr_service.py
|   |-- utils/
|   |   |-- __init__.py
|   |   `-- logging.py
|   `-- __init__.py
|-- .gitattributes
|-- .pre-commit-config.yaml
|-- .template-profile
|-- AGENTS.md
|-- CLAUDE.md
|-- LICENSE
|-- Makefile
|-- pyproject.toml
|-- README.md
|-- requirements.lambda.txt
|-- run_pipeline.py
`-- uv.lock
```
