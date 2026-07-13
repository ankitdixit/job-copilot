#!/usr/bin/env python3
"""Health check for job-copilot automation.

Checks:
  1. Gmail OAuth token — valid and refreshable
  2. LM Studio — responding at configured endpoint (with retries)

Exit codes:
  0 — all clear
  1 — degraded (LM Studio down; email still works)
  2 — critical (Gmail token missing or expired with no refresh token)

JSON output (--json):
  {"gmail": "ok|expired|missing", "lm_studio": "ok|down", "timestamp": "..."}

macOS: fires an osascript banner notification on any non-OK check.
Linux: skips osascript silently; still logs and exits with correct code.

Usage:
    python3 tools/health_check.py
    python3 tools/health_check.py --json
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

TOKEN_FILE = Path(os.getenv("GMAIL_TOKEN_FILE", "~/.config/job-copilot/token_send.json")).expanduser()
LM_STUDIO_URL = os.getenv("LLM_BASE_URL", "http://localhost:1234") + "/v1/models"
LOG_FILE = Path(__file__).parent.parent / "health_check.log"
LM_STUDIO_RETRIES = 3
LM_STUDIO_RETRY_DELAY = 2


def log(msg: str) -> None:
    entry = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(entry)
    with open(LOG_FILE, "a") as f:
        f.write(entry + "\n")


def notify(title: str, message: str) -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.run([
            "osascript", "-e",
            f'display notification "{message}" with title "{title}" sound name "Basso"'
        ], check=False)
    elif system == "Linux":
        subprocess.run(["notify-send", "-u", "critical", title, message], check=False)
    else:
        print(f"ALERT: {title} — {message}", file=sys.stderr)


def check_gmail_token() -> str:
    """Returns 'ok', 'expired', or 'missing'."""
    if not TOKEN_FILE.exists():
        notify("Job Copilot", "Gmail token missing — run send_email.py to re-authorize")
        log("FAIL gmail_token: file not found")
        return "missing"

    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE))
        if creds.expired and not creds.refresh_token:
            notify("Job Copilot", "Gmail token expired — re-authorize via send_email.py")
            log("FAIL gmail_token: expired, no refresh token")
            return "expired"
        log("OK   gmail_token")
        return "ok"
    except Exception as e:
        notify("Job Copilot", f"Gmail token invalid: {e}")
        log(f"FAIL gmail_token: {e}")
        return "expired"


def check_lm_studio() -> str:
    """Returns 'ok' or 'down'. Retries up to LM_STUDIO_RETRIES times."""
    for attempt in range(1, LM_STUDIO_RETRIES + 1):
        try:
            req = urllib.request.urlopen(LM_STUDIO_URL, timeout=5)
            if req.status == 200:
                log("OK   lm_studio")
                return "ok"
        except Exception:
            pass
        if attempt < LM_STUDIO_RETRIES:
            time.sleep(LM_STUDIO_RETRY_DELAY)

    notify("Job Copilot", "LM Studio is not responding — email triage will skip until it restarts")
    log(f"FAIL lm_studio: no response after {LM_STUDIO_RETRIES} attempts")
    return "down"


def main() -> None:
    parser = argparse.ArgumentParser(description="Job Copilot health check")
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    args = parser.parse_args()

    log("--- health check start ---")
    gmail_status = check_gmail_token()
    lm_status = check_lm_studio()

    result = {
        "gmail": gmail_status,
        "lm_studio": lm_status,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    if args.json:
        print(json.dumps(result))

    all_ok = gmail_status == "ok" and lm_status == "ok"
    if all_ok:
        log("--- all checks passed ---")
        sys.exit(0)
    elif gmail_status in ("expired", "missing"):
        log("--- CRITICAL: Gmail token invalid ---")
        sys.exit(2)
    else:
        log("--- DEGRADED: LM Studio down ---")
        sys.exit(1)


if __name__ == "__main__":
    main()
