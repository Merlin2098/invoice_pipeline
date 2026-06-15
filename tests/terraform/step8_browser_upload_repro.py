#!/usr/bin/env python3
"""Reproduce the browser's upload flow for a data/raw file and capture every
HTTP response in detail (status, headers, body) so portal upload failures
can be diagnosed without needing browser DevTools.

Flow (mirrors frontend/src/api/client.js):
  1) terraform output -raw web_api_base_url
  2) terraform output -raw portal_url (sent as Origin header, like a browser)
  3) POST {base_url}/uploads with file metadata -> presigned PUT URL
  4) PUT the file to the presigned URL with the same Content-Type used to
     request it (image/tiff for .tif/.tiff, application/pdf for .pdf)

On any HTTP error, logs status code, all response headers, and the full
response body (S3 error responses are XML with a specific <Code> that
pinpoints the failure, e.g. SignatureDoesNotMatch, AccessDenied).

Logs combined output to logs/tf_step8_browser_upload_repro_<timestamp>.log.

Usage:
  python tests/terraform/step8_browser_upload_repro.py [--file path] [--poll]
"""

import argparse
import datetime
import json
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


def tf_output(name):
    chdir_arg = f"-chdir={TERRAFORM_DIR}"
    return run(["terraform", chdir_arg, "output", "-raw", name])


def log_http_error(log, e):
    log(f"HTTPError: {e.code} {e.reason}")
    log("Response headers:")
    for k, v in e.headers.items():
        log(f"  {k}: {v}")
    body = e.read().decode(errors="replace")
    log("Response body:")
    log(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default=None, help="Path to a file under data/raw (default: first .tif found)")
    parser.add_argument("--poll", action="store_true", help="Poll invoice status after upload until terminal")
    parser.add_argument("--timeout", type=int, default=900, help="Seconds to wait for terminal status")
    parser.add_argument("--poll-interval", type=int, default=15, help="Seconds between status polls")
    args = parser.parse_args()

    LOGS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"tf_step8_browser_upload_repro_{timestamp}.log"

    lines = []

    def log(msg=""):
        print(msg)
        lines.append(str(msg))

    def flush():
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    log("Terraform Step 8: reproduce browser upload flow with detailed error capture")
    log(f"Timestamp: {datetime.datetime.now().isoformat()}")

    # 1) Resolve base URL and portal URL (Origin header, like a browser request)
    log("")
    log("=== terraform output web_api_base_url ===")
    base_url, code = tf_output("web_api_base_url")
    log(base_url)
    log(f"Exit code: {code}")
    if code != 0:
        log("")
        log(f"=== Aborting: could not resolve web_api_base_url. Full log written to: {log_file} ===")
        flush()
        return 1
    base_url = base_url.rstrip("/")

    log("")
    log("=== terraform output portal_url ===")
    portal_url, code = tf_output("portal_url")
    log(portal_url)
    log(f"Exit code: {code}")
    if code != 0:
        portal_url = ""
    portal_url = portal_url.rstrip("/")

    # 2) Select file
    if args.file:
        selected = Path(args.file)
        if not selected.is_absolute():
            selected = REPO_ROOT / selected
    else:
        candidates = sorted(p for p in DATA_RAW_DIR.iterdir() if p.is_file() and p.suffix.lower() in CONTENT_TYPES)
        if not candidates:
            log(f"No PDF/TIF/TIFF fixtures found in {DATA_RAW_DIR}")
            flush()
            return 1
        selected = candidates[0]

    if not selected.is_file():
        log(f"File not found: {selected}")
        flush()
        return 1

    ext = selected.suffix.lower()
    if ext not in CONTENT_TYPES:
        log(f"Unsupported file extension: {ext}")
        flush()
        return 1

    size_bytes = selected.stat().st_size
    if size_bytes > MAX_SIZE_BYTES:
        log(f"File exceeds 20 MB API limit: {selected}")
        flush()
        return 1

    content_type = CONTENT_TYPES[ext]

    log("")
    log(f"Web API: {base_url}")
    log(f"Origin (portal_url): {portal_url or '(unresolved)'}")
    log(f"Selected file: {selected.name} ({size_bytes} bytes)")
    log(f"Content-Type: {content_type}")

    # 3) POST /uploads (mirrors requestUploadUrls in client.js)
    log("")
    log("=== POST /uploads ===")
    payload = {
        "files": [
            {
                "name": selected.name,
                "content_type": content_type,
                "size_bytes": size_bytes,
            }
        ]
    }
    log(f"Request: {json.dumps(payload)}")

    headers = {"Content-Type": "application/json"}
    if portal_url:
        headers["Origin"] = portal_url

    req = urllib.request.Request(
        f"{base_url}/uploads",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            resp_headers = dict(resp.getheaders())
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        log_http_error(log, e)
        flush()
        return 1
    except urllib.error.URLError as e:
        log(f"URLError: {e.reason}")
        flush()
        return 1

    log(f"Status: {status}")
    log("Response headers:")
    for k, v in resp_headers.items():
        log(f"  {k}: {v}")
    log(f"Response body: {json.dumps(body)}")

    run_id = body.get("run_id")
    uploads = body.get("uploads") or []
    if not run_id or not uploads:
        log("")
        log("ERROR: response missing run_id or uploads.")
        flush()
        return 1

    upload = uploads[0]
    log(f"run_id: {run_id}")

    # 4) PUT the file to its presigned URL (mirrors uploadFileToS3 in client.js)
    log("")
    log(f"=== PUT {selected.name} -> presigned URL ===")
    log(f"Presigned URL: {upload['upload_url']}")
    log(f"Content-Type header sent: {content_type}")

    put_headers = {"Content-Type": content_type}
    if portal_url:
        put_headers["Origin"] = portal_url

    put_req = urllib.request.Request(
        upload["upload_url"],
        data=selected.read_bytes(),
        headers=put_headers,
        method="PUT",
    )
    try:
        with urllib.request.urlopen(put_req, timeout=300) as resp:
            status = resp.status
            resp_headers = dict(resp.getheaders())
            body_bytes = resp.read()
    except urllib.error.HTTPError as e:
        log_http_error(log, e)
        flush()
        return 1
    except urllib.error.URLError as e:
        log(f"URLError: {e.reason}")
        flush()
        return 1

    log(f"Status: {status}")
    log("Response headers:")
    for k, v in resp_headers.items():
        log(f"  {k}: {v}")
    log(f"Body bytes read: {len(body_bytes)}")

    # 5) Optional: poll invoice status
    if args.poll:
        invoice_id = selected.stem
        log("")
        log(f"=== Polling status for invoice_id={invoice_id} ===")
        deadline = time.monotonic() + args.timeout
        last_status = None
        while time.monotonic() < deadline:
            try:
                status_req = urllib.request.Request(f"{base_url}/invoices/{invoice_id}/status", method="GET")
                with urllib.request.urlopen(status_req, timeout=30) as resp:
                    status_body = json.loads(resp.read())
                last_status = status_body
                log(f"Status: {status_body.get('status')}")
                if status_body.get("status") in TERMINAL_STATUSES:
                    break
            except urllib.error.HTTPError as e:
                log(f"Status not available yet (HTTP {e.code})")
            time.sleep(args.poll_interval)
        else:
            log(f"Timed out waiting for terminal status. Last status: {json.dumps(last_status)}")

    log("")
    log(f"=== Done. Full log written to: {log_file} ===")
    flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
