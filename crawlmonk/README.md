# CrawlMonk

City-wise B2B lead finder for India + Firecrawl-style scraping API (scrape, crawl, map, search, batch, extract, agent, parse, monitors, interact, MCP).

- Single FastAPI service (`app/`) serving the API, Postgres-backed job queue workers and the static UI (`static/`).
- Deployed as a Docker web service on Render (Playwright base image for headless Chromium). Postgres on Neon.
- Env: `DATABASE_URL`, `JWT_SECRET`, `PUBLIC_URL`, optional `GEMINI_API_KEY`, `GEMINI_MODEL`, `BROWSER_ENABLED`, `DAILY_CREDITS`.
- Local: `pip install -r requirements.txt && uvicorn app.main:app` ; live smoke test: `python tests/live_smoke.py <base_url>`.

See PARITY.md for the Firecrawl feature matrix and limits.
