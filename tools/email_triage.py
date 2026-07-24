#!/usr/bin/env python3
"""email_triage.py — classify an email via a local Qwen model running in LM Studio.

Extracted from the personal vault_update.py orchestrator so it can be used standalone
or imported by other tools without any personal configuration.

Usage:
    python3 tools/email_triage.py --subject "Interview invite" --body "Hi, we'd like..."
    python3 tools/email_triage.py --subject "..." --body "..." --url http://127.0.0.1:1234 --model qwen/qwen3-27b

Returns JSON: {"action": ..., "priority": ..., "company": ..., "summary": ...}

Actions:
    reply_needed      — sender expects a response (e.g. scheduling, interest confirmation)
    schedule_interview — calendar invite or scheduling link received
    reject            — rejection notice
    informational     — no action needed (newsletter, FYI, etc.)
    spam              — not relevant

Requires LM Studio running with a Qwen model loaded. No API key needed.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request

SYSTEM_PROMPT = (
    "You are an email classifier for a job seeker. "
    "Classify the email and return ONLY a valid JSON object — no prose, no markdown fences.\n\n"
    "JSON fields:\n"
    '  "action": one of [reply_needed, schedule_interview, reject, informational, spam]\n'
    '  "priority": one of [high, medium, low]\n'
    '  "company": company name string, or "unknown"\n'
    '  "summary": one sentence describing what the email says\n\n'
    "Do not include any text outside the JSON object."
)


def triage_email(
    subject: str,
    body: str,
    lm_studio_url: str = "http://127.0.0.1:1234",
    model: str = "qwen/qwen3-27b",
) -> dict:
    """Classify a single email using a local Qwen model via LM Studio.

    Returns dict with keys: action, priority, company, summary.
    Raises RuntimeError if LM Studio is unreachable or the model call fails.
    """
    prompt = f"Subject: {subject}\n\nBody:\n{body[:2000]}"

    is_qwen3 = "qwen3" in model.lower()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    # Prefill the assistant turn with "{" — forces Qwen3 to continue generating JSON
    # directly without opening a <think> block. Bypasses thinking mode reliably since
    # LM Studio ignores the thinking:{type:disabled} API parameter.
    if is_qwen3:
        messages.append({"role": "assistant", "content": "{"})

    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 512,  # 256 was too low for Qwen3 thinking to complete
        }
    ).encode()

    req = urllib.request.Request(
        f"{lm_studio_url}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError as e:
        raise RuntimeError(f"LM Studio unreachable at {lm_studio_url}: {e}") from e

    msg = data["choices"][0]["message"]
    # Qwen3 may route CoT to reasoning_content and leave content empty
    content = (msg.get("content") or "").strip()
    if not content and msg.get("reasoning_content"):
        # Fallback: find last JSON object in the reasoning text
        r = msg["reasoning_content"]
        end = r.rfind("}")
        if end != -1:
            content = r[r.rfind("{", 0, end) : end + 1]

    # Restore prefill char if the model continued from "{" without including it
    if is_qwen3 and content and not content.startswith("{"):
        content = "{" + content

    # Strip markdown fences and <think> blocks (belt-and-suspenders)
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)

    # raw_decode stops at first valid JSON object, ignoring any trailing text
    try:
        obj, _ = json.JSONDecoder().raw_decode(content)
        return obj
    except json.JSONDecodeError:
        return {
            "action": "informational",
            "priority": "low",
            "company": "unknown",
            "summary": content[:200],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify an email via local Qwen (LM Studio)")
    parser.add_argument("--subject", required=True, help="Email subject line")
    parser.add_argument("--body", required=True, help="Email body text")
    parser.add_argument("--url", default="http://127.0.0.1:1234", help="LM Studio base URL (default: http://127.0.0.1:1234)")
    parser.add_argument("--model", default="qwen/qwen3-27b", help="Model identifier (default: qwen/qwen3-27b)")
    args = parser.parse_args()

    try:
        result = triage_email(args.subject, args.body, args.url, args.model)
        print(json.dumps(result, indent=2))
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
