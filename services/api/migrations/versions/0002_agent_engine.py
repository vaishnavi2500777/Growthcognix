"""Agent engine: registry, runs, steps, approvals.

Revision ID: 0002
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APP_ROLE = "gc_app"
TENANT_TABLES = ["agent_runs", "agent_run_steps", "approvals"]


def upgrade() -> None:
    op.execute(
        """
        -- Global catalogue of agents (not tenant data)
        CREATE TABLE agents (
            slug VARCHAR(80) PRIMARY KEY,
            code VARCHAR(10) NOT NULL UNIQUE,          -- A001...
            name VARCHAR(120) NOT NULL,
            level SMALLINT NOT NULL CHECK (level BETWEEN 0 AND 4),
            department VARCHAR(60) NOT NULL,
            description TEXT NOT NULL,
            risk VARCHAR(10) NOT NULL CHECK (risk IN ('read','draft','external')),
            version VARCHAR(20) NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE
        );
        INSERT INTO agents VALUES
          ('market-research','A001','Market Research Agent',3,'research',
           'Studies your business, market and competitors from real sources and writes up opportunities.',
           'read','0.1.0',TRUE);

        CREATE TABLE agent_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id),
            agent_slug VARCHAR(80) NOT NULL REFERENCES agents(slug),
            agent_version VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
            input JSONB NOT NULL DEFAULT '{}',
            output JSONB,
            error JSONB,
            model VARCHAR(80),
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        );
        CREATE INDEX idx_runs_org_date ON agent_runs(organization_id, created_at DESC);

        CREATE TABLE agent_run_steps (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id),
            run_id UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
            seq SMALLINT NOT NULL,
            name VARCHAR(80) NOT NULL,
            kind VARCHAR(20) NOT NULL CHECK (kind IN ('data','tool','model','approval')),
            status VARCHAR(20) NOT NULL DEFAULT 'running'
                CHECK (status IN ('running','succeeded','failed','skipped')),
            summary TEXT,
            detail JSONB NOT NULL DEFAULT '{}',
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ,
            UNIQUE (run_id, seq)
        );

        -- Every external action waits here. Agents can request; only people decide.
        CREATE TABLE approvals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id),
            run_id UUID REFERENCES agent_runs(id),
            action_type VARCHAR(80) NOT NULL,
            title VARCHAR(255) NOT NULL,
            payload JSONB NOT NULL,
            payload_hash CHAR(64) NOT NULL,
            idempotency_key VARCHAR(120) NOT NULL,
            risk VARCHAR(10) NOT NULL DEFAULT 'external',
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','approved','rejected','expired','executed')),
            requested_by_agent VARCHAR(80) REFERENCES agents(slug),
            decided_by UUID REFERENCES users(id),
            decided_at TIMESTAMPTZ,
            decision_note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (organization_id, idempotency_key)
        );
        CREATE INDEX idx_approvals_org_status ON approvals(organization_id, status, created_at DESC);
        """
    )
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY; ALTER TABLE {t} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""CREATE POLICY tenant_isolation ON {t}
                USING (organization_id::text = current_setting('app.org_id', true))
                WITH CHECK (organization_id::text = current_setting('app.org_id', true));"""
        )
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            GRANT SELECT ON agents TO {APP_ROLE};
            GRANT SELECT, INSERT, UPDATE ON agent_runs, agent_run_steps, approvals TO {APP_ROLE};
          ELSE
            RAISE WARNING 'role {APP_ROLE} missing: runtime grants skipped';
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE approvals, agent_run_steps, agent_runs, agents")
