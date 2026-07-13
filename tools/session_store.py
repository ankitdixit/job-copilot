#!/usr/bin/env python3
"""session_store.py — save and restore browser session cookies for job portals.

Usage:
    # Save a session after manual login (run once per portal):
    python3 tools/session_store.py --save google --url https://accounts.google.com

    # List saved sessions:
    python3 tools/session_store.py --list

    # Check if a session is still valid:
    python3 tools/session_store.py --check google

The save flow opens a real browser, lets you log in manually, then pickles
the cookies. Future apply_agent.py runs load these cookies to skip login.
"""

import argparse
import asyncio
import json
import pickle
import sys
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright

SESSION_DIR = Path.home() / ".job-copilot" / "sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)


def session_path(name: str) -> Path:
    return SESSION_DIR / f"{name}.pkl"


async def save_session(name: str, url: str):
    """Open browser at url, wait for user to log in, then save cookies."""
    print(f"[session_store] Opening {url}")
    print(f"[session_store] Log in manually, then press ENTER in this terminal to save cookies.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(url)

        input("Press ENTER after you have logged in successfully...")

        cookies = await context.cookies()
        storage = await page.evaluate("() => JSON.stringify(window.localStorage)")

        data = {
            "name": name,
            "url": url,
            "saved_at": datetime.now().isoformat(),
            "cookies": cookies,
            "local_storage": storage,
        }

        path = session_path(name)
        with open(path, "wb") as f:
            pickle.dump(data, f)

        print(f"[session_store] Saved {len(cookies)} cookies to {path}")
        await browser.close()


async def check_session(name: str) -> bool:
    path = session_path(name)
    if not path.exists():
        print(f"No session found for '{name}' at {path}")
        return False

    with open(path, "rb") as f:
        data = pickle.load(f)

    print(f"Session '{name}' saved at {data['saved_at']}")
    print(f"Cookies: {len(data['cookies'])}")
    print(f"URL: {data['url']}")
    return True


def list_sessions():
    sessions = list(SESSION_DIR.glob("*.pkl"))
    if not sessions:
        print("No saved sessions. Run --save <name> --url <login_url> to create one.")
        return
    for s in sessions:
        with open(s, "rb") as f:
            data = pickle.load(f)
        print(f"  {s.stem:20s} saved={data['saved_at'][:19]}  url={data['url']}")


async def inject_session(context, name: str) -> bool:
    """Inject saved cookies into a playwright browser context."""
    path = session_path(name)
    if not path.exists():
        return False
    with open(path, "rb") as f:
        data = pickle.load(f)
    await context.add_cookies(data["cookies"])
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", metavar="NAME", help="Save session under this name")
    parser.add_argument("--url", help="Login URL to open for --save")
    parser.add_argument("--check", metavar="NAME", help="Check if a saved session exists")
    parser.add_argument("--list", action="store_true", help="List all saved sessions")
    args = parser.parse_args()

    if args.list:
        list_sessions()
    elif args.check:
        asyncio.run(check_session(args.check))
    elif args.save:
        if not args.url:
            print("--url required with --save")
            sys.exit(1)
        asyncio.run(save_session(args.save, args.url))
    else:
        parser.print_help()
