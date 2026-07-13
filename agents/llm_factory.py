"""agents/llm_factory.py — single construction point for the LM Studio / OpenAI-compatible LLM.

Environment overrides (all optional — LM Studio defaults work out of the box):
  LLM_BASE_URL  default: http://localhost:1234/v1
  LLM_MODEL     default: qwen/qwen3.6-27b
  LLM_API_KEY   default: lm-studio
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.browser_agent import CompatibleChatOpenAI


def get_llm(temperature: float = 0.0, model: str | None = None) -> CompatibleChatOpenAI:
    """Return a configured LLM client.

    Args:
        temperature: 0.0 for deterministic form-filling; 0.2 for creative drafting.
        model: override LLM_MODEL env var for this call.
    """
    base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
    resolved_model = model or os.getenv("LLM_MODEL", "qwen/qwen3.6-27b")
    api_key = os.getenv("LLM_API_KEY", "lm-studio")

    return CompatibleChatOpenAI(
        base_url=base_url,
        api_key=api_key,
        model=resolved_model,
        temperature=temperature,
        max_completion_tokens=2048,
        timeout=300,
        dont_force_structured_output=True,
        add_schema_to_system_prompt=True,
        remove_min_items_from_schema=True,
        remove_defaults_from_schema=True,
    )
