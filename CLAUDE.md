# job-copilot — Claude context

Quick map so Claude doesn't need to read every file to understand the repo.

## What this is
AI-assisted job search automation for senior engineers. Two loops:
- **Outreach loop**: browser agent finds contacts, drafts emails, sends via Gmail
- **Prep loop**: tracks interview gaps, spawns drill tasks, updates dashboard

## LLM stack
All local — no cloud API cost.
- **Runtime**: LM Studio on `http://localhost:1234` (OpenAI-compatible)
- **Default model**: `qwen/qwen3.6-27b` (set in `agents/llm_factory.py` and env `LLM_MODEL`)
- **Qwen3 quirk**: thinking mode is always on in current LM Studio; disable via assistant prefill `{` — see `tools/email_triage.py` for the pattern

## File map

### Entry points
| File | Purpose |
|---|---|
| `run_applications.py` | Main orchestrator — Claude decides targets, Qwen executes each |
| `tools/health_check.py` | Pre-flight: Gmail token + LM Studio status + loaded model |

### Agents (`agents/`)
| File | Purpose |
|---|---|
| `llm_factory.py` | Single construction point for LM Studio client. Change model here. |
| `browser_agent.py` | Playwright-based browser automation; uses `CompatibleChatOpenAI` |
| `apply_agent.py` | End-to-end application flow per company |
| `outreach_agent.py` | Finds contacts, drafts + sends cold emails |
| `debrief_agent.py` | Post-interview: extracts gaps, updates pipeline, spawns tasks |

### Tools (`tools/`)
| File | Purpose |
|---|---|
| `email_triage.py` | Classifies a single email (action/priority/company/summary) via local LLM. **Contains the Qwen3 prefill fix.** |
| `health_check.py` | Gmail token + LM Studio + loaded model check. Returns JSON. |
| `task_runner.py` | Runs YAML task lists against the browser agent |
| `prep_company.py` | Generates structured prep file for a company/round |
| `gap_scan.py` | Scans debriefs for recurring gaps, updates drill targets |
| `send_email.py` | Gmail send via OAuth; always confirm before calling |
| `generate_dashboard.py` | Regenerates `dashboard/index.html` from pipeline.md + tasks |
| `session_store.py` | Lightweight KV store for browser session state |

### Config (`config/`)
Company configs, outreach templates, YAML task definitions.

## Key patterns

**Qwen3 thinking bypass** (in `email_triage.py`, copy this pattern everywhere):
```python
# Add prefill to bypass thinking — LM Studio ignores thinking:{type:disabled}
messages.append({"role": "assistant", "content": "{"})
# After response: prepend '{' if model continued without it
if content and not content.startswith("{"):
    content = "{" + content
# Use raw_decode to stop at first valid JSON, ignoring trailing text
obj, _ = json.JSONDecoder().raw_decode(content)
```

**Model mismatch detection** (in vault_update.py, not yet ported here):
```python
def _loaded_model():
    r = requests.get("http://localhost:1234/v1/models", timeout=3)
    models = r.json().get("data", [])
    return models[0]["id"] if models else ""
```

## What NOT to commit
- `pipeline.md` — personal company data (salaries, contacts, stages)
- `config/targets.yml` / any company-specific configs with real names
- `~/.config/job-copilot/` — OAuth tokens
