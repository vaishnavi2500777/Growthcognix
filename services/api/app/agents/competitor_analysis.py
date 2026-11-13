"""A005 Competitor Analysis Agent (L3, read-only).

Sources it may use, all real: the business profile the owner wrote (source P), the business's own
website (W1), web search results for competitors in the business's markets (S1..), and the
websites of up to five competitors that search found (C1..). Every competitor must carry a URL on
the domain of a search or competitor-site source it cites; anything unsupported is dropped before
the report is saved. Without search there is nothing outside the owner's own material to compare
against, so the report says so instead of guessing.
"""
import asyncio
import re
from urllib.parse import urlparse

from app.agents.market_research import _load_profile, _profile_text
from app.agents.runtime import RunContext, StepSkipped
from app.ai.gateway import ModelUnavailable, get_model
from app.ai.search import get_search
from app.ai.web import PageUnavailable, read_page

SLUG, VERSION = "competitor-analysis", "0.1.0"
MAX_SITES = 5

SYSTEM = """You are the Competitor Analysis Agent of GrowthCognix, working for one real business.
Rules:
- Use ONLY the numbered sources provided. Never invent companies, numbers, prices, statistics or quotes.
- Every item must list the ids of the sources that support it in "basis" (e.g. ["S2"], ["C1","P"]).
- A competitor must come from a search (S) or competitor website (C) source, with its URL on the
  same website as given in that source. Listings, directories, marketplaces and news articles are
  not competitors; a business named inside them can be, if the source gives its own website.
- "pricing_signals": only prices, discounts, minimum orders or payment terms written in a cited
  source. If none are stated, return an empty string. Never estimate.
- Strengths and weaknesses of a competitor must come from its cited sources, not general knowledge.
- A comparison or differentiation point must cite at least one S or C source, plus P or W1 for
  what this business does. Do not add reputation, size or history the owner did not write.
- If the sources are thin, return fewer items. Put what you could not establish in "open_questions".
- Write plainly for a busy owner in India. No hype, no emoji. British/Indian English spelling."""

BASIS = {"type": "array", "items": {"type": "string"}}
STRS = {"type": "array", "items": {"type": "string"}}
SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "competitors": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "url": {"type": "string"},
            "what_they_sell": {"type": "string"}, "positioning": {"type": "string"},
            "pricing_signals": {"type": "string"}, "strengths": STRS, "weaknesses": STRS,
            "basis": BASIS},
            "required": ["name", "url", "what_they_sell", "positioning", "pricing_signals",
                         "strengths", "weaknesses", "basis"]}},
        "comparison": {"type": "array", "items": {"type": "object", "properties": {
            "dimension": {"type": "string"}, "this_business": {"type": "string"},
            "competitors": {"type": "string"}, "basis": BASIS},
            "required": ["dimension", "this_business", "competitors", "basis"]}},
        "differentiation": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "why": {"type": "string"},
            "first_step": {"type": "string"}, "basis": BASIS},
            "required": ["title", "why", "first_step", "basis"]}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "competitors", "comparison", "differentiation", "open_questions"],
}

# Pages that list or discuss businesses rather than being one. Search may still cite them (S..),
# but they are not read as competitor websites.
NOT_COMPETITOR_SITES = (
    "wikipedia.org", "indiamart.com", "justdial.com", "tradeindia.com", "exportersindia.com",
    "linkedin.com", "facebook.com", "instagram.com", "youtube.com", "x.com", "twitter.com",
    "amazon.in", "amazon.com", "flipkart.com", "quora.com", "reddit.com", "glassdoor.co.in",
    "glassdoor.com", "ambitionbox.com", "zaubacorp.com", "tofler.in", "crunchbase.com",
    "medium.com", "google.com", "maps.google.com", "economictimes.indiatimes.com",
)

NO_COMPETITOR_QUESTIONS = [
    ("Which businesses do your customers most often compare you with? Their names or websites "
     "would let this agent study them directly."),
    "When you lose an order, who usually wins it, and why do customers say they chose them?",
]


def domain(url: str | None) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    return host.removeprefix("www.")


def _is_listing(host: str) -> bool:
    return any(host == d or host.endswith("." + d) for d in NOT_COMPETITOR_SITES)


def _queries(p: dict) -> list[str]:
    main = p["offerings"][0].split(": ", 1)[1].split(" (")[0] if p["offerings"] else p["industry"]
    sub = p["industry"].split(" > ")[1]
    places = p["locations"][:2] or ["India"]
    qs = [f"{main} companies {place}" for place in places]
    qs.append(f"{sub} brands {places[0]}")
    return qs


NUM = re.compile(r"\d[\d,.]*")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower().replace(",", "")


def _clean(report: dict, sources: list[dict]) -> tuple[dict, int]:
    valid = {s["id"] for s in sources}
    external = {s["id"] for s in sources if s["kind"] in ("search", "competitor_site")}
    urls = {s["id"]: s["url"] for s in sources}
    texts = {s["id"]: _norm(s.get("text") or "") for s in sources}
    dropped = 0

    def ok(item, need_external=False):
        nonlocal dropped
        item["basis"] = [b for b in item.get("basis", []) if b in valid]
        if not item["basis"] or (need_external and not set(item["basis"]) & external):
            dropped += 1
            return False
        return True

    comps = []
    for c in report.get("competitors", []):
        if not ok(c):
            continue
        cited = {domain(urls[b]) for b in c["basis"] if b in external}
        host = domain(c.get("url"))
        if not host or host not in cited or _is_listing(host):
            dropped += 1
            continue
        # A price signal survives only if every figure in it appears in a cited source.
        sig = (c.get("pricing_signals") or "").strip()
        corpus = " ".join(texts[b] for b in c["basis"])
        figures = [n.replace(",", "").rstrip(".") for n in NUM.findall(sig)]
        if any(f not in corpus for f in figures):
            dropped += 1
            sig = ""
        c["pricing_signals"] = sig
        c["strengths"] = [x for x in c.get("strengths", []) if x.strip()]
        c["weaknesses"] = [x for x in c.get("weaknesses", []) if x.strip()]
        comps.append(c)
    report["competitors"] = comps
    report["comparison"] = [i for i in report.get("comparison", []) if ok(i, need_external=True)]
    report["differentiation"] = [i for i in report.get("differentiation", [])
                                 if ok(i, need_external=True)]
    report["open_questions"] = [q for q in report.get("open_questions", []) if q.strip()]
    return report, dropped


async def run(ctx: RunContext, inp: dict) -> dict:
    model, search = get_model(), get_search()
    sources: list[dict] = []
    limitations: list[str] = []

    async def load():
        p = await _load_profile(ctx)
        return p, f"Read the profile of {p['company_name']}", {"industry": p["industry"]}
    profile = await ctx.step("Read business profile", "data", load)
    sources.append({"id": "P", "kind": "profile", "title": "Business profile (written by you)",
                    "url": None, "text": _profile_text(profile)})
    own = domain(profile["website"])

    async def website():
        if not profile["website"]:
            raise StepSkipped("No website on your profile.")
        try:
            url, title, text = await read_page(profile["website"])
        except PageUnavailable as e:
            raise StepSkipped(f"Could not read your website: {e}") from e
        if len(text) < 200:
            raise StepSkipped("Your website returned too little text to read.")
        return ([{"id": "W1", "kind": "website", "title": title or url, "url": url, "text": text}],
                f"Read {len(text):,} characters from {urlparse(url).netloc}", {"url": url})
    sources += await ctx.step("Read your website", "tool", website) or []

    async def find():
        if search is None:
            raise StepSkipped("Web search is not connected yet, so competitors could not be "
                              "looked up.")
        qs = _queries(profile)
        results = await asyncio.gather(*(search.search(q, 6) for q in qs), return_exceptions=True)
        hits, seen = [], set()
        for res in results:
            if isinstance(res, Exception):
                continue
            for h in res:
                if h.url not in seen and domain(h.url) != own:
                    seen.add(h.url)
                    hits.append(h)
        if not hits:
            raise StepSkipped("Search returned no pages about other businesses.")
        out = [{"id": f"S{i}", "kind": "search", "title": h.title, "url": h.url, "text": h.content}
               for i, h in enumerate(hits[:15], 1)]
        return out, f"Found {len(out)} sources across {len(qs)} searches", {"queries": qs}
    found = await ctx.step("Search for competitors", "tool", find) or []
    sources += found

    async def read_sites():
        if not found:
            raise StepSkipped("No search results to follow.")
        targets, hosts = [], set()
        for s in found:
            host = domain(s["url"])
            if host and host != own and host not in hosts and not _is_listing(host):
                hosts.add(host)
                u = urlparse(s["url"])
                targets.append(f"{u.scheme}://{u.netloc}/")
            if len(targets) == MAX_SITES:
                break
        if not targets:
            raise StepSkipped("Search found only directories and listings, no company websites.")
        pages = await asyncio.gather(*(read_page(t) for t in targets), return_exceptions=True)
        out, skipped = [], []
        for t, pg in zip(targets, pages, strict=True):
            if isinstance(pg, Exception) or len(pg[2]) < 200:
                skipped.append(domain(t))
                continue
            url, title, text = pg
            out.append({"id": f"C{len(out) + 1}", "kind": "competitor_site", "title": title or url,
                        "url": url, "text": text})
        if not out:
            raise StepSkipped(f"Could not read any of {len(targets)} competitor websites.")
        msg = f"Read {len(out)} of {len(targets)} competitor websites"
        if skipped:
            msg += f"; skipped {', '.join(skipped)}"
        return out, msg, {"read": [domain(s["url"]) for s in out], "skipped": skipped}
    sources += await ctx.step("Read competitor websites", "tool", read_sites) or []

    has_external = any(s["kind"] in ("search", "competitor_site") for s in sources)
    if search is None:
        limitations.append("Web search not connected: no competitors could be looked up, so this "
                           "report has no competitor list or comparison.")
    elif not has_external:
        limitations.append("Search found nothing usable about other businesses in your markets, "
                           "so this report has no competitor list or comparison.")

    async def analyse():
        if not has_external:
            raise StepSkipped("Nothing outside your own profile and website to compare against.")
        if model is None:
            raise ModelUnavailable("No AI provider is connected.")
        ctx.model = model.name
        blocks = [f"[P] Business profile written by the owner\n{_profile_text(profile)}"] + [
            f"[{s['id']}] {s['title']} <{s['url']}>\n{s['text']}" for s in sources if s["id"] != "P"]
        prompt = ("Analyse this business's competitors using only these sources. S sources are "
                  "search results; C sources are competitor websites.\n\n" + "\n\n".join(blocks))
        r = await model.generate_json(SYSTEM, prompt, SCHEMA)
        return r.data, f"Analysed {len(sources)} sources with {r.model}", {
            "_tokens": (r.input_tokens, r.output_tokens)}
    raw = await ctx.step("Analyse competitors", "model", analyse)
    if raw is None:
        raw = {"summary": ("No competitors are listed because this run had no sources outside "
                           "your own profile and website. Nothing has been guessed."),
               "competitors": [], "comparison": [], "differentiation": [],
               "open_questions": list(NO_COMPETITOR_QUESTIONS)}

    async def verify():
        report, dropped = _clean(raw, sources)
        return report, (f"Removed {dropped} unsupported finding{'s' if dropped != 1 else ''}"
                        if dropped else "Every finding is tied to a source"), {"dropped": dropped}
    report = await ctx.step("Check every claim has a source", "data", verify)

    report["sources"] = [{k: s[k] for k in ("id", "kind", "title", "url")} for s in sources]
    report["limitations"] = limitations
    return report
