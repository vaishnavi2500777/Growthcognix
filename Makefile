.PHONY: setup db migrate api web test e2e

setup:            ## install dependencies
	cd services/api && python -m pip install -e ".[dev]"
	cd apps/web && npm ci

db:               ## start Postgres + pgvector
	docker compose up -d db

migrate:          ## apply database migrations
	cd services/api && python -m alembic upgrade head

api:              ## run the API on :8000
	cd services/api && python -m uvicorn app.main:app --reload --port 8000

web:              ## run the web app on :3000
	cd apps/web && npm run dev

test:             ## backend tests against real Postgres
	cd services/api && TEST_ADMIN_URL=postgresql://app:app@localhost:5432/postgres python -m pytest -q

e2e:              ## browser smoke test (api + web must be running)
	python e2e/smoke.py
