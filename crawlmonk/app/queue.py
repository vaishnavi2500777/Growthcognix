"""Postgres-backed job queue (FOR UPDATE SKIP LOCKED) + workers, webhooks, monitors."""
import asyncio
import datetime as dt
import difflib
import hashlib
import hmac
import json
import re
import traceback
import uuid

from . import ai, auth, crawler, db, leads, net, search
from .net import FetchError
from .scrape import scrape

WORKERS = 2
_wake = asyncio.Event()


async def enqueue(user_id: int, kind: str, params: dict) -> str:
    jid = uuid.uuid4()
    await db.P().execute("INSERT INTO jobs(id,user_id,kind,status,params) VALUES($1,$2,$3,'queued',$4)",
                         jid, user_id, kind, params)
    _wake.set()
    return str(jid)


async def webhook_send(user_id, spec, event_type, job_id, data=None, error=None):
    if not spec:
        return
    if isinstance(spec, str):
        spec = {"url": spec}
    events = spec.get("events")
    short = event_type.split(".")[-1]
    if events and short not in events:
        return
    url = spec.get("url")
    try:
        await net.check_url(url)
    except FetchError:
        return
    secret = await db.P().fetchval("SELECT webhook_secret FROM users WHERE id=$1", user_id)
    body = json.dumps({"success": error is None, "type": event_type, "id": job_id, "data": data or [],
                       "metadata": spec.get("metadata") or {}, "error": error}, default=str).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-CrawlMonk-Signature": f"sha256={sig}",
               **(spec.get("headers") or {})}
    try:
        await net.client().post(url, content=body, headers=headers, timeout=10)
    except Exception:
        pass


class Ctx(crawler.CrawlCtx):
    def __init__(self, job):
        self.job = job
        self.id = job["id"]
        self.prog = dict(job["progress"] or {})
        self._last_cancel_check = 0
        self._cancel = False

    async def progress(self, **kw):
        self.prog.update(kw)
        await db.P().execute("UPDATE jobs SET progress=$2, updated_at=now() WHERE id=$1", self.id, self.prog)

    async def add_doc(self, url, doc):
        await db.P().execute("INSERT INTO job_docs(job_id,url,doc) VALUES($1,$2,$3)", self.id, url, doc)
        if self.job["kind"] in ("crawl", "batch_scrape"):
            await auth.charge(self.job["user_id"], self.job["kind"], 1)

    async def cancelled(self):
        now = asyncio.get_running_loop().time()
        if now - self._last_cancel_check > 2:
            self._last_cancel_check = now
            st = await db.P().fetchval("SELECT status FROM jobs WHERE id=$1", self.id)
            self._cancel = st == "cancelled"
        return self._cancel

    async def webhook(self, event, data=None):
        p = self.job["params"]
        prefix = {"crawl": "crawl", "batch_scrape": "batch_scrape"}.get(self.job["kind"], self.job["kind"])
        await webhook_send(self.job["user_id"], p.get("webhook"), f"{prefix}.{event}", str(self.id), data)


async def run_crawl(job, ctx):
    p = job["params"]
    await db.P().execute("DELETE FROM job_docs WHERE job_id=$1", job["id"])
    await crawler.crawl(p["url"], p, ctx, job["user_id"])


async def run_batch(job, ctx):
    p = job["params"]
    await db.P().execute("DELETE FROM job_docs WHERE job_id=$1", job["id"])
    urls = p["urls"]
    sem = asyncio.Semaphore(3)
    done = failed = 0
    await ctx.webhook("started")

    async def one(u):
        nonlocal done, failed
        async with sem:
            if await ctx.cancelled():
                return
            try:
                doc, _ = await scrape(u, p.get("scrapeOptions") or p, job["user_id"])
                await ctx.add_doc(u, doc)
                await ctx.webhook("page", [doc])
                done += 1
            except Exception as e:
                failed += 1
                await ctx.add_doc(u, {"metadata": {"sourceURL": u, "error": str(e)}})
            await ctx.progress(completed=done, failed=failed, total=len(urls))
    await asyncio.gather(*(one(u) for u in urls))


async def gather_pages(urls: list[str], limit=10, user_id=None) -> list[dict]:
    """Resolve /* wildcards via map, then scrape. Returns [{url, markdown}]."""
    targets = []
    for u in urls:
        if u.endswith("/*"):
            base = u[:-2]
            links = await crawler.map_site(base, limit=limit)
            targets += [base] + [x["url"] for x in links]
        else:
            targets.append(u)
    targets = list(dict.fromkeys(targets))[:limit]
    out = []

    async def one(u):
        try:
            d, _ = await scrape(u, {"formats": ["markdown"]}, user_id)
            out.append({"url": u, "markdown": d.get("markdown", "")})
        except Exception:
            pass
    await asyncio.gather(*(one(u) for u in targets))
    return out


async def run_extract(job, ctx):
    p = job["params"]
    if not ai.enabled():
        raise ai.AIUnavailable("GEMINI_API_KEY is not set on the server; /extract is disabled")
    urls = list(p.get("urls") or [])
    if p.get("enableWebSearch") and p.get("prompt"):
        res, _ = await search.web(p["prompt"][:200], 5)
        urls += [r["url"] for r in res]
    await ctx.progress(stage="scraping", urls=len(urls))
    pages = await gather_pages(urls, int(p.get("limit", 10)), job["user_id"])
    if not pages:
        raise FetchError("None of the URLs could be scraped", "NO_CONTENT")
    await ctx.progress(stage="extracting", pages=len(pages))
    content = "\n\n".join(f"### SOURCE: {x['url']}\n{x['markdown'][:12000]}" for x in pages)
    data = await ai.extract_json(content, p.get("prompt"), p.get("schema"))
    await ctx.add_doc(None, {"data": data, "sources": [x["url"] for x in pages]})


async def run_agent(job, ctx):
    """Prompt-driven research: plan queries -> search -> scrape -> answer with sources."""
    p = job["params"]
    if not ai.enabled():
        raise ai.AIUnavailable("GEMINI_API_KEY is not set on the server; /agent is disabled")
    prompt = p["prompt"]
    await ctx.progress(stage="planning")
    plan = ai.parse_json(await ai.generate(
        "Plan web searches to answer this request. Return JSON {\"queries\": [3 short web search queries]}.\n"
        f"Request: {prompt}", json_mode=True, max_tokens=400))
    queries = (plan.get("queries") if isinstance(plan, dict) else None) or [prompt[:150]]
    urls = list(p.get("urls") or [])
    steps = []
    for q in queries[:3]:
        await ctx.progress(stage=f"searching: {q}")
        res, _ = await search.web(q, 6)
        steps.append({"query": q, "results": [r["url"] for r in res]})
        urls += [r["url"] for r in res[:4]]
    urls = [u for u in dict.fromkeys(urls) if not re.search(r"youtube\.com|facebook\.com|instagram\.com", u)]
    await ctx.progress(stage="reading pages", urls=len(urls))
    pages = await gather_pages(urls, int(p.get("maxPages", 10)), job["user_id"])
    if not pages:
        raise FetchError("Search returned no readable pages", "NO_CONTENT")
    await ctx.progress(stage="answering", pages=len(pages))
    content = "\n\n".join(f"### SOURCE: {x['url']}\n{x['markdown'][:8000]}" for x in pages)
    instr = ("Answer the request using ONLY the sources. Return JSON {\"answer\": ..., \"sources\": [urls used]}"
             + (". 'answer' must follow this JSON Schema: " + json.dumps(p["schema"])[:5000] if p.get("schema") else
                ". 'answer' is a clear markdown string.")
             + " If the sources do not contain it, say so; never invent facts.\nRequest: " + prompt + "\n\n" + content[:90000])
    data = ai.parse_json(await ai.generate(instr, json_mode=True, max_tokens=6000))
    await ctx.add_doc(None, {"data": data, "steps": steps, "pagesRead": [x["url"] for x in pages]})


async def run_leads(job, ctx):
    p = job["params"]
    await db.P().execute("DELETE FROM leads WHERE job_id=$1", job["id"])
    total, per_city = 0, []
    for c in p["cities"]:
        city, state = c.get("city", "").strip(), (c.get("state") or "").strip() or None
        if await ctx.cancelled():
            break

        async def report(**kw):
            await ctx.progress(**kw, leads=total, cities=per_city)
        try:
            found, stats = await leads.find_city(city, state, p, report)
        except Exception as e:  # one city failing must not kill the job
            per_city.append({"city": city, "error": str(e)})
            continue
        async with db.P().acquire() as con:
            await con.executemany(
                "INSERT INTO leads(job_id,city,name,category,address,phone,website,emails,phones,socials,signals,"
                "score,reason,ai_reason,lat,lon,source,source_ref) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,"
                "$14,$15,$16,$17,$18)",
                [(job["id"], l["city"], l["name"], l["category"], l["address"], l.get("phone"), l.get("website"),
                  l["emails"], l["phones"], l["socials"], l["signals"], l["score"], l["reason"], l.get("ai_reason"),
                  l.get("lat"), l.get("lon"), l["source"], l["source_ref"]) for l in found])
        total += len(found)
        per_city.append(stats)
        await ctx.progress(stage=f"{city}: done", leads=total, cities=per_city)
    await ctx.progress(stage="done", leads=total, cities=per_city)


HANDLERS = {"crawl": run_crawl, "batch_scrape": run_batch, "extract": run_extract, "agent": run_agent,
            "leads": run_leads}


async def _run(job):
    ctx = Ctx(job)
    try:
        await HANDLERS[job["kind"]](job, ctx)
        st = await db.P().fetchval("SELECT status FROM jobs WHERE id=$1", job["id"])
        if st != "cancelled":
            await db.P().execute("UPDATE jobs SET status='completed', finished_at=now(), updated_at=now() WHERE id=$1",
                                 job["id"])
            await ctx.webhook("completed")
    except Exception as e:
        msg = str(e) or type(e).__name__
        if not isinstance(e, (FetchError, ai.AIUnavailable, ai.AIError, leads.LeadError)):
            traceback.print_exc()
        await db.P().execute("UPDATE jobs SET status='failed', error=$2, finished_at=now(), updated_at=now() WHERE id=$1",
                             job["id"], msg[:1000])
        await ctx.webhook("failed")


async def worker(n):
    while True:
        try:
            job = await db.P().fetchrow(
                "UPDATE jobs SET status='running', started_at=coalesce(started_at, now()), updated_at=now() "
                "WHERE id=(SELECT id FROM jobs WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)"
                " RETURNING *")
        except Exception:
            await asyncio.sleep(5)
            continue
        if not job:
            _wake.clear()
            try:
                await asyncio.wait_for(_wake.wait(), 3)
            except asyncio.TimeoutError:
                pass
            continue
        await _run(job)


async def monitor_loop():
    while True:
        try:
            due = await db.P().fetch("SELECT * FROM monitors WHERE active AND next_run <= now() LIMIT 5")
            for m in due:
                await check_monitor(m)
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(30)


async def check_monitor(m):
    nxt = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=max(15, m["interval_minutes"]))
    try:
        doc, _ = await scrape(m["url"], {**(m["params"] or {}), "formats": ["markdown"]}, None)
        md = doc.get("markdown", "")
        if m["last_markdown"] is None:
            status, diff = "new", None
        elif m["last_markdown"] == md:
            status, diff = "same", None
        else:
            status = "changed"
            diff = "".join(difflib.unified_diff(m["last_markdown"].splitlines(True), md.splitlines(True),
                                                "previous", "current", n=1))[:50000]
        await db.P().execute("INSERT INTO monitor_checks(monitor_id,status,change_status,diff) VALUES($1,'ok',$2,$3)",
                             m["id"], status, diff)
        await db.P().execute("UPDATE monitors SET last_markdown=$2, next_run=$3 WHERE id=$1", m["id"], md, nxt)
        if status == "changed" and m["webhook"]:
            await webhook_send(m["user_id"], m["webhook"], "monitor.changed", str(m["id"]),
                               [{"url": m["url"], "diff": diff}])
    except Exception as e:
        await db.P().execute("INSERT INTO monitor_checks(monitor_id,status,error) VALUES($1,'error',$2)",
                             m["id"], str(e)[:500])
        await db.P().execute("UPDATE monitors SET next_run=$2 WHERE id=$1", m["id"], nxt)
