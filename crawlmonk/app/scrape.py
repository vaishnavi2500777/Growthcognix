"""Single-page scrape producing a Firecrawl-compatible document."""
import base64
import difflib
import time
import uuid

from . import ai, browser, config, db, parse
from .net import FetchError, fetch

TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/plain", "application/xml", "text/xml", "")


def norm_formats(formats):
    """Accept Firecrawl v1 strings ('screenshot@fullPage') and v2 objects ({'type':'json',...})."""
    out = {}
    for f in formats or ["markdown"]:
        if isinstance(f, str):
            if f == "screenshot@fullPage":
                out["screenshot"] = {"type": "screenshot", "fullPage": True}
            elif f == "extract":
                out["json"] = {"type": "json"}
            else:
                out[f] = {"type": f}
        elif isinstance(f, dict) and f.get("type"):
            out[f["type"]] = f
    return out


async def _save_file(data: bytes, mime="image/png") -> str:
    fid = uuid.uuid4()
    await db.P().execute("INSERT INTO files(id,mime,data) VALUES($1,$2,$3)", fid, mime, data)
    return f"{config.PUBLIC_URL}/files/{fid}"


def looks_js_only(html: str, text: str) -> bool:
    return len(text) < 250 and (html.count("<script") >= 3 or 'id="root"' in html or 'id="__next"' in html
                                or 'id="app"' in html)


async def scrape(url: str, opts: dict | None = None, user_id: int | None = None) -> tuple[dict, int]:
    o = opts or {}
    fm = norm_formats(o.get("formats"))
    timeout = max(3, min(int(o.get("timeout", 30000)) // 1000, 90))
    mobile = bool(o.get("mobile"))
    headers = o.get("headers") or None
    actions = o.get("actions") or []
    wait_for = int(o.get("waitFor", 0) or 0)
    engine = o.get("engine", "auto")  # auto | static | browser
    shot_mode = None
    if "screenshot" in fm:
        shot_mode = "full" if fm["screenshot"].get("fullPage") else "viewport"
    need_browser = engine == "browser" or bool(actions) or bool(shot_mode) or wait_for > 0
    t0 = time.monotonic()
    warning = None
    html = None
    status, final_url, ct = 200, url, "text/html"
    rendered = None
    doc_md = None
    doc_meta = {}
    credits = 1

    if need_browser:
        if not browser.available():
            raise FetchError("This request needs the headless browser (actions/screenshot/waitFor), "
                             "which is not available on this server", "BROWSER_UNAVAILABLE")
        rendered = await browser.render(url, wait_for=wait_for, timeout=timeout, mobile=mobile, headers=headers,
                                        actions=actions, screenshot=shot_mode)
        html, final_url, status = rendered["html"], rendered["final_url"], rendered["status"]
        engine_used = "browser"
    else:
        r = await fetch(url, headers=headers, timeout=timeout, mobile=mobile,
                        max_age_ms=int(o.get("maxAge", 0) or 0))
        status, final_url, ct = r.status, r.final_url, r.content_type
        engine_used = "cache" if getattr(r, "cached", False) else "static"
        kind = parse.doc_kind(ct, final_url, r.body[:8])
        if kind and o.get("parsePDF", True) is not False:
            try:
                doc_md, doc_meta = parse.doc_to_markdown(kind, r.body)
            except Exception as e:
                raise FetchError(f"Could not parse {kind.upper()}: {type(e).__name__}", "PARSE_ERROR")
            engine_used += f"+{kind}"
        elif ct not in TEXT_TYPES and not ct.startswith("text/"):
            raise FetchError(f"Unsupported content type {ct}", "UNSUPPORTED_TYPE")
        else:
            html = r.text
            txt = parse.soup_of(html).get_text(" ", strip=True)
            blocked = status in (403, 429, 503)
            if engine == "auto" and browser.available() and (looks_js_only(html, txt) or blocked):
                try:
                    rendered = await browser.render(url, timeout=timeout, mobile=mobile, headers=headers)
                    html, final_url, status = rendered["html"], rendered["final_url"], rendered["status"]
                    engine_used = "browser(fallback)"
                except FetchError as e:
                    warning = f"Browser fallback failed: {e}"
            elif engine == "auto" and looks_js_only(html, txt):
                warning = "Page looks JavaScript-rendered; headless browser unavailable, content may be incomplete"

    out = {}
    if doc_md is not None:
        md = doc_md
        meta = {"sourceURL": url, "url": final_url, "statusCode": status, "contentType": ct, **doc_meta}
        soup = None
    else:
        soup = parse.soup_of(html)
        parse.absolutize(soup, final_url)
        meta = parse.metadata(soup, url, status, ct)
        meta["url"] = final_url
        raw_after_abs = str(soup)
        if "rawHtml" in fm:
            out["rawHtml"] = html
        if "links" in fm:
            out["links"] = parse.links(soup)
        if "images" in fm:
            out["images"] = parse.images(soup)
        if "contacts" in fm:
            out["contacts"] = parse.contacts(soup)
        cleaned = parse.clean(parse.soup_of(raw_after_abs), only_main=o.get("onlyMainContent", True),
                              include_tags=o.get("includeTags"), exclude_tags=o.get("excludeTags"))
        if "html" in fm:
            body = cleaned.body or cleaned
            out["html"] = str(body)
        md = parse.to_markdown(cleaned.body or cleaned)
    if "markdown" in fm or "json" in fm or "summary" in fm or "changeTracking" in fm:
        if "markdown" in fm:
            out["markdown"] = md
    if rendered and rendered.get("screenshot"):
        out["screenshot"] = await _save_file(rendered["screenshot"])
    if rendered and rendered.get("actions"):
        acts = rendered["actions"]
        out["actions"] = {"screenshots": [await _save_file(p) for p in acts["screenshots"]],
                          "scrapes": [{"url": s["url"], "markdown": parse.to_markdown(
                              parse.clean(parse.soup_of(s["html"])))} for s in acts["scrapes"]],
                          "javascriptReturns": acts["javascriptReturns"]}
    if "json" in fm:
        f = fm["json"]
        out["json"] = await ai.extract_json(md, f.get("prompt") or o.get("jsonOptions", {}).get("prompt"),
                                            f.get("schema") or o.get("jsonOptions", {}).get("schema"))
        credits += 4
    if "summary" in fm:
        out["summary"] = await ai.summarize(md)
        credits += 1
    if "changeTracking" in fm and user_id:
        tag = fm["changeTracking"].get("tag") or ""
        prev = await db.P().fetchrow("SELECT markdown, at FROM snapshots WHERE user_id=$1 AND url=$2 AND tag=$3",
                                     user_id, url, tag)
        ctk = {"previousScrapeAt": prev["at"].isoformat() if prev else None, "visibility": "visible"}
        if not prev:
            ctk["changeStatus"] = "new"
        elif prev["markdown"] == md:
            ctk["changeStatus"] = "same"
        else:
            ctk["changeStatus"] = "changed"
            ctk["diff"] = {"text": "".join(difflib.unified_diff(
                prev["markdown"].splitlines(True), md.splitlines(True), "previous", "current", n=1))[:50000]}
        await db.P().execute(
            "INSERT INTO snapshots(user_id,url,tag,markdown,at) VALUES($1,$2,$3,$4,now()) "
            "ON CONFLICT(user_id,url,tag) DO UPDATE SET markdown=$4, at=now()", user_id, url, tag, md)
        out["changeTracking"] = ctk
    meta["engine"] = engine_used
    meta["elapsedMs"] = int((time.monotonic() - t0) * 1000)
    if status >= 400:
        meta["error"] = f"Target returned HTTP {status}"
    out["metadata"] = meta
    if warning:
        out["warning"] = warning
    return out, credits


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()
