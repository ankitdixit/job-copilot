#!/usr/bin/env python3
"""tools/prep_company.py — build a prep plan for a company from the private question bank.

Given a company, this tool:
  1. Ensures a local clone of the interview question-bank repo (default:
     dark-interview-questions), cloning or pulling it IF the running user has
     read access. Access is gated via `gh`/`git` — no access prints a clear
     message and exits cleanly (never crashes).
  2. Locates that company's questions in the bank: `1point3acres/<Company>/`
     (scraped bank) and any curated top-level `<Company>/` folders.
  3. Writes a prep-plan markdown (question checklist grouped by category) and
     prints a summary.

This is the portable version of the Second Brain `prep-company` flow: point it
at the shared repo and it works for anyone the owner has granted access to.

Usage:
    # Owner / any collaborator with read access to the bank repo
    python3 tools/prep_company.py --company databricks
    python3 tools/prep_company.py --company google_deepmind --out prep-plans/

    # Point at an existing local checkout instead of cloning (e.g. for testing)
    python3 tools/prep_company.py --company xai --bank-dir /path/to/dark-interview-questions

    # Use a different bank repo
    python3 tools/prep_company.py --company stripe --bank-repo owner/repo
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

DEFAULT_BANK_REPO = "ankitdixit/dark-interview-questions"
DEFAULT_BANK_DIR = Path.home() / ".job-copilot" / "dark-interview-questions"

# Where scraped question banks live inside the repo, relative to its root.
SCRAPED_SUBDIR = "1point3acres"

CATEGORY_ORDER = ["Coding", "System Design", "Behavioral", "Other"]


# ── Bank repo: clone / pull, gated on access ─────────────────────────────────

def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd) if cwd else None)


def has_repo_access(repo: str) -> bool:
    """True if the running user can read `repo`. Uses gh; falls back to a git ls-remote."""
    gh = _run(["gh", "repo", "view", repo, "--json", "name"])
    if gh.returncode == 0:
        return True
    # gh unavailable or not authed — try an unauthenticated/https ls-remote
    ls = _run(["git", "ls-remote", f"https://github.com/{repo}.git", "HEAD"])
    return ls.returncode == 0


def ensure_bank(repo: str, bank_dir: Path) -> Path | None:
    """Ensure a readable local checkout of the bank. Returns its path, or None if no access."""
    if bank_dir.exists() and (bank_dir / ".git").exists():
        print(f"[prep] Updating bank at {bank_dir} ...")
        pull = _run(["git", "pull", "--ff-only"], cwd=bank_dir)
        if pull.returncode != 0:
            print(f"[prep] warning: git pull failed ({pull.stderr.strip()}); using existing checkout.",
                  file=sys.stderr)
        return bank_dir

    if not has_repo_access(repo):
        print(
            f"\n[prep] No read access to '{repo}'.\n"
            f"       Ask the repo owner to add you as a collaborator "
            f"(GitHub → repo → Settings → Collaborators), then re-run.\n"
            f"       Or pass --bank-dir to point at a local checkout you already have.",
            file=sys.stderr,
        )
        return None

    print(f"[prep] Cloning {repo} → {bank_dir} ...")
    bank_dir.parent.mkdir(parents=True, exist_ok=True)
    clone = _run(["gh", "repo", "clone", repo, str(bank_dir)])
    if clone.returncode != 0:
        clone = _run(["git", "clone", f"https://github.com/{repo}.git", str(bank_dir)])
    if clone.returncode != 0:
        print(f"[prep] clone failed: {clone.stderr.strip()}", file=sys.stderr)
        return None
    return bank_dir


# ── Locate + parse a company's questions ─────────────────────────────────────

def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def find_company_dirs(bank_dir: Path, company: str) -> list[tuple[str, Path]]:
    """Return [(source_label, questions_dir)] for every folder in the bank matching `company`."""
    target = _norm(company)
    hits: list[tuple[str, Path]] = []

    search_roots = [
        ("bank", bank_dir / SCRAPED_SUBDIR),   # scraped 1point3acres bank
        ("curated", bank_dir),                 # curated top-level company folders
    ]
    for label, root in search_roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if _norm(child.name) == target:
                qdir = child / "Questions"
                qdir = qdir if qdir.is_dir() else child
                hits.append((f"{label}:{child.name}", qdir))
    return hits


def parse_question(md_path: Path) -> dict:
    """Extract title + category from a scraped/curated question markdown file."""
    title = md_path.stem
    category = "Other"
    try:
        text = md_path.read_text(errors="replace")
    except Exception:
        return {"title": title, "category": category, "file": md_path}

    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        title = m.group(1).strip()
    tags = re.search(r"^\*\*Tags:\*\*\s*(.+)$", text, re.MULTILINE)
    if tags:
        for cat in CATEGORY_ORDER:
            if re.search(rf"`{re.escape(cat)}`", tags.group(1)):
                category = cat
                break
    return {"title": title, "category": category, "file": md_path}


def collect_questions(qdir: Path) -> list[dict]:
    if not qdir.is_dir():
        return []
    return [parse_question(p) for p in sorted(qdir.glob("*.md"))]


# ── Build the prep plan ──────────────────────────────────────────────────────

def build_plan(company: str, sources: list[tuple[str, list[dict]]]) -> str:
    total = sum(len(qs) for _, qs in sources)
    lines = [
        f"# Prep plan — {company}",
        "",
        f"Generated {date.today().isoformat()} · {total} questions from the shared bank.",
        "",
        "> Drill rule: pick the highest-severity category, do one timed rep out loud, "
        "check against the fix rule, then move on. Reading ≠ a rep.",
        "",
    ]
    for source_label, qs in sources:
        if not qs:
            continue
        lines.append(f"## Source: {source_label} ({len(qs)})")
        by_cat: dict[str, list[dict]] = {c: [] for c in CATEGORY_ORDER}
        for q in qs:
            by_cat.setdefault(q["category"], []).append(q)
        for cat in CATEGORY_ORDER:
            items = by_cat.get(cat) or []
            if not items:
                continue
            lines.append(f"\n### {cat} ({len(items)})")
            for q in items:
                lines.append(f"- [ ] {q['title']}")
        lines.append("")
    return "\n".join(lines)


def _resolve_llm() -> dict | None:
    """Pick the LLM for the web fallback: local LM Studio if it's running, else a
    configured cloud LLM (LLM_BASE_URL/LLM_MODEL/LLM_API_KEY). None if neither is available."""
    # 1. Prefer local LM Studio if it's up with a usable chat model.
    try:
        with urllib.request.urlopen("http://127.0.0.1:1234/v1/models", timeout=3) as r:
            models = [m["id"] for m in json.loads(r.read()).get("data", [])]
        chat = [m for m in models if "embed" not in m.lower()]
        qwen = [m for m in chat if "qwen" in m.lower()]
        # Browsing wants a general/instruct model, not a code model.
        model = (next((m for m in qwen if "coder" not in m.lower()), None)
                 or (qwen[0] if qwen else (chat[0] if chat else None)))
        if model:
            return {"LLM_BASE_URL": "http://localhost:1234/v1", "LLM_MODEL": model,
                    "LLM_API_KEY": "lm-studio", "_which": f"local LM Studio ({model})"}
    except Exception:
        pass
    # 2. Otherwise use whatever model is configured via env (cloud or remote).
    if os.getenv("LLM_API_KEY") and os.getenv("LLM_BASE_URL"):
        return {"_which": f"configured LLM ({os.getenv('LLM_MODEL', 'default')})"}  # inherit env as-is
    return None


def web_fallback(company: str, out: Path, timeout: int = 240) -> bool:
    """Best-effort: search the web for the company's questions via the browser agent.

    Used when the shared bank isn't accessible or doesn't cover the company. Needs an
    LLM endpoint (LM Studio) + browser-use, which the browser agent already wires up.
    Shelled out (not imported) so this tool stays dependency-light when the bank works.
    """
    agent = PROJECT_ROOT / "agents" / "browser_agent.py"
    if not agent.exists():
        print("[prep] web fallback unavailable (agents/browser_agent.py missing).", file=sys.stderr)
        return False
    task = (
        f"Search the web for '{company} software engineer interview questions'. "
        f"Open 2-3 of the most relevant results (Glassdoor, LeetCode discuss, engineering blogs, 1point3acres). "
        f"List every specific technical interview question or problem you find as a markdown bullet list, "
        f"grouped under Coding / System Design / Behavioral where possible. Output only the list."
    )
    llm = _resolve_llm()
    if llm is None:
        print("[prep] No local LM Studio running and no cloud LLM configured for the web fallback.\n"
              "       Start LM Studio with a model loaded, or set LLM_BASE_URL / LLM_MODEL / LLM_API_KEY\n"
              "       for a cloud provider (OpenAI/Anthropic/etc.).", file=sys.stderr)
        return False
    env = os.environ.copy()
    env.update({k: v for k, v in llm.items() if not k.startswith("_")})
    print(f"[prep] Searching the web via the browser agent using {llm['_which']} (up to {timeout}s)...")
    proc = subprocess.run(
        [sys.executable, str(agent), "--max-runtime", str(timeout), task],
        capture_output=True, text=True, env=env,
    )
    body = (proc.stdout or "").strip()
    if proc.returncode != 0 or not body:
        err = ((proc.stderr or "").strip().splitlines() or ["no output"])[-1]
        print(f"[prep] web fallback failed: {err[:200]}\n"
              f"       (needs LM Studio running with a model loaded, and browser-use installed.)",
              file=sys.stderr)
        return False
    out.mkdir(parents=True, exist_ok=True)
    out_path = out / f"{_norm(company)}-web-{date.today().isoformat()}.md"
    out_path.write_text(
        f"# Prep plan (web-sourced) — {company}\n\n"
        f"Generated {date.today().isoformat()} via web search — best-effort, verify before relying on it.\n\n"
        f"{body}\n"
    )
    print(f"[prep] web-sourced plan → {out_path}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a company prep plan from the shared question bank")
    parser.add_argument("--company", required=True, help="Company name (e.g. databricks, google_deepmind)")
    parser.add_argument("--bank-repo", default=DEFAULT_BANK_REPO, help="Question-bank GitHub repo (owner/name)")
    parser.add_argument("--bank-dir", type=Path, default=DEFAULT_BANK_DIR,
                        help="Local checkout of the bank (cloned/pulled if it's the default managed path)")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "prep-plans",
                        help="Directory to write the prep plan into")
    parser.add_argument("--stdout", action="store_true", help="Print the plan instead of writing a file")
    parser.add_argument("--web", action="store_true",
                        help="Skip the bank and search the web for questions (needs LM Studio + browser agent)")
    args = parser.parse_args()

    # Resolve the bank unless --web forces a web-only run. A user-supplied --bank-dir
    # is used as-is; the managed default is cloned/pulled (None if no access).
    bank: Path | None = None
    if not args.web:
        if args.bank_dir == DEFAULT_BANK_DIR:
            bank = ensure_bank(args.bank_repo, args.bank_dir)
        elif args.bank_dir.is_dir():
            bank = args.bank_dir
        else:
            print(f"[prep] --bank-dir not found: {args.bank_dir}", file=sys.stderr)

    dirs = find_company_dirs(bank, args.company) if bank else []

    if dirs:
        sources = [(label, collect_questions(qdir)) for label, qdir in dirs]
        total = sum(len(qs) for _, qs in sources)
        plan = build_plan(args.company, sources)
        if args.stdout:
            print(plan)
        else:
            args.out.mkdir(parents=True, exist_ok=True)
            out_path = args.out / f"{_norm(args.company)}-{date.today().isoformat()}.md"
            out_path.write_text(plan)
            print(f"[prep] {total} questions across {len(dirs)} source(s) → {out_path}")
        return

    # No bank data (no access, not covered, or --web) → best-effort web search.
    if not args.web:
        reason = "bank unavailable (no repo access)" if bank is None else f"'{args.company}' not in the bank"
        print(f"[prep] {reason} — falling back to a web search.", file=sys.stderr)
    if not web_fallback(args.company, args.out):
        sys.exit(1)


if __name__ == "__main__":
    main()
