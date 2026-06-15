#!/usr/bin/env python3
"""Diagnose the AccessDenied error on the CloudFront/S3 static site.

Runs:
  1) aws s3 ls s3://<site-bucket>/ --recursive
  2) aws s3api get-bucket-policy --bucket <site-bucket>
  3) terraform -chdir=infra/envs/dev state list | grep site_bucket_policy

Logs combined output to logs/tf_step5_check_site_bucket_<timestamp>.log.
"""

import datetime
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = REPO_ROOT / "logs"

TERRAFORM_DIR = "infra/envs/dev"
SITE_BUCKET = "invoice-pipeline-dev-184670914470-site"
REGION = "us-east-1"


def run(args, cwd=REPO_ROOT):
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    return output, result.returncode


def main():
    LOGS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"tf_step5_check_site_bucket_{timestamp}.log"

    lines = []

    def log(msg=""):
        print(msg)
        lines.append(msg)

    log("Terraform Step 5: check site bucket contents, policy, and state")
    log(f"Site bucket: {SITE_BUCKET}")
    log(f"Terraform dir: {TERRAFORM_DIR}")
    log(f"Timestamp: {datetime.datetime.now().isoformat()}")

    # 1) Bucket contents
    log("")
    log("=== aws s3 ls (recursive) ===")
    cmd = ["aws", "s3", "ls", f"s3://{SITE_BUCKET}/", "--recursive", "--region", REGION]
    log(f"Command: {' '.join(cmd)}")
    output, code = run(cmd)
    log(output.rstrip())
    log(f"Exit code: {code}")

    # 2) Bucket policy
    log("")
    log("=== aws s3api get-bucket-policy ===")
    cmd = ["aws", "s3api", "get-bucket-policy", "--bucket", SITE_BUCKET, "--region", REGION]
    log(f"Command: {' '.join(cmd)}")
    output, code = run(cmd)
    log(output.rstrip())
    log(f"Exit code: {code}")

    # 3) Terraform state list, filtered to site bucket policy resources
    log("")
    log("=== terraform state list (filtered: site) ===")
    cmd = ["terraform", f"-chdir={TERRAFORM_DIR}", "state", "list"]
    log(f"Command: {' '.join(cmd)}")
    output, code = run(cmd)
    filtered = [line for line in output.splitlines() if "site" in line.lower()]
    log("\n".join(filtered) if filtered else "(no matching resources found)")
    log(f"Exit code: {code}")

    log("")
    log(f"=== Done. Full log written to: {log_file} ===")

    log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
