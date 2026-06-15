#!/usr/bin/env python3
"""Test the natural-language-to-SQL chat endpoint (POST /chat).

Flow (mirrors frontend/src/api/client.js sendChat):
  1) terraform output -raw web_api_base_url
  2) POST {base_url}/chat with {"question": "..."} for each test question
  3) Log the generated SQL, answer, row count, and Athena metrics

On any HTTP error, logs status code, response headers, and the full
response body (validation errors, SQL validation errors, timeouts, etc.).

Logs combined output to logs/tf_step9_test_chat_nlq_<timestamp>.log.

Usage:
  python tests/terraform/step9_test_chat_nlq.py [--questions "..." "..."] [--timeout SECONDS]
"""

import argparse
import datetime
import json
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = REPO_ROOT / "logs"
TERRAFORM_DIR = "infra/envs/dev"

DEFAULT_QUESTIONS = [
    "How much did we spend in total?",
    "Who are the top 5 suppliers by total amount?",
    "How many invoices were processed last month?",
    "Show me invoices with status Failed.",
]

ROW_PREVIEW_LIMIT = 5


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
    parser.add_argument("--questions", nargs="*", default=None, help="Natural-language questions to send (default: a built-in set)")
    parser.add_argument("--timeout", type=int, default=90, help="HTTP timeout per request in seconds")
    args = parser.parse_args()

    LOGS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"tf_step9_test_chat_nlq_{timestamp}.log"

    lines = []

    def log(msg=""):
        print(msg)
        lines.append(str(msg))

    def flush():
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    log("Terraform Step 9: test natural-language SQL chat endpoint (/chat)")
    log(f"Timestamp: {datetime.datetime.now().isoformat()}")

    # 1) Resolve base URL
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

    questions = args.questions if args.questions else DEFAULT_QUESTIONS

    log("")
    log(f"Web API: {base_url}")
    log(f"Questions to test: {len(questions)}")

    results_summary = []

    for i, question in enumerate(questions, start=1):
        log("")
        log(f"=== [{i}/{len(questions)}] POST /chat ===")
        log(f"Question: {question}")

        payload = {"question": question}
        req = urllib.request.Request(
            f"{base_url}/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=args.timeout) as resp:
                status = resp.status
                body = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            log_http_error(log, e)
            results_summary.append((question, f"HTTP {e.code}"))
            continue
        except urllib.error.URLError as e:
            log(f"URLError: {e.reason}")
            results_summary.append((question, "URLError"))
            continue

        log(f"Status: {status}")

        if "error" in body:
            log(f"Error response: {json.dumps(body)}")
            results_summary.append((question, f"error: {body.get('error')}"))
            continue

        generated_sql = body.get("generated_sql")
        rows = body.get("rows") or []
        answer = body.get("answer")
        query_id = body.get("query_id")
        execution_time_ms = body.get("execution_time_ms")
        athena_scan_mb = body.get("athena_scan_mb")

        log(f"Generated SQL: {generated_sql}")
        log(f"query_id: {query_id}")
        log(f"execution_time_ms: {execution_time_ms}")
        log(f"athena_scan_mb: {athena_scan_mb}")
        log(f"Row count: {len(rows)}")
        if rows:
            log(f"First {min(ROW_PREVIEW_LIMIT, len(rows))} row(s): {json.dumps(rows[:ROW_PREVIEW_LIMIT], ensure_ascii=False)}")
        log(f"Answer: {answer}")

        results_summary.append((question, "OK" if answer else "no answer"))

    # Summary
    log("")
    log("=== Summary ===")
    for question, outcome in results_summary:
        log(f"  [{outcome}] {question}")

    failures = [q for q, outcome in results_summary if outcome != "OK"]

    log("")
    log(f"=== Done. {len(results_summary) - len(failures)}/{len(results_summary)} questions answered OK. Full log written to: {log_file} ===")
    flush()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
