"""HTML/doc -> clean markdown + metadata, links, images, contacts."""
import io
import re
from urllib.parse import urljoin, urlparse, urldefrag

import phonenumbers
from bs4 import BeautifulSoup, Comment
from markdownify import MarkdownConverter

# Same idea as Firecrawl's excludeNonMainTags list (apps/api/src/scraper/scrapeURL/lib/removeUnwantedElements.ts)
NON_MAIN = ["header", "footer", "nav", "aside", ".header", ".top", ".navbar", "#header", ".footer", ".bottom",
            "#footer", ".sidebar", ".side", ".aside", "#sidebar", ".modal", ".popup", "#modal", ".overlay", ".ad",
            ".ads", ".advert", "#ad", ".lang-selector", ".language", "#language-selector", ".social",
            ".social-media", ".social-links", "#social", ".menu", ".navigation", "#nav", ".breadcrumbs",
            "#breadcrumbs", ".share", "#share", ".widget", "#widget", ".cookie", "#cookie", "[role=navigation]",
            "[role=banner]", "[role=contentinfo]", "[aria-modal=true]"]
FORCE_KEEP = ["#main", "main", "article", "[role=main]"]

SOCIAL = {"facebook": r"facebook\.com|fb\.com", "instagram": r"instagram\.com", "linkedin": r"linkedin\.com",
          "twitter": r"twitter\.com|//x\.com|\.x\.com", "youtube": r"youtube\.com|youtu\.be",
          "whatsapp": r"wa\.me|whatsapp\.com|api\.whatsapp", "pinterest": r"pinterest\.", "threads": r"threads\.net"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,200}\.[A-Za-z]{2,12}")
BAD_EMAIL_END = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js", ".avif")
BAD_EMAIL_PART = ("example.com", "sentry", "wixpress", "domain.com", "email.com", "yourdomain", "@2x", "u003e")


class _MD(MarkdownConverter):
    def convert_img(self, el, text, convert_as_inline=False, **kw):
        alt = el.attrs.get("alt", "") or ""
        src = el.attrs.get("src", "") or ""
        if not src or src.startswith("data:"):
            return ""
        return f"![{alt}]({src})"


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def absolutize(soup: BeautifulSoup, base: str):
    b = soup.find("base", href=True)
    if b:
        base = urljoin(base, b["href"])
    for t in soup.find_all(["a", "link"], href=True):
        t["href"] = urljoin(base, t["href"].strip())
    for t in soup.find_all(["img", "source", "script", "iframe"], src=True):
        t["src"] = urljoin(base, t["src"].strip())
    for t in soup.find_all("img"):
        if not t.get("src") and t.get("data-src"):
            t["src"] = urljoin(base, t["data-src"])
    return base


def metadata(soup: BeautifulSoup, url: str, status: int, ct: str) -> dict:
    m = {"sourceURL": url, "statusCode": status, "contentType": ct}
    if soup.title and soup.title.string:
        m["title"] = soup.title.string.strip()
    for t in soup.find_all("meta"):
        k = t.get("name") or t.get("property") or t.get("itemprop")
        v = t.get("content")
        if k and v and len(m) < 80:
            k = k.strip()
            if k in ("description", "keywords", "robots", "viewport", "author", "generator") or k.startswith(("og:", "twitter:", "article:")):
                m[k] = v.strip()[:1000]
    html = soup.find("html")
    if html and html.get("lang"):
        m["language"] = html["lang"]
    c = soup.find("link", rel=lambda r: r and "canonical" in r)
    if c and c.get("href"):
        m["canonical"] = c["href"]
    fav = soup.find("link", rel=lambda r: r and "icon" in [x.lower() for x in r])
    if fav and fav.get("href"):
        m["favicon"] = fav["href"]
    return m


def clean(soup: BeautifulSoup, only_main=True, include_tags=None, exclude_tags=None) -> BeautifulSoup:
    for t in soup(["script", "style", "noscript", "template", "svg", "canvas", "iframe", "head", "meta", "link"]):
        t.decompose()
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    if include_tags:
        new = soup_of("<div></div>")
        root = new.div
        for sel in include_tags:
            for el in soup.select(sel):
                root.append(el)
        soup = new
    if exclude_tags:
        for sel in exclude_tags:
            for el in soup.select(sel):
                el.decompose()
    if only_main and not include_tags:
        for sel in NON_MAIN:
            try:
                els = soup.select(sel)
            except Exception:
                continue
            for el in els:
                if getattr(el, "decomposed", False):
                    continue
                if any(el.select_one(k) for k in FORCE_KEEP):
                    continue
                el.decompose()
    return soup


def to_markdown(soup_or_html) -> str:
    html = str(soup_or_html)
    md = _MD(heading_style="ATX", bullets="-", strip=["form", "button", "input", "select"]).convert(html)
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def norm_url(u: str, ignore_query=False) -> str:
    u = urldefrag(u)[0]
    p = urlparse(u)
    path = p.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    q = "" if ignore_query else (("?" + p.query) if p.query else "")
    return f"{p.scheme}://{p.netloc.lower()}{path}{q}"


def links(soup: BeautifulSoup) -> list[str]:
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        h = urldefrag(a["href"])[0]
        if h.startswith(("http://", "https://")) and h not in seen:
            seen.add(h)
            out.append(h)
    return out


def images(soup: BeautifulSoup) -> list[str]:
    out = []
    for i in soup.find_all(["img", "source"]):
        s = i.get("src") or ""
        if s.startswith("http") and s not in out:
            out.append(s)
    return out


def contacts(soup: BeautifulSoup, text: str | None = None) -> dict:
    text = text if text is not None else soup.get_text(" ", strip=True)
    emails, phones, socials = [], [], {}
    for a in soup.find_all("a", href=True):
        h = a["href"]
        hl = h.lower()
        if hl.startswith("mailto:"):
            e = h[7:].split("?")[0].strip()
            if EMAIL_RE.fullmatch(e):
                emails.append(e.lower())
        elif hl.startswith("tel:"):
            phones.append(h[4:].strip())
        else:
            for k, rx in SOCIAL.items():
                if re.search(rx, hl) and not re.search(r"/sharer|/share\?|intent/tweet|/plugins/", hl):
                    socials.setdefault(k, h.split("?")[0] if k != "whatsapp" else h)
    deob = re.sub(r"\s*[\[(]\s*at\s*[\])]\s*", "@", text, flags=re.I)
    deob = re.sub(r"\s*[\[(]\s*dot\s*[\])]\s*", ".", deob, flags=re.I)
    for e in EMAIL_RE.findall(deob):
        e = e.lower().strip(".")
        emails.append(e)
    emails = [e for e in dict.fromkeys(emails)
              if not e.endswith(BAD_EMAIL_END) and not any(b in e for b in BAD_EMAIL_PART)]
    nums = []
    for raw in phones + [text[:200000]]:
        try:
            for m in phonenumbers.PhoneNumberMatcher(raw, "IN", leniency=phonenumbers.Leniency.VALID):
                nums.append(phonenumbers.format_number(m.number, phonenumbers.PhoneNumberFormat.E164))
        except Exception:
            pass
    return {"emails": emails[:30], "phones": list(dict.fromkeys(nums))[:20], "socials": socials}


def site_signals(soup: BeautifulSoup, raw_html: str, final_url: str) -> dict:
    """Simple, explainable website-quality signals (useful for agencies selling web/social services)."""
    years = [int(y) for y in re.findall(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?((?:19|20)\d{2})", raw_html, re.I)]
    gen = soup.find("meta", attrs={"name": "generator"})
    return {
        "https": final_url.startswith("https://"),
        "mobile_meta": bool(soup.find("meta", attrs={"name": "viewport"})),
        "copyright_year": max(years) if years else None,
        "has_meta_description": bool(soup.find("meta", attrs={"name": "description"})),
        "generator": gen.get("content") if gen else None,
        "html_kb": round(len(raw_html) / 1024),
        "has_analytics": bool(re.search(r"googletagmanager|gtag\(|google-analytics|fbq\(", raw_html)),
        "has_whatsapp_link": bool(re.search(r"wa\.me|api\.whatsapp", raw_html)),
    }


# ---------- documents ----------

def pdf_to_markdown(data: bytes) -> tuple[str, dict]:
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(data))
    parts = []
    for i, p in enumerate(r.pages):
        t = (p.extract_text() or "").strip()
        if t:
            parts.append(f"<!-- page {i + 1} -->\n{t}")
    meta = {"numPages": len(r.pages)}
    if r.metadata and r.metadata.title:
        meta["title"] = str(r.metadata.title)
    return "\n\n".join(parts), meta


def docx_to_markdown(data: bytes) -> tuple[str, dict]:
    import docx
    d = docx.Document(io.BytesIO(data))
    out = []
    for p in d.paragraphs:
        t = p.text.strip()
        if not t:
            continue
        st = (p.style.name or "").lower()
        if st.startswith("heading"):
            n = re.findall(r"\d", st)
            out.append("#" * int(n[0] if n else 1) + " " + t)
        elif "list" in st:
            out.append("- " + t)
        else:
            out.append(t)
    for tb in d.tables:
        rows = [[c.text.strip().replace("|", "\\|") for c in r.cells] for r in tb.rows]
        out.append(_md_table(rows))
    return "\n\n".join(out), {"title": d.core_properties.title or None}


def xlsx_to_markdown(data: bytes) -> tuple[str, dict]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        rows = []
        for r in ws.iter_rows(values_only=True):
            if len(rows) > 2000:
                break
            if any(v is not None for v in r):
                rows.append(["" if v is None else str(v).replace("|", "\\|") for v in r])
        if rows:
            out.append(f"## {ws.title}\n\n" + _md_table(rows))
    return "\n\n".join(out), {"sheets": wb.sheetnames}


def _md_table(rows):
    if not rows:
        return ""
    w = max(len(r) for r in rows)
    rows = [r + [""] * (w - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * w]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def doc_kind(ct: str, url: str, head: bytes) -> str | None:
    u = urlparse(url).path.lower()
    if "html" in ct and not head.startswith(b"%PDF"):
        return None
    if "pdf" in ct or u.endswith(".pdf") or head.startswith(b"%PDF"):
        return "pdf"
    if "wordprocessingml" in ct or u.endswith(".docx"):
        return "docx"
    if "spreadsheetml" in ct or u.endswith(".xlsx"):
        return "xlsx"
    return None


def doc_to_markdown(kind, data):
    return {"pdf": pdf_to_markdown, "docx": docx_to_markdown, "xlsx": xlsx_to_markdown}[kind](data)
