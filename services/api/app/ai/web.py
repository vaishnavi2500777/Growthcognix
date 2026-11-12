"""Read a public web page as plain text, safely (no internal addresses, size and time limits)."""
import asyncio
import ipaddress
import re
import socket
from html import unescape
from urllib.parse import urlparse

import httpx

MAX_BYTES = 1_500_000
UA = {"user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0 Safari/537.36 GrowthCognixBot/0.1"),
      "accept": "text/html,application/xhtml+xml", "accept-language": "en-IN,en;q=0.9"}


class PageUnavailable(Exception):
    pass


async def _assert_public(host: str) -> None:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise PageUnavailable(f"Could not find {host}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise PageUnavailable("That address is not a public website.")


def html_to_text(html: str) -> tuple[str, str]:
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    meta = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)', html, re.IGNORECASE)
    body = re.sub(r"<(script|style|noscript|svg|nav|footer)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"\s+", " ", unescape(body)).strip()
    if meta:
        text = unescape(meta.group(1)).strip() + "\n" + text
    return (unescape(title.group(1)).strip() if title else ""), text


async def read_page(url: str, max_chars: int = 12000) -> tuple[str, str, str]:
    """Returns (final_url, title, text)."""
    for _ in range(4):  # follow redirects manually so every hop is checked
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise PageUnavailable("Only http and https websites can be read.")
        await _assert_public(u.hostname)
        async with (
            httpx.AsyncClient(timeout=20, follow_redirects=False, headers=UA) as c,
            c.stream("GET", url) as r,
        ):
            if r.is_redirect:
                url = str(r.url.join(r.headers.get("location", "")))
                continue
            if r.status_code != 200:
                raise PageUnavailable(f"The website answered {r.status_code}.")
            if "html" not in r.headers.get("content-type", "html"):
                raise PageUnavailable("That address is not a web page.")
            chunks, size = [], 0
            async for b in r.aiter_bytes():
                size += len(b)
                chunks.append(b)
                if size > MAX_BYTES:
                    break
            html = b"".join(chunks).decode(r.encoding or "utf-8", errors="replace")
            title, text = html_to_text(html)
            return url, title, text[:max_chars]
    raise PageUnavailable("Too many redirects.")
