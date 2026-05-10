# Lambda Bundle Generation

## Purpose
This guide explains how to generate the deployment bundle used by the AWS Lambda functions in this repository.

## Output artifact
The packaging script generates this file:

```text
artifacts/lambda/control_plane_bundle.zip
```

## Recommended command
Run this from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\package.py --package-manager uv
```

## What the command does
- packages the `src/` directory
- packages the `specs/` directory
- vendors runtime modules required by the Lambda bundle
- writes a `requirements.txt` into the zip
- creates or replaces `artifacts/lambda/control_plane_bundle.zip`

## Prerequisites
- the virtual environment must exist at `.venv`
- project dependencies must already be installed
- `uv.lock` and `pyproject.toml` must be present if using `--package-manager uv`

## Verify that the bundle was created
After running the command, confirm that the zip exists:

```powershell
Get-Item artifacts\lambda\control_plane_bundle.zip
```

## Remove the generated bundle
If you need to delete the generated artifact and build it again:

```powershell
.\.venv\Scripts\python.exe scripts\package.py --clean
```

## Typical next step
After generating the bundle, upload it to the artifact bucket expected by Terraform:

```powershell
aws s3 cp artifacts/lambda/control_plane_bundle.zip s3://<artifact-bucket>/artifacts/lambda/control_plane_bundle.zip
```
