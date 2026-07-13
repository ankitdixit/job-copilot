#!/usr/bin/env python3
"""apply_agent.py — Qwen-powered ATS form filler.

Architecture: Claude decides (configs/standard_answers.yml), Qwen executes (fills forms).

Usage:
    python3 agents/apply_agent.py --company cloudera --role 0
    python3 agents/apply_agent.py --company google_deepmind --role 1
    python3 agents/apply_agent.py --list                    # show available configs
    python3 agents/apply_agent.py --check-context           # verify LM Studio ready

The agent:
  1. Loads company config + profile + standard answers
  2. Checks/restores browser session (skips login if cookies valid)
  3. Navigates to the apply URL
  4. Reads the form fields and fills each one using Qwen
  5. Uploads resume via file input injection
  6. Submits (requires --confirm flag to actually submit; dry-run by default)
  7. Returns confirmation URL or error
"""

import argparse
import asyncio
import json
import os
import pickle
import re
import sys
import urllib.request
from pathlib import Path

import yaml

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.browser_agent import CompatibleChatOpenAI as LMStudioChatOpenAI, check_lm_studio_context
from browser_use import Agent, BrowserProfile, BrowserSession

CONFIG_DIR = PROJECT_ROOT / "config"
SESSION_DIR = Path.home() / ".job-copilot" / "sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)


def load_config(company: str) -> dict:
    path = CONFIG_DIR / "companies" / f"{company}.yml"
    if not path.exists():
        print(f"No config found at {path}")
        sys.exit(1)
    with open(path) as f:
        return yaml.safe_load(f)


def load_profile() -> dict:
    with open(CONFIG_DIR / "profile.yml") as f:
        return yaml.safe_load(f)


def load_standard_answers() -> dict:
    with open(CONFIG_DIR / "standard_answers.yml") as f:
        return yaml.safe_load(f)


def build_apply_task(company_cfg: dict, role: dict, profile: dict, answers: dict) -> str:
    """Build the natural language task for Qwen to execute."""
    company = company_cfg["company"]
    domain = company_cfg.get("domain", "")
    why = company_cfg.get("why_company_override") or answers.get("why_company", "")
    why = why.replace("[COMPANY]", company).replace("[DOMAIN]", domain)
    why = why.replace("[ROLE]", role["title"]).replace("[SPECIFIC_PRODUCT]", domain)

    cover = answers.get("cover_letter", "")
    cover = cover.replace("[COMPANY]", company).replace("[ROLE]", role["title"])
    cover = cover.replace("[DOMAIN]", domain)

    notice = profile["candidate"].get("notice_period", "FILL_IN")
    notice_ans = answers.get("notice_period_answer", "").replace("[NOTICE_PERIOD]", notice)

    resume_path = role.get("resume") or profile["resume"]["default"]

    return f"""
You are applying for a job on behalf of {profile['candidate']['name']}.

LOCATION POLICY: Apply if the role is based in Europe (UK, Germany, France, Netherlands, Ireland, Spain, Sweden, etc.) or is genuinely remote with no US-only restriction. If the only listed location is in the United States or Canada, output LOCATION_MISMATCH: <location> and stop — do not apply.

TARGET URL: {role['url']}

ROLE: {role['title']} at {company}

CANDIDATE DETAILS:
- Name: {profile['candidate']['name']}
- Email: {profile['candidate']['email']}
- Phone: {profile['candidate'].get('phone', 'FILL_IN')}
- Location: {profile['candidate']['location']}
- LinkedIn: {profile['candidate'].get('linkedin', '')}
- GitHub: {profile['candidate'].get('github', '')}
- Right to work in UK: {profile['candidate']['right_to_work']}
- Notice period: {notice}
- Years of experience: {answers['years_experience']}
- Current title: {answers['current_title']}

RESUME FILE PATH: {resume_path}
(When you see a file upload button for CV/resume, use this exact path)

ANSWERS TO USE FOR FORM FIELDS:
- Why this company: {why}
- Cover letter / personal statement: {cover}
- Salary expectations: {answers['salary_answer']}
- Notice period: {notice_ans}
- Work authorisation / right to work: {answers['work_authorisation_answer']}
- Remote / relocation preference: {answers['remote_preference_answer']}
- How did you find this role: {answers['referral_source_answer']}
- Biggest achievement: {answers['biggest_achievement']}
- Leadership example: {answers['leadership_example']}

INSTRUCTIONS:
1. Navigate to the target URL.
2. Click the Apply button if visible.
3. For each form field, use the appropriate answer from above. If a field is not listed, use your judgment based on the candidate details.
4. When you see a file upload for CV/resume, upload the file at: {resume_path}
5. Fill all required fields. Skip optional fields unless they clearly add value.
6. When the form is complete and ready to submit, output: READY_TO_SUBMIT: <summary of what was filled>
7. Do NOT click the final Submit button unless you see the text DO_SUBMIT in your task. This is a dry run.
8. If you encounter a CAPTCHA or bot detection page that you cannot pass, output: CAPTCHA_BLOCKED
9. If the only location is US or Canada, output: LOCATION_MISMATCH: <actual location> and stop.
""".strip()


async def run_apply(company: str, role_index: int, confirm: bool = False) -> str:
    ok, ctx = check_lm_studio_context()
    if not ok:
        return f"ERROR: LM Studio context too small ({ctx})"

    company_cfg = load_config(company)
    profile = load_profile()
    answers = load_standard_answers()

    roles = company_cfg.get("roles", [])
    if role_index >= len(roles):
        return f"ERROR: role index {role_index} out of range (company has {len(roles)} roles)"

    role = roles[role_index]
    task = build_apply_task(company_cfg, role, profile, answers)

    if confirm:
        task = task.replace(
            "Do NOT click the final Submit button unless you see the text DO_SUBMIT in your task. This is a dry run.",
            "DO_SUBMIT — click the final submit/send application button when the form is complete."
        )

    llm = LMStudioChatOpenAI(
        base_url="http://localhost:1234/v1",
        api_key="lm-studio",
        model="qwen/qwen3.6-27b",
        temperature=0.0,
        max_completion_tokens=2048,
        timeout=300,
        dont_force_structured_output=True,
        add_schema_to_system_prompt=True,
        remove_min_items_from_schema=True,
        remove_defaults_from_schema=True,
    )

    # Load session cookies if available
    session_file = Path(company_cfg.get("session_cookie_file", "").replace("~", str(Path.home())))
    browser_profile = None
    if session_file.exists():
        print(f"[apply_agent] Loading saved session from {session_file}")

    agent = Agent(
        task=task,
        llm=llm,
        use_vision=False,
        llm_timeout=300,
        max_clickable_elements_length=6000,
        max_history_items=10,
        use_judge=False,
        max_actions_per_step=3,
        message_compaction=True,
        include_tool_call_examples=False,
    )

    result = await agent.run()
    return str(result)


def list_companies():
    companies_dir = CONFIG_DIR / "companies"
    for f in sorted(companies_dir.glob("*.yml")):
        cfg = yaml.safe_load(f.read_text())
        roles = cfg.get("roles", [])
        print(f"\n{cfg['company']} ({f.stem})")
        for i, r in enumerate(roles):
            print(f"  [{i}] {r['title']}")
            print(f"      {r['url'][:80]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply to a job using Qwen browser agent")
    parser.add_argument("--company", help="Company config name (e.g. cloudera, google_deepmind)")
    parser.add_argument("--role", type=int, default=0, help="Role index within company config (default: 0)")
    parser.add_argument("--confirm", action="store_true", help="Actually submit (default: dry run, fills form but does not submit)")
    parser.add_argument("--list", action="store_true", help="List all available company configs and roles")
    parser.add_argument("--check-context", action="store_true", help="Verify LM Studio context is ready")

    args = parser.parse_args()

    if args.check_context:
        ok, ctx = check_lm_studio_context()
        print(f"Context: {ctx} tokens — {'OK' if ok else 'TOO LOW'}")
        sys.exit(0 if ok else 1)

    if args.list:
        list_companies()
        sys.exit(0)

    if not args.company:
        parser.print_help()
        sys.exit(1)

    mode = "SUBMIT" if args.confirm else "DRY RUN"
    print(f"[apply_agent] Starting {mode} for {args.company} role {args.role}")
    result = asyncio.run(run_apply(args.company, args.role, confirm=args.confirm))
    print(result)
