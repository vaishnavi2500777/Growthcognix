"""Web search contract. Tavily free tier today; any provider that returns real URLs can plug in."""
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import get_settings


@dataclass
class SearchHit:
    title: str
    url: str
    content: str


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, max_results: int = 5) -> list[SearchHit]: ...


class TavilySearch:
    name = "tavily"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, max_results: int = 5) -> list[SearchHit]:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post("https://api.tavily.com/search",
                             headers={"authorization": f"Bearer {self.api_key}"},
                             json={"query": query, "max_results": max_results,
                                   "search_depth": "basic"})
            r.raise_for_status()
        return [SearchHit(h.get("title") or h["url"], h["url"], (h.get("content") or "")[:1500])
                for h in r.json().get("results", []) if h.get("url")]


def get_search() -> SearchProvider | None:
    key = get_settings().tavily_api_key
    return TavilySearch(key) if key else None
