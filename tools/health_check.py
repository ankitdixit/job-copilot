#!/usr/bin/env python3
"""Health check for job-copilot automation.

Checks:
  1. Gmail token is valid and not expired
  2. (Extensible) any background automation is running

Runs silently when healthy. Sends a desktop notification on failure.
Designed to run every 2 hours via LaunchAgent (macOS) or systemd timer (Linux).

Usage:
    python3 tools/health_check.py
"""

import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

TOKEN_FILE = Path(os.getenv("GMAIL_TOKEN_FILE", "~/.config/job-copilot/token_send.json")).expanduser()
LOG_FILE = Path(__file__).parent.parent / "health_check.log"


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


def check_gmail_token() -> bool:
    if not TOKEN_FILE.exists():
        notify("Job Copilot", "Gmail token missing — run send_email.py to re-authorize")
        log("FAIL gmail_token: file not found")
        return False

    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE))
        if creds.expired and not creds.refresh_token:
            notify("Job Copilot", "Gmail token expired and cannot refresh — re-authorize")
            log("FAIL gmail_token: expired, no refresh token")
            return False
        log("OK   gmail_token")
        return True
    except Exception as e:
        notify("Job Copilot", f"Gmail token invalid: {e}")
        log(f"FAIL gmail_token: {e}")
        return False


def main() -> None:
    log("--- health check start ---")
    all_ok = True
    all_ok &= check_gmail_token()
    if all_ok:
        log("--- all checks passed ---")
    else:
        log("--- one or more checks FAILED ---")
        sys.exit(1)


if __name__ == "__main__":
    main()
