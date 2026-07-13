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

Reply to an existing thread (threads correctly in Gmail):
    python3 tools/send_email.py --to addr@example.com --subject "Re: ..." --body "..." \\
        --thread-id <gmail-thread-id> --in-reply-to <gmail-message-id>

Get thread-id and message-id from the Gmail API or MCP search/get_thread output.
Set EMAIL_FOOTER env var to append a P.S. line to every outbound email (optional).
"""

import argparse
import base64
import mimetypes
import os
import sys
from email import encoders
from email.mime.base import MIMEBase
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
EMAIL_FOOTER = os.getenv("EMAIL_FOOTER", "")


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


def send_email(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    attachment: Optional[str] = None,
) -> None:
    service = get_service()
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.attach(MIMEText(body + EMAIL_FOOTER, "plain"))
    if attachment:
        path = Path(attachment)
        mime_type, _ = mimetypes.guess_type(str(path))
        main_type, sub_type = (mime_type or "application/octet-stream").split("/", 1)
        with open(path, "rb") as f:
            part = MIMEBase(main_type, sub_type)
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=path.name)
        msg.attach(part)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload: dict = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id
    service.users().messages().send(userId="me", body=payload).execute()
    reply_info = f" [reply in thread {thread_id}]" if thread_id else ""
    print(f"Sent: '{subject}' → {to}" + (f" (cc: {cc})" if cc else "") + reply_info)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send email via Gmail API")
    parser.add_argument("--to", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body", help="Email body text")
    parser.add_argument("--body-file", help="Path to file containing email body")
    parser.add_argument("--cc", default=None)
    parser.add_argument("--thread-id", default=None, help="Gmail thread ID — places reply in existing thread")
    parser.add_argument("--in-reply-to", default=None, help="Gmail message ID of the message being replied to")
    parser.add_argument("--attachment", default=None, metavar="PATH", help="Path to file to attach")
    args = parser.parse_args()

    if args.body_file:
        body = Path(args.body_file).read_text()
    elif args.body:
        body = args.body
    else:
        print("Error: provide --body or --body-file", file=sys.stderr)
        sys.exit(1)

    send_email(args.to, args.subject, body, args.cc, args.thread_id, args.in_reply_to, args.attachment)


if __name__ == "__main__":
    main()
