import json
import asyncpg
from . import config

pool: asyncpg.Pool | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id SERIAL PRIMARY KEY, email TEXT UNIQUE NOT NULL,
  pw_hash TEXT NOT NULL, webhook_secret TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS api_keys(id SERIAL PRIMARY KEY, user_id INT REFERENCES users ON DELETE CASCADE,
  key_hash TEXT UNIQUE NOT NULL, prefix TEXT NOT NULL, name TEXT, created_at TIMESTAMPTZ DEFAULT now(),
  revoked BOOLEAN DEFAULT false);
CREATE TABLE IF NOT EXISTS jobs(id UUID PRIMARY KEY, user_id INT REFERENCES users ON DELETE CASCADE,
  kind TEXT NOT NULL, status TEXT NOT NULL, params JSONB NOT NULL, progress JSONB DEFAULT '{}'::jsonb,
  error TEXT, created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),
  started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ);
CREATE INDEX IF NOT EXISTS jobs_user ON jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status, created_at);
CREATE TABLE IF NOT EXISTS job_docs(id BIGSERIAL PRIMARY KEY, job_id UUID REFERENCES jobs ON DELETE CASCADE,
  url TEXT, doc JSONB, created_at TIMESTAMPTZ DEFAULT now());
CREATE INDEX IF NOT EXISTS job_docs_job ON job_docs(job_id, id);
CREATE TABLE IF NOT EXISTS leads(id BIGSERIAL PRIMARY KEY, job_id UUID REFERENCES jobs ON DELETE CASCADE,
  city TEXT, name TEXT, category TEXT, address TEXT, phone TEXT, website TEXT, emails TEXT[],
  phones TEXT[], socials JSONB, signals JSONB, score INT, reason TEXT, ai_reason TEXT, lat DOUBLE PRECISION,
  lon DOUBLE PRECISION, source TEXT, source_ref TEXT, created_at TIMESTAMPTZ DEFAULT now());
CREATE INDEX IF NOT EXISTS leads_job ON leads(job_id, score DESC);
CREATE TABLE IF NOT EXISTS page_cache(key TEXT PRIMARY KEY, url TEXT, status INT, content_type TEXT,
  final_url TEXT, body BYTEA, fetched_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS snapshots(user_id INT, url TEXT, tag TEXT DEFAULT '', markdown TEXT,
  at TIMESTAMPTZ DEFAULT now(), PRIMARY KEY(user_id, url, tag));
CREATE TABLE IF NOT EXISTS files(id UUID PRIMARY KEY, mime TEXT, data BYTEA, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS usage(id BIGSERIAL PRIMARY KEY, user_id INT, endpoint TEXT, credits INT,
  at TIMESTAMPTZ DEFAULT now());
CREATE INDEX IF NOT EXISTS usage_user ON usage(user_id, at);
CREATE TABLE IF NOT EXISTS monitors(id UUID PRIMARY KEY, user_id INT REFERENCES users ON DELETE CASCADE,
  url TEXT, name TEXT, interval_minutes INT, webhook TEXT, params JSONB DEFAULT '{}'::jsonb,
  active BOOLEAN DEFAULT true, next_run TIMESTAMPTZ DEFAULT now(), last_markdown TEXT,
  created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS monitor_checks(id BIGSERIAL PRIMARY KEY, monitor_id UUID REFERENCES monitors ON DELETE CASCADE,
  status TEXT, change_status TEXT, diff TEXT, error TEXT, at TIMESTAMPTZ DEFAULT now());
"""


async def _init(conn):
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def connect():
    global pool
    pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=6, init=_init,
                                     command_timeout=60)
    async with pool.acquire() as c:
        await c.execute(SCHEMA)
        # jobs stuck from a previous process (Render free restarts/sleeps) go back to the queue once
        await c.execute("UPDATE jobs SET status='queued' WHERE status='running' AND kind<>'interact'")
        await c.execute("DELETE FROM page_cache WHERE fetched_at < now() - interval '7 days'")


def P():
    assert pool is not None
    return pool
