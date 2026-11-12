"""A001 Market Research Agent (L3, read-only).

Sources it may use, all real: the business profile the owner wrote (source P), the business's own
website (W1..), and web search results (S1..). The model must tie every finding to source ids;
findings without a valid source are dropped before anything is saved.
"""
import asyncio
from urllib.parse import urlparse

from sqlalchemy import select

from app.agents.runtime import RunContext, StepSkipped
from app.ai.gateway import ModelUnavailable, get_model
from app.ai.search import get_search
from app.ai.web import PageUnavailable, read_page
from app.db import SessionLocal, set_tenant
from app.models import BusinessOffering, BusinessProfile, Industry

SLUG, VERSION = "market-research", "0.1.0"

SYSTEM = """You are the Market Research Agent of GrowthCognix, working for one real business.
Rules:
- Use ONLY the numbered sources provided. Never invent companies, numbers, prices, statistics or quotes.
- Every item must list the ids of the sources that support it in "basis" (e.g. ["P"], ["W1","S3"]).
- A competitor must come from a search or website source, with its URL exactly as given in that source.
- A point based on [P] must be stated or directly implied by the profile text. Do not add reputation,
  size, history or market position the owner did not write.
- If the sources are thin, return fewer items. Put what you could not establish in "open_questions".
- Write plainly for a busy owner in India. No hype, no emoji. British/Indian English spelling."""

ITEM = {"type": "object", "properties": {"point": {"type": "string"},
        "basis": {"type": "array", "items": {"type": "string"}}}, "required": ["point", "basis"]}
SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "strengths": {"type": "array", "items": ITEM},
        "gaps": {"type": "array", "items": ITEM},
        "audiences": {"type": "array", "items": {"type": "object", "properties": {
            "segment": {"type": "string"}, "needs": {"type": "string"},
            "where_to_reach": {"type": "string"},
            "basis": {"type": "array", "items": {"type": "string"}}},
            "required": ["segment", "needs", "where_to_reach", "basis"]}},
        "competitors": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "url": {"type": "string"}, "notes": {"type": "string"},
            "basis": {"type": "array", "items": {"type": "string"}}},
            "required": ["name", "url", "notes", "basis"]}},
        "opportunities": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "why": {"type": "string"},
            "first_step": {"type": "string"}, "channel": {"type": "string"},
            "basis": {"type": "array", "items": {"type": "string"}}},
            "required": ["title", "why", "first_step", "channel", "basis"]}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "strengths", "gaps", "audiences", "competitors", "opportunities",
                 "open_questions"],
}


async def _load_profile(ctx: RunContext) -> dict:
    async with SessionLocal() as s, s.begin():
        await set_tenant(s, ctx.org_id, ctx.user_id)
        p = await s.scalar(select(BusinessProfile).where(BusinessProfile.organization_id == ctx.org_id))
        if p is None:
            raise ValueError("Business profile is missing.")
        ind = await s.get(Industry, p.industry_id)
        parent = await s.get(Industry, ind.parent_id)
        offs = (await s.scalars(select(BusinessOffering)
                                .where(BusinessOffering.organization_id == ctx.org_id))).all()
    return {"company_name": p.company_name, "website": p.website,
            "industry": f"{parent.name} > {ind.name}", "model": p.business_model,
            "description": p.description, "target_customers": p.target_customers,
            "locations": p.locations, "languages": p.languages,
            "offerings": [f"{o.kind}: {o.name}" + (f" ({o.description})" if o.description else "")
                          for o in offs]}


MODEL_WORDS = {"b2b": "businesses", "b2c": "consumers", "both": "both businesses and consumers"}


def _profile_text(p: dict) -> str:
    return "\n".join([
        f"Company: {p['company_name']}", f"Website: {p['website'] or 'none'}",
        f"Industry: {p['industry']}", f"Sells to: {MODEL_WORDS[p['model']]}",
        f"About: {p['description']}", f"Ideal customers: {p['target_customers']}",
        f"Products and services: {'; '.join(p['offerings']) or 'not listed'}",
        f"Markets: {', '.join(p['locations']) or 'not listed'}",
        f"Customer languages: {', '.join(p['languages']) or 'not listed'}",
    ])


def _queries(p: dict) -> list[str]:
    place = ", ".join(p["locations"][:2]) or "India"
    main = p["offerings"][0].split(": ", 1)[1].split(" (")[0] if p["offerings"] else p["industry"]
    return [f"{main} suppliers {place}", f"{p['industry'].split(' > ')[1]} companies {place}",
            f"{main} market demand India 2026"]


def _clean(report: dict, valid: set[str], urls: dict[str, str]) -> tuple[dict, int]:
    dropped = 0

    def ok(item):
        nonlocal dropped
        item["basis"] = [b for b in item.get("basis", []) if b in valid]
        if not item["basis"]:
            dropped += 1
            return False
        return True

    for key in ("strengths", "gaps", "audiences", "opportunities"):
        report[key] = [i for i in report.get(key, []) if ok(i)]
    comps = []
    for c in report.get("competitors", []):
        cited = {urlparse(urls[b]).netloc for b in c.get("basis", []) if b in urls and b != "P"}
        if ok(c) and urlparse(c["url"]).netloc in cited:
            comps.append(c)
        else:
            dropped += 1
    report["competitors"] = comps
    return report, dropped


async def run(ctx: RunContext, inp: dict) -> dict:
    model, search = get_model(), get_search()
    sources: list[dict] = []

    async def load():
        p = await _load_profile(ctx)
        return p, f"Read the profile of {p['company_name']}", {"industry": p["industry"]}
    profile = await ctx.step("Read business profile", "data", load)
    sources.append({"id": "P", "kind": "profile", "title": "Business profile (written by you)",
                    "url": None})

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

    async def web_search():
        if search is None:
            raise StepSkipped("Web search is not connected yet, so competitors and market "
                              "signals are not included.")
        qs = _queries(profile)
        results = await asyncio.gather(*(search.search(q, 5) for q in qs), return_exceptions=True)
        hits, seen = [], set()
        for res in results:
            if isinstance(res, Exception):
                continue
            for h in res:
                if h.url not in seen:
                    seen.add(h.url)
                    hits.append(h)
        if not hits:
            raise StepSkipped("Search returned no results.")
        out = [{"id": f"S{i}", "kind": "search", "title": h.title, "url": h.url, "text": h.content}
               for i, h in enumerate(hits[:15], 1)]
        return out, f"Found {len(out)} sources across {len(qs)} searches", {"queries": qs}
    sources += await ctx.step("Search the web", "tool", web_search) or []

    async def analyse():
        if model is None:
            raise ModelUnavailable("No AI provider is connected.")
        ctx.model = model.name
        blocks = [f"[P] Business profile written by the owner\n{_profile_text(profile)}"] + [
            f"[{s['id']}] {s['title']} <{s['url']}>\n{s['text']}" for s in sources if s["id"] != "P"]
        prompt = ("Research this business's market using only these sources.\n\n"
                  + "\n\n".join(blocks))
        r = await model.generate_json(SYSTEM, prompt, SCHEMA)
        return r.data, f"Analysed {len(sources)} sources with {r.model}", {
            "_tokens": (r.input_tokens, r.output_tokens)}
    raw = await ctx.step("Analyse market", "model", analyse)

    urls = {s["id"]: s["url"] for s in sources}
    async def verify():
        report, dropped = _clean(raw, set(urls), urls)
        return report, (f"Removed {dropped} unsupported finding{'s' if dropped != 1 else ''}"
                        if dropped else "Every finding is tied to a source"), {"dropped": dropped}
    report = await ctx.step("Check every claim has a source", "data", verify)

    report["sources"] = [{k: s[k] for k in ("id", "kind", "title", "url")} for s in sources]
    report["limitations"] = [] if search else [("Web search not connected: no competitor or "
                                               "market data from outside your own profile and website.")]
    return report
