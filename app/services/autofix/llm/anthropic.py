"""
Anthropic Claude LLM Client for CodeVanguard Auto-Fix.
"""
import os
import json
import logging
import urllib.request
import urllib.error
from typing import Optional

from app.services.autofix.llm.client import LLMClient, LLMResponse, estimate_cost

logger = logging.getLogger(__name__)

class AnthropicClient(LLMClient):
    def __init__(self, model: str = "claude-3-5-sonnet-20241022", timeout: int = 45):
        super().__init__(model=model, timeout=timeout)
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    def generate_patch(self, prompt: str, system_prompt: str) -> LLMResponse:
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not configured.")

        url = "https://api.anthropic.com/v1/messages"
        payload = {
            "model": self.model,
            "max_tokens": 2048,
            "temperature": 0.1,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))

        content_list = resp_data.get("content", [])
        raw_text = content_list[0].get("text", "") if content_list else ""

        usage = resp_data.get("usage", {})
        tokens_in = usage.get("input_tokens", 0)
        tokens_out = usage.get("output_tokens", 0)
        cost = estimate_cost("anthropic", self.model, tokens_in, tokens_out)
        parsed_json = self.parse_json_response(raw_text)

        return LLMResponse(
            text=raw_text,
            model=self.model,
            provider="anthropic",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            parsed_json=parsed_json
        )
