"""
OpenAI LLM Client for CodeVanguard Auto-Fix.
"""
import os
import json
import logging
import urllib.request
import urllib.error
from typing import Optional

from app.services.autofix.llm.client import LLMClient, LLMResponse, estimate_cost

logger = logging.getLogger(__name__)

class OpenAIClient(LLMClient):
    def __init__(self, model: str = "gpt-4o-mini", timeout: int = 45):
        super().__init__(model=model, timeout=timeout)
        self.api_key = os.environ.get("OPENAI_API_KEY", "")

    def generate_patch(self, prompt: str, system_prompt: str) -> LLMResponse:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not configured.")

        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))

        choices = resp_data.get("choices", [])
        raw_text = choices[0].get("message", {}).get("content", "") if choices else ""

        usage = resp_data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        cost = estimate_cost("openai", self.model, tokens_in, tokens_out)
        parsed_json = self.parse_json_response(raw_text)

        return LLMResponse(
            text=raw_text,
            model=self.model,
            provider="openai",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            parsed_json=parsed_json
        )
