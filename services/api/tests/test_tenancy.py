"""Tenant isolation is enforced by PostgreSQL RLS, not only by API filters."""
import psycopg
import pytest

from tests.helpers import a_subcategory, profile_body, signup


def _ctx(conn, org_id="", user_id=""):
    conn.execute("SELECT set_config('app.org_id', %s, true), set_config('app.user_id', %s, true)",
                 (org_id, user_id))


async def _org_id(client, h):
    return (await client.get("/api/v1/me", headers=h)).json()["organization"]["id"]


async def test_api_never_returns_other_tenant_profile(client):
    _, ha = await signup(client, "Tenant A")
    _, hb = await signup(client, "Tenant B")
    _, s = await a_subcategory(client)
    await client.put("/api/v1/business-profile", headers=ha, json=profile_body(s["id"], "Tenant A"))
    r = await client.get("/api/v1/business-profile", headers=hb)
    assert r.status_code == 404


async def test_rls_blocks_cross_tenant_reads_and_writes(client, app_db):
    _, ha = await signup(client, "Tenant A")
    _, hb = await signup(client, "Tenant B")
    _, s = await a_subcategory(client)
    await client.put("/api/v1/business-profile", headers=ha, json=profile_body(s["id"], "Tenant A"))
    a, b = await _org_id(client, ha), await _org_id(client, hb)

    with app_db.transaction():
        _ctx(app_db)  # no tenant bound
        assert app_db.execute("SELECT count(*) FROM business_profiles").fetchone()[0] == 0
        assert app_db.execute("SELECT count(*) FROM business_offerings").fetchone()[0] == 0
    with app_db.transaction():
        _ctx(app_db, b)
        n = app_db.execute("SELECT count(*) FROM business_profiles WHERE organization_id=%s",
                           (a,)).fetchone()[0]
        assert n == 0
        assert app_db.execute("SELECT count(*) FROM organizations WHERE id=%s",
                              (a,)).fetchone()[0] == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege), app_db.transaction():
        _ctx(app_db, b)
        app_db.execute("INSERT INTO business_offerings (organization_id, kind, name) "
                       "VALUES (%s, 'product', 'injected')", (a,))


async def test_audit_log_is_append_only(client, app_db):
    _, h = await signup(client)
    org = await _org_id(client, h)
    with app_db.transaction():
        _ctx(app_db, org)
        assert app_db.execute("SELECT count(*) FROM audit_logs").fetchone()[0] >= 1
    for stmt in ("UPDATE audit_logs SET action='x'", "DELETE FROM audit_logs"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), app_db.transaction():
            _ctx(app_db, org)
            app_db.execute(stmt)


async def test_runtime_role_cannot_bypass_rls(app_db):
    row = app_db.execute(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user").fetchone()
    assert row == (False, False)
