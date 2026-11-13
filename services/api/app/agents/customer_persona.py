"""A006 Customer Persona Agent (L3, read-only).

Sources it may use, all real: the business profile the owner wrote (source P), the business's own
website (W1), the findings of this organisation's latest finished Market Research run (R), and,
when search is connected, web search results about how these customers buy (S1..). Every persona
must cite its sources; personas without one are dropped, and so are lines carrying figures
(percentages, money, ages) or quotations that no source contains.
"""
import asyncio
import re
from urllib.parse import urlparse

from sqlalchemy import select

from app.agents import market_research
from app.agents.market_research import _load_profile, _profile_text
from app.agents.runtime import RunContext, StepSkipped
from app.ai.gateway import ModelUnavailable, get_model
from app.ai.search import get_search
from app.ai.web import PageUnavailable, read_page
from app.db import SessionLocal, set_tenant
from app.models import AgentRun

SLUG, VERSION = "customer-persona", "0.1.0"

SYSTEM = """You are the Customer Persona Agent of GrowthCognix, working for one real business.
Rules:
- Use ONLY the numbered sources provided. Never invent statistics, percentages, ages, incomes,
  company sizes, names of real people or quotes. A persona is a role, not a fictional person:
  label it by what they do (e.g. "Plant procurement head", "Independent site contractor").
- Every persona must list the ids of the sources that support it in "basis" (e.g. ["P","R"]).
  R is the owner's earlier market research; cite it when you use its findings.
- Goals, pains, buying triggers, objections and channels must be stated in or directly implied
  by the cited sources. Languages must come from the profile or another cited source.
- "message" is one or two plain sentences this business could say to that persona, built only on
  what the business actually offers according to P or W1.
- If the sources are thin, return fewer personas. Put what you could not establish in
  "open_questions".
- Write plainly for a busy owner in India. No hype, no emoji. British/Indian English spelling."""

STRS = {"type": "array", "items": {"type": "string"}}
LIST_FIELDS = ("goals", "pains", "buying_triggers", "objections", "channels", "languages")
SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "personas": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "role": {"type": "string"}, "segment": {"type": "string"},
            **{f: STRS for f in LIST_FIELDS},
            "message": {"type": "string"}, "basis": STRS},
            "required": ["name", "role", "segment", *LIST_FIELDS, "message", "basis"]}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "personas", "open_questions"],
}

# Figures a persona must not carry unless a source states them: percentages, money, ages, counts
# of years, and quoted speech.
FIGURE = re.compile(
    r"\d[\d,.]*\s*%|(?:₹|rs\.?|inr)\s*\d[\d,.]*|\d[\d,.]*\s*(?:lakh|lakhs|crore|crores|k\b)"
    r"|\b(?:aged?|age)\s+\d+|\d+\s*(?:-|to|–)\s*\d+\s*(?:years|yrs)|\d+\s*(?:years|yrs)\s+old",
    re.IGNORECASE)
QUOTE = re.compile(r"[\"“”]([^\"“”]{12,})[\"“”]")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower().replace(",", "")


def _unsupported(text: str, corpus: str) -> bool:
    for m in FIGURE.finditer(text):
        if _norm(m.group(0)) not in corpus:
            return True
    return any(_norm(q) not in corpus for q in QUOTE.findall(text))


def _clean(report: dict, sources: list[dict]) -> tuple[dict, int]:
    valid = {s["id"] for s in sources}
    texts = {s["id"]: _norm(s.get("text") or "") for s in sources}
    dropped = 0
    personas = []
    for p in report.get("personas", []):
        p["basis"] = [b for b in p.get("basis", []) if b in valid]
        if not p["basis"]:
            dropped += 1
            continue
        corpus = " ".join(texts[b] for b in p["basis"])
        if any(_unsupported(p.get(k) or "", corpus) for k in ("name", "role", "segment")):
            dropped += 1
            continue
        for f in LIST_FIELDS:
            keep = [x for x in p.get(f, []) if x.strip() and not _unsupported(x, corpus)]
            dropped += len([x for x in p.get(f, []) if x.strip()]) - len(keep)
            p[f] = keep
        if _unsupported(p.get("message") or "", corpus):
            dropped += 1
            p["message"] = ""
        personas.append(p)
    report["personas"] = personas
    report["open_questions"] = [q for q in report.get("open_questions", []) if q.strip()]
    return report, dropped


def _research_text(out: dict) -> str:
    """The latest market research findings, as plain text (its own source ids removed)."""
    def g(d: dict, k: str) -> str:
        return d.get(k) or ""

    lines = [f"Summary: {g(out, 'summary')}"]
    for key, label in (("strengths", "Strength"), ("gaps", "Gap")):
        lines += [f"{label}: {g(i, 'point')}" for i in out.get(key) or []]
    lines += [f"Audience: {g(a, 'segment')}. Needs: {g(a, 'needs')}. "
              f"Reach them: {g(a, 'where_to_reach')}" for a in out.get("audiences") or []]
    lines += [f"Competitor: {g(c, 'name')} ({g(c, 'url')}): {g(c, 'notes')}"
              for c in out.get("competitors") or []]
    lines += [f"Opportunity: {g(o, 'title')}. {g(o, 'why')} First step: {g(o, 'first_step')} "
              f"(channel: {g(o, 'channel')})" for o in out.get("opportunities") or []]
    return "\n".join(lines)


async def _latest_research(ctx: RunContext) -> tuple | None:
    """(run id, finished date, output) of this organisation's latest finished research run."""
    async with SessionLocal() as s, s.begin():
        await set_tenant(s, ctx.org_id, ctx.user_id)
        row = (await s.execute(
            select(AgentRun.id, AgentRun.finished_at, AgentRun.output)
            .where(AgentRun.organization_id == ctx.org_id,
                   AgentRun.agent_slug == market_research.SLUG,
                   AgentRun.status == "succeeded", AgentRun.output.is_not(None))
            .order_by(AgentRun.finished_at.desc().nulls_last()).limit(1))).first()
    return tuple(row) if row else None


def _queries(p: dict) -> list[str]:
    main = p["offerings"][0].split(": ", 1)[1].split(" (")[0] if p["offerings"] else p["industry"]
    place = ", ".join(p["locations"][:2]) or "India"
    return [f"how {p['target_customers'][:80]} choose {main} suppliers",
            f"{main} buyers {place} purchase decision challenges"]


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

    async def research():
        found = await _latest_research(ctx)
        if found is None:
            raise StepSkipped("No finished Market Research run yet. Running it first gives "
                              "these personas more to work from.")
        run_id, finished, output = found
        when = finished.strftime("%d %b %Y") if finished else "an earlier date"
        return ([{"id": "R", "kind": "research", "title": f"Your market research of {when}",
                  "url": f"/runs/{run_id}", "text": _research_text(output)}],
                f"Used the market research finished on {when}", {"run_id": str(run_id)})
    sources += await ctx.step("Read your market research", "data", research) or []

    async def web_search():
        if search is None:
            raise StepSkipped("Web search is not connected, so personas use only your own "
                              "material.")
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
               for i, h in enumerate(hits[:10], 1)]
        return out, f"Found {len(out)} sources across {len(qs)} searches", {"queries": qs}
    sources += await ctx.step("Search the web", "tool", web_search) or []

    if not any(s["id"] == "R" for s in sources):
        limitations.append("No market research run yet: personas rest on your profile"
                           + (" and website" if any(s["id"] == "W1" for s in sources) else "")
                           + (" and search results." if search else "."))
    if search is None:
        limitations.append("Web search not connected: nothing from outside your own material "
                           "was used.")

    async def draft():
        if model is None:
            raise ModelUnavailable("No AI provider is connected.")
        ctx.model = model.name
        blocks = [f"[{s['id']}] {s['title']}" + (f" <{s['url']}>" if s["kind"] in
                                                  ("website", "search") else "")
                  + f"\n{s['text']}" for s in sources]
        prompt = ("Describe the customers this business sells to, using only these sources.\n\n"
                  + "\n\n".join(blocks))
        r = await model.generate_json(SYSTEM, prompt, SCHEMA)
        return r.data, f"Drafted from {len(sources)} sources with {r.model}", {
            "_tokens": (r.input_tokens, r.output_tokens)}
    raw = await ctx.step("Draft personas", "model", draft)

    async def verify():
        report, dropped = _clean(raw, sources)
        return report, (f"Removed {dropped} unsupported detail{'s' if dropped != 1 else ''}"
                        if dropped else "Every persona is tied to a source"), {"dropped": dropped}
    report = await ctx.step("Check every claim has a source", "data", verify)

    report["sources"] = [{k: s[k] for k in ("id", "kind", "title", "url")} for s in sources]
    report["limitations"] = limitations
    return report
