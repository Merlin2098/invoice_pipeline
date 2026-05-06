```text
invoice_pipeline/
|-- docs/
|   |-- modelos.png
|   `-- sistema.png
|-- infra/
|   |-- env/
|   |-- main.tf
|   |-- outputs.tf
|   |-- providers.tf
|   |-- terraform.tfvars.example
|   `-- variables.tf
|-- scripts/
|   |-- hooks/
|   |   |-- ai_refresh.py
|   |   `-- sync_dependencies.py
|   |-- testing/
|   |   |-- run_pytest.py
|   |   |-- run_ruff_check.py
|   |   `-- run_ruff_format.py
|   |-- windows/
|   |   |-- run_make.ps1
|   |   |-- setup_env.ps1
|   |   `-- update_venv.ps1
|   |-- generate_treemap.py
|   |-- package.py
|   |-- run_pip_init.py
|   `-- run_uv_sync.py
|-- src/
|   |-- config/
|   |   |-- __init__.py
|   |   |-- data_contract.yaml
|   |   |-- pipeline.yaml
|   |   `-- pipeline_config.py
|   |-- pipeline/
|   |   |-- __init__.py
|   |   |-- bronze_pipeline.py
|   |   |-- gold_model.py
|   |   |-- llm_ollama.py
|   |   |-- ocr.py
|   |   |-- postprocess.py
|   |   `-- silver_pipeline.py
|   |-- services/
|   |   |-- __init__.py
|   |   |-- llm_service.py
|   |   `-- ocr_service.py
|   |-- utils/
|   |   |-- __init__.py
|   |   `-- logging.py
|   `-- __init__.py
|-- tests/
|   |-- test_document_pipeline.py
|   |-- test_example_job.py
|   `-- test_olama.py
|-- .gitattributes
|-- .pre-commit-config.yaml
|-- .template-profile
|-- AGENTS.md
|-- Makefile
|-- pyproject.toml
|-- run_pipeline.py
`-- uv.lock
```
