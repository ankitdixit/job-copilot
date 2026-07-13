#!/usr/bin/env python3
"""agents/debrief_agent.py — portable interview debrief + gap extraction.

Reads a transcript file (or prompts for manual input) and uses local Qwen to:
  1. Classify the call type (technical screen / system design / behavioral / HM)
  2. Extract questions asked, what landed, what didn't, gaps surfaced
  3. Write a structured debrief note to debriefs/
  4. Append new gaps to gaps.md
  5. Append drill tasks to tasks.md (one per HIGH gap)

Uses LM Studio directly (no browser_use) — works offline, zero API cost.

Usage:
    # With transcript file (Snaply markdown or plain text)
    python3 agents/debrief_agent.py --company mistral --transcript transcripts/2026-07-13-mistral.md

    # No transcript — manual input via prompts
    python3 agents/debrief_agent.py --company xai --round system-design --no-transcript

    # Dry run — show debrief without writing files
    python3 agents/debrief_agent.py --company stripe --transcript ... --dry-run

Integrates with run_applications.py:
    python3 run_applications.py --debrief mistral --transcript transcripts/2026-07-13-mistral.md
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

DEBRIEFS_DIR = PROJECT_ROOT / "debriefs"
GAPS_FILE = PROJECT_ROOT / "gaps.md"
TASKS_FILE = PROJECT_ROOT / "tasks.md"

ROUND_TYPES = ["technical-screen", "system-design", "behavioral", "hiring-manager", "coding", "unknown"]


# ── Qwen call ─────────────────────────────────────────────────────────────────

def call_qwen(prompt: str, temperature: float = 0.1) -> str:
    base = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
    url = base.rstrip("/") + "/chat/completions"
    model = os.getenv("LLM_MODEL", "qwen/qwen3.6-27b")

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 3000,
    }).encode()

    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
    content = data["choices"][0]["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()


# ── Manual input (no-transcript mode) ────────────────────────────────────────

def gather_manual_input(company: str, round_type: str) -> str:
    print(f"\nManual debrief — {company} / {round_type}")
    print("Answer each question. Press Enter twice to finish a multi-line answer.\n")

    def ask(question: str) -> str:
        print(f"{question}")
        lines = []
        while True:
            line = input()
            if line == "" and lines and lines[-1] == "":
                break
            lines.append(line)
        return "\n".join(lines).strip()

    questions = ask("What questions were you asked? (list them, one per line)")
    landed = ask("What went well? What answers landed clearly?")
    missed = ask("What didn't land? Where did you stumble or get stuck?")
    notes = ask("Any other notes? (follow-up topics, interviewer signals, etc.)")

    return f"""INTERVIEW DEBRIEF INPUT
Company: {company}
Round type: {round_type}
Date: {datetime.now().strftime('%Y-%m-%d')}

QUESTIONS ASKED:
{questions}

WHAT LANDED:
{landed}

WHAT DIDN'T LAND / STUMBLES:
{missed}

ADDITIONAL NOTES:
{notes}
"""


# ── Qwen analysis prompt ──────────────────────────────────────────────────────

ANALYSIS_PROMPT = """You are analyzing an interview debrief. Extract structured information.

{input_text}

Output EXACTLY in this format (no extra text before or after):

CALL_TYPE: <technical-screen|system-design|behavioral|hiring-manager|coding|unknown>

QUESTIONS_ASKED:
- <question 1, verbatim where possible>
- <question 2>
(list all questions; use "unclear" if you can't reconstruct it)

WHAT_LANDED:
- <point 1>
- <point 2>

WHAT_DIDNT_LAND:
- <point 1>
- <point 2>

GAPS:
GAP: <skill or concept> | SEVERITY: HIGH|MED|LOW | EVIDENCE: <specific moment from the call> | FIX: <one concrete practice action>
GAP: <skill or concept> | SEVERITY: HIGH|MED|LOW | EVIDENCE: <specific moment> | FIX: <action>
(list all gaps; HIGH = blocked an offer, MED = weakened performance, LOW = polish)

SUMMARY: <2-3 sentences on overall performance and most important takeaway>
"""


def parse_qwen_output(raw: str) -> dict:
    result = {
        "call_type": "unknown",
        "questions": [],
        "what_landed": [],
        "what_didnt_land": [],
        "gaps": [],
        "summary": "",
    }

    # Call type
    m = re.search(r"CALL_TYPE:\s*(\S+)", raw)
    if m:
        result["call_type"] = m.group(1).lower()

    # Bullet sections
    def extract_bullets(section_name: str) -> list[str]:
        m = re.search(rf"{section_name}:\n(.*?)(?:\n[A-Z_]+:|$)", raw, re.DOTALL)
        if not m:
            return []
        return [line.lstrip("- ").strip() for line in m.group(1).splitlines() if line.strip().startswith("-")]

    result["questions"] = extract_bullets("QUESTIONS_ASKED")
    result["what_landed"] = extract_bullets("WHAT_LANDED")
    result["what_didnt_land"] = extract_bullets("WHAT_DIDNT_LAND")

    # Gaps
    for gap_line in re.findall(r"^GAP:.*", raw, re.MULTILINE):
        parts = {p.split(":", 1)[0].strip(): p.split(":", 1)[1].strip()
                 for p in gap_line.split("|") if ":" in p}
        if "GAP" in parts:
            result["gaps"].append({
                "skill": parts.get("GAP", "unknown"),
                "severity": parts.get("SEVERITY", "MED").upper(),
                "evidence": parts.get("EVIDENCE", ""),
                "fix": parts.get("FIX", ""),
            })

    # Summary
    m = re.search(r"SUMMARY:\s*(.+?)(?:\n[A-Z_]+:|$)", raw, re.DOTALL)
    if m:
        result["summary"] = m.group(1).strip()

    return result


# ── File writers ──────────────────────────────────────────────────────────────

def write_debrief_note(company: str, parsed: dict, date_str: str, dry_run: bool) -> Path:
    DEBRIEFS_DIR.mkdir(exist_ok=True)
    round_slug = parsed["call_type"].replace(" ", "-")
    filename = f"{date_str}-{company}-{round_slug}.md"
    path = DEBRIEFS_DIR / filename

    lines = [
        f"# Debrief: {company} — {parsed['call_type']} ({date_str})",
        "",
        "## Meta",
        f"- Company: {company}",
        f"- Round: {parsed['call_type']}",
        f"- Date: {date_str}",
        "",
        "## Questions Asked",
    ]
    for q in parsed["questions"]:
        lines.append(f"- {q}")
    lines += ["", "## What Landed"]
    for w in parsed["what_landed"]:
        lines.append(f"- {w}")
    lines += ["", "## What Didn't Land"]
    for w in parsed["what_didnt_land"]:
        lines.append(f"- {w}")
    lines += ["", "## Gaps Surfaced", "| Skill | Severity | Evidence | Fix | Status |",
              "|-------|----------|----------|-----|--------|"]
    for g in parsed["gaps"]:
        lines.append(f"| {g['skill']} | {g['severity']} | {g['evidence']} | {g['fix']} | open |")
    lines += ["", "## Summary", parsed["summary"], ""]

    content = "\n".join(lines)
    if dry_run:
        print(f"\n--- DEBRIEF NOTE ({filename}) ---")
        print(content)
    else:
        path.write_text(content)
        print(f"[debrief] wrote {path}")
    return path


def append_gaps(parsed: dict, gaps_file: Path, dry_run: bool) -> None:
    if not parsed["gaps"]:
        return

    new_rows = []
    for g in parsed["gaps"]:
        new_rows.append(f"| {g['skill']} | {g['severity']} | {g['evidence']} | {g['fix']} | open |")

    if dry_run:
        print("\n--- GAPS TO APPEND (gaps.md) ---")
        for r in new_rows:
            print(r)
        return

    if gaps_file.exists():
        existing = gaps_file.read_text()
        if "| Skill |" not in existing:
            existing += "\n| Skill | Severity | Evidence | Fix | Status |\n|-------|----------|----------|-----|--------|\n"
    else:
        existing = "# Skill Gaps\n\n| Skill | Severity | Evidence | Fix | Status |\n|-------|----------|----------|-----|--------|\n"

    gaps_file.write_text(existing.rstrip() + "\n" + "\n".join(new_rows) + "\n")
    print(f"[debrief] appended {len(new_rows)} gap(s) to gaps.md")


def append_drill_tasks(parsed: dict, tasks_file: Path, company: str, dry_run: bool) -> None:
    high_gaps = [g for g in parsed["gaps"] if g["severity"] == "HIGH"]
    if not high_gaps:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    new_tasks = []
    for g in high_gaps:
        new_tasks.append(
            f"- [ ] (P1) [est: 1h] [flexible] #jobsearch drill ({company}): {g['fix'] or g['skill']}"
        )

    if dry_run:
        print("\n--- TASKS TO APPEND (tasks.md) ---")
        for t in new_tasks:
            print(t)
        return

    if tasks_file.exists():
        existing = tasks_file.read_text()
    else:
        existing = "# Tasks\n\n"

    tasks_file.write_text(existing.rstrip() + f"\n\n### Drill tasks from {company} debrief ({today})\n" + "\n".join(new_tasks) + "\n")
    print(f"[debrief] appended {len(new_tasks)} drill task(s) to tasks.md")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Interview debrief + gap extraction")
    parser.add_argument("--company", required=True, help="Company name (slug)")
    parser.add_argument("--transcript", type=Path, help="Path to transcript file")
    parser.add_argument("--no-transcript", action="store_true",
                        help="Manual debrief via prompts (no transcript file)")
    parser.add_argument("--round", default="unknown", choices=ROUND_TYPES,
                        help="Round type (auto-detected if transcript provided)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show output without writing files")
    parser.add_argument("--gaps-file", type=Path, default=GAPS_FILE,
                        help=f"Path to gaps.md (default: {GAPS_FILE})")
    parser.add_argument("--tasks-file", type=Path, default=TASKS_FILE,
                        help=f"Path to tasks.md (default: {TASKS_FILE})")
    args = parser.parse_args()

    if not args.transcript and not args.no_transcript:
        parser.error("Provide --transcript <file> or --no-transcript")

    if args.transcript and not args.transcript.exists():
        print(f"Transcript not found: {args.transcript}", file=sys.stderr)
        sys.exit(1)

    date_str = datetime.now().strftime("%Y-%m-%d")

    # Build input text
    if args.no_transcript:
        input_text = gather_manual_input(args.company, args.round)
    else:
        transcript_text = args.transcript.read_text()
        input_text = f"TRANSCRIPT ({args.company} / {date_str}):\n\n{transcript_text}"

    # Qwen analysis
    print(f"[debrief] Sending to Qwen for analysis ({len(input_text)} chars) ...")
    prompt = ANALYSIS_PROMPT.format(input_text=input_text)
    try:
        raw = call_qwen(prompt, temperature=0.1)
    except Exception as e:
        print(f"[debrief] Qwen error: {e}", file=sys.stderr)
        print("[debrief] Is LM Studio running? Try: curl http://localhost:1234/v1/models")
        sys.exit(1)

    parsed = parse_qwen_output(raw)

    if args.dry_run:
        print(f"\n[dry-run] company={args.company} call_type={parsed['call_type']}")
        print(f"  {len(parsed['questions'])} questions, {len(parsed['gaps'])} gaps")

    write_debrief_note(args.company, parsed, date_str, args.dry_run)
    append_gaps(parsed, args.gaps_file, args.dry_run)
    append_drill_tasks(parsed, args.tasks_file, args.company, args.dry_run)

    if not args.dry_run:
        print(f"\n[debrief] Done. {len(parsed['gaps'])} gap(s) extracted.")
        print(f"  Summary: {parsed['summary']}")


if __name__ == "__main__":
    main()
