# Architecture (decisions so far)

- **Supervised AI.** Agents read and draft freely; publishing, sending, spending and deleting always need a human approval verified server-side. An agent can never approve its own action.
- **Agent engine first.** One reusable runtime (LangGraph behind our own contracts) and many agents configured by industry knowledge packs. PostgreSQL is the source of truth; LangGraph only holds execution state.
- **Modular monolith.** FastAPI app split by domain (auth, organisations, industries, business, agents, approvals...). Workers added when agents run.
- **Tenant isolation in the database.** Every tenant table has `organization_id` and an RLS policy reading `app.org_id`, set per transaction only after the JWT and membership are verified. The API connects as `gc_app`, which owns nothing and cannot bypass RLS. Migrations run as the owner.
- **Audit trail.** `audit_logs` is insert/select only for the application role.
- **Real data only.** The UI never shows sample numbers; empty states explain what will appear.
- **Free first.** Local Docker, then free tiers (e.g. Neon/Supabase Postgres, Render/Fly for the API, Vercel for web). Paid infrastructure (AWS ap-south-1) later.

## Planned schema additions
agent registry and versions, executions and steps (with organization_id), approvals (payload hash + idempotency key), knowledge packs and chunks (with organization_id for filtered vector search), usage and cost.
