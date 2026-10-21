"""
Local Ollama LLM Client for CodeVanguard Auto-Fix (Fully Local / Air-Gapped).
"""
import os
import json
import logging
import urllib.request
import urllib.error
from typing import Optional

from app.services.autofix.llm.client import LLMClient, LLMResponse

logger = logging.getLogger(__name__)

class OllamaClient(LLMClient):
    def __init__(self, model: str = "qwen2.5-coder", timeout: int = 60):
        super().__init__(model=model, timeout=timeout)
        self.host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")

    def generate_patch(self, prompt: str, system_prompt: str) -> LLMResponse:
        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1
            }
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise ValueError(f"Failed to connect to local Ollama server at {self.host}: {e.reason}")

        raw_text = resp_data.get("response", "")
        tokens_in = resp_data.get("prompt_eval_count", 0)
        tokens_out = resp_data.get("eval_count", 0)
        parsed_json = self.parse_json_response(raw_text)

        return LLMResponse(
            text=raw_text,
            model=self.model,
            provider="ollama",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=0.0,
            parsed_json=parsed_json
        )
