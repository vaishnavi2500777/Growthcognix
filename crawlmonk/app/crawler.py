"""/map and /crawl."""
import asyncio
import gzip
import re
from urllib.parse import urlparse
from xml.etree import ElementTree

from . import net, parse, search
from .net import FetchError
from .scrape import scrape


def _reg_domain(host: str) -> str:
    parts = (host or "").lower().split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "gov", "ac", "edu", "res", "gen", "firm", "ind"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def same_site(u: str, root: str, subdomains: bool) -> bool:
    h, r = (urlparse(u).hostname or "").lower(), (urlparse(root).hostname or "").lower()
    h0, r0 = h.removeprefix("www."), r.removeprefix("www.")
    if h0 == r0:
        return True
    return subdomains and _reg_domain(h) == _reg_domain(r)


async def sitemap_urls(root: str, cap=5000) -> list[str]:
    p = urlparse(root)
    base = f"{p.scheme}://{p.netloc}"
    queue = list(dict.fromkeys(await net.robots_sitemaps(root) + [base + "/sitemap.xml", base + "/sitemap_index.xml"]))
    seen, out, fetched = set(), [], 0
    while queue and fetched < 25 and len(out) < cap:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        fetched += 1
        try:
            r = await net.fetch(sm, timeout=15, ua=None)
        except FetchError:
            continue
        if r.status >= 400:
            continue
        body = r.body
        if body[:2] == b"\x1f\x8b":
            try:
                body = gzip.decompress(body)[:20_000_000]
            except OSError:
                continue
        try:
            root_el = ElementTree.fromstring(body)
        except ElementTree.ParseError:
            continue
        for loc in root_el.iter():
            if loc.tag.endswith("loc") and loc.text:
                u = loc.text.strip()
                if root_el.tag.endswith("sitemapindex"):
                    queue.append(u)
                else:
                    out.append(u)
    return out[:cap]


async def map_site(url: str, *, search_q=None, include_subdomains=True, limit=5000, sitemap="include",
                   ignore_query=True) -> list[dict]:
    await net.check_url(url)
    found: dict[str, dict] = {}

    def add(u, **kw):
        if not u.startswith("http") or not same_site(u, url, include_subdomains):
            return
        n = parse.norm_url(u, ignore_query)
        if n not in found:
            found[n] = {"url": n, **kw}
    if sitemap != "skip":
        for u in await sitemap_urls(url, cap=limit * 2):
            add(u)
    if sitemap != "only":
        try:
            r = await net.fetch(url, timeout=20)
            s = parse.soup_of(r.text)
            parse.absolutize(s, r.final_url)
            add(r.final_url)
            for a in s.find_all("a", href=True):
                t = a.get_text(" ", strip=True)
                add(a["href"], **({"title": t[:120]} if t else {}))
        except FetchError:
            pass
        # search engine discovery (like Firecrawl's map, which also uses a search index)
        try:
            host = urlparse(url).hostname.removeprefix("www.")
            res, _ = await search.web(f"site:{host} {search_q or ''}".strip(), 30)
            for x in res:
                add(x["url"], title=x["title"], description=x["description"])
        except Exception:
            pass
    links = list(found.values())
    if search_q:
        words = [w.lower() for w in re.findall(r"\w+", search_q)]

        def rel(x):
            hay = (x["url"] + " " + x.get("title", "") + " " + x.get("description", "")).lower()
            return sum(hay.count(w) for w in words)
        links = [x for x in links if rel(x) > 0] or links
        links.sort(key=rel, reverse=True)
    return links[:limit]


class CrawlCtx:
    """Implemented by the queue worker."""
    async def progress(self, **kw): ...
    async def add_doc(self, url, doc): ...
    async def cancelled(self) -> bool: ...
    async def webhook(self, event, data=None): ...


async def crawl(start: str, o: dict, ctx: CrawlCtx, user_id=None):
    limit = max(1, min(int(o.get("limit", 10)), 200))
    max_depth = int(o.get("maxDiscoveryDepth", o.get("maxDepth", 3)))
    inc = [re.compile(p) for p in (o.get("includePaths") or [])]
    exc = [re.compile(p) for p in (o.get("excludePaths") or [])]
    ext = bool(o.get("allowExternalLinks"))
    subs = bool(o.get("allowSubdomains"))
    ignq = o.get("ignoreQueryParameters", True)
    entire = bool(o.get("crawlEntireDomain", o.get("allowBackwardLinks", False)))
    delay = float(o.get("delay", 0.5) or 0)
    conc = max(1, min(int(o.get("maxConcurrency", 3)), 5))
    sopts = dict(o.get("scrapeOptions") or {})
    want = sopts.get("formats") or ["markdown"]
    want_links = "links" in want
    sopts["formats"] = list(want) + ([] if want_links else ["links"])
    start = parse.norm_url(start, ignq)
    await net.check_url(start)
    base_path = urlparse(start).path.rstrip("/")

    def allowed(u):
        pu = urlparse(u)
        if pu.scheme not in ("http", "https"):
            return False
        if re.search(r"\.(jpg|jpeg|png|gif|webp|svg|zip|rar|gz|mp4|mp3|avi|mov|exe|dmg|css|js|woff2?|ico)$", pu.path, re.I):
            return False
        if not same_site(u, start, subs) and not ext:
            return False
        if same_site(u, start, subs) and not entire and base_path and not pu.path.startswith(base_path):
            return False
        path = pu.path + (("?" + pu.query) if pu.query else "")
        if inc and u != start and not any(r.search(path) for r in inc):
            return False
        if exc and any(r.search(path) for r in exc):
            return False
        return True

    seen = {start}
    frontier: list[tuple[str, int]] = [(start, 0)]
    if o.get("sitemap", "include") != "skip":
        for u in await sitemap_urls(start, cap=limit * 5):
            n = parse.norm_url(u, ignq)
            if n not in seen and allowed(n):
                seen.add(n)
                frontier.append((n, 1))
    done = failed = skipped = 0
    sem = asyncio.Semaphore(conc)
    await ctx.webhook("started")

    async def one(u, depth):
        nonlocal done, failed, skipped
        async with sem:
            if done >= limit or await ctx.cancelled():
                return []
            if not await net.robots_allowed(u):
                skipped += 1
                return []
            await net.polite(urlparse(u).hostname, delay)
            try:
                doc, _ = await scrape(u, sopts, user_id)
            except Exception as e:  # noqa
                failed += 1
                await ctx.progress(failed=failed, lastError=f"{u}: {e}")
                return []
            new = doc.get("links", []) if depth < max_depth else []
            if not want_links:
                doc.pop("links", None)
            if done >= limit:
                return []
            done += 1
            await ctx.add_doc(u, doc)
            await ctx.webhook("page", [doc])
            await ctx.progress(completed=done, total=min(limit, len(seen)), failed=failed, robotsSkipped=skipped)
            return [(parse.norm_url(x, ignq), depth + 1) for x in new]

    while frontier and done < limit and not await ctx.cancelled():
        batch, frontier = frontier[:conc * 2], frontier[conc * 2:]
        results = await asyncio.gather(*(one(u, d) for u, d in batch))
        for lst in results:
            for n, d in lst:
                if n not in seen and allowed(n) and len(seen) < limit * 20:
                    seen.add(n)
                    frontier.append((n, d))
    await ctx.progress(completed=done, total=done, failed=failed, robotsSkipped=skipped, discovered=len(seen))
