"""Agent engine tests. The model and search providers are test doubles (mocks live only in tests);
the runtime, database, RLS and approval rules are real."""
import uuid

import pytest

from app.agents import market_research
from app.ai.gateway import ModelResult, ModelUnavailable
from app.ai.search import SearchHit
from app.ai.web import PageUnavailable, read_page
from app.routers import agents as agents_router
from tests.helpers import a_subcategory, profile_body, signup


class FakeModel:
    name = "test-model"

    def __init__(self, data=None, fail=False):
        self.data, self.fail, self.prompts = data, fail, []

    async def generate_json(self, system, prompt, schema):
        self.prompts.append(prompt)
        if self.fail:
            raise ModelUnavailable("quota exceeded")
        return ModelResult(self.data, self.name, 1200, 340)


class FakeSearch:
    name = "test-search"

    async def search(self, query, max_results=5):
        return [SearchHit("Rival Steels", "https://rivalsteels.example/tmt", "TMT bars in Hubballi")]


REPORT = {
    "summary": "Builders in North Karnataka buy on trust and delivery speed.",
    "strengths": [{"point": "Cut and bend service saves site labour", "basis": ["P"]},
                  {"point": "Invented: 40% market share", "basis": ["X9"]}],
    "gaps": [{"point": "No pricing on website", "basis": ["W1"]}],
    "audiences": [{"segment": "Contractors", "needs": "Reliable delivery",
                   "where_to_reach": "Dealer counters", "basis": ["P"]}],
    "competitors": [{"name": "Rival Steels", "url": "https://rivalsteels.example/about",
                     "notes": "Same region", "basis": ["S1"]},
                    {"name": "Made Up Ltd", "url": "https://madeup.example", "notes": "x",
                     "basis": ["S1"]}],
    "opportunities": [{"title": "Publish a delivery promise", "why": "Speed matters",
                       "first_step": "Add it to the homepage", "channel": "Website",
                       "basis": ["W1", "P"]}],
    "open_questions": ["What is your monthly capacity?"],
}


async def fake_page(url):
    return url, "Acme Steel Works", "We manufacture TMT bars. " * 20


@pytest.fixture
def providers(monkeypatch):
    def use(model=None, search=None):
        for mod in (market_research, agents_router):
            monkeypatch.setattr(mod, "get_model", lambda: model)
            monkeypatch.setattr(mod, "get_search", lambda: search)
        monkeypatch.setattr(market_research, "read_page", fake_page)
    return use


async def onboarded(client, org="Acme Steel Works"):
    _, h = await signup(client, org)
    _, s = await a_subcategory(client)
    r = await client.put("/api/v1/business-profile", headers=h, json=profile_body(s["id"], org))
    assert r.status_code == 200
    return h


async def test_agents_list_reports_missing_ai(client, providers):
    providers(None, None)
    h = await onboarded(client)
    agents = (await client.get("/api/v1/agents", headers=h)).json()
    mr = next(a for a in agents if a["slug"] == "market-research")
    assert mr["code"] == "A001" and mr["can_run"] is False
    assert mr["blocked_reason"] == "Needs an AI provider connection."
    r = await client.post("/api/v1/agents/market-research/runs", headers=h)
    assert r.status_code == 412 and r.json()["error"]["code"] == "AI_NOT_CONNECTED"


async def test_run_requires_profile(client, providers):
    providers(FakeModel(REPORT), None)
    _, h = await signup(client)
    r = await client.post("/api/v1/agents/market-research/runs", headers=h)
    assert r.json()["error"]["code"] == "PROFILE_REQUIRED"


async def test_full_run_records_steps_and_drops_unsourced_claims(client, providers):
    model = FakeModel(REPORT)
    providers(model, FakeSearch())
    h = await onboarded(client)
    r = await client.post("/api/v1/agents/market-research/runs", headers=h)
    assert r.status_code == 202
    run = (await client.get(f"/api/v1/runs/{r.json()['id']}", headers=h)).json()
    assert run["status"] == "succeeded", run
    assert [s["name"] for s in run["steps"]] == [
        "Read business profile", "Read your website", "Search the web", "Analyse market",
        "Check every claim has a source"]
    assert all(s["status"] == "succeeded" for s in run["steps"])
    out = run["output"]
    assert [i["point"] for i in out["strengths"]] == ["Cut and bend service saves site labour"]
    assert [c["name"] for c in out["competitors"]] == ["Rival Steels"]  # same domain as its source
    assert {s["id"] for s in out["sources"]} == {"P", "W1", "S1"}
    assert out["limitations"] == []
    assert run["model"] == "test-model" and run["input_tokens"] == 1200
    assert "rivalsteels.example" in model.prompts[0]  # the model saw the real sources


async def test_run_without_search_is_honest(client, providers):
    providers(FakeModel({**REPORT, "competitors": []}), None)
    h = await onboarded(client)
    rid = (await client.post("/api/v1/agents/market-research/runs", headers=h)).json()["id"]
    run = (await client.get(f"/api/v1/runs/{rid}", headers=h)).json()
    step = run["steps"][2]
    assert step["status"] == "skipped" and "not connected" in step["summary"]
    assert run["output"]["limitations"]


async def test_model_failure_is_recorded(client, providers):
    providers(FakeModel(fail=True), None)
    h = await onboarded(client)
    rid = (await client.post("/api/v1/agents/market-research/runs", headers=h)).json()["id"]
    run = (await client.get(f"/api/v1/runs/{rid}", headers=h)).json()
    assert run["status"] == "failed" and "quota" in run["error"]["message"]
    assert run["steps"][-1]["status"] == "failed"


async def test_runs_are_tenant_isolated(client, providers):
    providers(FakeModel(REPORT), None)
    h1 = await onboarded(client, "First Co")
    h2 = await onboarded(client, "Second Co")
    rid = (await client.post("/api/v1/agents/market-research/runs", headers=h1)).json()["id"]
    assert (await client.get(f"/api/v1/runs/{rid}", headers=h2)).status_code == 404
    assert (await client.get("/api/v1/runs", headers=h2)).json() == []


async def test_approvals_flow(client, app_db):
    from app.agents.approvals import request_approval
    from app.db import SessionLocal, set_tenant

    _, h = await signup(client)
    me = (await client.get("/api/v1/me", headers=h)).json()
    org = uuid.UUID(me["organization"]["id"])
    async with SessionLocal() as s, s.begin():
        await set_tenant(s, org, None)
        a = await request_approval(s, org, agent_slug="market-research", run_id=None,
                                   action_type="social.publish", title="Post to LinkedIn",
                                   payload={"text": "Hello"}, idempotency_key="k1")
        again = await request_approval(s, org, agent_slug="market-research", run_id=None,
                                       action_type="social.publish", title="Post to LinkedIn",
                                       payload={"text": "Hello"}, idempotency_key="k1")
        b = await request_approval(s, org, agent_slug="market-research", run_id=None,
                                   action_type="social.publish", title="Second",
                                   payload={"text": "Original"}, idempotency_key="k2")
        assert again.id == a.id
    pending = (await client.get("/api/v1/approvals?status=pending", headers=h)).json()
    assert len(pending) == 2
    r = await client.post(f"/api/v1/approvals/{a.id}/decision", headers=h,
                          json={"decision": "approved", "note": "Fine"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert r.json()["decided_by"] == me["id"]
    r = await client.post(f"/api/v1/approvals/{a.id}/decision", headers=h,
                          json={"decision": "rejected"})
    assert r.json()["error"]["code"] == "ALREADY_DECIDED"
    # tamper with the payload after the request was made
    app_db.execute("SELECT set_config('app.org_id', %s, false)", (str(org),))
    app_db.execute("UPDATE approvals SET payload = '{\"text\": \"Changed\"}' WHERE id = %s", (b.id,))
    app_db.commit()
    r = await client.post(f"/api/v1/approvals/{b.id}/decision", headers=h,
                          json={"decision": "approved"})
    assert r.json()["error"]["code"] == "PAYLOAD_CHANGED"


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/", "http://localhost/", "file:///etc/passwd",
                                 "http://169.254.169.254/latest/meta-data"])
async def test_website_reader_refuses_internal_addresses(url):
    with pytest.raises(PageUnavailable):
        await read_page(url)
