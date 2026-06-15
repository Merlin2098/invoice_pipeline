#!/usr/bin/env python3
"""Test uploading document(s) from data/raw via the web API's presigned-URL flow.

Flow:
  1) terraform output -raw web_api_base_url
  2) POST {base_url}/uploads with file metadata -> presigned PUT URLs
  3) PUT each selected file to its presigned URL
  4) Poll GET {base_url}/invoices/{invoice_id}/status until terminal

Logs combined output to logs/tf_step7_test_raw_uploads_<timestamp>.log.

Usage:
  python tests/terraform/step7_test_raw_uploads.py [--count N] [--files path1 path2 ...]
                                                     [--timeout SECONDS] [--poll-interval SECONDS]
"""

import argparse
import datetime
import json
import mimetypes
import random
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = REPO_ROOT / "logs"
DATA_RAW_DIR = REPO_ROOT / "data" / "raw"
TERRAFORM_DIR = "infra/envs/dev"

SUPPORTED_EXTENSIONS = {".pdf", ".tif", ".tiff"}
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}
MAX_SIZE_BYTES = 20 * 1024 * 1024
TERMINAL_STATUSES = {"Completed", "Failed"}


def run(args, cwd=REPO_ROOT):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return (result.stdout + result.stderr).strip(), result.returncode


def http_json(method, url, payload=None, timeout=30):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        return resp.status, json.loads(body) if body else None


def http_put_file(url, file_path, content_type, timeout=300):
    data = file_path.read_bytes()
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Content-Type", content_type)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1, help="Number of files to randomly select from data/raw")
    parser.add_argument("--files", nargs="*", default=None, help="Explicit file paths to upload (overrides --count)")
    parser.add_argument("--timeout", type=int, default=900, help="Seconds to wait for terminal status per invoice")
    parser.add_argument("--poll-interval", type=int, default=15, help="Seconds between status polls")
    args = parser.parse_args()

    LOGS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"tf_step7_test_raw_uploads_{timestamp}.log"

    lines = []

    def log(msg=""):
        print(msg)
        lines.append(str(msg))

    log("Terraform Step 7: test data/raw upload via web API presigned URLs")
    log(f"Data dir: {DATA_RAW_DIR}")
    log(f"Timestamp: {datetime.datetime.now().isoformat()}")

    # 1) Resolve base URL
    log("")
    log("=== terraform output web_api_base_url ===")
    chdir_arg = f"-chdir={TERRAFORM_DIR}"
    cmd = ["terraform", chdir_arg, "output", "-raw", "web_api_base_url"]
    log(f"Command: {' '.join(cmd)}")
    output, code = run(cmd)
    log(output)
    log(f"Exit code: {code}")

    if code != 0:
        log("")
        log(f"=== Aborting: could not resolve web_api_base_url. Full log written to: {log_file} ===")
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    base_url = output.rstrip("/")

    # 2) Select files
    if args.files:
        selected = [Path(p) for p in args.files]
        for p in selected:
            if not p.is_file():
                log(f"File not found: {p}")
                log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return 1
    else:
        candidates = [p for p in DATA_RAW_DIR.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]
        if not candidates:
            log(f"No PDF/TIF/TIFF fixtures found in {DATA_RAW_DIR}")
            log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return 1
        selected = random.sample(candidates, min(args.count, len(candidates)))

    for p in selected:
        if p.stat().st_size > MAX_SIZE_BYTES:
            log(f"File exceeds 20 MB API limit: {p}")
            log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return 1
        if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
            log(f"Unsupported file extension: {p}")
            log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return 1

    log("")
    log(f"Web API: {base_url}")
    log("Selected files:")
    for p in selected:
        log(f"  - {p.name} ({p.stat().st_size} bytes)")

    # 3) POST /uploads
    log("")
    log("=== POST /uploads ===")
    payload = {
        "files": [
            {
                "name": p.name,
                "content_type": CONTENT_TYPES[p.suffix.lower()],
                "size_bytes": p.stat().st_size,
            }
            for p in selected
        ]
    }
    log(f"Request: {json.dumps(payload)}")
    try:
        status, body = http_json("POST", f"{base_url}/uploads", payload)
    except urllib.error.HTTPError as e:
        log(f"HTTPError: {e.code} {e.reason}")
        log(e.read().decode(errors="replace"))
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1
    log(f"Status: {status}")
    log(f"Response: {json.dumps(body)}")

    run_id = body.get("run_id")
    uploads = body.get("uploads") or []
    if not run_id or len(uploads) != len(selected):
        log("")
        log("ERROR: response missing run_id or upload count mismatch.")
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    log(f"run_id: {run_id}")

    # 4) PUT each file to its presigned URL
    for p, upload in zip(selected, uploads):
        log("")
        log(f"=== PUT {p.name} -> presigned URL ===")
        status = http_put_file(upload["upload_url"], p, CONTENT_TYPES[p.suffix.lower()])
        log(f"Status: {status}")

    # 5) Poll status per invoice (invoice_id = filename without extension)
    for p in selected:
        invoice_id = p.stem
        log("")
        log(f"=== Polling status for invoice_id={invoice_id} ===")
        deadline = time.monotonic() + args.timeout
        last_status = None
        while time.monotonic() < deadline:
            try:
                status, body = http_json("GET", f"{base_url}/invoices/{invoice_id}/status")
                last_status = body
                log(f"Status: {body.get('status')}")
                if body.get("status") in TERMINAL_STATUSES:
                    break
            except urllib.error.HTTPError as e:
                log(f"Status not available yet (HTTP {e.code})")
            time.sleep(args.poll_interval)
        else:
            log(f"Timed out waiting for terminal status. Last status: {json.dumps(last_status)}")

    # 6) Final history check
    log("")
    log("=== GET /invoices?limit=20 ===")
    try:
        status, body = http_json("GET", f"{base_url}/invoices?limit=20")
        log(f"Status: {status}")
        log(f"history_count: {len(body.get('invoices') or [])}")
    except urllib.error.HTTPError as e:
        log(f"HTTPError: {e.code} {e.reason}")

    log("")
    log(f"=== Done. Full log written to: {log_file} ===")
    log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
