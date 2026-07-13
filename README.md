# Job Copilot

An AI-assisted job search system for senior engineers. Automates the grind — outreach, tracking, follow-up, scheduling, prep tracking — so you spend your time preparing for interviews, not managing a spreadsheet.

**[→ Live demo](https://ankitdixit.github.io/job-copilot/dashboard/demo.html)** — sample pipeline, no setup needed.

![Dashboard — pipeline, Gantt, and comp chart](docs/dashboard-overview.png)

![Dashboard — prep levels and stage board](docs/dashboard-prep.png)

### What it does

- **Automated outreach** — browser agent finds the right contact at any company, drafts a personalised email, sends via your own Gmail account after you approve
- **Threaded follow-up** — flags stale outreach after N days, drafts a follow-up in the same Gmail thread
- **Pipeline tracking** — every company in one markdown file; stage, next action, contact, and date updated automatically
- **Interview scheduling support** — 14-day Gantt view of confirmed rounds; alerts for upcoming interviews pulled from your task list
- **Comp vs fit visualisation** — scatter plot of every active company by total comp and role fit so you can see at a glance which are genuine targets vs. practice rounds
- **Prep gap tracking** — every interview debrief extracts gaps with severity (HIGH/MED) and evidence; exercise tasks spawned automatically
- **Prep level chart** — readiness per topic on a 1–5 scale, updated after each practice session, sorted worst-first so the weak spots are impossible to ignore
- **Stage board** — kanban columns (Applied → Screening → Interviewing → Final Round → Offer) regenerated hourly from your pipeline
- **Background automation** — hourly Gmail scan via local LLM (Qwen, zero API cost); dashboard regenerates without you touching anything
- **Local-first, no lock-in** — plain markdown files, your own Gmail account, runs on LM Studio for free or any OpenAI-compatible endpoint

---

## How it works

There are two loops. The outreach loop fills your pipeline. The prep loop raises your interview bar.

**Outreach loop**

```mermaid
%%{init: {'theme': 'dark'}}%%
flowchart LR
    A([🎯 Target company]) --> B[Browser agent\nfinds contact + open roles]
    B --> C[Draft outreach email]
    C --> D{You review\nand approve}
    D -->|Yes| E[Gmail API sends]
    D -->|Edit| C
    E --> F[pipeline.md updated]
    F --> G[Dashboard shows stage]
    G --> H{Reply received?}
    H -->|Yes| I[Advance stage\nSchedule interview]
    H -->|No after 7d| J[Follow-up flagged]
    J --> D
    I --> K([🎉 Interview])
```

**Prep loop — what makes this different from a spreadsheet**

```mermaid
%%{init: {'theme': 'dark'}}%%
flowchart LR
    K([Interview]) --> L[Transcript\nor manual debrief]
    L --> M[Debrief note:\nwhat was asked\nwhat went well / badly]
    M --> N[gaps.md:\nnew gaps with\nseverity + evidence]
    N --> O[Exercise tasks\nspawned in tasks.md]
    O --> P[Practice session]
    P --> Q[Prep level updated\nin dashboard]
    Q --> K
```

Every interview feeds back into preparation for the next one. The dashboard shows where you are on each topic — not just where you are in each pipeline.

## What this is

Job searching at senior/staff level is a full-time job: tracking 20+ companies, writing personalised outreach, following up at the right time, keeping notes on every conversation, figuring out which gaps you revealed in the last round. This project automates the mechanical parts using AI so you can focus on the parts that actually matter — preparation and conversation.

**The outreach loop:**

```
You add a target company
  → Copilot finds the right contact and drafts an outreach email
  → You review and send (one command)
  → Pipeline tracker updates automatically
  → Follow-up is flagged if no reply after N days
  → Dashboard shows your full pipeline at a glance
```

**The prep loop (runs in parallel):**

```
Interview ends
  → Drop transcript into transcripts/ (or debrief manually)
  → Debrief note created: questions asked, what landed, what didn't
  → gaps.md updated: new gap + severity + evidence from that specific call
  → Exercise tasks spawned in tasks.md: one concrete fix per gap
  → Practice fills the gap
  → Prep level rises — visible in the dashboard chart
  → Next interview: same pattern, surfacing the next layer
```

---

## What's working today (v0.1)

| Feature | Status | Details |
|---------|--------|---------|
| Browser agent | ✅ | Navigates any careers page, finds contacts, extracts job details |
| Gmail outreach | ✅ | Sends via your Gmail account (OAuth2, no password stored) |
| Pipeline tracker | ✅ | `pipeline.md` — one row per company, plain markdown |
| Health monitoring | ✅ | Checks Gmail token validity and automation health every 2h |
| Dashboard | ✅ | HTML file, opens locally — visual pipeline by stage |
| Background automation | ✅ | LaunchAgent (macOS) / systemd (Linux) for periodic checks |
| Interview debrief | ✅ | Reads meeting transcripts, creates structured debrief notes, updates pipeline |
| Prep notes + cheat sheets | ✅ | Per-company prep folders, topic cheat sheets, gap tracker |

## Planned

| Feature | Target |
|---------|--------|
| Auto job discovery | v0.2 — periodic scan of target company career pages |
| Follow-up automation | v0.2 — flag stale outreach, draft follow-ups |
| Standalone prep module | v0.3 — extract from Obsidian vault into portable format |
| Cloud deployment | v0.3 — Dockerfile + setup guide, run on a €4/mo VPS |
| Application assist | v0.3 — navigate to job application, hand off to Simplify/autofill |

---

## Architecture

```
job-copilot/
├── agents/
│   ├── browser_agent.py     # AI browser automation (browser-use + local/cloud LLM)
│   ├── llm_factory.py       # Single LLM construction point (reads LLM_BASE_URL/MODEL/API_KEY env)
│   ├── apply_agent.py       # ATS form filler (Qwen-powered; dry-run by default)
│   └── outreach_agent.py    # Finds recruiter contact, drafts outreach email
├── tools/
│   ├── send_email.py        # Gmail API sender (OAuth2, --attachment support)
│   ├── email_triage.py      # Classify emails via local Qwen (standalone, no personal config)
│   ├── generate_dashboard.py# pipeline.md + tasks.md → HTML dashboard (standalone)
│   ├── session_store.py     # Browser session persistence (pickle-based)
│   └── health_check.py      # Monitors token validity and automation health
├── config/
│   ├── profile.example.yml           # → copy to profile.yml and fill in your details
│   ├── standard_answers.example.yml  # → copy to standard_answers.yml
│   ├── targets.example.yml           # → copy to targets.yml (your automation queue)
│   └── companies/
│       └── example_company.yml       # → copy to <company>.yml for each target
├── run_applications.py      # Orchestrator: reads config/targets.yml, runs agents
├── Makefile                 # make setup / config / smoke / dashboard / list
├── scripts/
│   └── smoke_test.sh        # Fresh-clone verification (no LM Studio or Gmail required)
├── dashboard/
│   └── index.html           # Visual pipeline dashboard (open as local file)
├── automation/
│   ├── com.jobcopilot.health.plist   # macOS LaunchAgent (runs health_check every 2h)
│   └── job-copilot-health.service   # Linux systemd service
├── pipeline.md              # Your opportunity tracker (edit this directly)
└── requirements.txt
```

**LLM layer:** The browser agent works with any OpenAI-compatible endpoint. Run it with a local model (LM Studio, Ollama) for zero ongoing cost, or point it at OpenAI/Anthropic for speed and accuracy. Qwen3 27B works well locally for navigation tasks.

**Email layer:** OAuth2 via Gmail API. Credentials stay on your machine, never in the repo. The send script requires you to see and approve the full draft before anything goes out.

**Pipeline layer:** Plain markdown. No database, no sync, no lock-in. `pipeline.md` is the source of truth — edit it directly, or let the scripts update it.

---

## Quickstart

```bash
git clone https://github.com/ankitdixit/job-copilot
cd job-copilot
make setup      # creates venv, installs deps, installs playwright
make config     # copies example configs (skips files that already exist)
# Edit config/profile.yml with your details
make smoke      # verify the clone is working end-to-end
```

`make smoke` checks Python version, pyyaml, playwright, config files, and all tool CLIs. It does **not** require LM Studio or Gmail credentials — those come later.

<details>
<summary>Manual setup (without make)</summary>

### 1. Clone and install

```bash
git clone https://github.com/ankitdixit/job-copilot
cd job-copilot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure

Copy the example configs and fill in your details:

```bash
cp config/profile.example.yml config/profile.yml
cp config/standard_answers.example.yml config/standard_answers.yml
cp config/targets.example.yml config/targets.yml
```

Edit `config/profile.yml` with your name, email, LinkedIn, resume path, and comp expectations.

Edit `config/standard_answers.yml` with your STAR stories, cover letter, and logistics answers.
All personal configs are gitignored — they never end up in the repo.

</details>

### 3. Gmail setup (one-time)

You need a Google Cloud project to send email via Gmail API.

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → Enable **Gmail API**
3. Go to **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID** → Desktop app
4. Download the JSON → save as `~/.config/job-copilot/credentials.json`
5. Run the auth flow once:
   ```bash
   python3 tools/send_email.py --to you@gmail.com --subject "test" --body "hello"
   ```
   A browser window opens → click Allow → token saved to `~/.config/job-copilot/token_send.json`

After this, email sending works silently from the command line.

### 4. Set up background monitoring (optional)

**macOS:**
```bash
cp automation/com.jobcopilot.health.plist ~/Library/LaunchAgents/
sed -i '' "s|/path/to/job-copilot|$(pwd)|g" ~/Library/LaunchAgents/com.jobcopilot.health.plist
launchctl load ~/Library/LaunchAgents/com.jobcopilot.health.plist
```

**Linux (systemd):**
```bash
cp automation/job-copilot-health.service ~/.config/systemd/user/
sed -i "s|/path/to/job-copilot|$(pwd)|g" ~/.config/systemd/user/job-copilot-health.service
systemctl --user enable --now job-copilot-health.service
```

---

## Usage

### Find open roles at a target company

```bash
source .venv/bin/activate
python3 agents/browser_agent.py "go to mistral.ai/careers and list all open engineering roles with titles and links"
```

### Run the automation queue

```bash
# List your targets (from config/targets.yml)
python3 run_applications.py --list

# Run outreach for a single company
python3 run_applications.py --outreach example_company --role 0

# Run ATS apply (dry-run by default; --confirm to actually submit)
python3 run_applications.py --apply example_company --role 0

# Run all targets in your queue
python3 run_applications.py --run-all
```

Edit `config/targets.yml` to add or remove companies from your automation queue.

### Draft and send outreach

Always review before sending. Never sends automatically.

```bash
# Draft your email in a file
cat > /tmp/outreach.txt << 'EOF'
Hi [Name],

I came across [Company] and was impressed by [specific thing].
I'm a Staff Engineer with a background in [X, Y, Z] and I'm exploring
opportunities in AI infrastructure. Would you have 20 minutes for a
quick call?

[Your name]
EOF

# Preview and send
python3 tools/send_email.py \
  --to name@company.com \
  --subject "Staff Engineer — interested in [Company]" \
  --body-file /tmp/outreach.txt
```

### Reply in an existing Gmail thread

Pass `--thread-id` and `--in-reply-to` to place the reply inside an existing conversation (so it threads correctly in Gmail rather than starting a new one). Get both IDs from the Gmail API or from `mcp__gmail get_thread` output.

```bash
python3 tools/send_email.py \
  --to name@company.com \
  --subject "Re: Staff Engineer — interested in [Company]" \
  --body-file /tmp/followup.txt \
  --thread-id <gmail-thread-id> \
  --in-reply-to <gmail-message-id>
```

| Flag | Description |
|------|-------------|
| `--thread-id` | Gmail thread ID — places the message inside an existing thread |
| `--in-reply-to` | Gmail message ID of the message being replied to (sets `In-Reply-To` / `References` headers) |

**Optional footer:** Set `EMAIL_FOOTER` in your `.env` to append a fixed line to every outbound email (e.g. a P.S. or a note about your availability). Leave it empty (the default) to send with no footer.

### View dashboard

Open `dashboard/index.html` in your browser. It reads from `pipeline.md` and shows stage, last action, and days since contact for each company.

### Update your pipeline

Edit `pipeline.md` directly after each action. Columns: Company, Role, Stage, Next Action, Contact, Date Added.

---

## LLM options

| Setup | Cost | Speed | Best for |
|-------|------|-------|---------|
| LM Studio + Qwen3 27B | Free | ~2 min/task | Local, private, no API cost |
| LM Studio + smaller model (7B) | Free | ~30s/task | Faster, less accurate |
| OpenAI GPT-4o | ~$0.01–0.10/task | ~5s/task | Best accuracy, cloud |
| Anthropic Claude | ~$0.01–0.10/task | ~5s/task | Best reasoning, cloud |

To use a cloud provider, set environment variables (or add to `.env`):
```bash
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_MODEL=gpt-4o
export LLM_API_KEY=sk-your-key-here
```

All agents read these via `agents/llm_factory.py` — no code changes needed to switch providers.

---

## Interview prep integration

This is the part that separates Job Copilot from a tracker. Every interview generates signal about where your gaps are. The system captures that signal and turns it into preparation.

### The gap tracking loop

**Step 1 — Debrief after every interview**

Drop the transcript into `transcripts/` (Snaply exports markdown directly; any recorder works). Then run:

```bash
# Reads transcript, classifies the call, creates structured debrief
ingest-meeting
```

Or debrief manually if no transcript:

```bash
interview-debrief
```

The debrief note captures: questions asked (verbatim where possible), what landed, what didn't, gaps surfaced with evidence.

**Step 2 — Gap extraction**

Every gap surfaced in a debrief gets added to `gaps.md` with:
- **What**: the specific skill or behaviour that failed
- **Severity**: HIGH (blocks offers at target level) or MED (weakens performance)
- **Evidence**: the specific moment from the call — e.g. "couldn't enumerate IPC primitives; interviewer had to guide to pipes and sockets"
- **Fix plan**: one concrete practice action

Example entry auto-added after a C++ screen:
```
| C++ smart pointers vocab | HIGH | xAI screen: described concept without terms; missed cyclic ref | Study shared_ptr mechanics, weak_ptr for cycles; practice 60s cold explanation | open |
```

**Step 3 — Exercise tasks**

Each new gap spawns a task in `tasks.md`:
```
- [ ] (P1) [est: 1h] [flexible] #jobsearch nail shared_ptr/weak_ptr/unique_ptr cold — 60s answer
```

**Step 4 — Track prep level**

After each practice session, update your prep level tracking. The dashboard generates a bar chart showing readiness per topic (1=unknown → 5=fluent under pressure), sorted HIGH-severity gaps first.

### Second Brain integration

The full system runs inside an Obsidian vault with:
- `pipeline.md` — company tracker
- `gaps.md` — skill gap backlog (grows after each debrief)
- `tasks.md` — prioritised action list (P1/P2/P3)
- `transcripts/` — auto-ingested meeting transcripts
- `debriefs/` — structured notes per interview round
- `plans/` — weekly plans anchored to interview dates

**Full orchestration (`vault_update.py`):** The complete personal setup runs a macOS LaunchAgent that scans Gmail every hour, triages emails via a local Qwen model (using `tools/email_triage.py`), extracts tasks, and regenerates a local HTML dashboard (using `tools/generate_dashboard.py`) — all without any cloud dependency or ongoing API cost.

The personal scheduler and vault configuration are not in this repo, but both tools work standalone:

```bash
# Triage a single email via local Qwen
python3 tools/email_triage.py --subject "Interview invite" --body "Hi, we'd like..." --url http://127.0.0.1:1234

# Generate dashboard from your pipeline + tasks files
python3 tools/generate_dashboard.py --pipeline pipeline.md --tasks tasks.md --output dashboard/schedule.html
```

Run `--help` on either tool to see all options. LM Studio must be running with a Qwen model loaded for `email_triage.py`.

## Design principles

- **Human in the loop on outreach** — the send script shows you the full draft (to, subject, body) and waits for explicit confirmation. No email goes out automatically.
- **Local-first** — works with local LLMs, no mandatory cloud API cost.
- **No lock-in** — pipeline is plain markdown, emails go through your own Gmail account.
- **Composable** — each script does one thing. Wire them together in whatever way fits your workflow.
- **Private by default** — credentials never leave your machine, nothing is sent to third parties except the LLM endpoint you configure.

---

## Contributing

Issues and PRs welcome. The highest-value contributions right now:

- **Cloud deployment** — Dockerfile + setup guide that gets someone running on a VPS in under 10 minutes
- **Job discovery** — script that takes a list of target companies and checks their careers pages for new roles
- **Follow-up logic** — scan pipeline.md for stale outreach and surface a draft follow-up

See [open issues](https://github.com/ankitdixit/job-copilot/issues) for the full roadmap.
