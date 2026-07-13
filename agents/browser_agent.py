#!/usr/bin/env python3
"""browser_agent.py — AI browser automation for job search tasks.

Supports local LLMs via LM Studio (OpenAI-compatible API) or any OpenAI-compatible endpoint.
Compatible with Qwen3 models — strips thinking tokens and tool-call wrappers automatically.

Usage:
    python3 agents/browser_agent.py "go to greenhouse.io/databricks and list open backend roles"
    python3 agents/browser_agent.py "find the careers page at mistral.ai and list engineering jobs"
    python3 agents/browser_agent.py --check-context   # verify LM Studio is ready

Environment variables (or set in config.yml):
    LLM_BASE_URL   OpenAI-compatible API base URL (default: http://localhost:1234/v1)
    LLM_MODEL      Model name to use (default: qwen/qwen3.6-27b)
    LLM_API_KEY    API key (default: lm-studio for local)

Context requirements (Qwen 27B via LM Studio):
    LM Studio must load the model with ≥16384 context tokens (default was 4096).
    Fix: ~/.lmstudio/bin/lms unload qwen/qwen3.6-27b
         ~/.lmstudio/bin/lms load qwen/qwen3.6-27b -c 32768
    Or change ~/.lmstudio/settings.json defaultContextLength to 32768.
"""

import asyncio
import json
import os
import re
import sys
import urllib.request

from browser_use.llm.openai.chat import ChatOpenAI as _BrowserUseChatOpenAI
from browser_use import Agent

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_API_BASE = LLM_BASE_URL.replace("/v1", "/api/v0")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen/qwen3.6-27b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "lm-studio")
MIN_CONTEXT_TOKENS = 16384


def check_lm_studio_context() -> tuple[bool, int]:
    """Return (ok, loaded_context_length). Warns if context < MIN_CONTEXT_TOKENS."""
    try:
        req = urllib.request.Request(f"{LLM_API_BASE}/models/{LLM_MODEL}")
        with urllib.request.urlopen(req, timeout=5) as r:
            info = json.loads(r.read())
        ctx = info.get("loaded_context_length", 0)
        if ctx < MIN_CONTEXT_TOKENS:
            print(
                f"[browser_agent] WARNING: {LLM_MODEL} loaded with {ctx} context tokens "
                f"(need ≥{MIN_CONTEXT_TOKENS}). Browser tasks will fail.\n"
                f"Fix: ~/.lmstudio/bin/lms unload {LLM_MODEL} && "
                f"~/.lmstudio/bin/lms load {LLM_MODEL} -c 32768",
                file=sys.stderr,
            )
            return False, ctx
        return True, ctx
    except Exception as e:
        print(f"[browser_agent] Could not check LM Studio context: {e}", file=sys.stderr)
        return True, 0  # optimistic — don't block if API is unavailable


class CompatibleChatOpenAI(_BrowserUseChatOpenAI):
    """browser-use ChatOpenAI with compatibility fixes for local LLMs.

    Handles Qwen3-specific quirks:
    - Injects enable_thinking=False to suppress thinking token overhead
    - Strips <thinking> blocks leaked into content by LM Studio
    - Strips <tool_call> wrappers that break JSON parsing
    - Disables response_format=json_schema (not supported by most local servers)
    """

    @staticmethod
    def _clean_content(text: str) -> str:
        text = text.strip()
        text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)
        text = re.sub(r'<tool_call[^>]*>', '', text)
        text = re.sub(r'</tool_call>', '', text)
        # Strip <step>...</step> and XML-style wrappers Qwen3 uses under loop pressure
        text = re.sub(r'<step>.*?</step>', '', text, flags=re.DOTALL)
        text = re.sub(r'<search_page\b[^>]*>.*?</search_page>', '', text, flags=re.DOTALL)
        text = re.sub(r'^<[a-zA-Z_][^>]*/?>.*', '', text, flags=re.DOTALL)
        text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)
        return text.strip()

    def get_client(self):
        client = super().get_client()
        original_create = client.chat.completions.create

        async def patched_create(*args, **kw):
            eb = kw.get("extra_body") or {}
            eb["chat_template_kwargs"] = {"enable_thinking": False}
            kw["extra_body"] = eb
            response = await original_create(*args, **kw)
            if response.choices:
                choice = response.choices[0]
                if choice.message.content:
                    cleaned = self._clean_content(choice.message.content)
                    if cleaned != choice.message.content:
                        clean_msg = choice.message.model_copy(update={"content": cleaned})
                        clean_choice = choice.model_copy(update={"message": clean_msg})
                        response = response.model_copy(
                            update={"choices": [clean_choice] + list(response.choices[1:])}
                        )
            return response

        client.chat.completions.create = patched_create
        return client


async def run(task: str) -> str:
    ok, ctx = check_lm_studio_context()
    if not ok:
        print(f"Aborting: context window too small ({ctx} tokens). See warning above.")
        sys.exit(1)

    llm = CompatibleChatOpenAI(
        base_url=LLM_BASE_URL,
        api_key=LLM_API_KEY,
        model=LLM_MODEL,
        temperature=0.0,
        max_completion_tokens=2048,
        timeout=300,
        dont_force_structured_output=True,
        add_schema_to_system_prompt=True,
        remove_min_items_from_schema=True,
        remove_defaults_from_schema=True,
    )
    agent = Agent(
        task=task,
        llm=llm,
        use_vision=False,
        llm_timeout=300,
        # Context reduction — critical for local 27B models
        max_clickable_elements_length=6000,   # was 40000; single biggest context saver
        max_history_items=10,                 # prevent history explosion (must be >5 or None)
        use_judge=False,                      # removes extra LLM call per step
        max_actions_per_step=3,               # simpler steps = smaller prompts
        message_compaction=True,              # compact old messages (already default)
        include_tool_call_examples=False,     # no few-shot examples (saves ~500 tokens)
    )
    result = await agent.run()
    return str(result)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--check-context":
        ok, ctx = check_lm_studio_context()
        print(f"Context: {ctx} tokens — {'OK' if ok else 'TOO LOW'} (need ≥{MIN_CONTEXT_TOKENS})")
        sys.exit(0 if ok else 1)

    if len(sys.argv) < 2:
        print("Usage: python3 agents/browser_agent.py '<task>'")
        sys.exit(1)

    task = " ".join(sys.argv[1:])
    output = asyncio.run(run(task))
    print(output)
