#!/usr/bin/env python3
"""run_applications.py — orchestrator. Claude decides targets; Qwen executes each one.

Usage:
    python3 run_applications.py --list                     # show targets + status
    python3 run_applications.py --apply cloudera --role 0  # dry-run ATS form fill
    python3 run_applications.py --apply cloudera --role 0 --confirm  # actually submit
    python3 run_applications.py --outreach cloudera        # find contact + draft email
    python3 run_applications.py --outreach cloudera --send # find + draft + prompt to send
    python3 run_applications.py --run-all                  # apply/outreach all pending targets
    python3 run_applications.py --debrief mistral --transcript transcripts/2026-07-13-mistral.md
    python3 run_applications.py --debrief xai --no-transcript  # manual input mode

Routing logic (set in company yml):
    apply_method: ats       → apply_agent.py (Qwen fills ATS form)
    apply_method: outreach  → outreach_agent.py (Qwen finds contact + drafts email)
    apply_method: both      → run both

Each run logs output to ~/.job-copilot/runs/<timestamp>-<company>.log
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent
CONFIG_DIR = PROJECT_ROOT / "config"
LOG_DIR = Path.home() / ".job-copilot" / "runs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def load_targets() -> list[dict]:
    """Load automation targets from config/targets.yml (gitignored — personal)."""
    path = CONFIG_DIR / "targets.yml"
    if not path.exists():
        print(f"[orchestrator] No targets file at {path}. Copy config/targets.example.yml to get started.")
        return []
    data = yaml.safe_load(path.read_text())
    return data.get("targets", [])


def load_company_configs() -> dict:
    configs = {}
    for f in (CONFIG_DIR / "companies").glob("*.yml"):
        cfg = yaml.safe_load(f.read_text())
        configs[f.stem] = cfg
    return configs


def list_targets(configs: dict):
    targets = load_targets()
    print(f"\nAutomation targets ({len(targets)} loaded from config/targets.yml):")
    print(f"{'Company':<25} {'Role':<50} {'Method':<10}")
    print("-" * 90)
    for t in targets:
        cfg = configs.get(t["company"], {})
        roles = cfg.get("roles", [])
        role_title = roles[t["role"]]["title"] if t["role"] < len(roles) else "?"
        print(f"{t['company']:<25} {role_title[:50]:<50} {t['method']:<10}")


def run_agent(cmd: list) -> tuple[int, str]:
    """Run a sub-agent and return (exit_code, output)."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def log_run(company: str, method: str, output: str):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = LOG_DIR / f"{ts}-{company}-{method}.log"
    path.write_text(output)
    print(f"[orchestrator] Log saved to {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Job application orchestrator")
    parser.add_argument("--list", action="store_true", help="List approved targets")
    parser.add_argument("--apply", metavar="COMPANY", help="Run ATS apply agent for a company")
    parser.add_argument("--outreach", metavar="COMPANY", help="Run outreach agent for a company")
    parser.add_argument("--role", type=int, default=0, help="Role index (default: 0)")
    parser.add_argument("--confirm", action="store_true", help="Actually submit (default: dry run)")
    parser.add_argument("--send", action="store_true", help="Prompt to send outreach email")
    parser.add_argument("--run-all", action="store_true", help="Run all approved targets (dry-run ATS, prompt-to-send outreach)")
    parser.add_argument("--debrief", metavar="COMPANY", help="Run interview debrief agent for a company")
    parser.add_argument("--transcript", metavar="FILE", help="Transcript file for --debrief")
    parser.add_argument("--no-transcript", action="store_true", help="Manual debrief input (no transcript file)")
    parser.add_argument("--dry-run", action="store_true", help="Show debrief output without writing files")

    args = parser.parse_args()
    configs = load_company_configs()

    if args.list:
        list_targets(configs)
        sys.exit(0)

    if args.apply:
        cmd = [
            "python3", str(PROJECT_ROOT / "agents" / "apply_agent.py"),
            "--company", args.apply,
            "--role", str(args.role),
        ]
        if args.confirm:
            cmd.append("--confirm")
        code, output = run_agent(cmd)
        print(output)
        log_run(args.apply, "apply", output)
        sys.exit(code)

    if args.outreach:
        cmd = [
            "python3", str(PROJECT_ROOT / "agents" / "outreach_agent.py"),
            "--company", args.outreach,
            "--role", str(args.role),
        ]
        if args.send:
            cmd.append("--send")
        code, output = run_agent(cmd)
        print(output)
        log_run(args.outreach, "outreach", output)
        sys.exit(code)

    if args.run_all:
        targets = load_targets()
        print(f"[orchestrator] Running {len(targets)} targets...")
        for t in targets:
            company = t["company"]
            role = t["role"]
            method = t["method"]
            print(f"\n{'='*60}")
            print(f"[orchestrator] {company} role={role} method={method}")

            if method in ("ats", "both"):
                cmd = [
                    "python3", str(PROJECT_ROOT / "agents" / "apply_agent.py"),
                    "--company", company, "--role", str(role),
                ]
                code, output = run_agent(cmd)
                log_run(company, "apply", output)
                print(output[-500:])  # show last 500 chars

            if method in ("outreach", "both"):
                cmd = [
                    "python3", str(PROJECT_ROOT / "agents" / "outreach_agent.py"),
                    "--company", company, "--role", str(role), "--send",
                ]
                code, output = run_agent(cmd)
                log_run(company, "outreach", output)
                print(output[-500:])

        print("\n[orchestrator] All targets processed.")
        sys.exit(0)

    if args.debrief:
        cmd = [
            "python3", str(PROJECT_ROOT / "agents" / "debrief_agent.py"),
            "--company", args.debrief,
        ]
        if args.transcript:
            cmd += ["--transcript", args.transcript]
        elif args.no_transcript:
            cmd.append("--no-transcript")
        else:
            print("--debrief requires --transcript <file> or --no-transcript", file=sys.stderr)
            sys.exit(1)
        if args.dry_run:
            cmd.append("--dry-run")
        code, output = run_agent(cmd)
        print(output)
        sys.exit(code)

    parser.print_help()
