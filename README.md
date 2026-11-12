# GrowthCognix

**Marketing that thinks. Growth you approve.**
An AI marketing department for every industry: specialist agents research, plan, create and run marketing, and nothing reaches the outside world without the owner's approval.

Built in Bengaluru · +91 90190 88160

## What works today (release 0.1)
- Sign up, sign in, sign out (Argon2 password hashing, signed JWT kept in an httpOnly cookie on the web server; the browser never sees it).
- Business onboarding: company, industry (25 groups, 134 categories), B2B/B2C, description, ideal customers, products and services, markets, languages.
- Dashboard with real setup progress and business profile. No sample or invented data anywhere.
- Light and dark themes.
- Multi-tenant PostgreSQL with Row-Level Security enforced by the database, an append-only audit log, and tests that prove one business cannot read or write another's data.

## Stack (free tools)
Next.js 16 + TypeScript + Tailwind 4 · FastAPI + SQLAlchemy 2 + Alembic · PostgreSQL 17 + pgvector · Pytest + Playwright · GitHub Actions.

## Run it locally
```bash
docker compose up -d db                     # Postgres + pgvector
cp services/api/.env.example services/api/.env
cp apps/web/.env.example apps/web/.env.local
make setup migrate
make api        # terminal 1 -> http://localhost:8000/api/docs
make web        # terminal 2 -> http://localhost:3000
make test       # backend tests
```

## Repository
```
apps/web            Next.js app (sign-up, onboarding, dashboard)
services/api        FastAPI API, migrations, tests
brand               Logo, icons, colour tokens, brand sheets
infrastructure/db   Database bootstrap (roles)
e2e                 Browser smoke test
docs                Product and architecture notes
```

## Roadmap
1. Brand ✓  2. Landing page ✓  3. App foundation ✓  4. First live agent: Market Research (needs a free AI key)  5. Approvals centre  6. Multi-agent strategy  7. Integrations (Search Console, GA4, Meta, Google Ads, WhatsApp).
