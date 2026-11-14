import asyncio
import csv
import io
import json
import os
import uuid

from fastapi import APIRouter, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import ai, auth, browser, config, crawler, db, parse, queue, search
from .auth import User
from .net import FetchError
from .scrape import scrape

app = FastAPI(title="CrawlMonk API", version="1.0", docs_url="/docs", redoc_url=None)
STATIC = os.path.join(os.path.dirname(__file__), "..", "static")


@app.on_event("startup")
async def startup():
    await db.connect()
    for i in range(queue.WORKERS):
        asyncio.create_task(queue.worker(i))
    asyncio.create_task(queue.monitor_loop())
    asyncio.create_task(browser.idle_reaper())


@app.exception_handler(FetchError)
async def fetch_err(req, e: FetchError):
    return JSONResponse({"success": False, "error": str(e), "code": e.code}, status_code=400 if e.code in (
        "INVALID_URL", "BLOCKED_PRIVATE", "BAD_ACTION", "UNSUPPORTED_TYPE") else 502)


@app.exception_handler(Exception)
async def any_err(req, e):
    import traceback
    traceback.print_exc()
    return JSONResponse({"success": False, "error": f"Internal error: {type(e).__name__}", "code": "INTERNAL"},
                        status_code=500)


@app.exception_handler(ai.AIUnavailable)
async def ai_un(req, e):
    return JSONResponse({"success": False, "error": str(e), "code": "AI_UNAVAILABLE"}, status_code=503)


@app.exception_handler(ai.AIError)
async def ai_err(req, e):
    return JSONResponse({"success": False, "error": str(e), "code": "AI_ERROR"}, status_code=502)


@app.exception_handler(HTTPException)
async def http_err(req, e: HTTPException):
    d = e.detail if isinstance(e.detail, dict) else {"success": False, "error": str(e.detail)}
    return JSONResponse(d, status_code=e.status_code)


@app.get("/health")
async def health():
    return {"ok": True, "browser": browser.available(), "ai": ai.enabled(), "model": config.GEMINI_MODEL}


@app.get("/files/{fid}")
async def get_file(fid: uuid.UUID):
    row = await db.P().fetchrow("SELECT mime,data FROM files WHERE id=$1", fid)
    if not row:
        raise HTTPException(404, "not found")
    return Response(bytes(row["data"]), media_type=row["mime"], headers={"Cache-Control": "public, max-age=86400"})


# ---------------- auth ----------------
@app.post("/auth/signup")
async def signup(req: Request):
    auth.rate_limit("signup:" + auth.client_ip(req), 5, 3600)
    auth.rate_limit("signup:all", 60, 3600)
    b = await req.json()
    uid = await auth.signup(b.get("email", ""), b.get("password", ""))
    return {"success": True, "token": auth.make_token(uid)}


@app.post("/auth/login")
async def login(req: Request):
    auth.rate_limit("login:" + auth.client_ip(req), 20, 600)
    b = await req.json()
    uid = await auth.login(b.get("email", ""), b.get("password", ""))
    return {"success": True, "token": auth.make_token(uid)}


@app.get("/auth/me")
async def me(uid: int = User):
    row = await db.P().fetchrow("SELECT id,email,webhook_secret,created_at FROM users WHERE id=$1", uid)
    return {"success": True, "user": dict(row), "usedToday": await auth.used_today(uid),
            "dailyCredits": config.DAILY_CREDITS}


api = APIRouter()


def url_of(b: dict) -> str:
    u = (b.get("url") or "").strip()
    if not u:
        raise HTTPException(400, {"success": False, "error": "url is required"})
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


# ---------------- scrape / map / search ----------------
@api.post("/scrape")
async def r_scrape(req: Request, uid: int = User):
    b = await req.json()
    await auth.require_credits(uid)
    doc, credits = await scrape(url_of(b), b, uid)
    await auth.charge(uid, "scrape", credits)
    return {"success": True, "data": doc}


@api.post("/map")
async def r_map(req: Request, uid: int = User):
    b = await req.json()
    await auth.require_credits(uid)
    links = await crawler.map_site(url_of(b), search_q=b.get("search"),
                                   include_subdomains=b.get("includeSubdomains", True),
                                   limit=min(int(b.get("limit", 5000)), 30000), sitemap=b.get("sitemap", "include"),
                                   ignore_query=b.get("ignoreQueryParameters", True))
    await auth.charge(uid, "map", 1)
    return {"success": True, "links": links}


@api.post("/search")
async def r_search(req: Request, uid: int = User):
    b = await req.json()
    q = (b.get("query") or "").strip()
    if not q:
        raise HTTPException(400, {"success": False, "error": "query is required"})
    limit = max(1, min(int(b.get("limit", 5)), 30))
    await auth.require_credits(uid, 1)
    data, warns = await search.search(q, limit, b.get("sources"), b.get("tbs"))
    so = b.get("scrapeOptions")
    credits = 1
    if so and so.get("formats"):
        async def one(item):
            try:
                d, c = await scrape(item["url"], so, uid)
                item.update({k: v for k, v in d.items()})
                return c
            except Exception as e:
                item["error"] = str(e)
                return 0
        credits += sum(await asyncio.gather(*(one(x) for x in data.get("web", []))))
    await auth.charge(uid, "search", credits)
    out = {"success": True, "data": data}
    if warns:
        out["warning"] = "; ".join(warns)
    return out


# ---------------- async jobs ----------------
def job_url(req: Request, kind: str, jid: str) -> str:
    return f"{config.PUBLIC_URL}{req.url.path.rsplit('/', 1)[0] if kind == 'x' else ''}/{jid}"


@api.post("/crawl")
async def r_crawl(req: Request, uid: int = User):
    b = await req.json()
    b["url"] = url_of(b)
    await crawler.net.check_url(b["url"])
    await auth.require_credits(uid, 1)
    b["limit"] = min(int(b.get("limit", 10)), config.MAX_CRAWL_LIMIT)
    jid = await queue.enqueue(uid, "crawl", b)
    return {"success": True, "id": jid, "url": f"{config.PUBLIC_URL}{req.url.path}/{jid}"}


@api.post("/batch/scrape")
async def r_batch(req: Request, uid: int = User):
    b = await req.json()
    urls = [u if u.startswith("http") else "https://" + u for u in (b.get("urls") or [])][:500]
    if not urls:
        raise HTTPException(400, {"success": False, "error": "urls is required"})
    await auth.require_credits(uid, len(urls))
    b["urls"] = urls
    jid = await queue.enqueue(uid, "batch_scrape", b)
    return {"success": True, "id": jid, "url": f"{config.PUBLIC_URL}{req.url.path}/{jid}"}


@api.post("/extract")
async def r_extract(req: Request, uid: int = User):
    b = await req.json()
    if not ai.enabled():
        raise ai.AIUnavailable("GEMINI_API_KEY is not set on the server; /extract is disabled")
    if not b.get("urls") and not b.get("enableWebSearch"):
        raise HTTPException(400, {"success": False, "error": "urls is required"})
    await auth.require_credits(uid, 5)
    jid = await queue.enqueue(uid, "extract", b)
    await auth.charge(uid, "extract", 5)
    return {"success": True, "id": jid}


@api.post("/agent")
async def r_agent(req: Request, uid: int = User):
    b = await req.json()
    if not ai.enabled():
        raise ai.AIUnavailable("GEMINI_API_KEY is not set on the server; /agent is disabled")
    if not b.get("prompt"):
        raise HTTPException(400, {"success": False, "error": "prompt is required"})
    await auth.require_credits(uid, 10)
    jid = await queue.enqueue(uid, "agent", b)
    await auth.charge(uid, "agent", 10)
    return {"success": True, "id": jid}


async def job_or_404(jid: str, uid: int, kinds: tuple):
    try:
        j = await db.P().fetchrow("SELECT * FROM jobs WHERE id=$1 AND user_id=$2", uuid.UUID(jid), uid)
    except ValueError:
        j = None
    if not j or j["kind"] not in kinds:
        raise HTTPException(404, {"success": False, "error": "Job not found"})
    return j


STATUS = {"queued": "scraping", "running": "scraping", "completed": "completed", "failed": "failed",
          "cancelled": "cancelled"}


async def job_status(req: Request, jid: str, uid: int, kinds: tuple):
    j = await job_or_404(jid, uid, kinds)
    skip = int(req.query_params.get("skip", 0))
    page = 100
    docs = await db.P().fetch("SELECT doc FROM job_docs WHERE job_id=$1 ORDER BY id OFFSET $2 LIMIT $3",
                              j["id"], skip, page + 1)
    count = await db.P().fetchval("SELECT count(*) FROM job_docs WHERE job_id=$1", j["id"])
    pr = j["progress"] or {}
    out = {"success": True, "status": STATUS[j["status"]], "jobStatus": j["status"],
           "total": pr.get("total", count), "completed": pr.get("completed", count), "creditsUsed": count,
           "progress": pr, "error": j["error"], "createdAt": j["created_at"].isoformat(),
           "data": [d["doc"] for d in docs[:page]]}
    if len(docs) > page:
        out["next"] = f"{config.PUBLIC_URL}{req.url.path}?skip={skip + page}"
    if j["kind"] in ("extract", "agent"):
        d = out.pop("data")
        out["data"] = d[0]["data"] if d else None
        if d:
            out["sources"] = d[0].get("sources") or d[0].get("pagesRead")
            if d[0].get("steps"):
                out["steps"] = d[0]["steps"]
    return out


async def cancel(jid, uid, kinds):
    j = await job_or_404(jid, uid, kinds)
    if j["status"] in ("queued", "running"):
        await db.P().execute("UPDATE jobs SET status='cancelled', finished_at=now() WHERE id=$1", j["id"])
    return {"success": True, "status": "cancelled"}


@api.get("/crawl/{jid}")
async def g_crawl(req: Request, jid: str, uid: int = User):
    return await job_status(req, jid, uid, ("crawl",))


@api.delete("/crawl/{jid}")
async def d_crawl(jid: str, uid: int = User):
    return await cancel(jid, uid, ("crawl",))


@api.get("/crawl/{jid}/errors")
async def e_crawl(jid: str, uid: int = User):
    j = await job_or_404(jid, uid, ("crawl", "batch_scrape"))
    pr = j["progress"] or {}
    return {"success": True, "errors": [pr["lastError"]] if pr.get("lastError") else [],
            "robotsBlocked": pr.get("robotsSkipped", 0)}


@api.get("/batch/scrape/{jid}")
async def g_batch(req: Request, jid: str, uid: int = User):
    return await job_status(req, jid, uid, ("batch_scrape",))


@api.delete("/batch/scrape/{jid}")
async def d_batch(jid: str, uid: int = User):
    return await cancel(jid, uid, ("batch_scrape",))


@api.get("/extract/{jid}")
async def g_extract(req: Request, jid: str, uid: int = User):
    return await job_status(req, jid, uid, ("extract",))


@api.get("/agent/{jid}")
async def g_agent(req: Request, jid: str, uid: int = User):
    return await job_status(req, jid, uid, ("agent",))


@api.get("/jobs")
async def jobs(uid: int = User):
    rows = await db.P().fetch("SELECT id,kind,status,params,progress,error,created_at,finished_at FROM jobs "
                              "WHERE user_id=$1 ORDER BY created_at DESC LIMIT 100", uid)
    return {"success": True, "jobs": [{**dict(r), "id": str(r["id"])} for r in rows]}


# ---------------- Lead Finder ----------------
@api.post("/leads")
async def r_leads(req: Request, uid: int = User):
    b = await req.json()
    cities = b.get("cities") or ([{"city": b.get("city"), "state": b.get("state")}] if b.get("city") else [])
    cities = [c if isinstance(c, dict) else {"city": c} for c in cities if c][:10]
    if not cities or not (b.get("category") or "").strip():
        raise HTTPException(400, {"success": False, "error": "city (or cities) and category are required"})
    b["cities"] = cities
    await auth.require_credits(uid, 10 * len(cities))
    jid = await queue.enqueue(uid, "leads", b)
    await auth.charge(uid, "leads", 10 * len(cities))
    return {"success": True, "id": jid}


LEAD_COLS = ["city", "name", "score", "category", "phone", "phones", "emails", "website", "address", "socials",
             "reason", "ai_reason", "signals", "lat", "lon", "source", "source_ref"]


@api.get("/leads/{jid}")
async def g_leads(jid: str, uid: int = User):
    j = await job_or_404(jid, uid, ("leads",))
    rows = await db.P().fetch(f"SELECT {','.join(LEAD_COLS)} FROM leads WHERE job_id=$1 ORDER BY score DESC, id",
                              j["id"])
    return {"success": True, "status": j["status"], "progress": j["progress"], "error": j["error"],
            "params": j["params"], "leads": [dict(r) for r in rows]}


@api.delete("/leads/{jid}")
async def d_leads(jid: str, uid: int = User):
    return await cancel(jid, uid, ("leads",))


@api.get("/leads/{jid}/csv")
async def csv_leads(jid: str, uid: int = User):
    j = await job_or_404(jid, uid, ("leads",))
    rows = await db.P().fetch(f"SELECT {','.join(LEAD_COLS)} FROM leads WHERE job_id=$1 ORDER BY city, score DESC",
                              j["id"])
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(LEAD_COLS)
    for r in rows:
        w.writerow([("; ".join(v) if isinstance(v, list) else json.dumps(v) if isinstance(v, dict) else
                     ("" if v is None else v)) for v in (r[c] for c in LEAD_COLS)])
    name = "crawlmonk-leads-" + "-".join(c["city"] for c in j["params"]["cities"]).replace(" ", "_")[:60] + ".csv"
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------- parse (upload) ----------------
@api.get("/parse/formats")
async def parse_formats():
    return {"success": True, "formats": ["pdf", "docx", "xlsx", "html", "txt", "md"]}


@api.post("/parse")
async def r_parse(file: UploadFile = File(...), uid: int = User):
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, {"success": False, "error": "File larger than 15 MB"})
    name = (file.filename or "").lower()
    kind = parse.doc_kind(file.content_type or "", name, data[:8])
    if kind:
        md, meta = parse.doc_to_markdown(kind, data)
    elif name.endswith((".html", ".htm")) or "html" in (file.content_type or ""):
        s = parse.clean(parse.soup_of(data.decode("utf-8", "replace")))
        md, meta = parse.to_markdown(s.body or s), {"kind": "html"}
    elif name.endswith((".txt", ".md", ".csv")):
        md, meta = data.decode("utf-8", "replace"), {"kind": "text"}
    else:
        raise HTTPException(400, {"success": False, "error": "Unsupported file type (pdf, docx, xlsx, html, txt)"})
    await auth.charge(uid, "parse", 1)
    return {"success": True, "data": {"markdown": md, "metadata": {"filename": file.filename, **meta}}}


# ---------------- monitors (change tracking) ----------------
@api.post("/monitor")
async def r_monitor(req: Request, uid: int = User):
    b = await req.json()
    u = url_of(b)
    await crawler.net.check_url(u)
    mid = uuid.uuid4()
    await db.P().execute("INSERT INTO monitors(id,user_id,url,name,interval_minutes,webhook,params) "
                         "VALUES($1,$2,$3,$4,$5,$6,$7)", mid, uid, u, b.get("name") or u,
                         max(15, int(b.get("intervalMinutes", 60))), b.get("webhook"), b.get("scrapeOptions") or {})
    return {"success": True, "id": str(mid)}


@api.get("/monitor")
async def l_monitor(uid: int = User):
    rows = await db.P().fetch("SELECT m.id,m.url,m.name,m.interval_minutes,m.active,m.next_run,m.created_at,"
                              "(SELECT change_status FROM monitor_checks c WHERE c.monitor_id=m.id ORDER BY id DESC LIMIT 1) last_change "
                              "FROM monitors m WHERE user_id=$1 ORDER BY created_at DESC", uid)
    return {"success": True, "monitors": [{**dict(r), "id": str(r["id"])} for r in rows]}


@api.get("/monitor/{mid}/checks")
async def c_monitor(mid: uuid.UUID, uid: int = User):
    ok = await db.P().fetchval("SELECT 1 FROM monitors WHERE id=$1 AND user_id=$2", mid, uid)
    if not ok:
        raise HTTPException(404, {"success": False, "error": "Monitor not found"})
    rows = await db.P().fetch("SELECT id,status,change_status,diff,error,at FROM monitor_checks WHERE monitor_id=$1 "
                              "ORDER BY id DESC LIMIT 50", mid)
    return {"success": True, "checks": [dict(r) for r in rows]}


@api.post("/monitor/{mid}/run")
async def run_monitor(mid: uuid.UUID, uid: int = User):
    m = await db.P().fetchrow("SELECT * FROM monitors WHERE id=$1 AND user_id=$2", mid, uid)
    if not m:
        raise HTTPException(404, {"success": False, "error": "Monitor not found"})
    await queue.check_monitor(m)
    return await c_monitor(mid, uid)


@api.delete("/monitor/{mid}")
async def del_monitor(mid: uuid.UUID, uid: int = User):
    await db.P().execute("DELETE FROM monitors WHERE id=$1 AND user_id=$2", mid, uid)
    return {"success": True}


# ---------------- interact (live browser session) ----------------
@api.post("/interact")
async def i_open(req: Request, uid: int = User):
    b = await req.json()
    await auth.require_credits(uid, 2)
    st = await browser.open_session(url_of(b), bool(b.get("mobile")))
    await auth.charge(uid, "interact", 2)
    st["markdown"] = parse.to_markdown(parse.clean(parse.soup_of(st.pop("html"))))
    return {"success": True, **st}


@api.post("/interact/{sid}")
async def i_act(sid: str, req: Request, uid: int = User):
    b = await req.json()
    st = await browser.session_act(sid, b.get("actions") or [])
    st["markdown"] = parse.to_markdown(parse.clean(parse.soup_of(st.pop("html"))))
    await auth.charge(uid, "interact", 1)
    return {"success": True, **st}


@api.delete("/interact/{sid}")
async def i_close(sid: str, uid: int = User):
    await browser.close_session(sid)
    return {"success": True}


# ---------------- keys & usage ----------------
@api.post("/keys")
async def k_create(req: Request, uid: int = User):
    b = await req.json() if (await req.body()) else {}
    n = await db.P().fetchval("SELECT count(*) FROM api_keys WHERE user_id=$1 AND NOT revoked", uid)
    if n >= 10:
        raise HTTPException(400, {"success": False, "error": "Max 10 active keys"})
    return {"success": True, "key": await auth.create_key(uid, b.get("name"))}


@api.get("/keys")
async def k_list(uid: int = User):
    rows = await db.P().fetch("SELECT id,prefix,name,created_at FROM api_keys WHERE user_id=$1 AND NOT revoked "
                              "ORDER BY id", uid)
    return {"success": True, "keys": [dict(r) for r in rows]}


@api.delete("/keys/{kid}")
async def k_del(kid: int, uid: int = User):
    await db.P().execute("UPDATE api_keys SET revoked=true WHERE id=$1 AND user_id=$2", kid, uid)
    return {"success": True}


@api.get("/team/credit-usage")
async def usage(uid: int = User):
    used = await auth.used_today(uid)
    rows = await db.P().fetch("SELECT endpoint, sum(credits) credits, count(*) calls FROM usage WHERE user_id=$1 "
                              "AND at > now() - interval '30 days' GROUP BY endpoint ORDER BY 2 DESC", uid)
    return {"success": True, "data": {"remainingCredits": max(0, config.DAILY_CREDITS - used), "usedLast24h": used,
                                      "dailyLimit": config.DAILY_CREDITS,
                                      "last30DaysByEndpoint": [dict(r) for r in rows]}}


app.include_router(api, prefix="/v1")
app.include_router(api, prefix="/v2")

from .mcp import router as mcp_router  # noqa: E402
app.include_router(mcp_router)


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")
