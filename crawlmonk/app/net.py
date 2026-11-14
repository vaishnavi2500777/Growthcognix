"""Safe HTTP fetching: SSRF guard, redirects checked hop by hop, robots.txt, per-host politeness, cache."""
import asyncio
import hashlib
import ipaddress
import socket
import time
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

import httpx

from . import config, db

MAX_BYTES = 15 * 1024 * 1024


class FetchError(Exception):
    def __init__(self, msg, code="FETCH_ERROR", status=None):
        super().__init__(msg)
        self.code = code
        self.status = status


def _ip_ok(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    return a.is_global and not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast
                                or a.is_reserved or a.is_unspecified)


async def check_url(url: str) -> str:
    """Raise FetchError if url is not public http(s). Returns normalized url."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise FetchError("Only public http(s) URLs are allowed", "INVALID_URL")
    host = p.hostname
    if host in ("localhost",) or host.endswith(".local") or host.endswith(".internal"):
        raise FetchError("Private hosts are blocked", "BLOCKED_PRIVATE")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80),
                                                              type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise FetchError(f"DNS lookup failed for {host}", "DNS_ERROR")
    for info in infos:
        if not _ip_ok(info[4][0]):
            raise FetchError("URL resolves to a private/reserved IP; blocked", "BLOCKED_PRIVATE")
    return url


_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(follow_redirects=False, http2=False,
                                    timeout=httpx.Timeout(20, connect=10),
                                    limits=httpx.Limits(max_connections=40, max_keepalive_connections=10))
    return _client


# politeness: minimum gap between requests to the same host
_host_last: dict[str, float] = {}
_host_locks: dict[str, asyncio.Lock] = {}


async def polite(host: str, delay: float):
    if delay <= 0:
        return
    lock = _host_locks.setdefault(host, asyncio.Lock())
    async with lock:
        wait = _host_last.get(host, 0) + delay - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _host_last[host] = time.monotonic()


class Resp:
    def __init__(self, url, final_url, status, headers, body: bytes):
        self.url, self.final_url, self.status, self.headers, self.body = url, final_url, status, headers, body

    @property
    def content_type(self):
        return (self.headers.get("content-type") or "").split(";")[0].strip().lower()

    @property
    def text(self):
        enc = "utf-8"
        ct = self.headers.get("content-type") or ""
        if "charset=" in ct:
            enc = ct.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        try:
            return self.body.decode(enc, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


async def fetch(url: str, *, headers: dict | None = None, timeout: float = 20, mobile=False, ua=None,
                delay: float = 0.0, method="GET", data=None, max_age_ms: int = 0) -> Resp:
    key = None
    if max_age_ms and method == "GET" and not headers:
        key = hashlib.sha256(f"{url}|{mobile}".encode()).hexdigest()
        row = await db.P().fetchrow(
            "SELECT * FROM page_cache WHERE key=$1 AND fetched_at > now() - make_interval(secs => $2)",
            key, max_age_ms / 1000)
        if row:
            r = Resp(url, row["final_url"], row["status"], {"content-type": row["content_type"]}, bytes(row["body"]))
            r.cached = True
            return r
    h = {"User-Agent": ua or (config.MOBILE_UA if mobile else config.BROWSER_UA),
         "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
         "Accept-Language": "en-IN,en;q=0.9"}
    if headers:
        h.update({k: v for k, v in headers.items() if k.lower() not in ("host",)})
    cur = url
    for _ in range(6):
        await check_url(cur)
        await polite(urlparse(cur).hostname, delay)
        try:
            req = client().build_request(method, cur, headers=h, content=data,
                                         timeout=httpx.Timeout(timeout, connect=min(10, timeout)))
            r = await client().send(req, stream=True)
        except httpx.TimeoutException:
            raise FetchError(f"Timed out after {timeout}s", "TIMEOUT")
        except httpx.HTTPError as e:
            raise FetchError(f"Connection failed: {type(e).__name__}", "CONNECTION_ERROR")
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
            await r.aclose()
            cur = urljoin(cur, r.headers["location"])
            if r.status_code == 303:
                method, data = "GET", None
            continue
        body = b""
        try:
            async for chunk in r.aiter_bytes():
                body += chunk
                if len(body) > MAX_BYTES:
                    raise FetchError("Response larger than 15 MB", "TOO_LARGE")
        finally:
            await r.aclose()
        resp = Resp(url, str(r.url), r.status_code, dict(r.headers), body)
        resp.cached = False
        if key and r.status_code < 400 and len(body) < 3_000_000:
            await db.P().execute(
                "INSERT INTO page_cache(key,url,status,content_type,final_url,body,fetched_at) "
                "VALUES($1,$2,$3,$4,$5,$6,now()) ON CONFLICT(key) DO UPDATE SET status=$3,content_type=$4,"
                "final_url=$5,body=$6,fetched_at=now()", key, url, r.status_code, resp.content_type,
                resp.final_url, body)
        return resp
    raise FetchError("Too many redirects", "TOO_MANY_REDIRECTS")


_robots: dict[str, tuple[float, RobotFileParser | None]] = {}


async def robots_allowed(url: str, ua="CrawlMonkBot") -> bool:
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    ent = _robots.get(base)
    if not ent or ent[0] < time.time() - 3600:
        rp = None
        try:
            r = await fetch(base + "/robots.txt", timeout=10, ua=config.BOT_UA)
            # Google's rules: 2xx = obey, 4xx = no robots.txt (allow), 5xx/429 = temporarily disallow all
            if r.status < 300 and "html" not in r.content_type:
                rp = RobotFileParser()
                rp.parse(r.text.splitlines())
            elif r.status >= 500 or r.status == 429:
                rp = RobotFileParser()
                rp.parse(["User-agent: *", "Disallow: /"])
        except FetchError:
            rp = None
        ent = (time.time(), rp)
        _robots[base] = ent
    rp = ent[1]
    return True if rp is None else rp.can_fetch(ua, url)


async def robots_sitemaps(url: str) -> list[str]:
    p = urlparse(url)
    await robots_allowed(url)
    rp = _robots.get(f"{p.scheme}://{p.netloc}", (0, None))[1]
    return list(rp.site_maps() or []) if rp else []
