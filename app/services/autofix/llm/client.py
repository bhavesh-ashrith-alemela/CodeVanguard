"""
Unified LLM Client Protocol, Data Classes, and Factory.
"""
import os
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    parsed_json: Optional[Dict[str, Any]] = None

class LLMClient(ABC):
    """Abstract interface for LLM patch generation providers."""

    def __init__(self, model: Optional[str] = None, timeout: int = 45):
        self.model = model
        self.timeout = timeout

    @abstractmethod
    def generate_patch(self, prompt: str, system_prompt: str) -> LLMResponse:
        """Generates a structured patch response from the model."""
        pass

    def parse_json_response(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """Extracts JSON object from model output handling potential markdown code fences."""
        clean = raw_text.strip()
        if clean.startswith("```"):
            lines = clean.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            clean = "\n".join(lines).strip()

        try:
            return json.loads(clean)
        except Exception:
            # Fallback: regex search for outer JSON object
            import re
            m = re.search(r'\{.*\}', clean, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    pass
        return None

def estimate_cost(provider: str, model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimates USD cost based on token usage and model rates."""
    rates = {
        "gemini": (0.075 / 1_000_000, 0.30 / 1_000_000),
        "openai": (0.15 / 1_000_000, 0.60 / 1_000_000),
        "anthropic": (3.00 / 1_000_000, 15.00 / 1_000_000),
        "ollama": (0.0, 0.0)
    }
    in_rate, out_rate = rates.get(provider.lower(), (0.15 / 1_000_000, 0.60 / 1_000_000))
    return round((tokens_in * in_rate) + (tokens_out * out_rate), 6)

def get_llm_client(provider: Optional[str] = None, model: Optional[str] = None) -> LLMClient:
    """
    Factory function returning the configured LLMClient.
    Priority:
    1. Explicit provider parameter
    2. LLM_PROVIDER env var (gemini | anthropic | openai | ollama)
    3. Auto-detected based on available environment API keys
    4. Fallback: Ollama / mock client
    """
    selected_provider = (provider or os.environ.get("LLM_PROVIDER", "")).lower()

    if not selected_provider:
        if os.environ.get("GEMINI_API_KEY"):
            selected_provider = "gemini"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            selected_provider = "anthropic"
        elif os.environ.get("OPENAI_API_KEY"):
            selected_provider = "openai"
        elif os.environ.get("OLLAMA_HOST"):
            selected_provider = "ollama"
        else:
            selected_provider = "gemini"

    if selected_provider == "anthropic":
        from app.services.autofix.llm.anthropic import AnthropicClient
        return AnthropicClient(model=model or "claude-3-5-sonnet-20241022")
    elif selected_provider == "openai":
        from app.services.autofix.llm.openai import OpenAIClient
        return OpenAIClient(model=model or "gpt-4o-mini")
    elif selected_provider == "ollama":
        from app.services.autofix.llm.ollama import OllamaClient
        return OllamaClient(model=model or "qwen2.5-coder")
    else: # default: gemini
        from app.services.autofix.llm.gemini import GeminiClient
        return GeminiClient(model=model or "gemini-1.5-flash")
