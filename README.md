# Job Copilot

An AI-assisted job search framework. Seed it with target companies, and it helps you with outreach, tracking, and follow-up — so you spend your time preparing for interviews, not managing spreadsheets.

## What it does today (v0.1)

- **Browser agent** — navigates any careers page, extracts open roles, finds contacts
- **Email outreach** — sends personalised cold emails via your Gmail account (OAuth2, no password stored)
- **Pipeline tracker** — `pipeline.md` tracks every opportunity: company, stage, contact, next action

## Planned

- [ ] Automatic discovery — periodic scan of target companies for new roles
- [ ] Dashboard — visual pipeline status (HTML, no server needed)
- [ ] Follow-up automation — flag stale outreach, draft follow-up emails
- [ ] Interview prep integration — link each pipeline entry to prep notes and cheat sheets
- [ ] Cloud deployment — run the background agent on a VPS, not your laptop

## Quickstart

```bash
git clone https://github.com/ankitdixit/job-copilot
cd job-copilot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### Gmail setup (one-time)
1. Go to [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Credentials
2. Create an OAuth 2.0 Client ID (Desktop app)
3. Download as `credentials.json` → place at `~/.config/job-copilot/credentials.json`
4. Run `python3 tools/send_email.py --to yourself@gmail.com --subject test --body hi` to authorize

### Browser agent setup
The agent works with any OpenAI-compatible LLM endpoint:

```bash
# Local (LM Studio with Qwen3)
export LLM_BASE_URL=http://localhost:1234/v1
export LLM_MODEL=qwen3-27b
export LLM_API_KEY=lm-studio

# Cloud (OpenAI)
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_MODEL=gpt-4o
export LLM_API_KEY=sk-...
```

## Usage

```bash
# Find open roles at a target company
python3 agents/browser_agent.py "go to mistral.ai/careers and list all open engineering roles"

# Send an outreach email (always review the draft first)
python3 tools/send_email.py \
  --to engineering@company.com \
  --subject "Staff Engineer — interested in [role]" \
  --body-file outreach/draft.txt

# Update pipeline.md manually after each action
# (automation coming in v0.2)
```

## Design principles

- **Local-first** — works with local LLMs, no mandatory cloud API costs
- **No lock-in** — pipeline is a plain markdown file, emails go through your own Gmail
- **Human in the loop** — never sends email without showing you the full draft first
- **Composable** — each script does one thing; wire them together how you want

## Project structure

```
agents/          AI browser automation
tools/           Utility scripts (email, etc.)
pipeline.md      Your opportunity tracker
```

## Contributing

Open issues welcome. PRs for the planned features above especially appreciated.
