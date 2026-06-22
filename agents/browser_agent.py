#!/usr/bin/env python3
"""browser_agent.py — AI browser automation for job search tasks.

Supports local LLMs via LM Studio (OpenAI-compatible API) or any OpenAI-compatible endpoint.
Compatible with Qwen3 models — strips thinking tokens and tool-call wrappers automatically.

Usage:
    python3 agents/browser_agent.py "go to greenhouse.io/databricks and list open backend roles"
    python3 agents/browser_agent.py "find the careers page at mistral.ai and list engineering jobs"

Environment variables (or set in config.yml):
    LLM_BASE_URL   OpenAI-compatible API base URL (default: http://localhost:1234/v1)
    LLM_MODEL      Model name to use (default: qwen3-27b)
    LLM_API_KEY    API key (default: lm-studio for local)
"""

import asyncio
import os
import re
import sys
from typing import Any

from browser_use.llm.openai.chat import ChatOpenAI as _BrowserUseChatOpenAI
from browser_use import Agent

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3-27b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "lm-studio")


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
    llm = CompatibleChatOpenAI(
        base_url=LLM_BASE_URL,
        api_key=LLM_API_KEY,
        model=LLM_MODEL,
        temperature=0.0,
        max_completion_tokens=4096,
        timeout=300,
        dont_force_structured_output=True,
        add_schema_to_system_prompt=True,
        remove_min_items_from_schema=True,
        remove_defaults_from_schema=True,
    )
    agent = Agent(task=task, llm=llm, use_vision=False, llm_timeout=300)
    result = await agent.run()
    return str(result)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 agents/browser_agent.py '<task>'")
        sys.exit(1)
    task = " ".join(sys.argv[1:])
    output = asyncio.run(run(task))
    print(output)
