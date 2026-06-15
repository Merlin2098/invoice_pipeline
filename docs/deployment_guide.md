# Deployment Guide — `dev` Environment

This guide is the single end-to-end checklist for standing up (or updating)
the `invoice-pipeline-dev` AWS environment: Terraform infrastructure, Lambda
artifacts, and the static web portal. `terraform apply` alone is **not**
enough — Lambda zips must be packaged and uploaded to S3 before `apply`, and
the frontend must be built with the correct API URL and synced to S3 +
CloudFront after `apply`.

> Do not run `terraform apply` / `terraform destroy` without explicit
> approval, per [AGENTS.md](../AGENTS.md).

## 1. Prerequisites

- AWS credentials configured for account `184670914470`, region
  `us-east-1`.
- Terraform, `uv`, Node/npm, and `make` available. On Windows without
  `make.exe` in `PATH`, see
  [docs/windows_setup/make_cheatlist.md](windows_setup/make_cheatlist.md).
- `infra/envs/dev/terraform.tfvars` exists and is filled in (copy from
  [infra/envs/dev/terraform.tfvars.example](../infra/envs/dev/terraform.tfvars.example)
  if missing). This file is gitignored — it must be created locally.

## 2. Bootstrap (one-time only)

Only needed if the Terraform S3 backend (`infra/bootstrap`) doesn't exist
yet for this account/region:

```bash
make bootstrap-init
make bootstrap-apply   # requires approval
```

## 3. First Terraform apply — initial infrastructure

Every Lambda module in
[infra/envs/dev/main.tf](../infra/envs/dev/main.tf) sets:

```hcl
source_code_hash = filebase64sha256("${path.root}/../../../artifacts/lambda/control_plane_bundle.zip")
```

Terraform reads this **local file** at plan time, so the zip must exist on
disk before any plan/apply. Separately, `s3_bucket`/`s3_key` point at the
artifact bucket (`invoice-pipeline-dev-184670914470-artifacts` — deterministic
from `${name_prefix}-${account_id}-${artifact_bucket_suffix}`), which doesn't
exist until Terraform creates it. On a from-scratch environment this is a
two-pass bootstrap:

```bash
# a) Init
make tf-init

# b) Build Lambda zips locally (required for source_code_hash to resolve)
make package
make package-chat

# c) First apply — creates the artifact bucket and most other infra.
#    aws_lambda_function resources WILL FAIL here because the S3 keys
#    don't exist in the bucket yet. This is expected for Lambda
#    resources only — buckets, IAM, Step Functions, API Gateway, and
#    CloudFront should apply successfully.
make tf-plan      # review the plan
make tf-apply     # requires approval

# d) Upload the zips now that the artifact bucket exists
aws s3 cp artifacts/lambda/control_plane_bundle.zip \
  s3://invoice-pipeline-dev-184670914470-artifacts/artifacts/lambda/control_plane_bundle.zip
aws s3 cp artifacts/lambda/chat_bundle.zip \
  s3://invoice-pipeline-dev-184670914470-artifacts/artifacts/lambda/chat_bundle.zip

# e) Second apply — Lambda functions (and everything depending on them:
#    Step Functions, API Gateway integrations, CloudFront) now create
#    successfully against the present S3 objects.
make tf-plan
make tf-apply     # requires approval
```

Confirm the artifact bucket name with:

```bash
terraform -chdir=infra/envs/dev output -raw artifact_bucket_name
```

If the artifact bucket **already exists** (e.g. re-running this guide
against an existing `dev` environment), steps (c)+(d) collapse: just run
(b), upload the zips, then a single `make tf-plan` / `make tf-apply`.

## 4. Frontend configuration and deploy

This is the step that caused both portal bugs fixed in this session — a
stale `frontend/.env.local` pointed at an old API Gateway ID, and the
upload `Content-Type` for `.tif`/`.tiff` files didn't match what was signed.

1. Get the live API base URL:

   ```bash
   terraform -chdir=infra/envs/dev output -raw web_api_base_url
   ```

2. Create or update `frontend/.env.local`:

   ```
   VITE_API_BASE_URL=<value from step 1, including trailing slash>
   ```

   **This file is gitignored and must be regenerated any time the API
   Gateway is recreated (new ID).** A stale value here is the most likely
   cause of "upload and chat fail only from the web portal" symptoms.

3. Install dependencies (first time, or after `package.json` changes):

   ```bash
   make frontend-install
   ```

4. Build:

   ```bash
   make build-frontend
   ```

5. Get the site bucket and CloudFront distribution ID:

   ```bash
   terraform -chdir=infra/envs/dev output -raw site_bucket_name
   terraform -chdir=infra/envs/dev output -raw cloudfront_distribution_id
   ```

6. Deploy:

   ```bash
   make deploy-frontend SITE_BUCKET=<bucket> CF_DIST_ID=<dist_id>
   ```

## 5. Verification

Read-only Python scripts under `tests/terraform/` (see each script's
docstring for options):

- `python tests/terraform/step6_check_portal_access.py` — confirms site
  bucket contents and CloudFront returns 200 for the portal and key assets.
  Note: this script has some asset filenames/bucket/distribution IDs
  hardcoded and may need updating after a fresh deploy with new asset
  hashes.
- `python tests/terraform/step7_test_raw_uploads.py` — end-to-end upload of
  a `data/raw` file via presigned URLs, polling invoice status to
  `Completed`.
- `python tests/terraform/step8_browser_upload_repro.py` — reproduces the
  browser's upload flow (same `Content-Type` logic, `Origin` header) with
  full HTTP error capture.
- `python tests/terraform/step9_test_chat_nlq.py` — sends natural-language
  questions to `POST /chat` and logs the generated SQL, rows, and answer.

After any frontend deploy, do a **hard refresh** (Ctrl+Shift+R) or open the
portal in an incognito window — CloudFront invalidation can take a minute,
and browsers cache the old JS bundle aggressively.

## 6. Subsequent updates

- **Backend code change** (`src/`): `make package` (and `make package-chat`
  if `src/analytics` or `src/aws` changed) → upload the changed zip(s) to
  the artifact bucket (same `aws s3 cp` commands as step 3d) → `make tf-plan`
  → `make tf-apply` (requires approval). The updated `source_code_hash`
  (computed from the local zip) is what tells Terraform the Lambda code
  changed — both the local rebuild and the S3 upload are required.
- **Frontend-only change**: `make build-frontend` → `make deploy-frontend
  SITE_BUCKET=... CF_DIST_ID=...`. No Terraform needed unless
  `VITE_API_BASE_URL` changed.
- **Infra change**: standard `make tf-plan` → `make tf-apply` (requires
  approval). If the API Gateway was replaced (new `web_api_base_url`),
  redo step 4 (update `.env.local`, rebuild, redeploy the frontend).

## 7. Teardown

See [docs/destruction_guide.md](destruction_guide.md) for the full safe
teardown checklist (what gets deleted, backup steps, dry run via
`tests/terraform/step3_destroy.ps1`, and post-destroy verification).
`terraform destroy` requires the same explicit approval as `apply`, per
[AGENTS.md](../AGENTS.md).
