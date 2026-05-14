# Rollback Runbook

This runbook covers the SPEC-004, SPEC-005, and SPEC-006 migration.

## Phase 0 Baseline

- Baseline Git SHA: `2a3f984`
- Baseline Lambda bundle SHA256: see `infra/envs/dev/versions.lock.md`
- Baseline ASL template snapshot: `docs/snapshots/state_machine.2a3f984.asl.json`

The checked-in snapshot is the local Terraform template with placeholders. Before
the ASL flip, capture the deployed definition with:

```powershell
aws stepfunctions describe-state-machine `
  --state-machine-arn <state-machine-arn> `
  --query definition `
  --output text > docs/snapshots/state_machine.2a3f984.deployed.asl.json
```

## SPEC-004

Runtime IAM validation is script-only. To roll back, revert the scripts under
`tests/aws/` and the `smoke-precheck.ps1` call in `validate_run.ps1`.

## SPEC-005

Revert the Lambda bundle to the baseline SHA and deploy the prior ASL definition
if structured logging or `execution_id` propagation causes unexpected behavior.
Terraform changes only manage log retention and do not mutate data.

## SPEC-006

The legacy `process_document` Lambda remains deployed during the OCR/LLM split.
To return traffic to the legacy path, update the Step Functions state machine
with the deployed baseline snapshot captured before the ASL flip:

```powershell
aws stepfunctions update-state-machine `
  --state-machine-arn <state-machine-arn> `
  --definition file://docs/snapshots/state_machine.2a3f984.deployed.asl.json
```

Run `tests/aws/validate_run.ps1` after rollback to confirm SQS, DLQ, Step
Functions, and S3 layer counts.

## Notes

`infra/modules/orchestration/state_machine.asl.json` was not deleted because the
root `infra/main.tf` still references the legacy orchestration module. Removing
that file should wait for a separate cleanup that either removes or rewires the
root module.
