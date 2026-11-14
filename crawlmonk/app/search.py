"""Web + news search from free public sources (no paid API):
web: Yahoo HTML results (primary), Bing and DuckDuckGo Lite (fallbacks); news: Google News RSS."""
import asyncio
import base64
import re
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from xml.etree import ElementTree

import os

import httpx

from . import parse
from .net import FetchError, fetch

SERPER_KEY = os.getenv("SERPER_API_KEY", "")
TAVILY_KEY = os.getenv("TAVILY_API_KEY", "")


async def serper(q: str, limit=10, news=False) -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"https://google.serper.dev/{'news' if news else 'search'}",
                         json={"q": q, "gl": "in", "num": min(limit, 100)}, headers={"X-API-KEY": SERPER_KEY})
    if r.status_code != 200:
        raise FetchError(f"Serper HTTP {r.status_code}", "SEARCH_PROVIDER")
    d = r.json()
    items = d.get("news" if news else "organic", [])
    return [{"url": x.get("link"), "title": x.get("title", ""), "description": x.get("snippet", ""),
             "source": "serper", **({"date": x.get("date")} if news else {})} for x in items][:limit]


async def tavily(q: str, limit=10, news=False) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post("https://api.tavily.com/search", json={"query": q, "max_results": min(limit, 20),
                                                                 "topic": "news" if news else "general"},
                         headers={"Authorization": f"Bearer {TAVILY_KEY}"})
    if r.status_code != 200:
        raise FetchError(f"Tavily HTTP {r.status_code}", "SEARCH_PROVIDER")
    return [{"url": x.get("url"), "title": x.get("title", ""), "description": (x.get("content") or "")[:300],
             "source": "tavily"} for x in r.json().get("results", [])][:limit]


def _bing_real(href: str) -> str:
    if "bing.com/ck/a" in href:
        u = parse_qs(urlparse(href).query).get("u", [""])[0]
        if u.startswith("a1"):
            s = u[2:]
            try:
                return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode()
            except Exception:
                return href
    return href


async def bing(q: str, limit=10, country="IN", tbs: str | None = None) -> list[dict]:
    out, first = [], 1
    while len(out) < limit and first < 60:
        url = f"https://www.bing.com/search?q={quote_plus(q)}&setlang=en-IN&cc={country}&count=20&first={first}"
        if tbs:
            url += f"&filters={quote_plus(tbs)}"
        r = await fetch(url, timeout=15, headers={"Cookie": "SRCHHPGUSR=ADLT=MODERATE"})
        s = parse.soup_of(r.text)
        items = s.select("li.b_algo")
        if not items:
            break
        for li in items:
            a = li.select_one("h2 a")
            if not a or not a.get("href"):
                continue
            link = _bing_real(a["href"])
            if not link.startswith("http") or any(x["url"] == link for x in out):
                continue
            p = li.select_one(".b_caption p") or li.select_one("p")
            out.append({"url": link, "title": a.get_text(" ", strip=True),
                        "description": p.get_text(" ", strip=True) if p else "", "source": "bing"})
        first += len(items)
    return out[:limit]


async def yahoo(q: str, limit=10, age: str | None = None) -> list[dict]:
    out, b = [], 1
    while len(out) < limit and b < 60:
        url = f"https://search.yahoo.com/search?p={quote_plus(q)}&b={b}&n=10"
        if age:
            url += f"&age={age}&btf={age[-1]}"
        r = await fetch(url, timeout=15, headers={"Accept-Language": "en-US,en;q=0.9"})
        s = parse.soup_of(r.text)
        items = s.select("div.algo")
        if not items:
            break
        for d in items:
            a = d.select_one("h3 a") or d.select_one("a")
            if not a:
                continue
            h = a.get("href", "")
            m = re.search(r"/RU=([^/]+)/RK=", h)
            link = unquote(m.group(1)) if m else h
            if not link.startswith("http") or "yahoo.com" in urlparse(link).netloc or any(x["url"] == link for x in out):
                continue
            t = d.select_one("h3")
            title = t.get_text(" ", strip=True) if t else a.get_text(" ", strip=True)
            title = re.sub(r"^\S+\s+https?://\S+\s+", "", title) if "://" in title else title
            sn = d.select_one(".compText")
            out.append({"url": link, "title": title, "description": sn.get_text(" ", strip=True) if sn else "",
                        "source": "yahoo"})
        b += 10
    return out[:limit]


async def ddg_lite(q: str, limit=10) -> list[dict]:
    r = await fetch(f"https://lite.duckduckgo.com/lite/?q={quote_plus(q)}&kl=in-en", timeout=15)
    s = parse.soup_of(r.text)
    out = []
    for a in s.select("a.result-link"):
        h = a.get("href", "")
        if "uddg=" in h:
            h = parse_qs(urlparse(h).query).get("uddg", [h])[0]
        if h.startswith("http"):
            out.append({"url": h, "title": a.get_text(" ", strip=True), "description": "", "source": "duckduckgo"})
    return out[:limit]


async def news(q: str, limit=10) -> list[dict]:
    r = await fetch(f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-IN&gl=IN&ceid=IN:en", timeout=15)
    root = ElementTree.fromstring(r.body)
    out = []
    for it in root.iter("item"):
        src = it.find("source")
        out.append({"url": it.findtext("link"), "title": it.findtext("title"),
                    "date": it.findtext("pubDate"), "snippet": re.sub("<[^>]+>", " ", it.findtext("description") or "").strip()[:300],
                    "publisher": src.text if src is not None else None})
        if len(out) >= limit:
            break
    return out


TBS = {"qdr:d": 'ex1:"ez1"', "qdr:w": 'ex1:"ez2"', "qdr:m": 'ex1:"ez3"'}


def _relevant(q: str, res: list[dict]) -> bool:
    """Engines facing a bot sometimes return unrelated filler; require query words in the results."""
    words = [w for w in re.findall(r"[a-z0-9]{3,}", q.lower()) if w not in ("site", "the", "and", "for", "with", "www", "com")]
    if not words or not res:
        return bool(res)
    hay = " ".join((x["url"] + " " + x["title"] + " " + x.get("description", "")).lower() for x in res)
    return sum(1 for w in words if w in hay) >= max(1, len(words) // 2)


async def _ddg_html(q: str, limit=10) -> list[dict]:
    r = await fetch("https://html.duckduckgo.com/html/", method="POST", data=f"q={quote_plus(q)}&kl=in-en".encode(),
                    headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
    s = parse.soup_of(r.text)
    out = []
    for d in s.select("div.result"):
        a = d.select_one("a.result__a")
        if not a:
            continue
        h = a.get("href", "")
        if "uddg=" in h:
            h = parse_qs(urlparse(h).query).get("uddg", [h])[0]
        sn = d.select_one(".result__snippet")
        if "result--ad" in (d.get("class") or []):
            continue
        if h.startswith("http") and not urlparse(h).netloc.endswith("duckduckgo.com"):
            out.append({"url": h, "title": a.get_text(" ", strip=True),
                        "description": sn.get_text(" ", strip=True) if sn else "", "source": "duckduckgo"})
    return out[:limit]


async def web(q: str, limit=10, tbs: str | None = None) -> tuple[list[dict], str | None]:
    age = {"qdr:d": "1d", "qdr:w": "1w", "qdr:m": "1m"}.get(tbs or "")
    engines = []
    if SERPER_KEY:
        engines.append(("serper", lambda: serper(q, limit)))
    if TAVILY_KEY:
        engines.append(("tavily", lambda: tavily(q, limit)))
    engines += [("yahoo", lambda: yahoo(q, limit, age)), ("duckduckgo", lambda: _ddg_html(q, limit)),
               ("duckduckgo-lite", lambda: ddg_lite(q, limit)), ("bing", lambda: bing(q, limit, tbs=TBS.get(tbs or "")))]
    notes = []
    for name, fn in engines:
        try:
            res = await fn()
        except FetchError as e:
            notes.append(f"{name}: {e}")
            continue
        except Exception as e:  # parser surprises
            notes.append(f"{name}: {type(e).__name__}")
            continue
        if res and _relevant(q, res):
            return res, None
        notes.append(f"{name}: no relevant results (likely bot-filtered)")
    return [], ("All free search engines refused or returned unrelated results (they block datacenter IPs); set "
                "SERPER_API_KEY or TAVILY_API_KEY for reliable search: " + "; ".join(notes))


async def search(q: str, limit=5, sources=None, tbs=None):
    sources = [s if isinstance(s, str) else s.get("type") for s in (sources or ["web"])]
    data, warns = {}, []
    tasks = {}
    if "web" in sources:
        tasks["web"] = web(q, limit, tbs)
    if "news" in sources:
        tasks["news"] = news(q, limit)
    res = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for k, v in zip(tasks, res):
        if isinstance(v, Exception):
            warns.append(f"{k}: {v}")
            data[k] = []
        elif k == "web":
            data["web"], w = v
            if w:
                warns.append(w)
        else:
            data[k] = v
    return data, warns
