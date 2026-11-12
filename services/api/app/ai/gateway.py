"""Model gateway. Agents talk to this contract, never to a vendor SDK, so providers can be swapped
(Gemini free tier today; paid Gemini, OpenAI, Anthropic or a self-hosted model later)."""
import asyncio
import json
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import get_settings


class ModelUnavailable(Exception):
    """No provider configured, or the provider refused (quota, outage)."""


@dataclass
class ModelResult:
    data: dict
    model: str
    input_tokens: int
    output_tokens: int


class ModelGateway(Protocol):
    name: str

    async def generate_json(self, system: str, prompt: str, schema: dict) -> ModelResult: ...


class GeminiGateway:
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str):
        self.api_key, self.name = api_key, model

    async def generate_json(self, system: str, prompt: str, schema: dict) -> ModelResult:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema,
                                 "temperature": 0.3},
        }
        last = ""
        async with httpx.AsyncClient(timeout=90) as c:
            for attempt in range(3):
                r = await c.post(self.URL.format(model=self.name), json=body,
                                 headers={"x-goog-api-key": self.api_key})
                if r.status_code in (429, 500, 503):
                    last = f"{r.status_code}: {r.text[:200]}"
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                if r.status_code != 200:
                    raise ModelUnavailable(f"{r.status_code}: {r.text[:300]}")
                d = r.json()
                try:
                    text = d["candidates"][0]["content"]["parts"][0]["text"]
                    data = json.loads(text)
                except (KeyError, IndexError, json.JSONDecodeError) as e:
                    raise ModelUnavailable(f"Unreadable model response: {e}") from e
                u = d.get("usageMetadata", {})
                return ModelResult(data, self.name, u.get("promptTokenCount", 0),
                                   u.get("candidatesTokenCount", 0))
        raise ModelUnavailable(f"Provider busy after retries ({last})")


def get_model() -> ModelGateway | None:
    s = get_settings()
    return GeminiGateway(s.gemini_api_key, s.gemini_model) if s.gemini_api_key else None
