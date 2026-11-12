from tests.helpers import a_subcategory, profile_body, signup


async def test_health(client):
    r = await client.get("/api/v1/health")
    assert r.json() == {"status": "ok", "database": "ok"}


async def test_industries_taxonomy(client):
    groups = (await client.get("/api/v1/industries")).json()
    assert len(groups) == 25
    assert all(g["subcategories"] for g in groups)


async def test_register_login_me(client):
    email, h = await signup(client)
    me = (await client.get("/api/v1/me", headers=h)).json()
    assert me["email"] == email and me["role"] == "owner" and me["onboarded"] is False
    r = await client.post("/api/v1/auth/login", json={"email": email.upper(),
                                                      "password": "correct-horse-battery"})
    assert r.status_code == 200


async def test_duplicate_email_and_bad_password(client):
    email, _ = await signup(client)
    r = await client.post("/api/v1/auth/register", json={
        "full_name": "X Y", "email": email, "password": "another-long-pass",
        "organization_name": "Other"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_TAKEN"
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pass"})
    assert r.status_code == 401
    r = await client.post("/api/v1/auth/login", json={"email": "nobody@example.com",
                                                      "password": "wrong-pass"})
    assert r.status_code == 401


async def test_weak_password_rejected(client):
    r = await client.post("/api/v1/auth/register", json={
        "full_name": "A B", "email": "weak@example.com", "password": "short",
        "organization_name": "Org"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_auth_required_and_tampered_token(client):
    assert (await client.get("/api/v1/me")).status_code == 401
    _, h = await signup(client)
    bad = {"Authorization": h["Authorization"][:-3] + "abc"}
    assert (await client.get("/api/v1/me", headers=bad)).status_code == 401


async def test_business_profile_roundtrip(client):
    _, h = await signup(client)
    assert (await client.get("/api/v1/business-profile", headers=h)).status_code == 404
    _, s = await a_subcategory(client)
    r = await client.put("/api/v1/business-profile", headers=h, json=profile_body(s["id"]))
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["industry"]["name"] == "Steel and metals"
    assert p["parent_industry"]["name"] == "Manufacturing"
    assert p["locations"] == ["Bengaluru", "Hubballi"]
    assert len(p["offerings"]) == 2
    assert (await client.get("/api/v1/me", headers=h)).json()["onboarded"] is True
    body = profile_body(s["id"]); body["offerings"] = [{"kind": "product", "name": "Steel plates"}]
    p2 = (await client.put("/api/v1/business-profile", headers=h, json=body)).json()
    assert [o["name"] for o in p2["offerings"]] == ["Steel plates"]


async def test_profile_requires_subcategory(client):
    _, h = await signup(client)
    g, _ = await a_subcategory(client)
    r = await client.put("/api/v1/business-profile", headers=h, json=profile_body(g["id"]))
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_INDUSTRY"
