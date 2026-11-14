"""Gemini calls. No key => AIUnavailable (never fake output)."""
import asyncio
import json
import re

import httpx

from . import config


class AIUnavailable(Exception):
    code = "AI_UNAVAILABLE"


class AIError(Exception):
    code = "AI_ERROR"


def enabled() -> bool:
    return bool(config.GEMINI_API_KEY)


async def generate(prompt: str, *, json_mode=False, system: str | None = None, max_tokens=4096) -> str:
    if not enabled():
        raise AIUnavailable("GEMINI_API_KEY is not set on the server; AI features (json/summary/extract/agent/"
                            "fit reasons) are disabled. Add it in Render > Environment.")
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": max_tokens}}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
    async with httpx.AsyncClient(timeout=90) as c:
        for delay in (4, 12, 0):  # free tier: transient 503 "high demand" and per-minute 429s
            r = await c.post(url, json=body, headers={"x-goog-api-key": config.GEMINI_API_KEY})
            if r.status_code not in (429, 500, 503) or not delay:
                break
            await asyncio.sleep(delay)
    if r.status_code == 429:
        raise AIError("Gemini free-tier rate limit reached; try again in a minute")
    if r.status_code >= 400:
        try:
            msg = r.json()["error"]["message"][:200]
        except Exception:
            msg = r.text[:200]
        raise AIError(f"Gemini error {r.status_code}: {msg}")
    d = r.json()
    try:
        return "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError):
        raise AIError("Gemini returned no content (possibly blocked by safety filters)")


def parse_json(s: str):
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[\]}]", s, re.S)
        if m:
            return json.loads(m.group(0))
        raise AIError("Model did not return valid JSON")


async def extract_json(content: str, prompt: str | None, schema: dict | None):
    if not enabled():
        await generate("")
    if not prompt and not schema:
        raise AIError("json format needs a prompt and/or schema")
    instr = "Extract information from the web content below and return ONLY JSON."
    if schema:
        instr += "\nThe JSON must follow this JSON Schema exactly:\n" + json.dumps(schema)[:6000]
    if prompt:
        instr += "\nInstructions: " + prompt
    instr += ("\nUse only facts present in the content. If a value is not present, use null. "
              "Do not invent data.\n\nCONTENT:\n" + content[:60000])
    return parse_json(await generate(instr, json_mode=True))


async def summarize(content: str) -> str:
    return (await generate("Summarize this web page in 3-6 concise sentences. Only use facts in it.\n\n"
                           + content[:40000], max_tokens=800)).strip()
