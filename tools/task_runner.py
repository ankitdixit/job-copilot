#!/usr/bin/env python3
"""tools/task_runner.py — route tasks to script | Qwen | Claude by engine label.

Engine routing:
  script  — runs shell command; 0 tokens; synchronous
  qwen    — NL prompt → LM Studio; 0 tokens; synchronous
  claude  — prints prompt for manual paste; human action required; exit 2

Task file: tools/tasks.yml (schema at bottom of this file)

Usage:
    python3 tools/task_runner.py --list
    python3 tools/task_runner.py --run-id fix-notice-period
    python3 tools/task_runner.py --run-all
    python3 tools/task_runner.py --run-all --engine qwen   # only Qwen tasks
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
TASKS_FILE = PROJECT_ROOT / "tools" / "tasks.yml"
LOG_FILE = PROJECT_ROOT / "tools" / "runner.log"

VALID_ENGINES = {"script", "qwen", "claude"}
VALID_STATUSES = {"open", "done", "skip"}


# ── Persistence ──────────────────────────────────────────────────────────────

def load_tasks() -> list[dict]:
    import yaml
    if not TASKS_FILE.exists():
        return []
    data = yaml.safe_load(TASKS_FILE.read_text())
    return data.get("tasks", [])


def save_tasks(tasks: list[dict]) -> None:
    import yaml
    TASKS_FILE.write_text(
        yaml.dump({"tasks": tasks}, default_flow_style=False, allow_unicode=True, sort_keys=False)
    )


def mark_done(tasks: list[dict], task_id: str) -> None:
    for t in tasks:
        if t["id"] == task_id:
            t["status"] = "done"
            t["completed_at"] = datetime.utcnow().isoformat() + "Z"
    save_tasks(tasks)


# ── Logging ───────────────────────────────────────────────────────────────────

def log_result(task_id: str, engine: str, exit_code: int, output: str) -> None:
    entry = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "id": task_id,
        "engine": engine,
        "exit_code": exit_code,
        "preview": output[:200],
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ── Runners ───────────────────────────────────────────────────────────────────

def run_script(task: dict) -> int:
    cmd = task.get("command", "")
    if not cmd:
        print(f"[task_runner] task '{task['id']}' has no command", file=sys.stderr)
        return 1
    print(f"[script] {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=False, text=True, cwd=PROJECT_ROOT)
    log_result(task["id"], "script", result.returncode, "")
    return result.returncode


def run_qwen(task: dict) -> int:
    prompt = task.get("prompt", "")
    if not prompt:
        print(f"[task_runner] task '{task['id']}' has no prompt", file=sys.stderr)
        return 1

    base = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
    url = base.rstrip("/") + "/chat/completions"
    model = os.getenv("LLM_MODEL", "qwen/qwen3.6-27b")

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": task.get("temperature", 0.2),
        "max_tokens": task.get("max_tokens", 2048),
    }).encode()

    print(f"[qwen] sending prompt ({len(prompt)} chars) to {url} ...")
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        print(content)
        log_result(task["id"], "qwen", 0, content)
        return 0
    except Exception as e:
        msg = f"Qwen error: {e}"
        print(msg, file=sys.stderr)
        log_result(task["id"], "qwen", 1, msg)
        return 1


def run_claude(task: dict) -> int:
    """Print prompt for manual Claude session — exit 2 so callers can detect."""
    print()
    print("=" * 64)
    print("CLAUDE TASK — paste this into your Claude session:")
    print("=" * 64)
    print(f"Task: {task['title']}")
    print()
    print(task.get("prompt", "(no prompt — see task description)"))
    print("=" * 64)
    print()
    log_result(task["id"], "claude", 2, "printed for manual execution")
    return 2


RUNNERS = {
    "script": run_script,
    "qwen": run_qwen,
    "claude": run_claude,
}


# ── Dispatch ──────────────────────────────────────────────────────────────────

def run_task(task: dict, tasks_list: list[dict], mark_on_success: bool = True) -> int:
    engine = task.get("engine", "claude")
    if engine not in VALID_ENGINES:
        print(f"[task_runner] unknown engine '{engine}' for task '{task['id']}'", file=sys.stderr)
        return 1

    print(f"\n[{engine}] {task['id']} — {task['title']}")
    exit_code = RUNNERS[engine](task)

    if exit_code == 0 and mark_on_success:
        mark_done(tasks_list, task["id"])
        print(f"[task_runner] marked '{task['id']}' as done")

    return exit_code


# ── CLI ───────────────────────────────────────────────────────────────────────

def cmd_list(tasks: list[dict], engine_filter: str | None) -> None:
    header = f"{'ID':<30} {'ENGINE':<8} {'STATUS':<6} TITLE"
    print(header)
    print("-" * len(header))
    for t in tasks:
        if engine_filter and t.get("engine") != engine_filter:
            continue
        status = t.get("status", "open")
        marker = "✓" if status == "done" else ("–" if status == "skip" else " ")
        print(f"{marker} {t['id']:<28} {t.get('engine','?'):<8} {status:<6} {t['title']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Route tasks to script / Qwen / Claude")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List all tasks")
    group.add_argument("--run-id", metavar="ID", help="Run a single task by ID")
    group.add_argument("--run-all", action="store_true", help="Run all open tasks")
    parser.add_argument("--engine", choices=list(VALID_ENGINES), help="Filter by engine")
    parser.add_argument("--include-done", action="store_true", help="Re-run done tasks too")
    args = parser.parse_args()

    tasks = load_tasks()
    if not tasks:
        print(f"No tasks found. Create {TASKS_FILE} — see tools/tasks.example.yml")
        sys.exit(0)

    if args.list:
        cmd_list(tasks, args.engine)
        return

    if args.run_id:
        matches = [t for t in tasks if t["id"] == args.run_id]
        if not matches:
            print(f"No task with id '{args.run_id}'", file=sys.stderr)
            sys.exit(1)
        sys.exit(run_task(matches[0], tasks))

    # --run-all
    to_run = [
        t for t in tasks
        if (args.include_done or t.get("status", "open") == "open")
        and t.get("status") != "skip"
        and (not args.engine or t.get("engine") == args.engine)
    ]
    if not to_run:
        print("No open tasks to run.")
        return

    failed = []
    for task in to_run:
        rc = run_task(task, tasks)
        if rc not in (0, 2):  # 2 = claude hand-off, not a failure
            failed.append(task["id"])

    print(f"\nDone. {len(to_run) - len(failed)}/{len(to_run)} tasks succeeded.")
    if failed:
        print(f"Failed: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()


# ── Task YAML schema (tools/tasks.yml) ────────────────────────────────────────
#
# tasks:
#   - id: fix-notice-period          # unique slug, no spaces
#     title: "Fix [NOTICE_PERIOD] substitution bug"
#     engine: script                 # script | qwen | claude
#     command: "python3 scripts/fix_notice.py"   # script engine only
#     status: open                   # open | done | skip
#
#   - id: draft-outreach-mistral
#     title: "Draft outreach email to Mistral recruiter"
#     engine: qwen
#     prompt: |
#       Draft a 4-paragraph outreach email for a Staff Engineer role at Mistral AI.
#       Tone: direct, no filler. Max 200 words. Output subject + body.
#     temperature: 0.3               # optional, default 0.2
#     status: open
#
#   - id: gap-analysis-stream-a
#     title: "Scan repo for new code gaps"
#     engine: claude
#     prompt: |
#       Read agents/, tools/, config/ and identify hardcoded personal values,
#       missing error handling, or portability gaps. Create GitHub Issues for each.
#     status: open
