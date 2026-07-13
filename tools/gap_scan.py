#!/usr/bin/env python3
"""tools/gap_scan.py — auto-discover gaps in code (Stream A) and interview performance (Stream B).

Stream A (code gaps): scans repo tracked files for personal data patterns and README vs code drift.
Stream B (interview gaps): parses gaps.md, counts by skill, flags recurring ones (3+ entries).

For each finding: prints a summary, optionally creates a GitHub Issue (--create-issues).
Idempotent: checks for existing open issues with the same title before creating.

Usage:
    # Stream A only (runs anywhere)
    python3 tools/gap_scan.py --stream a

    # Stream B — needs your gaps.md and tasks.md
    python3 tools/gap_scan.py --stream b \
        --gaps-file /path/to/gaps.md \
        --tasks-file /path/to/tasks.md

    # Both streams, create GitHub Issues for each finding
    python3 tools/gap_scan.py --stream all \
        --gaps-file /path/to/gaps.md \
        --tasks-file /path/to/tasks.md \
        --create-issues
"""

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# ── Stream A: personal data patterns ─────────────────────────────────────────

# Checked against tracked files only; gitignored personal configs are excluded.
PERSONAL_PATTERNS = [
    (r"[a-zA-Z0-9._%+\-]+@(?:gmail|outlook|hotmail|yahoo)\.com", "personal email address"),
    (r"\+44[0-9 ]{9,12}", "UK phone number (+44...)"),
    (r"linkedin\.com/in/[a-zA-Z0-9\-]+", "LinkedIn profile URL"),
    (r"github\.com/(?!ankitdixit/job-copilot)[a-zA-Z0-9\-]+(?:/[a-zA-Z0-9\-]+)?", "personal GitHub URL"),
]

# Email-local parts that are obviously placeholders — skip these matches
_PLACEHOLDER_EMAIL_RE = re.compile(
    r"^(you|your|example|user|someone|noreply|no-reply|test|name|email)@", re.IGNORECASE
)

# Files excluded from personal data scan (gitignored personal configs)
SCAN_EXCLUDE = [
    "config/profile.yml",
    "config/standard_answers.yml",
    "config/targets.yml",
    "config/companies/*.yml",
    # Example/template files intentionally contain placeholder patterns
    "config/profile.example.yml",
    "config/standard_answers.example.yml",
    "config/targets.example.yml",
    "config/companies/example_company.yml",
    ".env.example",
    "*.log",
    ".git",
]

# README feature table: column 1 = feature name, column 2 = status (✅ = implemented)
# Maps status emoji to expected file pattern for rough existence check
README_FEATURE_FILES = {
    "Browser agent": "agents/browser_agent.py",
    "Gmail outreach": "tools/send_email.py",
    "Pipeline tracker": "pipeline.md",
    "Health monitoring": "tools/health_check.py",
    "Dashboard": "tools/generate_dashboard.py",
    "Background automation": "automation/",
    "Interview debrief": "agents/debrief_agent.py",
}


def get_tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "ls-files"],
        capture_output=True, text=True,
    )
    return [PROJECT_ROOT / f.strip() for f in result.stdout.splitlines() if f.strip()]


def scan_personal_data(files: list[Path]) -> list[dict]:
    findings = []
    exclude_patterns = [re.compile(e.replace("*", ".*")) for e in SCAN_EXCLUDE]

    for path in files:
        rel = path.relative_to(PROJECT_ROOT)
        if any(p.match(str(rel)) for p in exclude_patterns):
            continue
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue
        for pattern, label in PERSONAL_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                if label == "personal email address" and _PLACEHOLDER_EMAIL_RE.match(match.group()):
                    continue
                line_no = text[:match.start()].count("\n") + 1
                findings.append({
                    "stream": "A",
                    "type": "gap:security",
                    "severity": "HIGH",
                    "file": str(rel),
                    "line": line_no,
                    "match": match.group()[:60],
                    "label": label,
                    "title": f"[gap:security] personal data in tracked file: {rel}:{line_no}",
                    "body": (
                        f"**Pattern:** {label}\n"
                        f"**Match:** `{match.group()[:60]}`\n"
                        f"**File:** `{rel}` line {line_no}\n\n"
                        f"**Fix:** Move to gitignored config file or replace with placeholder."
                    ),
                })
    return findings


def scan_readme_drift() -> list[dict]:
    readme = PROJECT_ROOT / "README.md"
    if not readme.exists():
        return []
    text = readme.read_text()
    findings = []
    for feature, expected_path in README_FEATURE_FILES.items():
        # Only check features marked as implemented in the README
        if feature in text and "✅" in text[text.find(feature):text.find(feature)+100]:
            target = PROJECT_ROOT / expected_path
            if not target.exists():
                findings.append({
                    "stream": "A",
                    "type": "gap:doc",
                    "severity": "MED",
                    "title": f"[gap:doc] README claims '{feature}' implemented but {expected_path} not found",
                    "body": (
                        f"README marks **{feature}** as ✅ implemented, "
                        f"but `{expected_path}` does not exist in the repo.\n\n"
                        f"**Fix:** Either implement `{expected_path}` or update the README status."
                    ),
                })
    return findings


# ── Stream B: interview gap analysis ─────────────────────────────────────────

def parse_gaps_md(path: Path) -> list[dict]:
    """Parse gaps.md markdown table. Expected columns: Skill | Severity | Evidence | Fix | Status."""
    rows = []
    in_table = False
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("|") and "---" not in line:
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if len(cells) >= 3:
                if not in_table:
                    in_table = True  # first row = header
                    continue
                rows.append({
                    "skill": cells[0],
                    "severity": cells[1].upper() if len(cells) > 1 else "MED",
                    "evidence": cells[2] if len(cells) > 2 else "",
                    "fix": cells[3] if len(cells) > 3 else "",
                    "status": cells[4].lower() if len(cells) > 4 else "open",
                })
        else:
            in_table = False
    return rows


def parse_tasks_md(path: Path) -> list[str]:
    """Return all task description text from tasks.md for keyword cross-checking."""
    lines = []
    for line in path.read_text().splitlines():
        if line.strip().startswith("- ["):
            lines.append(line.lower())
    return lines


def scan_interview_gaps(gaps_file: Path, tasks_file: Path | None) -> list[dict]:
    if not gaps_file.exists():
        print(f"[gap_scan] gaps file not found: {gaps_file}", file=sys.stderr)
        return []

    rows = parse_gaps_md(gaps_file)
    open_rows = [r for r in rows if r["status"] == "open"]

    task_lines = parse_tasks_md(tasks_file) if tasks_file and tasks_file.exists() else []

    skill_counts: dict[str, list[dict]] = defaultdict(list)
    for r in open_rows:
        skill_counts[r["skill"]].append(r)

    findings = []

    # Recurring gaps: skill appears in 3+ open rows → escalate
    for skill, entries in skill_counts.items():
        if len(entries) >= 3:
            worst_severity = "HIGH" if any(e["severity"] == "HIGH" for e in entries) else "MED"
            findings.append({
                "stream": "B",
                "type": "gap:interview",
                "severity": "HIGH",
                "title": f"[gap:interview] recurring gap ({len(entries)}×): {skill}",
                "body": (
                    f"**Skill:** {skill}\n"
                    f"**Occurrences:** {len(entries)} open entries in gaps.md\n"
                    f"**Worst severity:** {worst_severity}\n\n"
                    f"**Evidence samples:**\n"
                    + "\n".join(f"- {e['evidence']}" for e in entries[:3])
                    + f"\n\n**Fix:** Escalate to HIGH priority; add a dedicated drill session."
                ),
            })

    # NEEDS WORK entries with no corresponding task
    for skill, entries in skill_counts.items():
        skill_keywords = skill.lower().split()
        has_drill_task = any(
            all(kw in line for kw in skill_keywords[:2])
            for line in task_lines
        )
        if not has_drill_task and any(e["severity"] == "HIGH" for e in entries):
            findings.append({
                "stream": "B",
                "type": "gap:prep",
                "severity": "MED",
                "title": f"[gap:prep] HIGH gap with no drill task: {skill}",
                "body": (
                    f"**Skill:** {skill}\n"
                    f"**Severity:** HIGH in gaps.md\n"
                    f"**No matching task found in tasks.md**\n\n"
                    f"**Fix:** Add a drill task:\n"
                    f"`- [ ] (P1) [est: 1h] [flexible] #jobsearch drill: {skill}`"
                ),
            })

    return findings


# ── GitHub Issue creation ─────────────────────────────────────────────────────

def get_existing_issue_titles() -> set[str]:
    result = subprocess.run(
        ["gh", "issue", "list", "--state", "open", "--limit", "200", "--json", "title"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        return set()
    data = json.loads(result.stdout)
    return {item["title"] for item in data}


def create_issue(finding: dict, existing_titles: set[str]) -> bool:
    if finding["title"] in existing_titles:
        print(f"  [skip] already open: {finding['title']}")
        return False

    label_map = {
        "gap:security": "gap:security",
        "gap:doc": "gap:doc",
        "gap:code": "gap:code",
        "gap:interview": "gap:interview",
        "gap:prep": "gap:prep",
    }
    label = label_map.get(finding["type"], "gap")

    result = subprocess.run(
        ["gh", "issue", "create",
         "--title", finding["title"],
         "--label", label,
         "--body", finding["body"]],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    if result.returncode == 0:
        url = result.stdout.strip()
        print(f"  [created] {url}")
        existing_titles.add(finding["title"])
        return True
    else:
        print(f"  [error] {result.stderr.strip()}", file=sys.stderr)
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Discover code and interview gaps")
    parser.add_argument("--stream", choices=["a", "b", "all"], default="all",
                        help="Which stream to scan (default: all)")
    parser.add_argument("--gaps-file", type=Path, help="Path to gaps.md (Stream B)")
    parser.add_argument("--tasks-file", type=Path, help="Path to tasks.md (Stream B)")
    parser.add_argument("--create-issues", action="store_true",
                        help="Create GitHub Issues for each finding (requires gh CLI)")
    parser.add_argument("--json", action="store_true", help="Output findings as JSON")
    args = parser.parse_args()

    findings = []

    if args.stream in ("a", "all"):
        print("[gap_scan] Stream A — scanning tracked files for personal data...")
        tracked = get_tracked_files()
        findings += scan_personal_data(tracked)
        print("[gap_scan] Stream A — checking README vs code drift...")
        findings += scan_readme_drift()

    if args.stream in ("b", "all"):
        if not args.gaps_file:
            print("[gap_scan] --gaps-file required for Stream B", file=sys.stderr)
            if args.stream == "b":
                sys.exit(1)
        else:
            print(f"[gap_scan] Stream B — analysing {args.gaps_file} ...")
            findings += scan_interview_gaps(args.gaps_file, args.tasks_file)

    if args.json:
        print(json.dumps(findings, indent=2))
        return

    if not findings:
        print("\nNo gaps found.")
        return

    print(f"\n{'STREAM':<8} {'TYPE':<16} {'SEV':<5} TITLE")
    print("-" * 80)
    for f in findings:
        sev = f.get("severity", "?")
        print(f"  {f['stream']:<6} {f['type']:<16} {sev:<5} {f['title']}")

    print(f"\n{len(findings)} finding(s) total.")

    if args.create_issues:
        print("\nCreating GitHub Issues...")
        existing = get_existing_issue_titles()
        created = sum(create_issue(f, existing) for f in findings)
        print(f"{created} new issue(s) created.")


if __name__ == "__main__":
    main()
