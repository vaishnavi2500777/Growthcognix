"""Minimal MCP server (Streamable HTTP, JSON responses) exposing CrawlMonk tools. Auth: Bearer API key."""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import auth, crawler, queue, search
from .scrape import scrape

router = APIRouter()
TOOLS = [
    {"name": "crawlmonk_scrape", "description": "Scrape one URL to clean markdown (+ links, contacts).",
     "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "formats": {"type": "array", "items": {"type": "string"}}}, "required": ["url"]}},
    {"name": "crawlmonk_map", "description": "List URLs of a website (sitemap + links + search).",
     "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "search": {"type": "string"}}, "required": ["url"]}},
    {"name": "crawlmonk_search", "description": "Web search (Bing/DuckDuckGo) and news (Google News RSS).",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}},
    {"name": "crawlmonk_find_leads", "description": "Start a city-wise Indian business lead search; returns a job id. Poll with crawlmonk_job_status.",
     "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}, "state": {"type": "string"}, "category": {"type": "string"}, "max_leads": {"type": "integer"}}, "required": ["city", "category"]}},
    {"name": "crawlmonk_crawl", "description": "Start an async crawl of a site; returns a job id.",
     "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["url"]}},
    {"name": "crawlmonk_job_status", "description": "Status and results of a crawl or leads job.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
]


async def call(uid, name, a):
    if name == "crawlmonk_scrape":
        d, c = await scrape(a["url"], {"formats": a.get("formats") or ["markdown", "contacts"]}, uid)
        await auth.charge(uid, "mcp", c)
        return d
    if name == "crawlmonk_map":
        return {"links": await crawler.map_site(a["url"], search_q=a.get("search"), limit=500)}
    if name == "crawlmonk_search":
        d, w = await search.search(a["query"], int(a.get("limit", 5)), ["web", "news"])
        return d
    if name == "crawlmonk_find_leads":
        jid = await queue.enqueue(uid, "leads", {"cities": [{"city": a["city"], "state": a.get("state")}],
                                                 "category": a["category"], "max_leads": a.get("max_leads", 40)})
        return {"id": jid}
    if name == "crawlmonk_crawl":
        return {"id": await queue.enqueue(uid, "crawl", {"url": a["url"], "limit": min(int(a.get("limit", 10)), 50)})}
    if name == "crawlmonk_job_status":
        from . import db
        import uuid
        j = await db.P().fetchrow("SELECT id,kind,status,progress,error FROM jobs WHERE id=$1 AND user_id=$2",
                                  uuid.UUID(a["id"]), uid)
        if not j:
            return {"error": "not found"}
        out = {"status": j["status"], "progress": j["progress"], "error": j["error"]}
        if j["kind"] == "leads":
            rows = await db.P().fetch("SELECT name,city,score,phone,emails,website,reason FROM leads WHERE job_id=$1 "
                                      "ORDER BY score DESC LIMIT 50", j["id"])
            out["leads"] = [dict(r) for r in rows]
        else:
            rows = await db.P().fetch("SELECT doc FROM job_docs WHERE job_id=$1 ORDER BY id LIMIT 20", j["id"])
            out["data"] = [{"url": r["doc"].get("metadata", {}).get("sourceURL"),
                            "markdown": (r["doc"].get("markdown") or "")[:4000]} for r in rows]
        return out
    raise ValueError(f"Unknown tool {name}")


@router.post("/mcp")
async def mcp(req: Request):
    msg = await req.json()
    mid, method = msg.get("id"), msg.get("method")

    def ok(result):
        return JSONResponse({"jsonrpc": "2.0", "id": mid, "result": result})
    if method == "initialize":
        return ok({"protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                   "serverInfo": {"name": "crawlmonk", "version": "1.0"}})
    if method and method.startswith("notifications/"):
        return JSONResponse(None, status_code=202)
    if method == "ping":
        return ok({})
    uid = await auth.current_user(req)
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        p = msg.get("params") or {}
        try:
            res = await call(uid, p.get("name"), p.get("arguments") or {})
            return ok({"content": [{"type": "text", "text": json.dumps(res, default=str)[:200000]}]})
        except Exception as e:
            return ok({"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True})
    return JSONResponse({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "Method not found"}})
