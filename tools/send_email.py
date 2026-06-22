#!/usr/bin/env python3
"""Send email via Gmail API using OAuth2.

First run: opens browser for one-time OAuth authorization.
Subsequent runs: sends silently using the stored token.

Setup:
    1. Create a Google Cloud project and enable the Gmail API
    2. Download OAuth2 credentials as credentials.json
    3. Set GMAIL_CREDENTIALS_FILE and GMAIL_TOKEN_FILE env vars (or use defaults)
    4. Run once to authorize: python3 tools/send_email.py --to test@example.com --subject test --body hi

Usage:
    python3 tools/send_email.py --to addr@example.com --subject "Subject" --body "Body text"
    python3 tools/send_email.py --to addr@example.com --subject "Subject" --body-file /path/to/body.txt
    python3 tools/send_email.py --to addr@example.com --subject "Subject" --body "..." --cc other@example.com
"""

import argparse
import base64
import os
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CREDENTIALS_FILE = Path(os.getenv("GMAIL_CREDENTIALS_FILE", "~/.config/job-copilot/credentials.json")).expanduser()
TOKEN_FILE = Path(os.getenv("GMAIL_TOKEN_FILE", "~/.config/job-copilot/token_send.json")).expanduser()
GMAIL_USER = os.getenv("GMAIL_USER", "me")


def get_service():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                print(f"Error: credentials file not found at {CREDENTIALS_FILE}", file=sys.stderr)
                print("See setup instructions in the README.", file=sys.stderr)
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def send_email(to: str, subject: str, body: str, cc: Optional[str] = None) -> None:
    service = get_service()
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    msg.attach(MIMEText(body, "plain"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"Sent: '{subject}' → {to}" + (f" (cc: {cc})" if cc else ""))


def main() -> None:
    parser = argparse.ArgumentParser(description="Send email via Gmail API")
    parser.add_argument("--to", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body", help="Email body text")
    parser.add_argument("--body-file", help="Path to file containing email body")
    parser.add_argument("--cc", default=None)
    args = parser.parse_args()

    if args.body_file:
        body = Path(args.body_file).read_text()
    elif args.body:
        body = args.body
    else:
        print("Error: provide --body or --body-file", file=sys.stderr)
        sys.exit(1)

    send_email(args.to, args.subject, body, args.cc)


if __name__ == "__main__":
    main()
