import uuid


async def signup(client, org="Acme Steel Works"):
    email = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post("/api/v1/auth/register", json={
        "full_name": "Test Owner", "email": email, "password": "correct-horse-battery",
        "organization_name": org})
    assert r.status_code == 201, r.text
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


async def a_subcategory(client, slug="manufacturing/steel-and-metals"):
    groups = (await client.get("/api/v1/industries")).json()
    for g in groups:
        for s in g["subcategories"]:
            if s["slug"] == slug:
                return g, s
    raise AssertionError(slug)


def profile_body(industry_id, name="Acme Steel Works"):
    return {
        "company_name": name, "website": "https://example.com",
        "industry_id": industry_id, "business_model": "b2b",
        "description": "We manufacture TMT bars and structural steel for builders.",
        "target_customers": "Construction companies and contractors in Karnataka",
        "locations": ["Bengaluru", " ", "Hubballi"], "languages": ["English", "Kannada"],
        "offerings": [{"kind": "product", "name": "TMT bars"},
                      {"kind": "service", "name": "Cut and bend", "description": "On-site"}],
    }
