ifeq ($(OS),Windows_NT)
PYTHON ?= ./.venv/Scripts/python.exe
UV ?= py -3 -m uv
BOOTSTRAP_PYTHON ?= py -3
else
PYTHON ?= ./.venv/bin/python
UV ?= uv
BOOTSTRAP_PYTHON ?= python3
endif

.PHONY: init uv-init uv-update uv-reset package package-chat treemap lint fmt clean ai-refresh \
        bootstrap-init bootstrap-apply \
        tf-init tf-plan tf-apply

init:
	$(BOOTSTRAP_PYTHON) scripts/run_uv_sync.py init

uv-init:
	$(BOOTSTRAP_PYTHON) scripts/run_uv_sync.py init

uv-update:
	$(BOOTSTRAP_PYTHON) scripts/run_uv_sync.py update

uv-reset:
	$(BOOTSTRAP_PYTHON) scripts/run_uv_sync.py reset

package:
	uv run python scripts/package.py --package-manager uv

package-chat:
	uv run python scripts/package.py --package-manager uv --target chat

treemap:
	$(PYTHON) scripts/generate_treemap.py

lint:
	$(PYTHON) scripts/quality/run_ruff_check.py

fmt:
	$(PYTHON) scripts/quality/run_ruff_format.py

clean:
	uv run python scripts/package.py --package-manager uv --clean

ai-refresh:
	$(PYTHON) scripts/hooks/ai_refresh.py

bootstrap-init:
	terraform -chdir=infra/bootstrap init

bootstrap-apply:
	terraform -chdir=infra/bootstrap apply

tf-init:
	terraform -chdir=infra/envs/dev init

tf-plan:
	terraform -chdir=infra/envs/dev plan -var-file=terraform.tfvars -out=tfplan

tf-apply:
	terraform -chdir=infra/envs/dev apply tfplan
