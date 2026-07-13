#!/usr/bin/env python3
"""outreach_agent.py — Qwen finds recruiter/HM contact and drafts a personalised outreach email.

Architecture: Claude wrote the templates and targeting rules; Qwen executes the research and drafting.

Usage:
    python3 agents/outreach_agent.py --company dataiku
    python3 agents/outreach_agent.py --company mistral --send   # send after showing draft

The agent:
  1. Loads company config + profile + standard answers
  2. Uses browser_use + Qwen to find the right contact (recruiter or HM) for the role
  3. Drafts a personalised outreach email using the candidate profile + why_company
  4. Prints the full draft (To / Subject / Body) for review
  5. Only sends if --send flag is passed AND user confirms (respects email-confirm rule)
"""

import argparse
import asyncio
import re
import subprocess
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.browser_agent import check_lm_studio_context
from agents.llm_factory import get_llm
from browser_use import Agent

CONFIG_DIR = PROJECT_ROOT / "config"
SEND_SCRIPT = PROJECT_ROOT / "tools" / "send_email.py"


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


def build_outreach_task(company_cfg: dict, role: dict, profile: dict, answers: dict) -> str:
    company = company_cfg["company"]
    domain = company_cfg.get("domain", "")
    why = company_cfg.get("why_company_override") or answers.get("why_company", "")
    why = why.replace("[COMPANY]", company).replace("[DOMAIN]", domain)
    why = why.replace("[ROLE]", role["title"]).replace("[SPECIFIC_PRODUCT]", domain)

    return f"""
You are helping {profile['candidate']['name']} send a job outreach email for the role:
  Role: {role['title']}
  Company: {company}
  Apply URL: {role['url']}

STEP 1 — Find the right contact:
  Search LinkedIn or the company website for the hiring manager or engineering recruiter
  responsible for this role or team. Look for:
  - Engineering recruiter at {company} in London
  - Engineering manager or VP of Engineering for the relevant team
  - The person who posted the job listing if visible

  Good signals: "Recruiter at {company}", "Talent Acquisition", "Engineering Manager - [team]"
  Avoid: HR generalists, sales recruiters, non-engineering contacts

STEP 2 — Find their email:
  Try: first.last@{company.lower().replace(' ', '').replace('/', '')}.com
  Or look for email format on their LinkedIn profile, company about page, or blog posts.
  If you cannot find a direct email, find their LinkedIn URL instead.

STEP 3 — Draft the outreach email:
  Use the following structure. Be concise — 4 short paragraphs max.

  Subject: {role['title']} — {profile['candidate']['name']}

  Hi [Name],

  Paragraph 1: One sentence on why {company} / this specific role.
  Use this context: {why[:300]}

  Paragraph 2: Two sentences on most relevant experience:
{answers.get('outreach_bullets', '  - [YOUR_COMPANY_1]: [impact bullet]\n  - [YOUR_COMPANY_2]: [impact bullet]')}

  Paragraph 3: One sentence on what you bring to this specific team.

  Paragraph 4: Call to action — happy to share CV or jump on a 20-min call.

  Sign off:
  Best,
  {profile['candidate']['name']}
  {profile['candidate']['email']}
  {profile['candidate'].get('linkedin', '')}

STEP 4 — Output the result in this exact format:
  CONTACT_NAME: <name or "not found">
  CONTACT_EMAIL: <email or "not found">
  CONTACT_LINKEDIN: <linkedin URL or "not found">
  SUBJECT: <email subject>
  BODY:
  <full email body>
  END_BODY

Do not send the email. Output the draft only.
""".strip()


async def run_outreach(company: str, role_index: int) -> dict:
    ok, ctx = check_lm_studio_context()
    if not ok:
        return {"error": f"LM Studio context too small ({ctx})"}

    company_cfg = load_config(company)
    profile = load_profile()
    answers = load_standard_answers()

    roles = company_cfg.get("roles", [])
    if role_index >= len(roles):
        return {"error": f"role index {role_index} out of range"}

    role = roles[role_index]
    task = build_outreach_task(company_cfg, role, profile, answers)

    llm = get_llm(temperature=0.2)  # slight creativity for email drafting

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

    raw = str(await agent.run())

    # Parse structured output
    result = {"raw": raw, "company": company, "role": role["title"]}
    for field in ["CONTACT_NAME", "CONTACT_EMAIL", "CONTACT_LINKEDIN", "SUBJECT"]:
        m = re.search(rf"{field}:\s*(.+)", raw)
        result[field.lower()] = m.group(1).strip() if m else "not found"

    body_m = re.search(r"BODY:\n(.*?)END_BODY", raw, re.DOTALL)
    result["body"] = body_m.group(1).strip() if body_m else raw

    return result


def send_outreach(draft: dict, profile: dict):
    """Show draft and ask for confirmation before sending."""
    print("\n" + "="*60)
    print("EMAIL DRAFT — review before sending")
    print("="*60)
    print(f"To:      {draft.get('contact_name')} <{draft.get('contact_email')}>")
    print(f"Subject: {draft.get('subject')}")
    print("-"*60)
    print(draft.get("body"))
    print("="*60)

    if draft.get("contact_email") in ("not found", None):
        print("\nNo email found. Cannot send. Share the LinkedIn URL with recruiter manually:")
        print(draft.get("contact_linkedin"))
        return

    confirm = input("\nSend this email? [yes/no]: ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        return

    cmd = [
        "python3", str(SEND_SCRIPT),
        "--to", draft["contact_email"],
        "--subject", draft["subject"],
        "--body", draft["body"],
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("Sent.")
    else:
        print(f"Send failed: {result.stderr}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True)
    parser.add_argument("--role", type=int, default=0)
    parser.add_argument("--send", action="store_true", help="Offer to send after showing draft")
    args = parser.parse_args()

    profile = load_profile()
    draft = asyncio.run(run_outreach(args.company, args.role))

    if "error" in draft:
        print(f"Error: {draft['error']}")
        sys.exit(1)

    print(f"\nContact: {draft.get('contact_name')} — {draft.get('contact_email')}")
    print(f"LinkedIn: {draft.get('contact_linkedin')}")
    print(f"\nSubject: {draft.get('subject')}")
    print(f"\n{draft.get('body')}")

    if args.send:
        send_outreach(draft, profile)
