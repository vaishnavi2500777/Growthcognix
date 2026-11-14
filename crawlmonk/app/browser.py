"""Headless Chromium via Playwright. One shared browser, at most 2 pages at once (Render free = 512 MB).
Every network request from the page is checked against the SSRF guard."""
import asyncio
import base64
import time
import uuid
from urllib.parse import urlparse

from . import config
from .net import FetchError, check_url

_pw = None
_browser = None
_lock = asyncio.Lock()
_sem = asyncio.Semaphore(2)
_last_used = 0.0
sessions: dict[str, dict] = {}   # interact sessions


def available() -> bool:
    if not config.BROWSER_ENABLED:
        return False
    try:
        import playwright  # noqa
        return True
    except ImportError:
        return False


async def _get_browser():
    global _pw, _browser, _last_used
    async with _lock:
        _last_used = time.monotonic()
        if _browser and _browser.is_connected():
            return _browser
        from playwright.async_api import async_playwright
        _pw = await async_playwright().start()
        _browser = await _pw.chromium.launch(args=[
            "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--single-process", "--no-zygote",
            "--disable-extensions", "--js-flags=--max-old-space-size=192"])
        return _browser


async def idle_reaper():
    """Close the browser after 90s idle to give memory back."""
    global _browser, _pw
    while True:
        await asyncio.sleep(30)
        now = time.monotonic()
        for sid, s in list(sessions.items()):
            if now - s["last"] > 300:
                await close_session(sid)
        if _browser and not sessions and now - _last_used > 90:
            async with _lock:
                try:
                    await _browser.close()
                    await _pw.stop()
                except Exception:
                    pass
                _browser = _pw = None


async def _guard(route):
    u = route.request.url
    if u.startswith(("data:", "blob:")):
        return await route.continue_()
    try:
        await check_url(u)
    except FetchError:
        return await route.abort()
    rt = route.request.resource_type
    if rt in ("media", "font"):
        return await route.abort()
    await route.continue_()


async def _new_context(mobile=False, headers=None):
    b = await _get_browser()
    ctx = await b.new_context(
        user_agent=config.MOBILE_UA if mobile else config.BROWSER_UA,
        viewport={"width": 390, "height": 844} if mobile else {"width": 1366, "height": 900},
        is_mobile=mobile, has_touch=mobile, locale="en-IN", extra_http_headers=headers or {},
        java_script_enabled=True)
    await ctx.route("**/*", _guard)
    return ctx


async def run_actions(page, actions: list[dict]) -> dict:
    out = {"screenshots": [], "scrapes": [], "javascriptReturns": []}
    for i, a in enumerate(actions or []):
        try:
            await _one_action(page, a, out)
        except FetchError:
            raise
        except Exception as e:
            raise FetchError(f"Action {i} ({a.get('type')}) failed: {str(e).splitlines()[0][:200]}", "ACTION_FAILED")
        await page.wait_for_timeout(150)
    return out


async def _one_action(page, a, out):
    t = a.get("type")
    if True:
        if t == "wait":
            if a.get("selector"):
                await page.wait_for_selector(a["selector"], timeout=a.get("timeout", 15000))
            else:
                await page.wait_for_timeout(min(int(a.get("milliseconds", 1000)), 30000))
        elif t == "click":
            if a.get("all"):
                for el in await page.query_selector_all(a["selector"]):
                    await el.click()
            else:
                await page.click(a["selector"], timeout=10000)
        elif t == "write":
            await page.keyboard.type(a.get("text", ""), delay=20)
        elif t == "press":
            await page.keyboard.press(a.get("key", "Enter"))
        elif t == "scroll":
            dy = 900 if a.get("direction", "down") == "down" else -900
            if a.get("selector"):
                await page.eval_on_selector(a["selector"], f"e=>e.scrollBy(0,{dy})")
            else:
                await page.mouse.wheel(0, dy)
            await page.wait_for_timeout(400)
        elif t == "screenshot":
            png = await page.screenshot(full_page=bool(a.get("fullPage")), type="png")
            out["screenshots"].append(png)
        elif t == "scrape":
            out["scrapes"].append({"url": page.url, "html": await page.content()})
        elif t == "executeJavascript":
            out["javascriptReturns"].append({"value": await page.evaluate(a.get("script", "null"))})
        else:
            raise FetchError(f"Unknown action type: {t}", "BAD_ACTION")


async def render(url: str, *, wait_for=0, timeout=30, mobile=False, headers=None, actions=None,
                 screenshot=None) -> dict:
    """Returns {html, final_url, status, screenshot(png bytes)|None, actions}."""
    if not available():
        raise FetchError("Headless browser not available on this server", "BROWSER_UNAVAILABLE")
    await check_url(url)
    async with _sem:
        ctx = await _new_context(mobile, headers)
        try:
            page = await ctx.new_page()
            page.set_default_timeout(timeout * 1000)
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            except Exception as e:
                raise FetchError(f"Browser navigation failed: {str(e).splitlines()[0][:200]}", "BROWSER_ERROR")
            try:
                await page.wait_for_load_state("networkidle", timeout=min(8000, timeout * 1000))
            except Exception:
                pass
            if wait_for:
                await page.wait_for_timeout(min(int(wait_for), 30000))
            acts = await run_actions(page, actions) if actions else None
            shot = None
            if screenshot:
                shot = await page.screenshot(full_page=screenshot == "full", type="png")
            return {"html": await page.content(), "final_url": page.url,
                    "status": resp.status if resp else 200, "screenshot": shot, "actions": acts}
        except FetchError:
            raise
        except Exception as e:
            raise FetchError(f"Browser error: {str(e).splitlines()[0][:200]}", "BROWSER_ERROR")
        finally:
            await ctx.close()


# ---------- interact sessions (Firecrawl /interact equivalent) ----------

async def open_session(url: str, mobile=False) -> dict:
    if not available():
        raise FetchError("Headless browser not available on this server", "BROWSER_UNAVAILABLE")
    if len(sessions) >= 2:
        raise FetchError("Too many open browser sessions (max 2 on this server); close one first", "SESSION_LIMIT")
    await check_url(url)
    ctx = await _new_context(mobile)
    page = await ctx.new_page()
    page.set_default_timeout(20000)
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    sid = str(uuid.uuid4())
    sessions[sid] = {"ctx": ctx, "page": page, "last": time.monotonic()}
    return await session_state(sid)


async def session_state(sid, shot=True):
    s = sessions[sid]
    s["last"] = time.monotonic()
    p = s["page"]
    png = await p.screenshot(type="png") if shot else None
    return {"sessionId": sid, "url": p.url, "title": await p.title(), "html": await p.content(),
            "screenshot": base64.b64encode(png).decode() if png else None}


async def session_act(sid, actions):
    if sid not in sessions:
        raise FetchError("Session not found or expired (sessions close after 5 idle minutes)", "NOT_FOUND")
    s = sessions[sid]
    s["last"] = time.monotonic()
    acts = await run_actions(s["page"], actions)
    st = await session_state(sid)
    st["actions"] = {"screenshots": [base64.b64encode(x).decode() for x in acts["screenshots"]],
                     "javascriptReturns": acts["javascriptReturns"]}
    return st


async def close_session(sid):
    s = sessions.pop(sid, None)
    if s:
        try:
            await s["ctx"].close()
        except Exception:
            pass


def host_of(u):
    return urlparse(u).hostname
