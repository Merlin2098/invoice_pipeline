#!/usr/bin/env python3
"""Diagnose why the static portal isn't loading via CloudFront.

Runs:
  1) aws s3 ls s3://<site-bucket>/ --recursive  (confirm uploaded objects)
  2) aws cloudfront get-distribution --id <dist-id>  (status + domain)
  3) HTTP GET on the portal URL and key assets (status codes + headers)

Logs combined output to logs/tf_step6_check_portal_access_<timestamp>.log.
"""

import datetime
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = REPO_ROOT / "logs"

SITE_BUCKET = "invoice-pipeline-dev-184670914470-site"
DISTRIBUTION_ID = "E3LVGD3FCD8X9B"
PORTAL_URL = "https://d2wqopeygpab2z.cloudfront.net"
REGION = "us-east-1"

PATHS_TO_CHECK = [
    "/",
    "/index.html",
    "/assets/index-Bf0yr0AG.js",
    "/assets/index-C7E2h8Lk.css",
]


def run(args, cwd=REPO_ROOT):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return result.stdout + result.stderr, result.returncode


def main():
    LOGS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"tf_step6_check_portal_access_{timestamp}.log"

    lines = []

    def log(msg=""):
        print(msg)
        lines.append(msg)

    log("Terraform Step 6: check portal access via CloudFront")
    log(f"Site bucket: {SITE_BUCKET}")
    log(f"Distribution ID: {DISTRIBUTION_ID}")
    log(f"Portal URL: {PORTAL_URL}")
    log(f"Timestamp: {datetime.datetime.now().isoformat()}")

    # 1) Bucket contents
    log("")
    log("=== aws s3 ls (recursive) ===")
    cmd = ["aws", "s3", "ls", f"s3://{SITE_BUCKET}/", "--recursive", "--region", REGION]
    log(f"Command: {' '.join(cmd)}")
    output, code = run(cmd)
    log(output.rstrip())
    log(f"Exit code: {code}")

    # 2) CloudFront distribution status
    log("")
    log("=== aws cloudfront get-distribution ===")
    cmd = [
        "aws", "cloudfront", "get-distribution",
        "--id", DISTRIBUTION_ID,
        "--query", "Distribution.{Status:Status,DomainName:DomainName,Enabled:DistributionConfig.Enabled}",
    ]
    log(f"Command: {' '.join(cmd)}")
    output, code = run(cmd)
    log(output.rstrip())
    log(f"Exit code: {code}")

    # 3) HTTP checks against the portal
    for path in PATHS_TO_CHECK:
        url = PORTAL_URL + path
        log("")
        log(f"=== GET {url} ===")
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.status
                headers = dict(resp.getheaders())
                body_len = len(resp.read())
            log(f"Status: {status}")
            log(f"Content-Type: {headers.get('Content-Type')}")
            log(f"Content-Length header: {headers.get('Content-Length')}")
            log(f"X-Cache: {headers.get('X-Cache')}")
            log(f"Body bytes read: {body_len}")
        except urllib.error.HTTPError as e:
            log(f"HTTPError: {e.code} {e.reason}")
            body = e.read().decode(errors="replace")
            log(f"Body (first 500 chars): {body[:500]}")
        except urllib.error.URLError as e:
            log(f"URLError: {e.reason}")
        except Exception as e:
            log(f"Unexpected error: {type(e).__name__}: {e}")

    log("")
    log(f"=== Done. Full log written to: {log_file} ===")

    log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
