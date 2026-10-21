"""
Google Gemini LLM Client for CodeVanguard Auto-Fix.
"""
import os
import json
import logging
import urllib.request
import urllib.error
from typing import Optional

from app.services.autofix.llm.client import LLMClient, LLMResponse, estimate_cost

logger = logging.getLogger(__name__)

class GeminiClient(LLMClient):
    def __init__(self, model: str = "gemini-1.5-flash", timeout: int = 45):
        super().__init__(model=model, timeout=timeout)
        self.api_key = os.environ.get("GEMINI_API_KEY", "")

    def generate_patch(self, prompt: str, system_prompt: str) -> LLMResponse:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not configured.")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))

        candidates = resp_data.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned empty candidate response.")

        parts = candidates[0].get("content", {}).get("parts", [])
        raw_text = parts[0].get("text", "") if parts else ""

        usage = resp_data.get("usageMetadata", {})
        tokens_in = usage.get("promptTokenCount", 0)
        tokens_out = usage.get("candidatesTokenCount", 0)
        cost = estimate_cost("gemini", self.model, tokens_in, tokens_out)
        parsed_json = self.parse_json_response(raw_text)

        return LLMResponse(
            text=raw_text,
            model=self.model,
            provider="gemini",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            parsed_json=parsed_json
        )
