"""A005 Competitor Analysis and A006 Customer Persona. The model, search and web reader are test
doubles (mocks live only in tests); the runtime, database and RLS are real."""
import copy

import pytest

from app.agents import competitor_analysis, customer_persona, market_research
from app.ai.gateway import ModelResult
from app.ai.search import SearchHit
from app.ai.web import PageUnavailable
from app.routers import agents as agents_router
from tests.helpers import a_subcategory, profile_body, signup


class FakeModel:
    name = "test-model"

    def __init__(self, data):
        self.data, self.prompts = data, []

    async def generate_json(self, system, prompt, schema):
        self.prompts.append(prompt)
        return ModelResult(self.data, self.name, 900, 250)


HITS = [
    SearchHit("Acme Steel Works", "https://example.com/", "Our own site"),  # the business itself
    SearchHit("Rival Steels TMT", "https://rivalsteels.example/tmt", "TMT bars in Hubballi"),
    SearchHit("Second Rival", "https://www.secondrival.example/about", "Structural steel, Bengaluru"),
    SearchHit("TMT bar sellers", "https://www.indiamart.com/tmt-bars", "Listing of TMT bar sellers"),
    SearchHit("Dead Site", "https://deadsite.example/", "Steel trader"),
]


class FakeSearch:
    name = "test-search"

    async def search(self, query, max_results=5):
        return HITS


PAGES = {
    "example.com": ("Acme Steel Works", "We manufacture TMT bars. " * 20),
    "rivalsteels.example": ("Rival Steels", "Rival Steels makes Fe 550D TMT bars. "
                            "Dealer price Rs 52,000 per tonne. Delivery in 48 hours. " * 5),
    "secondrival.example": ("Second Rival", "Structural steel sections for builders. " * 10),
}


async def fake_page(url):
    host = competitor_analysis.domain(url)
    if host not in PAGES:
        raise PageUnavailable("The website answered 503.")
    title, text = PAGES[host]
    return url, title, text


@pytest.fixture
def providers(monkeypatch):
    def use(model=None, search=None):
        for mod in (market_research, competitor_analysis, customer_persona, agents_router):
            monkeypatch.setattr(mod, "get_model", lambda: model)
            monkeypatch.setattr(mod, "get_search", lambda: search)
        for mod in (market_research, competitor_analysis, customer_persona):
            monkeypatch.setattr(mod, "read_page", fake_page)
    return use


async def onboarded(client, org="Acme Steel Works"):
    _, h = await signup(client, org)
    _, s = await a_subcategory(client)
    r = await client.put("/api/v1/business-profile", headers=h, json=profile_body(s["id"], org))
    assert r.status_code == 200
    return h


async def run_agent(client, h, slug):
    r = await client.post(f"/api/v1/agents/{slug}/runs", headers=h)
    assert r.status_code == 202, r.text
    return (await client.get(f"/api/v1/runs/{r.json()['id']}", headers=h)).json()


COMPETITORS = {
    "summary": "Two regional mills compete on delivery speed.",
    "competitors": [
        {"name": "Rival Steels", "url": "https://www.rivalsteels.example/products",
         "what_they_sell": "Fe 550D TMT bars", "positioning": "Fast delivery",
         "pricing_signals": "Rs 52,000 per tonne to dealers", "strengths": ["48-hour delivery"],
         "weaknesses": [], "basis": ["C1", "S1"]},
        {"name": "Second Rival", "url": "https://secondrival.example/",
         "what_they_sell": "Structural steel", "positioning": "Builders",
         "pricing_signals": "Rs 49,999 per tonne", "strengths": [], "weaknesses": [],
         "basis": ["S2"]},
        {"name": "Ghost Traders", "url": "https://ghost.example/", "what_they_sell": "Steel",
         "positioning": "x", "pricing_signals": "", "strengths": [], "weaknesses": [],
         "basis": ["S1"]},
        {"name": "Listing seller", "url": "https://www.indiamart.com/tmt-bars",
         "what_they_sell": "TMT", "positioning": "x", "pricing_signals": "", "strengths": [],
         "weaknesses": [], "basis": ["S3"]},
        {"name": "Unsourced Ltd", "url": "https://rivalsteels.example/", "what_they_sell": "x",
         "positioning": "x", "pricing_signals": "", "strengths": [], "weaknesses": [],
         "basis": ["X1"]},
    ],
    "comparison": [
        {"dimension": "Delivery", "this_business": "Cut and bend on site",
         "competitors": "Rival Steels promises 48 hours", "basis": ["P", "C1"]},
        {"dimension": "Reputation", "this_business": "Trusted", "competitors": "Unknown",
         "basis": ["P"]},
    ],
    "differentiation": [
        {"title": "Lead with cut and bend", "why": "Rivals sell bars only",
         "first_step": "Put it on the homepage", "basis": ["W1", "C2"]},
        {"title": "Invented", "why": "x", "first_step": "x", "basis": ["Z9"]},
    ],
    "open_questions": ["What is your dealer price?"],
}


def test_competitor_clean_checks_basis_domain_and_prices():
    sources = [
        {"id": "P", "kind": "profile", "url": None, "text": "We sell TMT bars"},
        {"id": "S1", "kind": "search", "url": "https://rivalsteels.example/tmt", "text": "TMT"},
        {"id": "S2", "kind": "search", "url": "https://www.secondrival.example/about", "text": "x"},
        {"id": "S3", "kind": "search", "url": "https://www.indiamart.com/tmt-bars", "text": "x"},
        {"id": "W1", "kind": "website", "url": "https://example.com/", "text": "Cut and bend"},
        {"id": "C1", "kind": "competitor_site", "url": "https://rivalsteels.example/",
         "text": "Dealer price Rs 52,000 per tonne"},
        {"id": "C2", "kind": "competitor_site", "url": "https://secondrival.example/", "text": "x"},
    ]
    report, dropped = competitor_analysis._clean(copy.deepcopy(COMPETITORS), sources)
    assert [c["name"] for c in report["competitors"]] == ["Rival Steels", "Second Rival"]
    assert report["competitors"][0]["pricing_signals"] == "Rs 52,000 per tonne to dealers"
    assert report["competitors"][1]["pricing_signals"] == ""  # figure not in any cited source
    assert [c["dimension"] for c in report["comparison"]] == ["Delivery"]  # P alone is not enough
    assert [d["title"] for d in report["differentiation"]] == ["Lead with cut and bend"]
    # ghost domain, listing site, unsourced, unpriced price, P-only comparison, invented idea
    assert dropped == 6


async def test_agents_list_includes_new_agents(client, providers):
    providers(FakeModel({}), None)
    h = await onboarded(client)
    agents = {a["slug"]: a for a in (await client.get("/api/v1/agents", headers=h)).json()}
    assert agents["competitor-analysis"]["code"] == "A005"
    assert agents["customer-persona"]["code"] == "A006"
    assert agents["customer-persona"]["department"] == "strategy"
    assert all(agents[s]["can_run"] and agents[s]["risk"] == "read"
               for s in ("competitor-analysis", "customer-persona"))


async def test_competitor_run_reads_sites_and_drops_unsupported(client, providers):
    model = FakeModel(COMPETITORS)
    providers(model, FakeSearch())
    h = await onboarded(client)
    run = await run_agent(client, h, "competitor-analysis")
    assert run["status"] == "succeeded", run
    assert [s["name"] for s in run["steps"]] == [
        "Read business profile", "Read your website", "Search for competitors",
        "Read competitor websites", "Analyse competitors", "Check every claim has a source"]
    assert all(s["status"] == "succeeded" for s in run["steps"])
    sites = run["steps"][3]["summary"]
    assert "Read 2 of 3" in sites and "deadsite.example" in sites  # failed read is skipped
    out = run["output"]
    ids = {s["id"]: s["url"] for s in out["sources"]}
    assert set(ids) == {"P", "W1", "S1", "S2", "S3", "S4", "C1", "C2"}
    assert "example.com/" not in [u for k, u in ids.items() if k.startswith("S")]  # own site out
    assert "indiamart" not in ids["C1"] + ids["C2"]  # listings are not read as competitor sites
    assert [c["name"] for c in out["competitors"]] == ["Rival Steels", "Second Rival"]
    assert out["limitations"] == []
    assert "Rs 52,000 per tonne" in model.prompts[0]  # the model saw the competitor's own page


async def test_competitor_run_without_search_is_honest(client, providers):
    model = FakeModel(COMPETITORS)
    providers(model, None)
    h = await onboarded(client)
    run = await run_agent(client, h, "competitor-analysis")
    assert run["status"] == "succeeded", run
    steps = {s["name"]: s for s in run["steps"]}
    assert steps["Search for competitors"]["status"] == "skipped"
    assert "not connected" in steps["Search for competitors"]["summary"]
    assert steps["Analyse competitors"]["status"] == "skipped"
    out = run["output"]
    assert out["competitors"] == [] and out["comparison"] == [] and out["differentiation"] == []
    assert out["open_questions"] and out["limitations"]
    assert {s["id"] for s in out["sources"]} == {"P", "W1"}
    assert model.prompts == []  # nothing to compare against, so nothing was asked of the model
    assert run["model"] is None and run["input_tokens"] == 0


MARKET = {
    "summary": "Builders in North Karnataka buy on trust and delivery speed.",
    "strengths": [{"point": "Cut and bend service saves site labour", "basis": ["P"]}],
    "gaps": [], "competitors": [], "opportunities": [],
    "audiences": [{"segment": "Site contractors", "needs": "Bars delivered on the day promised",
                   "where_to_reach": "Dealer counters", "basis": ["P"]}],
    "open_questions": [],
}

PERSONAS = {
    "summary": "Two buyer roles matter most.",
    "personas": [
        {"name": "Independent site contractor", "role": "Runs residential sites",
         "segment": "Contractors in Karnataka",
         "goals": ["Bars delivered on the day promised", "Cut delivery costs by 30%"],
         "pains": ["Labour lost cutting bars on site"],
         "buying_triggers": ["A new site starting"],
         "objections": ['Says "your price is always higher than the dealer down the road"'],
         "channels": ["Dealer counters"], "languages": ["Kannada", "English"],
         "message": "We cut and bend to your drawings so your crew starts fixing on day one.",
         "basis": ["R", "P"]},
        {"name": "Made-up buyer", "role": "x", "segment": "x", "goals": [], "pains": [],
         "buying_triggers": [], "objections": [], "channels": [], "languages": [],
         "message": "x", "basis": ["Q9"]},
    ],
    "open_questions": ["Who signs off purchases at your larger customers?"],
}


async def test_persona_uses_latest_market_research(client, providers):
    h = await onboarded(client)
    providers(FakeModel(MARKET), None)
    mr = await run_agent(client, h, "market-research")
    assert mr["status"] == "succeeded"

    model = FakeModel(PERSONAS)
    providers(model, None)
    run = await run_agent(client, h, "customer-persona")
    assert run["status"] == "succeeded", run
    assert [s["name"] for s in run["steps"]] == [
        "Read business profile", "Read your website", "Read your market research",
        "Search the web", "Draft personas", "Check every claim has a source"]
    steps = {s["name"]: s for s in run["steps"]}
    assert steps["Read your market research"]["status"] == "succeeded"
    assert steps["Search the web"]["status"] == "skipped"
    out = run["output"]
    r = next(s for s in out["sources"] if s["id"] == "R")
    assert r["kind"] == "research" and r["url"] == f"/runs/{mr['id']}"
    assert "[R]" in model.prompts[0] and "Bars delivered on the day promised" in model.prompts[0]
    assert [p["name"] for p in out["personas"]] == ["Independent site contractor"]
    p = out["personas"][0]
    assert p["basis"] == ["R", "P"]
    assert p["goals"] == ["Bars delivered on the day promised"]  # invented 30% removed
    assert p["objections"] == []  # quote not found in any source removed
    assert not any("No market research" in x for x in out["limitations"])


async def test_persona_without_research_drops_r_citations(client, providers):
    model = FakeModel({**PERSONAS, "personas": [
        {**PERSONAS["personas"][0], "basis": ["R"]}]})
    providers(model, None)
    h = await onboarded(client, "Other Steel Co")
    run = await run_agent(client, h, "customer-persona")
    assert run["status"] == "succeeded", run
    steps = {s["name"]: s for s in run["steps"]}
    assert steps["Read your market research"]["status"] == "skipped"
    out = run["output"]
    assert out["personas"] == []  # it cited research that does not exist
    assert "R" not in {s["id"] for s in out["sources"]}
    assert any("No market research" in x for x in out["limitations"])


async def test_persona_ignores_other_orgs_research(client, providers):
    providers(FakeModel(MARKET), None)
    h1 = await onboarded(client, "First Steel")
    await run_agent(client, h1, "market-research")
    providers(FakeModel(PERSONAS), None)
    h2 = await onboarded(client, "Second Steel")
    run = await run_agent(client, h2, "customer-persona")
    assert "R" not in {s["id"] for s in run["output"]["sources"]}
