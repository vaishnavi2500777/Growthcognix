"""Foundation: tenants, users, industries, business profiles, audit, RLS.

Revision ID: 0001
"""
import uuid

from alembic import op

from app.industry_taxonomy import TAXONOMY, slugify

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = "gc_app"  # runtime role; must NOT own tables and must not have BYPASSRLS
TENANT_TABLES = ["business_profiles", "business_offerings", "audit_logs"]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE organizations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(120) NOT NULL UNIQUE,
            country_code CHAR(2) NOT NULL DEFAULT 'IN',
            timezone VARCHAR(100) NOT NULL DEFAULT 'Asia/Kolkata',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(320) NOT NULL UNIQUE,
            full_name VARCHAR(200) NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TABLE organization_members (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR(30) NOT NULL DEFAULT 'owner'
                CHECK (role IN ('owner','admin','approver','member','viewer')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (organization_id, user_id)
        );
        CREATE INDEX idx_members_user ON organization_members(user_id);

        CREATE TABLE industries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            parent_id UUID REFERENCES industries(id),
            slug VARCHAR(200) NOT NULL UNIQUE,
            name VARCHAR(200) NOT NULL,
            sort_order INT NOT NULL DEFAULT 0
        );
        CREATE INDEX idx_industries_parent ON industries(parent_id);

        CREATE TABLE business_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL UNIQUE REFERENCES organizations(id) ON DELETE CASCADE,
            industry_id UUID NOT NULL REFERENCES industries(id),
            company_name VARCHAR(255) NOT NULL,
            website VARCHAR(500),
            business_model VARCHAR(20) NOT NULL CHECK (business_model IN ('b2b','b2c','both')),
            description TEXT NOT NULL,
            target_customers TEXT NOT NULL,
            locations JSONB NOT NULL DEFAULT '[]',
            languages JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TABLE business_offerings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            kind VARCHAR(20) NOT NULL CHECK (kind IN ('product','service')),
            name VARCHAR(255) NOT NULL,
            description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_offerings_org ON business_offerings(organization_id);

        CREATE TABLE audit_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            actor_type VARCHAR(30) NOT NULL,
            actor_id UUID,
            action VARCHAR(150) NOT NULL,
            resource_type VARCHAR(100),
            resource_id UUID,
            details JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_audit_org_date ON audit_logs(organization_id, created_at DESC);
        """
    )

    # --- Row-Level Security -------------------------------------------------
    # The API sets app.org_id / app.user_id per transaction after verifying the JWT
    # and membership. Empty setting => no tenant => no rows.
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY; ALTER TABLE {t} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""CREATE POLICY tenant_isolation ON {t}
                USING (organization_id::text = current_setting('app.org_id', true))
                WITH CHECK (organization_id::text = current_setting('app.org_id', true));"""
        )
    op.execute(
        """
        ALTER TABLE organization_members ENABLE ROW LEVEL SECURITY;
        ALTER TABLE organization_members FORCE ROW LEVEL SECURITY;
        CREATE POLICY member_visibility ON organization_members
            USING (organization_id::text = current_setting('app.org_id', true)
                   OR user_id::text = current_setting('app.user_id', true))
            WITH CHECK (organization_id::text = current_setting('app.org_id', true));
        ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
        ALTER TABLE organizations FORCE ROW LEVEL SECURITY;
        CREATE POLICY org_visibility ON organizations
            USING (id::text = current_setting('app.org_id', true)
                   OR id IN (SELECT organization_id FROM organization_members
                             WHERE user_id::text = current_setting('app.user_id', true)))
            WITH CHECK (id::text = current_setting('app.org_id', true));
        """
    )

    # --- Runtime role grants (only when the role exists) ---------------------
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            GRANT USAGE ON SCHEMA public TO {APP_ROLE};
            GRANT SELECT ON industries TO {APP_ROLE};
            GRANT SELECT, INSERT, UPDATE ON users, organizations, organization_members,
                  business_profiles TO {APP_ROLE};
            GRANT SELECT, INSERT, UPDATE, DELETE ON business_offerings TO {APP_ROLE};
            -- audit trail is append-only for the application
            GRANT SELECT, INSERT ON audit_logs TO {APP_ROLE};
          END IF;
        END $$;
        """
    )

    # --- Seed industry taxonomy ---------------------------------------------
    rows = []
    for gi, (group, subs) in enumerate(TAXONOMY):
        gid, gslug = uuid.uuid4(), slugify(group)
        rows.append((gid, None, gslug, group, gi))
        for si, sub in enumerate(subs):
            rows.append((uuid.uuid4(), gid, f"{gslug}/{slugify(sub)}", sub, si))
    values = ",".join(
        "('{}',{},'{}','{}',{})".format(
            i, f"'{p}'" if p else "NULL", s, n.replace("'", "''"), o
        )
        for i, p, s, n, o in rows
    )
    op.execute(f"INSERT INTO industries (id,parent_id,slug,name,sort_order) VALUES {values}")


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS audit_logs, business_offerings, business_profiles, industries,"
        " organization_members, users, organizations CASCADE"
    )
